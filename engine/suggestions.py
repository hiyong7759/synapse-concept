"""검토 대상 런타임 도출기 — review target generator (v15).

원칙:
- 각 함수는 DB 쿼리 + 필요 시 LLM 호출로 제안 리스트를 반환한다.
- DB에 쓰지 않는다. 저장은 사용자가 승인한 시점에만 (api/routes/graph.py /review/apply).
- 유일한 저장 예외는 `unresolved_tokens` (Phase 3에서 INSERT됨, 여기서는 읽기만).
- LLM 의존 섹션은 use_llm=False일 때 빈 결과 또는 LLM 없는 fallback 반환.

v15 폐기 섹션 (DESIGN_REVIEW.md §폐기된 섹션 참고):
- `uncategorized` — 저장 시점에 origin='ai'/'rule'로 자동 분류 (예정)
- `cooccur_pairs` — 문장 하이퍼엣지(node_mentions)에 이미 자동 포함되므로 별도 제안 불필요
- `alias_suggestions` — origin='ai' 별칭으로 자동 등록 (예정)
- 의미 엣지 관련 섹션 — edges 테이블 폐기로 전체 제거
"""

from __future__ import annotations
from datetime import date, timedelta
from typing import Optional

from .db import get_connection, DB_PATH
from .save import find_suspected_typos
from .llm import chat, LLMError


# ─── 도출기들 ────────────────────────────────────────────

def unresolved(db_path: str = DB_PATH, limit: int = 30) -> list[dict]:
    """미해결 지시어. unresolved_tokens 읽고 옵션 구성.

    옵션은 토큰 종류에 따라 다름. 시간/장소/사물·인물 분기.
    Phase 3의 토큰 감지 규칙과 매칭되는 휴리스틱.

    응답에 게시물 정보(post_id, post_markdown 일부, 시각)도 포함 — UI가
    "어느 게시물의 어디인지" 직관적으로 보여줄 수 있도록.
    """
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT u.sentence_id, u.token, u.created_at,
                      s.text AS sentence_text, s.post_id, s.position,
                      p.markdown AS post_markdown, p.created_at AS post_created_at
               FROM unresolved_tokens u
               JOIN sentences s ON s.id = u.sentence_id
               LEFT JOIN posts p ON p.id = s.post_id
               ORDER BY u.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()

        # 사용자의 카테고리별 최근 노드 (옵션 후보)
        recent_by_cat: dict[str, list[str]] = {}
        cat_rows = conn.execute(
            """SELECT nc.category, n.name, n.updated_at
               FROM node_categories nc
               JOIN nodes n ON n.id = nc.node_id
               WHERE n.status='active'
               ORDER BY n.updated_at DESC LIMIT 200"""
        ).fetchall()
        for r in cat_rows:
            recent_by_cat.setdefault(r["category"], []).append(r["name"])
    finally:
        conn.close()

    _TIME_TOKENS = {"요즘", "최근", "그때", "당시", "주말", "이번에"}
    _PLACE_TOKENS = {"여기", "거기", "저기", "이곳", "그곳", "저곳"}
    _PERSON_TOKENS = {"이분", "그분", "저분", "걔", "쟤", "얘", "그녀"}

    today = date.today()
    result: list[dict] = []
    for r in rows:
        token = r["token"]
        # 게시물 markdown은 너무 길면 잘라 보여주기 (UI 부담 줄이기)
        post_md = r["post_markdown"] or ""
        if len(post_md) > 200:
            post_md = post_md[:200] + "..."
        item: dict = {
            "sentence_id": r["sentence_id"],
            "token": token,
            "sentence_text": r["sentence_text"],
            "post_id": r["post_id"],
            "post_position": r["position"],
            "post_markdown": post_md,
            "post_created_at": r["post_created_at"],
            "question": f"'{token}'을(를) 구체적으로 알려주세요",
            "options": [],
            "allow_free_input": True,
        }
        if token in _TIME_TOKENS:
            item["question"] = f"'{token}'은 언제부터 언제까지인가요?"
            item["options"] = [
                today.isoformat(),
                f"{(today - timedelta(days=7)).isoformat()}~{today.isoformat()}",
                today.strftime("%Y-%m"),
            ]
        elif token in _PLACE_TOKENS:
            item["question"] = f"'{token}'은 어디인가요?"
            for path, names in recent_by_cat.items():
                if any(k in path for k in ("장소", "REG", "TRV", "병원")):
                    item["options"].extend(names[:3])
                    break
        elif token in _PERSON_TOKENS:
            item["question"] = f"'{token}'은 누구인가요?"
            for path, names in recent_by_cat.items():
                if path.startswith("PER") or any(k in path for k in ("인물", "사람")):
                    item["options"].extend(names[:3])
                    break
        # 옵션 dedup
        item["options"] = list(dict.fromkeys(item["options"]))[:5]
        result.append(item)
    return result


