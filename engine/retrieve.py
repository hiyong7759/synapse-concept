"""Synapse 인출 파이프라인 (v20 — PLAN-004 M4).

흐름:
  질문
  → LLM 확장 + Kiwi: 노드 후보 키워드 목록
  → 축 A 시드 (v20 M2): 키워드가 categories.name 과 매칭되면 서브트리 재귀 CTE →
    sentence_categories 로 연결된 문장을 BFS 초기 시드에 주입
  → DB 매칭: aliases 우선 → name 직접 → substring
  → BFS 루프: 노드 → node_sentence_mentions JOIN → sentences → 함께 언급된 노드 → 반복
  → 축 B 보완: 시작 노드 major_category → 인접 소분류 노드 추가 → 재필터
  → 결과 과다 시 원문 LIKE fallback (v20 M4): 임계치 초과 시 원본 질문 토큰으로 좁힘.
    Kiwi 가 쪼갠 외래어 조각(예: React, Native) 을 원문 구절로 통짜 회복.
  → 최종 sentences 컨텍스트 + LLM 답변

v20 변경 (PLAN-004): 카테고리 바구니가 두 축으로 분리됨.
- 축 A = categories(adjacency list) + sentence_categories(문장 주 매핑) — 사용자 heading 계층.
  질문에서 "더나은 개발팀 휴가" 같은 heading 명 매칭 시 서브트리 스캔으로 관련 문장 일괄 수집.
- 축 B = node_categories.major_category — 19 대분류 + 인접 맵 한 홉 (기존 경로 유지).

v15: edges 테이블 폐기. 연결은 node_sentence_mentions + 카테고리 두 축(v20) + aliases 로 표현.
의미 관계(cause/avoid/similar) 해석은 외부 지능체 몫.
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
from .tokenizer import extract_for_retrieve as kiwi_extract_for_retrieve


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
    start_categories: list[str] = field(default_factory=list)  # v20 M2: 축 A 매칭 카테고리 이름
    # v20 M4 — LIKE fallback 메타데이터
    like_narrowed: bool = False           # narrowing 이 실제 적용됐는지
    like_tokens_used: list[str] = field(default_factory=list)  # 좁히기에 쓰인 토큰
    pre_narrow_count: int = 0             # narrowing 직전 문장 개수
    post_narrow_count: int = 0            # narrowing 후 문장 개수


# ─── DB 헬퍼 ──────────────────────────────────────────────

def _match_start_nodes(conn, keywords: list[str], question: str = "") -> dict[str, int]:
    """키워드 → 노드 ID 매핑 (별칭 → name 정확 → name substring)."""
    matched: dict[str, int] = {}
    alias_resolved_names: set[str] = set()

    if question:
        rows = conn.execute(
            "SELECT a.alias, n.id, n.name FROM aliases a "
            "JOIN nodes n ON n.id = a.node_id"
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
                   WHERE a.alias = ?""",
                (kw,),
            ).fetchone()
            if row:
                matched[f"{row['name']}#{row['id']}"] = row["id"]
                alias_resolved_names.add(row["name"])
                continue

        if kw in alias_resolved_names:
            continue
        rows = conn.execute(
            "SELECT id, name FROM nodes WHERE name = ?", (kw,)
        ).fetchall()
        if rows:
            for r in rows:
                if r["id"] not in matched.values():
                    matched[f"{r['name']}#{r['id']}"] = r["id"]
            continue

        rows = conn.execute(
            "SELECT id, name FROM nodes WHERE name LIKE ? LIMIT 5",
            (f"%{kw}%",),
        ).fetchall()
        for r in rows:
            if r["name"] not in alias_resolved_names and r["id"] not in matched.values():
                matched[f"{r['name']}#{r['id']}"] = r["id"]

    return matched


# ─── 축 A — 사용자 heading 계층 시드 (v20 PLAN-004 M2) ─────

