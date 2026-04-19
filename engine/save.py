"""Synapse 자동 저장 파이프라인 (v15).

원칙:
- 입력 단위 = 마크다운 구조화된 게시물 (posts 1건 = 저장 호출 1건)
- 자동 저장 범위: post + sentences + nodes + node_mentions (+ heading 경로 카테고리)
- v15: edges 테이블 자체 폐기. 노드 간 연결은 node_mentions(문장 바구니) + node_categories
  (카테고리 바구니) + aliases(별칭 바구니) 세 하이퍼엣지로만 표현.
- 의미 관계(cause/avoid/similar)는 sentence 원문에 이미 있고, 해석은 외부 지능체 몫.
- 평문 입력 → structure-suggest 게이트 → SaveResult.markdown_draft 반환 (저장 보류)

v15-A2 저장 정책:
- 동기 단계에서 aliases는 user·rule origin만 INSERT (Wikidata·LLM 추천 경로 없음).
- 동기 단계에서 node_categories는 user·rule origin만 INSERT (AI 분류 경로 없음).
- AI 카테고리 분류와 external 별칭 수집은 저장 완료 이벤트로 넘기고 백그라운드 워커가
  담당. save() 는 commit 성공 후 등록된 훅을 호출한다 (register_post_save_hook).

맥락 공유:
- save-pronoun context = 같은 게시물의 다른 sentences (직전 대화 주입 폐기)
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from .db import get_connection, DB_PATH
from .llm import chat, LLMError, save_pronoun, llm_extract, structure_suggest
from .markdown import parse_markdown, has_heading


@dataclass
class SaveResult:
    post_id: Optional[int] = None
    sentence_ids: list[int] = field(default_factory=list)
    nodes_added: list[str] = field(default_factory=list)
    node_ids_added: list[int] = field(default_factory=list)
    mentions_added: int = 0
    unresolved_added: list[tuple[int, str]] = field(default_factory=list)  # (sentence_id, token)
    nodes_deactivated: list[str] = field(default_factory=list)  # 상태 변경된 노드 이름
    markdown_draft: Optional[str] = None  # structure-suggest 초안 (저장 보류 시)
    question: Optional[str] = None


# ─── 저장 완료 이벤트 훅 (v15-A2) ─────────────────────────

PostSaveHook = Callable[["SaveResult", str], None]

_POST_SAVE_HOOKS: list[PostSaveHook] = []


def register_post_save_hook(hook: PostSaveHook) -> None:
    """저장 완료 시 호출될 훅 등록. hook(result, db_path) 시그니처.

    v15-A2: 백그라운드 워커(카테고리 분류 · Wikidata 별칭)가 이 훅에 등록해
    `result.node_ids_added` 신규 노드를 소비한다. 훅 내부에서 asyncio.create_task
    또는 FastAPI BackgroundTasks 로 비동기 스케줄링할 책임은 훅 쪽에 있다.
    """
    if hook not in _POST_SAVE_HOOKS:
        _POST_SAVE_HOOKS.append(hook)


def _fire_post_save_hooks(result: "SaveResult", db_path: str) -> None:
    """commit 성공 후 등록된 훅 일괄 호출. 훅 예외는 격리(저장 성공에 영향 없음)."""
    for hook in _POST_SAVE_HOOKS:
        try:
            hook(result, db_path)
        except Exception as e:
            print(f"[save] post_save_hook {hook.__name__} 예외: {e}")


# ─── DB 헬퍼 ──────────────────────────────────────────────

def _insert_post(conn, markdown: str) -> int:
    cur = conn.execute("INSERT INTO posts (markdown) VALUES (?)", (markdown,))
    return cur.lastrowid


def _insert_sentence(
    conn,
    text: str,
    post_id: Optional[int] = None,
    position: int = 0,
    role: str = "user",
) -> int:
    cur = conn.execute(
        "INSERT INTO sentences (post_id, position, text, role) VALUES (?,?,?,?)",
        (post_id, position, text, role),
    )
    return cur.lastrowid


def _upsert_node(conn, name: str) -> tuple[int, bool]:
    """노드 삽입 또는 기존 ID 반환. 대소문자 무시, active 노드만 매칭."""
    row = conn.execute(
        "SELECT id FROM nodes WHERE name=? COLLATE NOCASE AND status='active' "
        "ORDER BY updated_at DESC LIMIT 1",
        (name,),
    ).fetchone()
    if row:
        return row["id"], False
    cur = conn.execute("INSERT INTO nodes (name) VALUES (?)", (name,))
    return cur.lastrowid, True


def _add_node_category(
    conn, node_id: int, category: Optional[str], origin: str = "user"
) -> None:
    """카테고리 INSERT. origin: 'user' (heading·수동) / 'ai' (LLM 추론) / 'rule' (규칙)."""
    if not category:
        return
    conn.execute(
        "INSERT OR IGNORE INTO node_categories (node_id, category, origin) VALUES (?,?,?)",
        (node_id, category, origin),
    )


def _add_mention(conn, node_id: int, sentence_id: int) -> bool:
    cur = conn.execute(
        "INSERT OR IGNORE INTO node_mentions (node_id, sentence_id) VALUES (?,?)",
        (node_id, sentence_id),
    )
    return cur.rowcount > 0


def _add_unresolved(conn, sentence_id: int, token: str) -> bool:
    """치환 실패 토큰을 unresolved_tokens에 기록. 새 레코드면 True."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO unresolved_tokens (sentence_id, token) VALUES (?,?)",
        (sentence_id, token),
    )
    return cur.rowcount > 0


