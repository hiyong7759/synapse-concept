"""Synapse 자동 저장 파이프라인 (v20 — PLAN-004 M1).

원칙:
- 입력 단위 = 게시물 (posts 1건 = 저장 호출 1건).
- 저장 모드는 호출자가 mode='chat'|'markdown' 로 명시 (UI 입력창 선택 반영).
- 자동 저장 범위: post + sentences + nodes + node_mentions + sentence_categories(축 A)
  + node_categories(축 B — TIM.* 규칙만 동기, 나머지는 워커)
- v15: edges 테이블 자체 폐기. 노드 간 연결은 node_mentions(문장 바구니) + 카테고리
  두 축(v20 사용자 heading / 19 대분류) + aliases 세 하이퍼엣지로만 표현.
- 의미 관계(cause/avoid/similar)는 sentence 원문에 이미 있고, 해석은 외부 지능체 몫.

v20 변경점 (PLAN-004 M1 — 카테고리 재설계):
- 축 A(사용자 heading 계층) = categories(adjacency list) + sentence_categories(문장 매핑).
  heading path segments 를 상위→하위로 categories upsert 하고 말단 category_id 만
  sentence_categories 에 origin='user' 로 INSERT. 과거 "Kiwi 노드 전부에 heading
  경로 부여" 하던 과포함 제거.
- 축 B(19 대분류 의미 태깅) = node_categories.major_category. 저장 시점엔 결정론적
  규칙(TIM.* 자동 태깅) 만 origin='system' 으로 INSERT. AI 분류는 워커가 담당.
- 호출자 API 변경 없음 (save(text, mode=) 동일).

v19 변경점 (PLAN-003 M1 — chat 모드 정립):
- save(mode=) 파라미터 필수. 'chat' / 'markdown' 양자택일.
- chat 모드: 모든 줄을 category_path=None 의 sentence 로 분리. `#` 은 해시태그로 취급해
  heading 으로 해석하지 않는다 (즉 sentence INSERT 대상).
- markdown 모드: 기존 parse_markdown 그대로. kind 별 분기·save-pronoun skip 등의 세부
  동작은 M2 에서 도입 (PLAN-004 선수행 필요).
- posts.input_mode 컬럼에 mode 값 그대로 저장.

v17 파이프라인 변경:
- Kiwi 단독이 저장 기본 경로 (LLM extract/merge 폐기).
- 게시물 진입부에서 메타 필터(규칙 사전필터 + LLM 배치 1회) 로 메타 대화 문장 skip.
- structure-suggest 폐기 — 평문 게시물도 heading 없이 그대로 sentence 단위로 저장.
- 날짜 분할 노드(`2026년`/`4월`/`18일`/통째) 에 TIM.* 카테고리 origin='system' 자동 등록.
- origin rule→system 리네이밍 (엔진이 주체).

v15-A2 저장 정책 (v17 유지):
- 동기 단계에서 aliases는 user·system origin만 INSERT (Wikidata·LLM 추천 경로 없음).
- 동기 단계에서 node_categories는 TIM.* 규칙 시드만 (AI 분류는 워커).
- AI 카테고리 분류와 external 별칭 수집은 저장 완료 이벤트로 넘기고 백그라운드 워커가
  담당. save() 는 commit 성공 후 등록된 훅을 호출한다 (register_post_save_hook).

맥락 공유:
- save-pronoun context = 같은 게시물의 다른 sentences (직전 대화 주입 폐기)

LLM 실패 시 독립 동작 (원칙 11):
- 메타 필터 실패 → 규칙 사전필터 결과만 반영 (과포함 허용, UI 삭제로 해소)
- save-pronoun 실패 → 원문 그대로 진행
- extract-state 실패 → 상태 전이 skip
"""

from __future__ import annotations
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Optional

from .db import get_connection, DB_PATH, SEED_ROOT_NAMES
from .llm import (
    LLMError,
    llm_meta_filter,
    save_pronoun,
)
from .markdown import parse_markdown
from .tokenizer import extract_for_save as kiwi_extract_for_save


@dataclass
class SaveResult:
    post_id: Optional[int] = None
    sentence_ids: list[int] = field(default_factory=list)
    nodes_added: list[str] = field(default_factory=list)
    node_ids_added: list[int] = field(default_factory=list)
    mentions_added: int = 0
    unresolved_added: list[tuple[int, str]] = field(default_factory=list)  # (sentence_id, token)
    # v18: sentences_deactivated/pending/nodes_deactivated 폐기 (상태 레이어 제거)
    markdown_draft: Optional[str] = None  # v17: structure-suggest 폐기. 하위 호환용 필드 유지 (항상 None)
    question: Optional[str] = None
    # v20 (PLAN-004 M3): heading 루트가 19 대분류 시드 이름과 일치해 자동 병합된 경고.
    # 항목 예: "루트 'BOD' 이 19 대분류 시드와 동일 — 시드 트리에 병합됨"
    category_warnings: list[str] = field(default_factory=list)


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