def suspected_typos(db_path: str = DB_PATH, limit: int = 20) -> list[dict]:
    """오타 의심 쌍 — find_suspected_typos 재사용."""
    pairs = find_suspected_typos(db_path=db_path)[:limit]
    return [
        {
            "node_a_id": p["node_a"]["id"],
            "node_a_name": p["node_a"]["name"],
            "node_b_id": p["node_b"]["id"],
            "node_b_name": p["node_b"]["name"],
            "mention_count_a": p["node_a"]["mention_count"],
            "mention_count_b": p["node_b"]["mention_count"],
            "question": f"'{p['node_a']['name']}'와(과) '{p['node_b']['name']}'은(는) 같은 개념인가요?",
            "options": ["같음 (병합)", "다름 (무시)"],
        }
        for p in pairs
    ]


def stale_nodes(db_path: str = DB_PATH, days: int = 90, limit: int = 20) -> list[dict]:
    """오래 미참조 노드 — 유지/아카이브 결정 카드."""
    cutoff = (date.today() - timedelta(days=days)).isoformat()
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT n.id, n.name, n.updated_at,
                      (SELECT COUNT(*) FROM node_mentions WHERE node_id = n.id) AS mention_count
               FROM nodes n
               WHERE n.status='active' AND n.updated_at < ?
               ORDER BY n.updated_at LIMIT ?""",
            (cutoff, limit),
        ).fetchall()
    finally:
        conn.close()
    return [
        {
            "node_id": r["id"],
            "node_name": r["name"],
            "updated_at": r["updated_at"],
            "mention_count": r["mention_count"],
            "question": f"'{r['name']}'은(는) {r['updated_at']} 이후 변동이 없습니다. 어떻게 할까요?",
            "options": ["유지", "아카이브 (status=inactive)"],
        }
        for r in rows
    ]


def daily(db_path: str = DB_PATH, target_date: Optional[str] = None) -> dict:
    """하루 회고 뷰 — 해당 날짜 sentences 묶어서 반환."""
    d = target_date or date.today().isoformat()
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT s.id, s.text, s.role, s.post_id, s.position, s.created_at
               FROM sentences s
               WHERE date(s.created_at) = ?
               ORDER BY s.created_at""",
            (d,),
        ).fetchall()
    finally:
        conn.close()
    return {
        "date": d,
        "sentence_count": len(rows),
        "sentences": [
            {"id": r["id"], "text": r["text"], "role": r["role"],
             "post_id": r["post_id"], "position": r["position"]}
            for r in rows
        ],
    }


_BASIC_INFO_FIELDS = [
    {"name": "job",    "label": "직업", "keywords": ["회사", "직장", "일", "직업", "업무", "기획자", "개발자", "디자이너"],
     "question": "어떤 일을 하시나요?"},
    {"name": "region", "label": "지역", "keywords": ["살", "집", "동네", "지역", "거주", "도시", "구", "동"],
     "question": "주로 어디에 사세요?"},
    {"name": "interest", "label": "관심사", "keywords": ["좋아", "취미", "관심", "즐기"],
     "question": "관심 있거나 좋아하는 게 있으신가요?"},
]