def _deactivate_by_sentence_ids(conn, sentence_ids: list[int]) -> list[str]:
    """v15: deactivate 기능 축소 — Task 6B 어댑터 재학습 + 의미 재설계 대기 중.

    이전(v14)에는 edges 테이블을 통해 특정 대상 노드만 선택적으로 비활성화했으나,
    edges 폐기로 타겟팅 수단이 사라짐. 전체 공출현 노드를 비활성화하는 건 너무 공격적.
    현재는 no-op — sentence_id 목록만 문자열로 변환해 UI 표시용으로 반환.
    """
    if not sentence_ids:
        return []
    return [f"sentence#{sid}" for sid in sentence_ids if isinstance(sid, int)]


# ─── 토큰 감지 ────────────────────────────────────────────

_DATE_WORDS = (
    '어제', '그저께', '그제', '엊그제', '그끄제',
    '오늘', '내일', '모레', '글피', '그글피',
    '이번주', '이번 주', '지난주', '저번주', '다음주', '다음 주',
    '이번달', '지난달', '다음달',
    '올해', '작년', '내년', '재작년', '내후년',
)
_AGE_PATTERN = re.compile(r'\d{1,3}(살|세)|[0-9]0대')
_NEG_PATTERN = re.compile(r'(?:^|\s)(안|못)\s')


def _preprocess(text: str, post_context: str = "") -> dict:
    """지시대명사/날짜 치환. 모호하면 {"question": ...}.

    v12: post_context = 같은 게시물의 다른 sentences (개행 구분 문자열).
    """
    needs_today = any(w in text for w in _DATE_WORDS)
    needs_age = bool(_AGE_PATTERN.search(text))
    today = date.today().isoformat() if (needs_today or needs_age) else ""
    return save_pronoun(text, context=post_context, today=today)


def _detect_negation_tokens(text: str) -> list[str]:
    """부정부사 '안'/'못' 감지해 노드 후보로 반환."""
    tokens: list[str] = []
    for m in _NEG_PATTERN.finditer(f' {text} '):
        neg = m.group(1)
        if neg not in tokens:
            tokens.append(neg)
    return tokens


# ─── 날짜 정규화·분할 ────────────────────────────────────

