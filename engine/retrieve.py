"""Synapse 인출 파이프라인.

흐름:
  질문
  → LLM 확장: 노드 후보 키워드 목록
  → DB 매칭: aliases 우선 → name 직접 → substring
  → BFS 루프: 레이어마다 get_triples(+sentence JOIN) → LLM 트리플 필터
  → 카테고리 보완: 시작 노드 소분류 → ADJACENT_SUBCATEGORIES 1-hop → 해당 소분류 노드만
  → 최종 트리플 컨텍스트 + LLM 답변
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Optional

from .db import get_connection, DB_PATH
from .llm import (
    chat, SYSTEM_CHAT, LLMError,
    retrieve_expand, retrieve_filter_sentence,
)


@dataclass
class Triple:
    src: str
    label: Optional[str]
    tgt: str
    edge_id: int
    src_id: int = 0
    tgt_id: int = 0
    sentence_id: Optional[int] = None
    sentence_text: Optional[str] = None

    def __str__(self) -> str:
        if self.label:
            return f"{self.src} —({self.label})→ {self.tgt}"
        return f"{self.src} → {self.tgt}"


@dataclass
class RetrieveResult:
    context_triples: list[Triple] = field(default_factory=list)
    answer: Optional[str] = None
    start_nodes: list[str] = field(default_factory=list)


# ─── DB 헬퍼 ──────────────────────────────────────────────

def _match_start_nodes(conn, keywords: list[str], question: str = "") -> dict[str, int]:
    """키워드 → 노드 ID 매핑 (별칭 스캔 → name 직접 → substring).
    별칭으로 특정된 name은 name/substring 매칭에서 제외 (동명 노드 오매칭 방지).
    반환: {display_key: node_id}
    """
    matched: dict[str, int] = {}
    alias_resolved_names: set[str] = set()

    # 0. 질문 문자열 안에 포함된 별칭 스캔 (공백 포함 별칭 대응)
    if question:
        rows = conn.execute(
            "SELECT a.alias, n.id, n.name FROM aliases a JOIN nodes n ON n.id = a.node_id WHERE n.status = 'active'"
        ).fetchall()
        for r in rows:
            if r["alias"] in question:
                matched[f"{r['name']}#{r['id']}"] = r["id"]
                alias_resolved_names.add(r["name"])

    for kw in keywords:
        # 1. aliases 정확 매칭
        if kw not in alias_resolved_names:
            row = conn.execute(
                """SELECT n.id, n.name FROM aliases a
                   JOIN nodes n ON n.id = a.node_id
                   WHERE a.alias = ? AND n.status = 'active'""",
                (kw,),
            ).fetchone()
            if row:
                matched[f"{row['name']}#{row['id']}"] = row["id"]
                alias_resolved_names.add(row["name"])
                continue

        # 2. name 정확 매칭 (별칭 특정된 name 제외)
        if kw in alias_resolved_names:
            continue
        rows = conn.execute(
            "SELECT id, name FROM nodes WHERE name = ? AND status = 'active'", (kw,)
        ).fetchall()
        if rows:
            for r in rows:
                if r["id"] not in matched.values():
                    matched[f"{r['name']}#{r['id']}"] = r["id"]
            continue

        # 3. name substring 매칭
        rows = conn.execute(
            "SELECT id, name FROM nodes WHERE name LIKE ? AND status = 'active' LIMIT 5",
            (f"%{kw}%",),
        ).fetchall()
        for r in rows:
            if r["name"] not in alias_resolved_names and r["id"] not in matched.values():
                matched[f"{r['name']}#{r['id']}"] = r["id"]

    return matched


def _get_triples(conn, node_ids: set[int]) -> list[Triple]:
    """노드 ID 집합의 모든 연결 트리플 조회 (양방향). sentences 테이블 LEFT JOIN.

    last_used 업데이트는 하지 않음 — 호출자(retrieve)가 BFS 완료 후 배치 처리.
    """
    if not node_ids:
        return []
    placeholders = ",".join("?" * len(node_ids))
    ids = list(node_ids)
    rows = conn.execute(
        f"""
        SELECT e.id AS edge_id,
               n1.id AS src_id, n1.name AS src,
               n2.id AS tgt_id, n2.name AS tgt,
               e.label, e.sentence_id, s.text AS sentence_text
        FROM edges e
        JOIN nodes n1 ON n1.id = e.source_node_id
        JOIN nodes n2 ON n2.id = e.target_node_id
        LEFT JOIN sentences s ON s.id = e.sentence_id
        WHERE (e.source_node_id IN ({placeholders}) OR e.target_node_id IN ({placeholders}))
        """,
        ids + ids,
    ).fetchall()
    return [
        Triple(
            src=r["src"],
            label=r["label"],
            tgt=r["tgt"],
            edge_id=r["edge_id"],
            src_id=r["src_id"],
            tgt_id=r["tgt_id"],
            sentence_id=r["sentence_id"],
            sentence_text=r["sentence_text"],
        )
        for r in rows
    ]


# ─── 카테고리 인접 맵 ─────────────────────────────────────────
# 소분류 레벨 1-hop 인접. 단방향 정의 → _build_adjacent_map으로 양방향 전개.
# 인접에 인접은 허용하지 않음 (1-hop only).
# 전체 설계 근거: docs/DESIGN_CATEGORY.md

def _build_adjacent_map(pairs: list[tuple[str, str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for a, b in pairs:
        result.setdefault(a, []).append(b)
        result.setdefault(b, []).append(a)
    return result

_ADJACENT_PAIRS: list[tuple[str, str]] = [
    # BOD
    ("BOD.disease",    "MND.mental"),
    ("BOD.sleep",      "MND.mental"),
    ("BOD.sleep",      "MND.coping"),
    ("BOD.exercise",   "HOB.sport"),
    ("BOD.nutrition",  "FOD.ingredient"),
    ("BOD.nutrition",  "FOD.product"),
    ("BOD.medical",    "MON.insurance"),
    # MND
    ("MND.emotion",    "REL.romance"),
    ("MND.emotion",    "REL.conflict"),
    ("MND.motivation", "WRK.jobchange"),
    ("MND.motivation", "EDU.online"),
    ("MND.coping",     "HOB.sport"),
    ("MND.coping",     "HOB.outdoor"),
    ("MND.coping",     "REG.practice"),
    # HOB
    ("HOB.sing",       "CUL.music"),
    ("HOB.outdoor",    "TRV.domestic"),
    ("HOB.outdoor",    "NAT.terrain"),
    ("HOB.outdoor",    "NAT.weather"),
    ("HOB.game",       "TEC.sw"),
    ("HOB.game",       "TEC.hw"),
    ("HOB.craft",      "LIV.supply"),
    ("HOB.collect",    "CUL.art"),
    ("HOB.collect",    "MON.spending"),
    ("HOB.social",     "REL.comm"),
    ("HOB.social",     "TRV.place"),
    # CUL
    ("CUL.book",       "EDU.reading"),
    ("CUL.book",       "EDU.academic"),
    ("CUL.media",      "TEC.sw"),
    ("CUL.show",       "TRV.place"),
    # WRK
    ("WRK.workplace",  "PER.colleague"),
    ("WRK.workplace",  "MON.income"),
    ("WRK.workplace",  "LAW.rights"),
    ("WRK.jobchange",  "MON.income"),
    ("WRK.cert",       "EDU.exam"),
    ("WRK.cert",       "EDU.online"),
    ("WRK.business",   "MON.income"),
    ("WRK.business",   "LAW.contract"),
    ("WRK.tool",       "TEC.sw"),
    ("WRK.tool",       "TEC.ai"),
    # MON
    ("MON.income",     "LAW.tax"),
    ("MON.payment",    "LAW.tax"),
    ("MON.loan",       "LIV.housing"),
    ("MON.loan",       "LAW.contract"),
    ("MON.insurance",  "LAW.contract"),
    ("MON.invest",     "SOC.economy"),
    # LAW
    ("LAW.contract",   "LIV.housing"),
    ("LAW.rights",     "TEC.security"),
    ("LAW.statute",    "WRK.workplace"),
    ("LAW.admin",      "LIV.moving"),
    # EDU
    ("EDU.school",     "WRK.cert"),
    ("EDU.online",     "TEC.sw"),
    ("EDU.language",   "TRV.abroad"),
    # TRV
    ("TRV.domestic",   "FOD.restaurant"),
    ("TRV.domestic",   "HOB.outdoor"),
    ("TRV.domestic",   "NAT.weather"),
    ("TRV.abroad",     "FOD.restaurant"),
    ("TRV.abroad",     "SOC.international"),
    ("TRV.place",      "NAT.terrain"),
    # NAT
    ("NAT.animal",     "LIV.supply"),
    ("NAT.ecology",    "SOC.issue"),
    # LIV
    ("LIV.housing",    "MON.loan"),
    ("LIV.housing",    "LAW.contract"),
    ("LIV.appliance",  "TEC.hw"),
    ("LIV.appliance",  "TEC.sw"),
    ("LIV.moving",     "TRV.place"),
    # TEC
    ("TEC.ai",         "SOC.issue"),
    # PER
    ("PER.colleague",  "WRK.workplace"),
    ("PER.org",        "WRK.workplace"),
    ("PER.family",     "REL.romance"),
    ("PER.friend",     "REL.comm"),
    # REL
    ("REL.conflict",   "WRK.workplace"),
    ("REL.online",     "SOC.issue"),
    # SOC
    ("SOC.international", "TRV.abroad"),
    ("SOC.politics",   "LAW.statute"),
    # REG
    ("REG.practice",   "MND.coping"),
]

ADJACENT_SUBCATEGORIES: dict[str, list[str]] = _build_adjacent_map(_ADJACENT_PAIRS)


def _get_category_supplement_nodes(
    conn, start_node_ids: set[int], visited_ids: set[int]
) -> set[int]:
    """시작 노드 소분류의 인접 소분류(1-hop)에 해당하는 미방문 노드 ID 집합 반환.

    대분류 전체 조회 없음. ADJACENT_SUBCATEGORIES에 없는 소분류는 보완 조회 안 함.
    인접의 인접은 탐색하지 않음 (1-hop only).
    """
    if not start_node_ids:
        return set()

    # 시작 노드들의 소분류 수집 (node_categories JOIN)
    ph = ",".join("?" * len(start_node_ids))
    rows = conn.execute(
        f"SELECT nc.category FROM node_categories nc WHERE nc.node_id IN ({ph})",
        list(start_node_ids),
    ).fetchall()

    # 사용자 지정 category(대문자3글자.소분류 패턴이 아닌 것)는 보완 대상에서 제외
    import re as _re
    subcats: set[str] = {
        r["category"] for r in rows
        if r["category"] and _re.match(r"^[A-Z]{3}\.", r["category"])
    }
    if not subcats:
        return set()

    # 인접 소분류 목록 수집 (1-hop, 중복 제거)
    adjacent: set[str] = set()
    for sub in subcats:
        adjacent.update(ADJACENT_SUBCATEGORIES.get(sub, []))
    adjacent -= subcats  # 시작 소분류 자신은 제외

    if not adjacent:
        return set()

    # 인접 소분류별 활성 노드 조회 (미방문, 소분류당 최대 20개)
    result: set[int] = set()
    for sub in adjacent:
        cat_rows = conn.execute(
            "SELECT nc.node_id FROM node_categories nc "
            "JOIN nodes n ON n.id = nc.node_id "
            "WHERE nc.category = ? AND n.status='active' LIMIT 20",
            (sub,),
        ).fetchall()
        for r in cat_rows:
            if r["node_id"] not in visited_ids:
                result.add(r["node_id"])

    return result


# ─── LLM 헬퍼 ─────────────────────────────────────────────

def _llm_expand_keywords(question: str) -> list[str]:
    """질문 → 노드 후보 키워드 목록."""
    return retrieve_expand(question)


def _llm_filter_sentences(question: str, triples: list[Triple]) -> list[Triple]:
    """문장(sentence_text) 단위 LLM 필터. sentence_text 없으면 트리플 문자열로 대체."""
    if not triples:
        return []
    return [
        t for t in triples
        if retrieve_filter_sentence(
            question,
            t.sentence_text if t.sentence_text else str(t),
        )
    ]


def _llm_answer(
    question: str,
    context_triples: list[Triple],
    images: Optional[list[str]] = None,
    history: Optional[list[dict]] = None,
) -> str:
    """최종 컨텍스트로 자연어 답변 생성. sentence_text(원본 문장) 기준으로 모델에 전달."""
    seen: set[str] = set()
    lines: list[str] = []
    for t in context_triples:
        txt = t.sentence_text if t.sentence_text else str(t)
        if txt not in seen:
            seen.add(txt)
            lines.append(f"- {txt}")
    context = "\n".join(lines)
    user_msg = f"알려진 사실:\n{context}\n\n질문: {question}"
    try:
        return chat(
            SYSTEM_CHAT, user_msg,
            temperature=0.3, max_tokens=4096,
            images=images, history=history,
        )
    except LLMError:
        return f"[MLX 서버 미실행] 인출된 문장 {len(lines)}개:\n{context}"


# ─── BFS ─────────────────────────────────────────────────

def retrieve(
    question: str,
    db_path: str = DB_PATH,
    use_llm: bool = True,
    max_layers: int = 5,
    images: Optional[list[str]] = None,
    history: Optional[list[dict]] = None,
) -> RetrieveResult:
    """질문에 대한 BFS 인출 + LLM 답변. RetrieveResult 반환."""
    result = RetrieveResult()

    conn = get_connection(db_path)
    try:
        # 1. LLM 확장 (또는 단순 단어 분리)
        if use_llm:
            keywords = _llm_expand_keywords(question)
        else:
            keywords = question.split()

        # 2. 질문 원문 토큰을 keywords에 추가 → aliases 매칭으로 1인칭 등 자동 처리
        raw_tokens = question.split()
        keywords = list(dict.fromkeys(keywords + raw_tokens))

        start_nodes = _match_start_nodes(conn, keywords, question=question)
        if not start_nodes:
            result.answer = "관련 정보를 찾을 수 없습니다."
            return result

        result.start_nodes = list(start_nodes.keys())

        # 3. BFS
        visited_node_ids: set[int] = set(start_nodes.values())
        visited_edge_ids: set[int] = set()
        visited_sentence_ids: set[int] = set()  # 문장 단위 중복 방지
        all_visited_edge_ids: list[int] = []  # last_used 배치 업데이트용
        context_triples: list[Triple] = []
        current_node_ids = set(start_nodes.values())

        for _ in range(max_layers):
            layer_triples = [
                t for t in _get_triples(conn, current_node_ids)
                if t.edge_id not in visited_edge_ids
                and (t.sentence_id is None or t.sentence_id not in visited_sentence_ids)
            ]
            if not layer_triples:
                break

            # LLM 필터 (sentence_text 기준)
            if use_llm:
                filtered = _llm_filter_sentences(question, layer_triples)
            else:
                filtered = layer_triples

            context_triples.extend(filtered)
            for t in filtered:
                visited_edge_ids.add(t.edge_id)
                all_visited_edge_ids.append(t.edge_id)
                if t.sentence_id is not None:
                    visited_sentence_ids.add(t.sentence_id)

            # 다음 레이어: 통과 트리플의 새 노드 (Triple에서 직접 추출)
            new_ids = (
                {t.src_id for t in filtered} | {t.tgt_id for t in filtered}
            ) - visited_node_ids
            if not new_ids:
                break
            visited_node_ids.update(new_ids)
            current_node_ids = new_ids

        # 4. 카테고리 보완: BFS 미도달 동카테고리 노드 추가 탐색
        if use_llm:
            cat_node_ids = _get_category_supplement_nodes(
                conn, set(start_nodes.values()), visited_node_ids
            )
            if cat_node_ids:
                cat_triples = [
                    t for t in _get_triples(conn, cat_node_ids)
                    if t.edge_id not in visited_edge_ids
                ]
                if cat_triples:
                    filtered_cat = _llm_filter_sentences(question, cat_triples)
                    context_triples.extend(filtered_cat)
                    for t in filtered_cat:
                        visited_edge_ids.add(t.edge_id)
                        all_visited_edge_ids.append(t.edge_id)

        result.context_triples = context_triples

        # last_used 배치 업데이트 (BFS 완료 후 1회)
        if all_visited_edge_ids:
            ph = ",".join("?" * len(all_visited_edge_ids))
            conn.execute(
                f"UPDATE edges SET last_used=datetime('now') WHERE id IN ({ph})",
                all_visited_edge_ids,
            )
            conn.commit()

        # 4. LLM 답변
        if use_llm:
            result.answer = _llm_answer(question, context_triples, images=images, history=history)
        else:
            result.answer = "\n".join(str(t) for t in context_triples) or "관련 정보 없음"

    finally:
        conn.close()

    return result


if __name__ == "__main__":
    questions = ["언제 병원 갔지?", "허리는 어때?"]
    for q in questions:
        print(f"\n질문: {q}")
        r = retrieve(q, use_llm=False)
        print(f"시작 노드: {r.start_nodes}")
        for t in r.context_triples:
            print(f"  {t}  (sentence: {t.sentence_text!r})")
        print(f"답변: {r.answer}")