def _insert_post(conn, markdown: str, input_mode: str) -> int:
    cur = conn.execute(
        "INSERT INTO posts (markdown, input_mode) VALUES (?,?)",
        (markdown, input_mode),
    )
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


def _add_node_major_category(
    conn, node_id: int, major_category: Optional[str], origin: str = "system"
) -> None:
    """축 B: 노드 → 19 대분류 코드 INSERT (v20).

    origin:
      - 'ai'     LLM 분류 워커 (백그라운드, 기본 경로)
      - 'system' 결정론적 엔진 규칙 (TIM.* 자동 태깅 등)
      - 'user'   /review 에서 수동 교정
    """
    if not major_category:
        return
    conn.execute(
        "INSERT OR IGNORE INTO node_categories (node_id, major_category, origin) VALUES (?,?,?)",
        (node_id, major_category, origin),
    )


def _upsert_category_path(
    conn, path: Optional[str], warnings: Optional[list[str]] = None
) -> Optional[int]:
    """축 A: heading path (예: '더나은.개발팀') 를 categories 에 상위→하위 upsert.

    반환값: 말단 category_id (path 가 None/빈 문자열이면 None).
    parent_id 체인으로 저장하며 SQLite IS ? 로 NULL 비교.

    v20 PLAN-004 M3: warnings 리스트가 주어지면 루트 세그먼트가 19 대분류 시드명
    (`SEED_ROOT_NAMES`) 과 일치할 때 경고 메시지 누적. 현재 동작은 시드 트리에
    자동 병합이며, 사용자 의도 충돌 가능성을 `/review` 에 노출하기 위함.
    """
    if not path:
        return None
    segments = [s.strip() for s in path.split(".") if s and s.strip()]
    if not segments:
        return None
    parent_id: Optional[int] = None
    leaf_id: Optional[int] = None
    for idx, seg in enumerate(segments):
        # 루트 세그먼트가 시드명과 일치 → 경고 (자동 병합 동작은 유지, 같은 메시지 dedup)
        if idx == 0 and warnings is not None and seg in SEED_ROOT_NAMES:
            msg = (
                f"heading 루트 '{seg}' 이 19 대분류 시드 이름과 동일 — "
                f"시드 트리에 병합됨. /review 에서 분리 여부 확인 필요."
            )
            if msg not in warnings:
                warnings.append(msg)
        row = conn.execute(
            "SELECT id FROM categories WHERE name=? AND parent_id IS ?",
            (seg, parent_id),
        ).fetchone()
        if row:
            leaf_id = row["id"] if hasattr(row, "keys") else row[0]
        else:
            cur = conn.execute(
                "INSERT INTO categories (name, parent_id) VALUES (?,?)",
                (seg, parent_id),
            )
            leaf_id = cur.lastrowid
        parent_id = leaf_id
    return leaf_id