def _match_start_categories(conn, keywords: list[str]) -> dict[str, set[int]]:
    """키워드와 categories.name 매칭 → 서브트리 id 집합 수집.

    각 키워드마다 재귀 CTE 로 매칭 카테고리 + 모든 하위 카테고리 id 를 모은다.
    반환: {matched_name: {id, ...}} — 질문 키워드 → 카테고리 서브트리 매핑.

    예) categories: (더나은) → (개발팀·휴가), (건강) → (2026-04-10)
        keywords=['더나은'] → {'더나은': {더나은.id, 개발팀.id, 휴가.id}}
        keywords=['개발팀'] → {'개발팀': {개발팀.id}}
    """
    result: dict[str, set[int]] = {}
    for kw in keywords:
        if not kw or not kw.strip():
            continue
        rows = conn.execute(
            """WITH RECURSIVE sub(id) AS (
                   SELECT id FROM categories WHERE name = ?
                   UNION ALL
                   SELECT c.id FROM categories c JOIN sub ON c.parent_id = sub.id
               )
               SELECT id FROM sub""",
            (kw,),
        ).fetchall()
        if rows:
            result[kw] = {r["id"] for r in rows}
    return result


def _get_sentences_by_category_ids(
    conn, category_ids: set[int]
) -> list[Mention]:
    """category_id 서브트리 → sentence_categories JOIN 으로 문장 + 공출현 노드 수집.

    축 A 시드가 BFS 시작 레이어로 편입되도록 Mention 리스트로 반환.
    한 문장에 여러 노드가 mention 되면 각 페어가 Mention 한 건씩 생성됨.
    공출현 노드가 전혀 없는 문장(heading 전용)은 node_id=-1, node_name='' 로 최소 1건 반환
    해 context_sentences 에 누락되지 않게 한다.
    """
    if not category_ids:
        return []
    ph = ",".join("?" * len(category_ids))
    # 매칭된 서브트리의 고유 문장 id 집합 먼저 확보
    sent_rows = conn.execute(
        f"""SELECT DISTINCT s.id AS sentence_id, s.text AS sentence_text
            FROM sentence_categories sc
            JOIN sentences s ON s.id = sc.sentence_id
            WHERE sc.category_id IN ({ph})""",
        list(category_ids),
    ).fetchall()
    if not sent_rows:
        return []
    sentence_ids = {r["sentence_id"] for r in sent_rows}
    sentence_text: dict[int, str] = {r["sentence_id"]: r["sentence_text"] for r in sent_rows}

    # 공출현 노드 JOIN (문장별 모든 노드)
    ph2 = ",".join("?" * len(sentence_ids))
    mention_rows = conn.execute(
        f"""SELECT m.sentence_id, m.node_id, n.name AS node_name
            FROM node_sentence_mentions m
            JOIN nodes n ON n.id = m.node_id
            WHERE m.sentence_id IN ({ph2})""",
        list(sentence_ids),
    ).fetchall()
    mentions_by_sid: dict[int, list[tuple[int, str]]] = {}
    for r in mention_rows:
        mentions_by_sid.setdefault(r["sentence_id"], []).append(
            (r["node_id"], r["node_name"])
        )

    result: list[Mention] = []
    for sid in sentence_ids:
        text = sentence_text[sid]
        nodes = mentions_by_sid.get(sid, [])
        if nodes:
            for nid, name in nodes:
                result.append(Mention(
                    node_id=nid, node_name=name,
                    sentence_id=sid, sentence_text=text,
                ))
        else:
            # 공출현 노드 없는 문장(예: key_value 만 있는 heading 하위) 도 context 로 노출
            result.append(Mention(
                node_id=-1, node_name="",
                sentence_id=sid, sentence_text=text,
            ))
    return result


