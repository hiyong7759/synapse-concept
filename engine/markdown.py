"""마크다운 파서 — heading 경로 + kind 별 항목 분리 (v20 — PLAN-005 M1).

입력 텍스트를 (category_path, kind, text) 튜플 스트림으로 변환.

kind 체계:
- 'heading'   : `#` 으로 시작하는 섹션 제목 (개수 제한 없음). sentence INSERT 대상 아님
                (save.py 가 카테고리 path 만 등록). text 는 heading 본문 (prefix 제외).
- 'key_value' : `- key:: value` (Obsidian Dataview 스타일). sentence 에 원문
                `"key:: value"` 그대로 저장. save-pronoun / 메타 필터 skip.
- 'list'      : `-`, `*`, `1.` 로 시작하는 일반 리스트 항목. 자유 문장과 동일 취급.
- 'free'      : 나머지 일반 텍스트 줄. 각 줄(\\n 단위) = 한 sentence.
                빈 줄은 무시, strip 후 저장.

heading 없으면 category_path 는 모두 None.

v20 변경점 (PLAN-005 M1):
- `normalize_hash_syntax(text)` 신설 — `#분류` → `# 분류`, 두 번째 공백 → 개행.
  save() 진입부에서 mode 무관하게 1회 호출, posts.markdown 에 정규화 후 저장.
- heading 자연 상속 — 점 포함 heading 의 path_stack.clear() 분기 제거. 점 포함
  이름도 한 깊이에 통째로 push 하고, _upsert_category_path 가 점 split 해서
  다단 categories 저장. (`# A` + `## B.C` → `A.B.C`)

v12 → v19 변경점:
- 반환 튜플 확장: (path, text) → (path, kind, text). kind 추가.
- heading 을 **결과 리스트에 포함** (이전엔 path_stack 만 갱신하고 제외). save.py
  가 kind='heading' 에서 sentence INSERT 를 skip 하도록 일원화.
- `- key:: value` 파서 신설 (정규식 `^-\\s+(.+?)\\s*::\\s+(.+)$`).
"""

from __future__ import annotations
import re

_HEADING_RE = re.compile(r"^(#{1,})\s+(.+)$")
_LIST_UNORDERED_RE = re.compile(r"^[-*]\s+(.+)$")
_LIST_ORDERED_RE = re.compile(r"^\d+\.\s+(.+)$")
_KEY_VALUE_RE = re.compile(r"^-\s+(.+?)\s*::\s+(.+)$")


def parse_markdown(text: str) -> list[tuple[str | None, str, str]]:
    """마크다운 텍스트를 (경로, kind, 항목) 리스트로 파싱.

    Returns:
        [(category_path | None, kind, item_text), ...]
        kind ∈ {'heading', 'key_value', 'list', 'free'}.
    """
    lines = text.split("\n")

    result: list[tuple[str | None, str, str]] = []
    # heading 스택: [(depth, name), ...] — 현재 경로 추적
    path_stack: list[tuple[int, str]] = []

    def current_path() -> str | None:
        if not path_stack:
            return None
        return ".".join(name for _, name in path_stack)

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # heading 매칭
        hm = _HEADING_RE.match(line)
        if hm:
            depth = len(hm.group(1))
            name = hm.group(2).strip()

            # v20 (PLAN-005 M1): 자연 상속 — 점 포함 heading 도 일반 heading 과 동일하게
            # depth 기준 pop·push. 점 분리는 _upsert_category_path 가 담당.
            # 같은 깊이 또는 상위로 돌아가면 스택 정리
            while path_stack and path_stack[-1][0] >= depth:
                path_stack.pop()
            path_stack.append((depth, name))
            # heading 자체도 결과에 포함 (save.py 가 path 등록만 하고 sentence INSERT skip)
            result.append((current_path(), "heading", name))
            continue

        # key-value: `- key:: value` (일반 list 보다 먼저 판정)
        kvm = _KEY_VALUE_RE.match(line)
        if kvm:
            key = kvm.group(1).strip()
            value = kvm.group(2).strip()
            if key and value:
                # 원문 형태 보존 — sentence 에 "key:: value" 그대로 저장
                result.append((current_path(), "key_value", f"{key}:: {value}"))
                continue
            # key 나 value 가 비면 일반 list 로 강등 (_KEY_VALUE_RE 가 비어있으면 매칭 안 되므로 실질적으론 도달 안 함)

        # 리스트 항목 매칭 (순서 무관)
        um = _LIST_UNORDERED_RE.match(line)
        om = _LIST_ORDERED_RE.match(line)
        if um or om:
            item_text = um.group(1) if um else line
            result.append((current_path(), "list", item_text.strip()))
            continue

        # 일반 텍스트 줄 — 각 줄이 독립 sentence
        result.append((current_path(), "free", line))

    return result


def normalize_hash_syntax(text: str) -> str:
    """`#` 분류 문법을 마크다운 표준 형태로 정규화 (DB 저장 직전 1회 호출).

    규칙 (PLAN-007 M1):
    1. **줄 첫 문자가 `#` 인 줄만** 정규화 대상. 앞에 공백 있으면 평문.
    2. `#분류` → `# 분류` — `#` 뒤 공백이 없으면 하나 삽입.
    3. **분류명 비면 정규화 안 함** (`#`, `# `, `#\\n본문` 등). 평문 처리.
    4. **첫 `#` 만 분류** — 줄 안의 두 번째 이후 `#` 은 평문.

    heading 줄 **전체가 분류명** (표준 마크다운). 공백·괄호·특수문자 허용.
    분류명은 사용자 책임 — 시스템은 자동 변환·구두점 제거 안 함.

    ※ 이전 PLAN-005 M1 의 "분류명 뒤 첫 공백 → 개행 분리" 규칙은
    PLAN-007 M1 에서 폐기됨 (표준 마크다운 heading 복귀). chat 모드 한 줄
    입력 편의는 LLM 변환 핫키로 대체 예정 (본 PLAN 범위 밖).
    """
    out_lines: list[str] = []
    for line in text.split("\n"):
        # 규칙 1: 줄 첫 문자가 `#` 이 아니면 평문
        if not line.startswith("#"):
            out_lines.append(line)
            continue

        # `#` 개수 카운트 (depth)
        i = 0
        while i < len(line) and line[i] == "#":
            i += 1
        hashes = line[:i]
        rest = line[i:]

        # 규칙 3: rest 가 비면 분류명 없음 → 평문
        if not rest:
            out_lines.append(line)
            continue

        # `#` 뒤 공백이 있으면 떼고, 없으면 그대로
        if rest[0] == " ":
            content = rest[1:]
        else:
            content = rest

        # 규칙 3: 분류명 자체가 비면 평문
        if not content.strip():
            out_lines.append(line)
            continue

        # heading 줄 전체가 분류명 (표준 마크다운).
        out_lines.append(f"{hashes} {content}")

    return "\n".join(out_lines)


def has_heading(text: str) -> bool:
    """텍스트에 heading이 하나라도 있는지 빠른 검사.
    v17 에서 structure-suggest 가 폐기되어 저장 파이프라인에선 호출하지 않는다.
    외부(UI·API·도구) 에서 마크다운 여부 판단이 필요할 때만 유지된 헬퍼.
    """
    for raw_line in text.split("\n"):
        if _HEADING_RE.match(raw_line.strip()):
            return True
    return False
