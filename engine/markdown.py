"""마크다운 파서 — heading 경로 + kind 별 항목 분리 (v19 — PLAN-003 M2).

입력 텍스트를 (category_path, kind, text) 튜플 스트림으로 변환.

kind 체계:
- 'heading'   : `#`~`######` 로 시작하는 섹션 제목. sentence INSERT 대상 아님
                (save.py 가 카테고리 path 만 등록). text 는 heading 본문 (prefix 제외).
- 'key_value' : `- key:: value` (Obsidian Dataview 스타일). sentence 에 원문
                `"key:: value"` 그대로 저장. save-pronoun / 메타 필터 skip.
- 'list'      : `-`, `*`, `1.` 로 시작하는 일반 리스트 항목. 자유 문장과 동일 취급.
- 'free'      : 나머지 일반 텍스트 줄. 각 줄(\\n 단위) = 한 sentence.
                빈 줄은 무시, strip 후 저장.

heading 없으면 category_path 는 모두 None.

v12 → v19 변경점:
- 반환 튜플 확장: (path, text) → (path, kind, text). kind 추가.
- heading 을 **결과 리스트에 포함** (이전엔 path_stack 만 갱신하고 제외). save.py
  가 kind='heading' 에서 sentence INSERT 를 skip 하도록 일원화.
- `- key:: value` 파서 신설 (정규식 `^-\\s+(.+?)\\s*::\\s+(.+)$`).
"""

from __future__ import annotations
import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
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

            # 점 구분 경로: # 더나은.개발부.개발팀
            if "." in name:
                parts = name.split(".")
                path_stack.clear()
                for i, part in enumerate(parts):
                    path_stack.append((i + 1, part.strip()))
            else:
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


def has_heading(text: str) -> bool:
    """텍스트에 heading이 하나라도 있는지 빠른 검사.
    v17 에서 structure-suggest 가 폐기되어 저장 파이프라인에선 호출하지 않는다.
    외부(UI·API·도구) 에서 마크다운 여부 판단이 필요할 때만 유지된 헬퍼.
    """
    for raw_line in text.split("\n"):
        if _HEADING_RE.match(raw_line.strip()):
            return True
    return False