def _normalize_dates_to_korean(text: str) -> str:
    """ISO 날짜를 한국어 표기로 변환. sentence 저장 직전 적용.

    예: '2026-04-18' → '2026년 4월 18일', '2026-04' → '2026년 4월'
    한글 조사 뒤에서도 매칭되도록 \\b 대신 negative lookbehind/lookahead 사용.
    """
    text = re.sub(
        r'(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)',
        lambda m: f"{m.group(1)}년 {int(m.group(2))}월 {int(m.group(3))}일",
        text,
    )
    text = re.sub(
        r'(?<!\d)(\d{4})-(\d{1,2})(?!\d)(?!-)',
        lambda m: f"{m.group(1)}년 {int(m.group(2))}월",
        text,
    )
    return text


def _expand_date_tokens(text: str) -> list[str]:
    """본문에서 날짜 패턴 발견 시 (년·월·일) 단위로 노드 후보 반환.

    한국어 표기('2026년 4월 18일')만 인식 — _normalize_dates_to_korean 이후
    호출되므로 ISO는 이미 변환된 상태.
    한 sentence에 발견된 모든 단위(년/월/일)가 같은 sentence에 mention된다:
      "2026년 4월 18일 병원 갔어" → ['2026년', '4월', '18일']
    """
    out: list[str] = []
    seen: set[str] = set()

    def add(*tokens: str) -> None:
        for t in tokens:
            if t and t not in seen:
                seen.add(t)
                out.append(t)

    # 가장 구체적인 패턴부터: YYYY년 M월 D일
    for m in re.finditer(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', text):
        add(f"{m.group(1)}년", f"{int(m.group(2))}월", f"{int(m.group(3))}일")
    # YYYY년 M월
    for m in re.finditer(r'(\d{4})년\s*(\d{1,2})월(?!\s*\d{1,2}일)', text):
        add(f"{m.group(1)}년", f"{int(m.group(2))}월")
    # YYYY년 단독
    for m in re.finditer(r'(\d{4})년(?!\s*\d{1,2}월)', text):
        add(f"{m.group(1)}년")
    # M월 D일 (년 미상)
    for m in re.finditer(r'(?<![년\d])(\d{1,2})월\s*(\d{1,2})일', text):
        add(f"{int(m.group(1))}월", f"{int(m.group(2))}일")
    # M월 단독 (년 미상)
    for m in re.finditer(r'(?<![년\d])(\d{1,2})월(?!\s*\d{1,2}일)', text):
        add(f"{int(m.group(1))}월")

    return out


# ─── 별칭 — 자동 등록 금지, 인칭대명사만 예외 ──────────────

_FIRST_PERSON_ALIASES = (
    "내", "저", "제", "나의", "저의", "제가", "나는", "저는",
    "내가", "제가", "나한테", "저한테",
)


def _register_first_person_aliases(conn, node_id: int) -> None:
    """인칭대명사 11개 시드 — origin='rule'."""
    for alias in _FIRST_PERSON_ALIASES:
        conn.execute(
            "INSERT OR IGNORE INTO aliases (alias, node_id, origin) VALUES (?,?, 'rule')",
            (alias, node_id),
        )


# ─── 기존 카테고리 경로 수집 (structure-suggest 컨텍스트) ─

def _collect_known_paths(conn, limit: int = 30) -> list[str]:
    """사용자 정의 카테고리 경로 목록 (최근 사용 순)."""
    rows = conn.execute(
        """SELECT category, MAX(created_at) AS latest
           FROM node_categories
           GROUP BY category
           ORDER BY latest DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [r["category"] for r in rows]


# ─── 메인 저장 로직 ───────────────────────────────────────

def _merge_nodes_extracted(extracted_nodes: list[dict], extra_names: list[str]) -> list[dict]:
    seen = set()
    result: list[dict] = []
    for n in extracted_nodes:
        name = n.get("name") if isinstance(n, dict) else None
        if not name or name in seen:
            continue
        seen.add(name)
        result.append({"name": name})
    for name in extra_names:
        if name and name not in seen:
            seen.add(name)
            result.append({"name": name})
    return result


def _save_one_item(
    conn,
    item_text: str,
    category_path: Optional[str],
    post_id: int,
    position: int,
    post_context: str,
    use_llm: bool,
    retrieve_context_sentences: Optional[list[tuple[int, str]]],
    result: SaveResult,
) -> None:
    """게시물 내 항목 하나 저장."""
    # 1. 지시어 치환 (같은 게시물의 다른 문장들 context)
    effective_text = item_text
    unresolved_tokens: list[str] = []
    if use_llm:
        try:
            pre = _preprocess(item_text, post_context=post_context)
            if pre.get("question"):
                result.question = pre["question"]
                return
            effective_text = pre.get("text", item_text)
            unresolved_tokens = pre.get("unresolved", []) or []
        except LLMError:
            pass

    # 1-1. ISO 날짜 → 한국어 정규화 (사용자 언급 공간 = 한국어)
    effective_text = _normalize_dates_to_korean(effective_text)

    # 2. sentence 저장 (post_id + position)
    sid = _insert_sentence(conn, effective_text, post_id=post_id, position=position)
    result.sentence_ids.append(sid)

    # 2-1. 치환 실패 토큰을 unresolved_tokens에 기록
    for token in unresolved_tokens:
        if _add_unresolved(conn, sid, token):
            result.unresolved_added.append((sid, token))

    # 3. extract (v15-A2: nodes + deactivate만. 카테고리/별칭은 저장 후 백그라운드 워커)
    if use_llm:
        try:
            extracted = llm_extract(effective_text, context_sentences=retrieve_context_sentences)
        except LLMError:
            extracted = {"nodes": [], "deactivate": []}
    else:
        extracted = {"nodes": [], "deactivate": []}

    ext_nodes = extracted.get("nodes", [])
    ext_deactivate = extracted.get("deactivate", [])

    # 4. 규칙 기반 토큰 감지 (부정부사 + 날짜 분할)
    neg_tokens = _detect_negation_tokens(effective_text)
    date_tokens = _expand_date_tokens(effective_text)
    ext_nodes = _merge_nodes_extracted(ext_nodes, neg_tokens + date_tokens)

    # 5. deactivate — v15에선 no-op + 식별자 수집만 (재설계 대기)
    if ext_deactivate:
        deact_sids = [s for s in ext_deactivate if isinstance(s, int)]
        result.nodes_deactivated.extend(_deactivate_by_sentence_ids(conn, deact_sids))

    # 6. 노드 upsert + mentions + (heading 경로) category
    for node in ext_nodes:
        name = node["name"]
        nid, is_new = _upsert_node(conn, name)
        if _add_mention(conn, nid, sid):
            result.mentions_added += 1
        if category_path:
            _add_node_category(conn, nid, category_path)
        if is_new:
            result.nodes_added.append(name)
            result.node_ids_added.append(nid)
            if name == "나":
                _register_first_person_aliases(conn, nid)


def save(
    text: str,
    db_path: str = DB_PATH,
    use_llm: bool = True,
    images: Optional[list[str]] = None,
    context_sentences: Optional[list[tuple[int, str]]] = None,
) -> SaveResult:
    """텍스트를 게시물 단위로 저장. SaveResult 반환.

    v12:
    - 매 save() 호출 = posts 1건 INSERT (게시물 단위)
    - heading 없으면 structure-suggest 호출 → markdown_draft 반환 (저장 보류)
    - 마크다운 모드에서는 markdown.py가 돌려준 항목들을 순서대로 저장

    context_sentences: 인출에서 가져온 (sentence_id, text) 쌍. extract의 deactivate 판단용.
    """
    result = SaveResult()

    conn = get_connection(db_path)
    try:
        # heading 없으면 평문 → structure-suggest 게이트
        if not has_heading(text):
            if use_llm:
                try:
                    known = _collect_known_paths(conn)
                    draft = structure_suggest(text, known_paths=known)
                    # 초안이 여전히 heading 없으면 실패로 간주하고 그대로 저장
                    if has_heading(draft):
                        result.markdown_draft = draft
                        return result
                except LLMError:
                    pass
            # use_llm=False 또는 structure-suggest 실패 → heading 없이 저장 진행
            # (운영상 이 경로는 거의 타지 않음)

        parsed = parse_markdown(text)
        if not parsed:
            conn.commit()
            return result

        # posts 1건 INSERT (원본 마크다운 보관)
        post_id = _insert_post(conn, text)
        result.post_id = post_id

        # 같은 게시물 내 모든 문장을 context 문자열로 준비
        all_items_text = "\n".join(item for _, item in parsed)

        # 항목별 저장
        for position, (category_path, item_text) in enumerate(parsed):
            # 현재 항목을 제외한 나머지 게시물 문장들을 context로
            others = [item for i, (_, item) in enumerate(parsed) if i != position]
            post_context = "\n".join(others)

            _save_one_item(
                conn,
                item_text,
                category_path,
                post_id=post_id,
                position=position,
                post_context=post_context,
                use_llm=use_llm,
                retrieve_context_sentences=context_sentences,
                result=result,
            )
            if result.question:
                # 모호성 감지 → 현재 항목까지만 커밋 후 중단
                break

        conn.commit()
    finally:
        conn.close()

    # 저장 완료 이벤트 — 백그라운드 워커 체인 트리거 (v15-A2)
    _fire_post_save_hooks(result, db_path)

    return result


# ─── 문장/노드 관리 ───────────────────────────────────────

def rollback(sentence_ids: list[int], node_ids: list[int], db_path: str = DB_PATH) -> dict:
    """문장/노드 삭제. v15: edges 폐기로 문장 단위 롤백이 기본.

    sentence_ids: 삭제할 sentence들 (node_mentions CASCADE)
    node_ids: 공출현 참조가 없는 노드만 실제 삭제 (고아 정리)
    """
    conn = get_connection(db_path)
    sentences_deleted = 0
    nodes_deleted = 0
    try:
        if sentence_ids:
            ph = ",".join("?" * len(sentence_ids))
            cur = conn.execute(f"DELETE FROM sentences WHERE id IN ({ph})", sentence_ids)
            sentences_deleted = cur.rowcount

        if node_ids:
            ph = ",".join("?" * len(node_ids))
            orphan_ids = [
                r[0] for r in conn.execute(
                    f"""SELECT id FROM nodes WHERE id IN ({ph})
                        AND id NOT IN (SELECT node_id FROM node_mentions)""",
                    node_ids,
                ).fetchall()
            ]
            if orphan_ids:
                ph2 = ",".join("?" * len(orphan_ids))
                cur2 = conn.execute(f"DELETE FROM nodes WHERE id IN ({ph2})", orphan_ids)
                nodes_deleted = cur2.rowcount

        conn.commit()
    finally:
        conn.close()

    return {"sentences_deleted": sentences_deleted, "nodes_deleted": nodes_deleted}


def split_node(
    node_id: int,
    alias_for_original: str,
    alias_for_new: str,
    sentence_ids_to_move: list[int],
    db_path: str = DB_PATH,
) -> dict:
    """동명이의어 분리: 같은 이름 노드를 둘로 쪼개되, 지정한 sentence들의
    node_mentions를 새 노드로 이관. v15: edges 테이블 폐기로 문장 단위 이관만 수행."""
    conn = get_connection(db_path)
    try:
        orig = conn.execute("SELECT id, name FROM nodes WHERE id=?", (node_id,)).fetchone()
        if not orig:
            return {"error": "node not found"}

        cur = conn.execute("INSERT INTO nodes (name) VALUES (?)", (orig["name"],))
        new_id = cur.lastrowid
        conn.execute(
            "INSERT OR IGNORE INTO node_categories (node_id, category) "
            "SELECT ?, category FROM node_categories WHERE node_id=?",
            (new_id, node_id),
        )

        moved = 0
        if sentence_ids_to_move:
            ph = ",".join("?" * len(sentence_ids_to_move))
            cur2 = conn.execute(
                f"""UPDATE node_mentions SET node_id=?
                    WHERE node_id=? AND sentence_id IN ({ph})""",
                [new_id, node_id, *sentence_ids_to_move],
            )
            moved = cur2.rowcount

        conn.execute("INSERT OR IGNORE INTO aliases (alias, node_id) VALUES (?,?)", (alias_for_original, node_id))
        conn.execute("INSERT OR IGNORE INTO aliases (alias, node_id) VALUES (?,?)", (alias_for_new, new_id))

        conn.commit()
    finally:
        conn.close()

    return {
        "original_node_id": node_id,
        "new_node_id": new_id,
        "mentions_moved": moved,
        "aliases": {alias_for_original: node_id, alias_for_new: new_id},
    }


def merge_nodes(
    keep_id: int,
    remove_id: int,
    db_path: str = DB_PATH,
) -> dict:
    conn = get_connection(db_path)
    try:
        keep = conn.execute("SELECT id, name FROM nodes WHERE id=?", (keep_id,)).fetchone()
        remove = conn.execute("SELECT id, name FROM nodes WHERE id=?", (remove_id,)).fetchone()
        if not keep or not remove:
            return {"error": "node not found"}

        conn.execute(
            """INSERT OR IGNORE INTO node_mentions (node_id, sentence_id, created_at)
               SELECT ?, sentence_id, created_at FROM node_mentions WHERE node_id=?""",
            (keep_id, remove_id),
        )
        cur_m = conn.execute("DELETE FROM node_mentions WHERE node_id=?", (remove_id,))
        mentions_moved = cur_m.rowcount

        conn.execute(
            """INSERT OR IGNORE INTO node_categories (node_id, category, created_at)
               SELECT ?, category, created_at FROM node_categories WHERE node_id=?""",
            (keep_id, remove_id),
        )
        conn.execute("DELETE FROM node_categories WHERE node_id=?", (remove_id,))

        aliases_moved = []
        for r in conn.execute("SELECT alias FROM aliases WHERE node_id=?", (remove_id,)).fetchall():
            aliases_moved.append(r["alias"])
        conn.execute("UPDATE aliases SET node_id=? WHERE node_id=?", (keep_id, remove_id))

        conn.execute(
            "INSERT OR IGNORE INTO aliases (alias, node_id) VALUES (?,?)",
            (remove["name"], keep_id),
        )

        conn.execute(
            "UPDATE nodes SET status='inactive', updated_at=datetime('now') WHERE id=?",
            (remove_id,),
        )

        conn.commit()
    finally:
        conn.close()

    return {
        "keep_id": keep_id,
        "keep_name": keep["name"],
        "removed_id": remove_id,
        "removed_name": remove["name"],
        "mentions_moved": mentions_moved,
        "aliases_moved": aliases_moved,
    }


def find_suspected_typos(db_path: str = DB_PATH) -> list[dict]:
    from .jamo import decompose, levenshtein

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT n.id, n.name,
                  (SELECT COUNT(*) FROM node_mentions WHERE node_id=n.id) AS mention_count
               FROM nodes n WHERE n.status='active'"""
        ).fetchall()
    finally:
        conn.close()

    nodes = [{"id": r["id"], "name": r["name"], "mention_count": r["mention_count"]} for r in rows]
    jamo_cache = {n["name"]: decompose(n["name"]) for n in nodes}

    suspects = []
    for i, a in enumerate(nodes):
        ja = jamo_cache[a["name"]]
        if len(ja) < 6:
            continue
        for b in nodes[i + 1:]:
            jb = jamo_cache[b["name"]]
            if len(jb) < 6:
                continue
            if abs(len(ja) - len(jb)) > 1:
                continue
            if levenshtein(ja, jb) == 1:
                suspects.append({
                    "node_a": a,
                    "node_b": b,
                    "jamo_distance": 1,
                })

    suspects.sort(
        key=lambda s: max(s["node_a"]["mention_count"], s["node_b"]["mention_count"]),
        reverse=True,
    )
    return suspects


def save_response(text: str, db_path: str = DB_PATH) -> int:
    """assistant 응답 저장. post_id 없음 (대화 기록 전용)."""
    conn = get_connection(db_path)
    try:
        sid = _insert_sentence(conn, text, post_id=None, position=0, role="assistant")
        conn.commit()
    finally:
        conn.close()
    return sid


# ── 문장 검색/수정/삭제 ──────────────────────────────────────


def search_sentences(
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    role: str = "",
    offset: int = 0,
    limit: int = 20,
    db_path: str = DB_PATH,
) -> dict:
    conn = get_connection(db_path)
    try:
        where: list[str] = []
        params: list = []

        if q:
            where.append("s.text LIKE ?")
            params.append(f"%{q}%")
        if date_from:
            where.append("s.created_at >= ?")
            params.append(date_from)
        if date_to:
            where.append("s.created_at <= ?")
            params.append(date_to + " 23:59:59")
        if role:
            where.append("s.role = ?")
            params.append(role)

        where_clause = f"WHERE {' AND '.join(where)}" if where else ""

        total = conn.execute(
            f"SELECT COUNT(*) FROM sentences s {where_clause}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""SELECT s.id, s.post_id, s.position, s.text, s.role, s.created_at
                FROM sentences s {where_clause}
                ORDER BY s.created_at DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
    finally:
        conn.close()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": r["id"],
                "post_id": r["post_id"],
                "position": r["position"],
                "text": r["text"],
                "role": r["role"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
    }


def get_sentence_impact(sentence_id: int, db_path: str = DB_PATH) -> dict:
    """문장 삭제 시 영향 범위 조회. v15: edges 폐기로 mentions만 집계."""
    conn = get_connection(db_path)
    try:
        mentions = conn.execute(
            """SELECT n.id, n.name
               FROM node_mentions m
               JOIN nodes n ON n.id = m.node_id
               WHERE m.sentence_id = ?""",
            (sentence_id,),
        ).fetchall()
    finally:
        conn.close()

    return {
        "sentence_id": sentence_id,
        "affected_mentions": [
            {"node_id": m["id"], "node_name": m["name"]} for m in mentions
        ],
    }


def update_sentence(
    sentence_id: int,
    new_text: str,
    use_llm: bool = True,
    db_path: str = DB_PATH,
) -> SaveResult:
    """문장 수정: 기존 mentions 끊고 텍스트 갱신. 새 mentions는 즉시 재추출하지 않음
    (게시물 단위 재저장은 post 수정 API를 통해). Phase 2에서는 최소 인터페이스만."""
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM node_mentions WHERE sentence_id = ?", (sentence_id,))
        conn.execute(
            "UPDATE sentences SET text = ? WHERE id = ?",
            (new_text, sentence_id),
        )
        conn.commit()
    finally:
        conn.close()

    return SaveResult()


def delete_sentence(sentence_id: int, db_path: str = DB_PATH) -> dict:
    conn = get_connection(db_path)
    try:
        mentions_deleted = conn.execute(
            "SELECT COUNT(*) FROM node_mentions WHERE sentence_id = ?",
            (sentence_id,),
        ).fetchone()[0]
        conn.execute("DELETE FROM sentences WHERE id = ?", (sentence_id,))
        conn.commit()
    finally:
        conn.close()

    return {"sentence_id": sentence_id, "mentions_deleted": mentions_deleted}


if __name__ == "__main__":
    tests = [
        "# 병원.2026-04-18\n오늘 병원 다녀왔어\n세레콕시브 처방받았어\n허리디스크 L4-L5 진단",
        "# 직장.더나은\n## 개발팀\n- 팀장 박지수\n- 프론트엔드 김민수",
    ]
    for text in tests:
        r = save(text, use_llm=False)
        print(f"\n입력:\n{text}")
        print(f"  post_id: {r.post_id}")
        print(f"  sentence_ids: {r.sentence_ids}")
        print(f"  nodes_added: {r.nodes_added}")
        print(f"  mentions_added: {r.mentions_added}")