def _add_sentence_category(
    conn, sentence_id: int, category_id: Optional[int], origin: str = "user"
) -> None:
    """축 A: 문장 → 카테고리 말단 연결 INSERT (v20)."""
    if category_id is None:
        return
    conn.execute(
        "INSERT OR IGNORE INTO sentence_categories "
        "(sentence_id, category_id, origin) VALUES (?,?,?)",
        (sentence_id, category_id, origin),
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


# v18: _update_sentence_status · _deactivate_by_sentence_ids 폐기 (상태 레이어 제거).


# ─── 토큰 감지 ────────────────────────────────────────────

_DATE_WORDS = (
    '어제', '그저께', '그제', '엊그제', '그끄제',
    '오늘', '내일', '모레', '글피', '그글피',
    '이번주', '이번 주', '지난주', '저번주', '다음주', '다음 주',
    '이번달', '지난달', '다음달',
    '올해', '작년', '내년', '재작년', '내후년',
)
_AGE_PATTERN = re.compile(r'\d{1,3}(살|세)|[0-9]0대')


def _preprocess(text: str, post_context: str = "") -> dict:
    """지시대명사/날짜 치환. 모호하면 {"question": ...}.

    v12: post_context = 같은 게시물의 다른 sentences (개행 구분 문자열).
    """
    needs_today = any(w in text for w in _DATE_WORDS)
    needs_age = bool(_AGE_PATTERN.search(text))
    today = date.today().isoformat() if (needs_today or needs_age) else ""
    return save_pronoun(text, context=post_context, today=today)


def _detect_unresolved_tokens(text: str) -> list[str]:
    """지시대명사·모호 부사(시간/장소/인물/사물) 감지. 중복 제거한 원형 리스트 반환.

    어절 단위로 분할 후 각 어절의 시작이 사전의 토큰과 일치하고, 토큰 뒤가
    비어있거나 한글(조사·접미어)이 이어지면 매칭. 영숫자·기호가 바로 붙으면
    다른 단어로 간주해 거부.
    """
    from .suggestions import DEMONSTRATIVE_TOKENS
    found: list[str] = []
    for raw in re.split(r"\s+", text):
        word = re.sub(r"^[.,!?()\[\]\"'“”‘’]+|[.,!?()\[\]\"'“”‘’]+$", "", raw)
        if not word:
            continue
        for tok in DEMONSTRATIVE_TOKENS:
            if word.startswith(tok):
                rest = word[len(tok):]
                if not rest or ("\uAC00" <= rest[0] <= "\uD7AF"):
                    if tok not in found:
                        found.append(tok)
                    break
    return found


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


_QUANTITY_UNITS = (
    # 시간·기간
    "초", "분", "시간", "일", "주", "개월", "년", "박",
    # 횟수·차수
    "회", "번", "차",
    # 화폐
    "원", "만원", "억원", "원어치",
    # 비율
    "%", "퍼센트", "퍼",
    # 거리·길이·무게·부피
    "km", "m", "cm", "mm", "kg", "g", "t",
    "L", "ℓ", "ml", "cc",
    # 나이·인원
    "살", "세", "명", "인", "분",
    # 크기·용량
    "GB", "TB", "MB", "KB", "인치", "px",
    # 에너지
    "kcal", "cal", "W", "kW", "Wh", "kWh",
)

# 긴 단위부터 매칭 (예: '만원' 을 '원' 보다 먼저)
_QUANTITY_UNITS_SORTED = sorted(set(_QUANTITY_UNITS), key=len, reverse=True)
_QUANTITY_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(\d+(?:[,.]\d+)*)\s*(" + "|".join(
        re.escape(u) for u in _QUANTITY_UNITS_SORTED
    ) + r")(?![A-Za-z0-9])"
)


def _extract_quantity_tokens(text: str) -> list[str]:
    """본문에서 수량(숫자+단위) 결합 토큰을 노드 후보로 추출.

    v17: Kiwi 가 숫자(SN)와 단위명사(NNB/NNG)를 분리하면서 `1주`·`12시간`·`150%`
    같은 수량이 누락되므로, 결정론적 정규식으로 결합 토큰을 별도 캡처한다.
    날짜 패턴은 `_expand_date_tokens` 가 먼저 잡으므로 겹침은 dedup 단계에서 해소.
    """
    out: list[str] = []
    seen: set[str] = set()
    for m in _QUANTITY_PATTERN.finditer(text):
        num, unit = m.group(1), m.group(2)
        token = f"{num}{unit}"
        if token not in seen:
            seen.add(token)
            out.append(token)
    return out


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
    """인칭대명사 11개 시드 — origin='system' (v17: 이전 'rule')."""
    for alias in _FIRST_PERSON_ALIASES:
        conn.execute(
            "INSERT OR IGNORE INTO aliases (alias, node_id, origin) VALUES (?,?, 'system')",
            (alias, node_id),
        )


# ─── 날짜 분할 노드 → TIM.* 카테고리 매핑 ─────────────────

_TIM_CATEGORY_YEAR = "TIM.year"
_TIM_CATEGORY_MONTH = "TIM.month"
_TIM_CATEGORY_DAY = "TIM.day"
_TIM_CATEGORY_DATE = "TIM.date"

_RE_YEAR = re.compile(r"^\d{4}년$")
_RE_MONTH = re.compile(r"^\d{1,2}월$")
_RE_DAY = re.compile(r"^\d{1,2}일$")
_RE_DATE_FULL = re.compile(r"^\d{4}년\s*\d{1,2}월\s*\d{1,2}일$")


def _tim_category_for(name: str) -> Optional[str]:
    """날짜 노드 이름 → TIM.* 소분류. 해당 없으면 None."""
    if _RE_DATE_FULL.match(name):
        return _TIM_CATEGORY_DATE
    if _RE_YEAR.match(name):
        return _TIM_CATEGORY_YEAR
    if _RE_MONTH.match(name):
        return _TIM_CATEGORY_MONTH
    if _RE_DAY.match(name):
        return _TIM_CATEGORY_DAY
    return None