def _get_mentions_for_nodes(conn, node_ids: set[int]) -> list[Mention]:
    """노드 ID 집합이 언급된 모든 sentences 조회 (node_sentence_mentions JOIN sentences)."""
    if not node_ids:
        return []
    ph = ",".join("?" * len(node_ids))
    rows = conn.execute(
        f"""
        SELECT m.node_id, n.name AS node_name, m.sentence_id, s.text AS sentence_text
        FROM node_sentence_mentions m
        JOIN nodes n     ON n.id = m.node_id
        JOIN sentences s ON s.id = m.sentence_id
        WHERE m.node_id IN ({ph})
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
        FROM node_sentence_mentions m
        JOIN nodes n ON n.id = m.node_id
        WHERE m.sentence_id IN ({ph})
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
        f"SELECT nc.major_category FROM node_categories nc WHERE nc.node_id IN ({ph})",
        list(start_node_ids),
    ).fetchall()

    subcats: set[str] = {
        r["major_category"] for r in rows
        if r["major_category"] and re.match(r"^[A-Z]{3}\.", r["major_category"])
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
            "WHERE nc.major_category = ? LIMIT 20",
            (sub,),
        ).fetchall()
        for r in cat_rows:
            if r["node_id"] not in visited_ids:
                result.add(r["node_id"])

    return result


# ─── LIKE fallback — 결과 과다 시 원문 구절로 좁힘 (v20 PLAN-004 M4) ─

# 기본 임계치: BFS 결과가 이 숫자를 넘으면 원문 LIKE 로 좁힘 시도.
# Gemma 4 E2B 컨텍스트 여유를 고려해 보수적으로 설정, retrieve() 호출자가 덮어쓰기 가능.
_LIKE_FALLBACK_DEFAULT_THRESHOLD = 20

# 질문 토큰에서 strip 할 양쪽 기호 (조사·어미는 아닌, 순수 문장부호만).
_PUNCT_STRIP_RE = re.compile(r'^[.,!?()\[\]"\'“”‘’·~…]+|[.,!?()\[\]"\'“”‘’·~…]+$')


def _extract_original_phrase_tokens(question: str) -> list[str]:
    """질문을 공백으로 분리해 의미 있는 원문 토큰만 남김 (v20 M4).

    Kiwi 가 쪼갠 lemma 가 아니라 **사용자가 쓴 그대로**의 구절 토큰.
    React Native·자바스크립트 같은 외래어·고유명사 복원 용도.

    규칙:
    - 공백 분리 후 양쪽 문장부호 strip
    - 길이 >= 2 만 유지 (한 글자 조사/전치사 제거)
    - 순서 유지 dedup
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw in question.split():
        cleaned = _PUNCT_STRIP_RE.sub('', raw)
        if len(cleaned) < 2:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


def _narrow_by_like(
    sentences: list[tuple[int, str]], question: str
) -> tuple[list[tuple[int, str]], list[str]]:
    """결과 과다 시 원문 질문 토큰 AND 매칭으로 좁힘.

    반환: (narrowed_sentences, applied_tokens).
    - 의미 있는 토큰이 없으면 (원본, []) 반환 (narrowing 효과 없음)
    - 모든 토큰을 substring 으로 포함하는 문장만 남김 (AND)
    - AND 결과가 비면 원본 그대로 유지 (결과 보호)
    """
    tokens = _extract_original_phrase_tokens(question)
    if not tokens:
        return sentences, []
    filtered = [
        (sid, text) for sid, text in sentences
        if all(tok in text for tok in tokens)
    ]
    if not filtered:
        return sentences, tokens
    return filtered, tokens


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
    created_map: Optional[dict[int, str]] = None,
    images: Optional[list[str]] = None,
    history: Optional[list[dict]] = None,
) -> str:
    """sentence 원문 컨텍스트로 자연어 답변.

    v18: `created_map` (sentence_id → created_at) 을 받아 사실을 **시간 순으로 정렬**하고
    각 줄 앞에 `[YYYY-MM-DD]` 힌트를 붙인다. 충돌하는 사실은 최근 것 우선 반영이 답변
    프롬프트 규칙 (SYSTEM_CHAT). 상태 레이어 제거(v18) 로 모든 sentence 가 조회 대상이라
    시점 해석은 이 단계에서 수행.
    """
    created_map = created_map or {}
    items = sorted(
        [(sid, t) for sid, t in sentences if t],
        key=lambda x: created_map.get(x[0], ""),
    )
    lines: list[str] = []
    seen: set[str] = set()
    for sid, text in items:
        if text in seen:
            continue
        seen.add(text)
        ts = created_map.get(sid, "")
        date_hint = ts.split(" ")[0] if ts else ""  # `YYYY-MM-DD HH:MM:SS` → 날짜만
        if date_hint:
            lines.append(f"- [{date_hint}] {text}")
        else:
            lines.append(f"- {text}")
    context = "\n".join(lines)
    user_msg = f"알려진 사실 (시간 순):\n{context}\n\n질문: {question}"
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
    like_fallback_threshold: int = _LIKE_FALLBACK_DEFAULT_THRESHOLD,
) -> RetrieveResult:
    """질문에 대한 BFS 인출 + LLM 답변.

    v20 (PLAN-004): 카테고리 두 축 사용. 축 A(`sentence_categories`) 는 서브트리 재귀
    CTE 로 heading 매칭 시드, 축 B(`node_categories.major_category`) 는 인접 맵 보완.
    BFS 결과가 `like_fallback_threshold` 를 넘으면 원문 LIKE AND 매칭으로 좁힘(M4).
    """
    result = RetrieveResult()

    conn = get_connection(db_path)
    try:
        # 1. 키워드 확장 — retrieve-expand(LLM) ∪ question.split() ∪ Kiwi 형태소
        #    Kiwi 는 LLM 사용 여부와 무관하게 항상 실행: 조사·어미가 붙은 질문에서
        #    명사·용언 lemma 를 분리해 재현율을 높인다. 어댑터 실패·비활성 시 폴백 역할.
        if use_llm:
            keywords = _llm_expand_keywords(question)
        else:
            keywords = []
        try:
            kiwi_kws = kiwi_extract_for_retrieve(question)
        except Exception:
            kiwi_kws = []
        keywords = list(dict.fromkeys(keywords + question.split() + kiwi_kws))

        start_nodes = _match_start_nodes(conn, keywords, question=question)
        result.start_nodes = list(start_nodes.keys())

        # 1-A. 축 A 시드 — categories 재귀 CTE 서브트리 → sentence_categories 경유 (v20)
        cat_match = _match_start_categories(conn, keywords)
        result.start_categories = list(cat_match.keys())
        all_category_ids: set[int] = set()
        for ids in cat_match.values():
            all_category_ids.update(ids)
        axis_a_mentions = _get_sentences_by_category_ids(conn, all_category_ids)

        # 노드·카테고리 양쪽 다 비면 조기 종료
        if not start_nodes and not axis_a_mentions:
            result.answer = "관련 정보를 찾을 수 없습니다."
            return result

        # 2. BFS 초기화 — 노드 시드 + 축 A 시드 통합
        visited_node_ids: set[int] = set(start_nodes.values())
        visited_sentence_ids: set[int] = set()
        all_mentions: list[Mention] = list(axis_a_mentions)
        # 축 A 시드 문장은 이미 수집 완료 — 다음 레이어 확장에만 쓰이도록 visited 업데이트
        for m in axis_a_mentions:
            visited_sentence_ids.add(m.sentence_id)
            if m.node_id > 0:
                visited_node_ids.add(m.node_id)
        # 첫 BFS 레이어는 (a) 노드 시드 (b) 축 A 시드 문장의 공출현 노드 모두 포함
        current_node_ids: set[int] = set(start_nodes.values())
        for m in axis_a_mentions:
            if m.node_id > 0:
                current_node_ids.add(m.node_id)

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

        # 4-B. 결과 과다 시 원문 LIKE fallback (v20 PLAN-004 M4)
        #      Kiwi 쪼갬으로 BFS 가 과도하게 넓어졌을 때 질문의 원문 구절(조사 제외)
        #      AND 매칭으로 좁힘. AND 결과가 비면 원본 유지 (보호).
        result.pre_narrow_count = len(context_sentences)
        if len(context_sentences) > like_fallback_threshold:
            narrowed, tokens_used = _narrow_by_like(context_sentences, question)
            result.like_tokens_used = tokens_used
            if narrowed is not context_sentences and len(narrowed) < len(context_sentences):
                context_sentences = narrowed
                result.like_narrowed = True
        result.post_narrow_count = len(context_sentences)
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

        # 6. LLM 답변 — v18: created_at 시간 순 정렬 힌트 포함
        created_map: dict[int, str] = {}
        if context_sentences:
            sids = [sid for sid, _ in context_sentences]
            ph = ",".join("?" * len(sids))
            for r in conn.execute(
                f"SELECT id, created_at FROM sentences WHERE id IN ({ph})",
                sids,
            ).fetchall():
                created_map[r["id"]] = r["created_at"]

        if use_llm:
            result.answer = _llm_answer(
                question, context_sentences, created_map,
                images=images, history=history,
            )
        else:
            # --no-llm: 시간 순으로 정렬해 그대로 출력
            sorted_items = sorted(
                context_sentences, key=lambda x: created_map.get(x[0], "")
            )
            lines = []
            for sid, t in sorted_items:
                ts = created_map.get(sid, "")
                d = ts.split(" ")[0] if ts else ""
                lines.append(f"[{d}] {t}" if d else t)
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