def missing_basic_info(db_path: str = DB_PATH) -> list[dict]:
    """온보딩 후 누락된 기본 정보 (직업·지역·관심사) 감지.

    '나' 노드 mentions sentences를 모은 텍스트에 분야 키워드가 없으면 누락 판정.
    Phase 6 — /review에 자연스럽게 채울 수 있도록.
    """
    conn = get_connection(db_path)
    try:
        me = conn.execute(
            "SELECT id FROM nodes WHERE name='나' AND status='active' LIMIT 1"
        ).fetchone()
        if not me:
            return []
        rows = conn.execute(
            """SELECT s.text FROM node_mentions m
               JOIN sentences s ON s.id = m.sentence_id
               WHERE m.node_id = ?""",
            (me["id"],),
        ).fetchall()
    finally:
        conn.close()

    all_text = " ".join(r["text"] for r in rows)
    result: list[dict] = []
    for f in _BASIC_INFO_FIELDS:
        if not any(k in all_text for k in f["keywords"]):
            result.append({
                "field": f["name"],
                "label": f["label"],
                "question": f["question"],
                "options": [],
                "allow_free_input": True,
            })
    return result


def gaps(db_path: str = DB_PATH, threshold_days: int = 7, limit: int = 5) -> list[dict]:
    """sentences.created_at 분석 → N일 이상 비어있는 구간."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT date(created_at) AS day FROM sentences "
            "WHERE role='user' GROUP BY day ORDER BY day"
        ).fetchall()
    finally:
        conn.close()

    if len(rows) < 2:
        return []

    gaps_found: list[dict] = []
    prev = date.fromisoformat(rows[0]["day"])
    for r in rows[1:]:
        cur = date.fromisoformat(r["day"])
        delta = (cur - prev).days
        if delta > threshold_days:
            gaps_found.append({
                "from": prev.isoformat(),
                "to": cur.isoformat(),
                "days": delta,
                "question": f"{prev.isoformat()}부터 {cur.isoformat()}까지 {delta}일간 기록이 없어요. 그 기간 일이 있었나요?",
                "options": ["기록 추가", "특별한 일 없었음"],
                "allow_free_input": True,
            })
        prev = cur
    gaps_found.sort(key=lambda x: x["days"], reverse=True)
    return gaps_found[:limit]


# ─── 통합 ─────────────────────────────────────────────────

def all_sections(
    db_path: str = DB_PATH,
    use_llm: bool = True,
    sections: Optional[list[str]] = None,
) -> dict:
    """전체 섹션 호출. sections 인자로 일부만 선택 가능."""
    available = {
        "unresolved":         lambda: unresolved(db_path=db_path),
        "suspected_typos":    lambda: suspected_typos(db_path=db_path),
        "missing_basic_info": lambda: missing_basic_info(db_path=db_path),
        "stale_nodes":        lambda: stale_nodes(db_path=db_path),
        "daily":              lambda: daily(db_path=db_path),
        "gaps":               lambda: gaps(db_path=db_path),
    }
    keys = sections if sections else list(available.keys())
    return {k: available[k]() for k in keys if k in available}


def counts(db_path: str = DB_PATH) -> dict:
    """배지용 집계 — 빠른 쿼리만."""
    conn = get_connection(db_path)
    try:
        unresolved_n = conn.execute("SELECT COUNT(*) FROM unresolved_tokens").fetchone()[0]
    finally:
        conn.close()
    typos_n = len(find_suspected_typos(db_path=db_path))
    basic_n = len(missing_basic_info(db_path=db_path))
    total = unresolved_n + typos_n + basic_n
    return {
        "total":              total,
        "unresolved":         unresolved_n,
        "suspected_typos":    typos_n,
        "missing_basic_info": basic_n,
    }