# ─── 메인 저장 로직 ───────────────────────────────────────

def _dedup_names(*name_groups: list[str]) -> list[str]:
    """순서 보존 중복 제거로 노드명 리스트 병합."""
    seen: set[str] = set()
    out: list[str] = []
    for group in name_groups:
        for name in group:
            if name and name not in seen:
                seen.add(name)
                out.append(name)
    return out


def _save_one_item(
    conn,
    item_text: str,
    category_path: Optional[str],
    post_id: int,
    position: int,
    post_context: str,
    use_llm: bool,
    result: SaveResult,
) -> None:
    """게시물 내 항목 하나 저장 (v17 Kiwi-first 파이프라인).

    흐름: ① save-pronoun (LLM) → ② 날짜 정규화 → ③ unresolved 감지 →
          ④ sentence INSERT → ⑤ Kiwi 형태소 분석 → ⑥ 날짜 분할 + 수량
          정규식 + TIM.* 카테고리 → ⑦ 노드 upsert + mentions + category.

    v18: ⑧ extract-state 전면 폐기 — 상태 레이어 없음 (sentences.status 컬럼 삭제).
    """
    # ① save-pronoun — 지시어·날짜 치환 (LLM, 실패 시 원문 유지)
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

    # ② ISO 날짜 → 한국어 정규화 (사용자 언급 공간 = 한국어)
    effective_text = _normalize_dates_to_korean(effective_text)

    # ③ 규칙 기반 지시어·모호 부사 감지 (LLM unresolved 와 병합)
    rule_unresolved = _detect_unresolved_tokens(effective_text)
    for tok in rule_unresolved:
        if tok not in unresolved_tokens:
            unresolved_tokens.append(tok)

    # ④ sentence 저장 (post_id + position)
    sid = _insert_sentence(conn, effective_text, post_id=post_id, position=position)
    result.sentence_ids.append(sid)

    # ④-1. 치환 실패 토큰을 unresolved_tokens 에 기록
    for token in unresolved_tokens:
        if _add_unresolved(conn, sid, token):
            result.unresolved_added.append((sid, token))

    # ④-2. 축 A — heading path 가 있으면 categories 재귀 upsert → sentence_categories 연결 (v20)
    if category_path:
        leaf_id = _upsert_category_path(
            conn, category_path, warnings=result.category_warnings
        )
        _add_sentence_category(conn, sid, leaf_id, origin="user")

    # ⑤ Kiwi 형태소 분석 — 저장 기본 경로 (LLM 사용 여부와 무관, 원칙 11)
    try:
        kiwi = kiwi_extract_for_save(effective_text)
    except Exception:
        kiwi = {"nouns": [], "lemmas": [], "negations": []}

    # ⑥ 날짜 분할 + 수량 정규식으로 Kiwi 가 놓치는 토큰 보강
    date_tokens = _expand_date_tokens(effective_text)
    quantity_tokens = _extract_quantity_tokens(effective_text)
    node_names = _dedup_names(
        kiwi["nouns"],
        kiwi["lemmas"],
        kiwi["negations"],
        date_tokens,
        quantity_tokens,
    )

    # ⑦ 노드 upsert + mentions + TIM.* 자동 태깅 (축 B 결정론 예외, v20)
    #    heading 경로는 ④-2 에서 sentence_categories 로 이미 반영 — 여기선 걷지 않음.
    for name in node_names:
        nid, is_new = _upsert_node(conn, name)
        if _add_mention(conn, nid, sid):
            result.mentions_added += 1
        # 축 B — TIM.* 자동 major_category (origin='system')
        tim_cat = _tim_category_for(name)
        if tim_cat:
            _add_node_major_category(conn, nid, tim_cat, origin="system")
        if is_new:
            result.nodes_added.append(name)
            result.node_ids_added.append(nid)
            if name == "나":
                _register_first_person_aliases(conn, nid)

    # v18: ⑧ extract-state · sentences.status 전면 폐기 (상태 레이어 제거).
    # 시점 해석은 인출 LLM 이 created_at 기반 최근성 판단으로 처리.


_VALID_MODES = ("chat", "markdown")


