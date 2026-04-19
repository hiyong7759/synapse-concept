"""Synapse 인출 파이프라인 (v15).

흐름:
  질문
  → LLM 확장: 노드 후보 키워드 목록
  → DB 매칭: aliases 우선 → name 직접 → substring
  → BFS 루프: 노드 → node_mentions JOIN → sentences → 함께 언급된 노드 → 반복
  → 카테고리 보완: 시작 노드 카테고리 → 인접 카테고리 노드 추가 → 재필터
  → 최종 sentences 컨텍스트 + LLM 답변

v15 변경: edges 테이블 자체 폐기. 연결은 node_mentions(문장 바구니) + node_categories
(카테고리 바구니) + aliases(별칭 바구니) 세 종류의 하이퍼엣지로만 표현. 의미 관계
(cause/avoid/similar) 해석은 외부 지능체 몫이라, sentence 원문만 컨텍스트로 전달.
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Optional

from .db import get_connection, DB_PATH
from .llm import (
    chat, SYSTEM_CHAT, LLMError,
    retrieve_expand, retrieve_filter_sentence,
)


@dataclass
class Mention:
    """노드↔문장 역참조 한 건. BFS의 단위 데이터."""
    node_id: int
    node_name: str
    sentence_id: int
    sentence_text: str

    def __str__(self) -> str:
        return f"{self.node_name} ▸ {self.sentence_text}"


@dataclass
class Triple:
    """같은 sentence에 함께 언급된 두 노드를 트리플처럼 표현 (시각화·API 호환용).
    v15: 모든 Triple은 label=None. 공출현 페어만 의미 있음."""
    src: str
    label: Optional[str]  # v15: 항상 None (edges 테이블 폐기)
    tgt: str
    src_id: int = 0
    tgt_id: int = 0
    sentence_id: Optional[int] = None
    sentence_text: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.src} ↔ {self.tgt}" if self.tgt else self.src


@dataclass
class RetrieveResult:
    context_triples: list[Triple] = field(default_factory=list)
    context_sentences: list[tuple[int, str]] = field(default_factory=list)
    answer: Optional[str] = None
    start_nodes: list[str] = field(default_factory=list)


# ─── DB 헬퍼 ──────────────────────────────────────────────

def _match_start_nodes(conn, keywords: list[str], question: str = "") -> dict[str, int]:
    """키워드 → 노드 ID 매핑 (별칭 → name 정확 → name substring)."""
    matched: dict[str, int] = {}
    alias_resolved_names: set[str] = set()

    if question:
        rows = conn.execute(
            "SELECT a.alias, n.id, n.name FROM aliases a "
            "JOIN nodes n ON n.id = a.node_id WHERE n.status = 'active'"
        ).fetchall()
        for r in rows:
            if r["alias"] in question:
                matched[f"{r['name']}#{r['id']}"] = r["id"]
                alias_resolved_names.add(r["name"])

    for kw in keywords:
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

        rows = conn.execute(
            "SELECT id, name FROM nodes WHERE name LIKE ? AND status = 'active' LIMIT 5",
            (f"%{kw}%",),
        ).fetchall()
        for r in rows:
            if r["name"] not in alias_resolved_names and r["id"] not in matched.values():
                matched[f"{r['name']}#{r['id']}"] = r["id"]

    return matched


def _get_mentions_for_nodes(conn, node_ids: set[int]) -> list[Mention]:
    """노드 ID 집합이 언급된 모든 sentences 조회 (node_mentions JOIN sentences)."""
    if not node_ids:
        return []
    ph = ",".join("?" * len(node_ids))
    rows = conn.execute(
        f"""
        SELECT m.node_id, n.name AS node_name, m.sentence_id, s.text AS sentence_text
        FROM node_mentions m
        JOIN nodes n     ON n.id = m.node_id
        JOIN sentences s ON s.id = m.sentence_id
        WHERE m.node_id IN ({ph}) AND n.status='active'
        """,
        list(node_ids),
    ).fetchall()
    return [
        Mention(
            node_id=r["node_id"],
            node_name=r["node_name"],
            sentence_id=r["sentence_id"],
            sentence_text=r["sentence_text"],
        )
        for r in rows
    ]


def _get_co_mentioned_node_ids(conn, sentence_ids: set[int]) -> dict[int, list[tuple[int, str]]]:
    """sentence_id 집합 → {sentence_id: [(node_id, node_name), ...]} 매핑.
    인출 컨텍스트로 보여줄 '같은 문장의 다른 노드들' 수집용."""
    if not sentence_ids:
        return {}
    ph = ",".join("?" * len(sentence_ids))
    rows = conn.execute(
        f"""
        SELECT m.sentence_id, m.node_id, n.name
        FROM node_mentions m
        JOIN nodes n ON n.id = m.node_id
        WHERE m.sentence_id IN ({ph}) AND n.status='active'
        """,
        list(sentence_ids),
    ).fetchall()
    result: dict[int, list[tuple[int, str]]] = {}
    for r in rows:
        result.setdefault(r["sentence_id"], []).append((r["node_id"], r["name"]))
    return result


# ─── 카테고리 인접 맵 ─────────────────────────────────────────

def _build_adjacent_map(pairs: list[tuple[str, str]]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for a, b in pairs:
        result.setdefault(a, []).append(b)
        result.setdefault(b, []).append(a)
    return result

_ADJACENT_PAIRS: list[tuple[str, str]] = [
    ("BOD.disease",    "MND.mental"),
    ("BOD.sleep",      "MND.mental"),
    ("BOD.sleep",      "MND.coping"),
    ("BOD.exercise",   "HOB.sport"),
    ("BOD.nutrition",  "FOD.ingredient"),
    ("BOD.nutrition",  "FOD.product"),
    ("BOD.medical",    "MON.insurance"),
    ("MND.emotion",    "REL.romance"),
    ("MND.emotion",    "REL.conflict"),
    ("MND.motivation", "WRK.jobchange"),
    ("MND.motivation", "EDU.online"),
    ("MND.coping",     "HOB.sport"),
    ("MND.coping",     "HOB.outdoor"),
    ("MND.coping",     "REG.practice"),
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
    ("CUL.book",       "EDU.reading"),
    ("CUL.book",       "EDU.academic"),
    ("CUL.media",      "TEC.sw"),
    ("CUL.show",       "TRV.place"),
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
    ("MON.income",     "LAW.tax"),
    ("MON.payment",    "LAW.tax"),
    ("MON.loan",       "LIV.housing"),
    ("MON.loan",       "LAW.contract"),
    ("MON.insurance",  "LAW.contract"),
    ("MON.invest",     "SOC.economy"),
    ("LAW.contract",   "LIV.housing"),
    ("LAW.rights",     "TEC.security"),
    ("LAW.statute",    "WRK.workplace"),
    ("LAW.admin",      "LIV.moving"),
    ("EDU.school",     "WRK.cert"),
    ("EDU.online",     "TEC.sw"),
    ("EDU.language",   "TRV.abroad"),
    ("TRV.domestic",   "FOD.restaurant"),
    ("TRV.domestic",   "HOB.outdoor"),
    ("TRV.domestic",   "NAT.weather"),
    ("TRV.abroad",     "FOD.restaurant"),
    ("TRV.abroad",     "SOC.international"),
    ("TRV.place",      "NAT.terrain"),
    ("NAT.animal",     "LIV.supply"),
    ("NAT.ecology",    "SOC.issue"),
    ("LIV.housing",    "MON.loan"),
    ("LIV.housing",    "LAW.contract"),
    ("LIV.appliance",  "TEC.hw"),
    ("LIV.appliance",  "TEC.sw"),
    ("LIV.moving",     "TRV.place"),
    ("TEC.ai",         "SOC.issue"),
    ("PER.colleague",  "WRK.workplace"),
    ("PER.org",        "WRK.workplace"),
    ("PER.family",     "REL.romance"),
    ("PER.friend",     "REL.comm"),
    ("REL.conflict",   "WRK.workplace"),
    ("REL.online",     "SOC.issue"),
    ("SOC.international", "TRV.abroad"),
    ("SOC.politics",   "LAW.statute"),
    ("REG.practice",   "MND.coping"),
]

ADJACENT_SUBCATEGORIES: dict[str, list[str]] = _build_adjacent_map(_ADJACENT_PAIRS)


def _get_category_supplement_nodes(
    conn, start_node_ids: set[int], visited_ids: set[int]
) -> set[int]:
    """시작 노드 소분류의 인접 소분류 노드 ID 집합 (미방문)."""
    if not start_node_ids:
        return set()

    ph = ",".join("?" * len(start_node_ids))
    rows = conn.execute(
        f"SELECT nc.category FROM node_categories nc WHERE nc.node_id IN ({ph})",
        list(start_node_ids),
    ).fetchall()

    subcats: set[str] = {
        r["category"] for r in rows
        if r["category"] and re.match(r"^[A-Z]{3}\.", r["category"])
    }
    if not subcats:
        return set()

    adjacent: set[str] = set()
    for sub in subcats:
        adjacent.update(ADJACENT_SUBCATEGORIES.get(sub, []))
    adjacent -= subcats

    if not adjacent:
        return set()

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
    return retrieve_expand(question)


def _llm_filter_mentions(question: str, mentions: list[Mention]) -> list[Mention]:
    """sentence 단위 LLM 필터. 같은 sentence는 한 번만 판정."""
    if not mentions:
        return []
    decided: dict[int, bool] = {}
    result: list[Mention] = []
    for m in mentions:
        if m.sentence_id not in decided:
            decided[m.sentence_id] = retrieve_filter_sentence(question, m.sentence_text)
        if decided[m.sentence_id]:
            result.append(m)
    return result


def _llm_answer(
    question: str,
    sentences: list[tuple[int, str]],
    images: Optional[list[str]] = None,
    history: Optional[list[dict]] = None,
) -> str:
    """sentence 원문 컨텍스트로 자연어 답변. v15: 의미 관계 해석은 LLM 몫."""
    lines: list[str] = []
    seen: set[str] = set()
    for _, text in sentences:
        if text and text not in seen:
            seen.add(text)
            lines.append(f"- {text}")
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
    """질문에 대한 BFS 인출 + LLM 답변. v15: node_mentions + node_categories 하이퍼엣지 기반."""
    result = RetrieveResult()

    conn = get_connection(db_path)
    try:
        # 1. 키워드 확장
        if use_llm:
            keywords = _llm_expand_keywords(question)
        else:
            keywords = question.split()
        keywords = list(dict.fromkeys(keywords + question.split()))

        start_nodes = _match_start_nodes(conn, keywords, question=question)
        if not start_nodes:
            result.answer = "관련 정보를 찾을 수 없습니다."
            return result

        result.start_nodes = list(start_nodes.keys())

        # 2. BFS — node_mentions JOIN 단일 경로
        visited_node_ids: set[int] = set(start_nodes.values())
        visited_sentence_ids: set[int] = set()
        all_mentions: list[Mention] = []
        current_node_ids = set(start_nodes.values())

        for _ in range(max_layers):
            mentions = [
                m for m in _get_mentions_for_nodes(conn, current_node_ids)
                if m.sentence_id not in visited_sentence_ids
            ]
            if not mentions:
                break

            if use_llm:
                filtered_m = _llm_filter_mentions(question, mentions)
            else:
                filtered_m = mentions

            if not filtered_m:
                break

            all_mentions.extend(filtered_m)
            for m in filtered_m:
                visited_sentence_ids.add(m.sentence_id)

            # 다음 레이어: 같은 sentence 바구니의 다른 노드
            new_ids: set[int] = set()
            co_map = _get_co_mentioned_node_ids(
                conn, {m.sentence_id for m in filtered_m}
            )
            for nodes_in_sentence in co_map.values():
                for nid, _name in nodes_in_sentence:
                    if nid not in visited_node_ids:
                        new_ids.add(nid)

            if not new_ids:
                break
            visited_node_ids.update(new_ids)
            current_node_ids = new_ids

        # 3. 카테고리 바구니 보완 (인접 맵으로 한 홉 확장)
        if use_llm:
            cat_node_ids = _get_category_supplement_nodes(
                conn, set(start_nodes.values()), visited_node_ids
            )
            if cat_node_ids:
                cat_mentions = [
                    m for m in _get_mentions_for_nodes(conn, cat_node_ids)
                    if m.sentence_id not in visited_sentence_ids
                ]
                if cat_mentions:
                    fm = _llm_filter_mentions(question, cat_mentions)
                    all_mentions.extend(fm)
                    for m in fm:
                        visited_sentence_ids.add(m.sentence_id)

        # 4. 결과 정리: sentence 단위 dedup
        seen_sids: set[int] = set()
        context_sentences: list[tuple[int, str]] = []
        for m in all_mentions:
            if m.sentence_id not in seen_sids:
                seen_sids.add(m.sentence_id)
                context_sentences.append((m.sentence_id, m.sentence_text))
        result.context_sentences = context_sentences

        # 5. 하위 호환: context_triples — 같은 sentence 공출현 노드 페어를 Triple로 펼침
        co_map = _get_co_mentioned_node_ids(conn, {sid for sid, _ in context_sentences})
        triples: list[Triple] = []
        for sid, text in context_sentences:
            nodes_in_s = co_map.get(sid, [])
            if not nodes_in_s:
                continue
            if len(nodes_in_s) == 1:
                nid, name = nodes_in_s[0]
                triples.append(Triple(
                    src=name, label=None, tgt="",
                    src_id=nid, tgt_id=0,
                    sentence_id=sid, sentence_text=text,
                ))
            else:
                for i in range(len(nodes_in_s) - 1):
                    s_nid, s_name = nodes_in_s[i]
                    t_nid, t_name = nodes_in_s[i + 1]
                    triples.append(Triple(
                        src=s_name, label=None, tgt=t_name,
                        src_id=s_nid, tgt_id=t_nid,
                        sentence_id=sid, sentence_text=text,
                    ))
        result.context_triples = triples

        # 6. LLM 답변
        if use_llm:
            result.answer = _llm_answer(
                question, context_sentences,
                images=images, history=history,
            )
        else:
            lines = [t for _, t in context_sentences]
            result.answer = "\n".join(lines) or "관련 정보 없음"

    finally:
        conn.close()

    return result


if __name__ == "__main__":
    questions = ["언제 병원 갔지?", "허리는 어때?"]
    for q in questions:
        print(f"\n질문: {q}")
        r = retrieve(q, use_llm=False)
        print(f"시작 노드: {r.start_nodes}")
        for sid, text in r.context_sentences:
            print(f"  [{sid}] {text}")
        print(f"답변: {r.answer}")