def _parse_for_chat(text: str) -> list[tuple[Optional[str], str]]:
    """chat 모드 파서 — heading 해석 안 함. 각 줄 (None, 줄) 로 분리.

    사용자가 `#야근` 처럼 해시태그 감각으로 입력해도 sentence 로 저장된다.
    빈 줄은 무시하고 각 줄은 strip 처리.
    """
    result: list[tuple[Optional[str], str]] = []
    for raw in text.split("\n"):
        line = raw.strip()
        if line:
            result.append((None, line))
    return result


def save(
    text: str,
    *,
    mode: str,
    db_path: str = DB_PATH,
    use_llm: bool = True,
    images: Optional[list[str]] = None,
) -> SaveResult:
    """텍스트를 게시물 단위로 저장. SaveResult 반환.

    mode (필수, keyword-only):
      - 'chat'     : 메신저 스타일 평문. `#` 을 해시태그로 해석 (heading 파싱 안 함).
      - 'markdown' : heading + list + 자유 문장 혼재. parse_markdown 으로 경로 상속.
      호출자가 UI 입력창 선택에 따라 필수로 지정. 기본값 없음.

    v19 흐름 (PLAN-003 M1):
    - 매 save() 호출 = posts 1건 INSERT (mode 를 input_mode 컬럼에 저장).
    - chat: 모든 줄 (None, line) → category_path 없이 일반 sentence.
    - markdown: 기존 parse_markdown (category_path 상속). M2 에서 kind 별 분기 도입.
    - 진입부 메타 필터 1회 (use_llm=True 시). 실패·MLX 다운 시 skip.
    - 각 항목은 _save_one_item() 이 Kiwi-first 파이프라인(①~⑦) 으로 처리.
    - 상태 레이어 없음 (v18: extract-state 폐기, sentences.status 컬럼 삭제).
    """
    if mode not in _VALID_MODES:
        raise ValueError(
            f"save(mode=): 'chat' 또는 'markdown' 필수, 받은 값: {mode!r}"
        )

    result = SaveResult()

    conn = get_connection(db_path)
    try:
        parsed = _parse_for_chat(text) if mode == "chat" else parse_markdown(text)
        if not parsed:
            conn.commit()
            return result

        # posts 1건 INSERT (원본 마크다운 + input_mode 보관)
        post_id = _insert_post(conn, text, input_mode=mode)
        result.post_id = post_id

        # 진입부 메타 필터 (v17) — LLM 사용 시만. 실패·MLX 다운 시 빈 집합(과포함 허용)
        item_texts = [item for _, item in parsed]
        meta_idx: set[int] = set()
        if use_llm:
            try:
                meta_idx = llm_meta_filter(item_texts)
            except Exception:
                meta_idx = set()

        # 항목별 저장
        for position, (category_path, item_text) in enumerate(parsed):
            if position in meta_idx:
                continue
            # 현재 항목을 제외한 나머지 게시물 문장들을 context 로
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
            "INSERT OR IGNORE INTO node_categories (node_id, major_category, origin) "
            "SELECT ?, major_category, origin FROM node_categories WHERE node_id=?",
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
            """INSERT OR IGNORE INTO node_categories
               (node_id, major_category, origin, created_at)
               SELECT ?, major_category, origin, created_at
               FROM node_categories WHERE node_id=?""",
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
    from .tokenizer import lemmatize_word

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
    # L3: Kiwi lemma 로 활용형 쌍을 오타 의심에서 제외하기 위한 캐시
    lemma_cache = {n["name"]: lemmatize_word(n["name"]) for n in nodes}

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
                # lemma 동일 쌍은 활용형 차이 — 오타로 보지 않는다.
                # 예: '배고파' vs '배고프' → 둘 다 lemma '배고프'.
                if lemma_cache[a["name"]] == lemma_cache[b["name"]]:
                    continue
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
            "UPDATE sentences SET text = ?, updated_at = datetime('now') WHERE id = ?",
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
    tests: list[tuple[str, str]] = [
        ("markdown", "# 병원.2026-04-18\n오늘 병원 다녀왔어\n세레콕시브 처방받았어\n허리디스크 L4-L5 진단"),
        ("markdown", "# 직장.더나은\n## 개발팀\n- 팀장 박지수\n- 프론트엔드 김민수"),
        ("chat",     "나 요즘 피곤해\n허리가 또 아픔"),
    ]
    for mode, text in tests:
        r = save(text, mode=mode, use_llm=False)
        print(f"\n[mode={mode}] 입력:\n{text}")
        print(f"  post_id: {r.post_id}")
        print(f"  sentence_ids: {r.sentence_ids}")
        print(f"  nodes_added: {r.nodes_added}")
        print(f"  mentions_added: {r.mentions_added}")
