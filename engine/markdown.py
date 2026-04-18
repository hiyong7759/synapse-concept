"""마크다운 파서 — heading 경로 + 항목 분리 (v12).

입력 텍스트를 (category_path, item_text) 쌍 리스트로 변환.

분리 규칙 — 사용자가 명시한 경계만 사용:
- heading(#): 카테고리 경로 설정. 섹션 경계.
- 리스트 항목(-, *, 1.): 각각 독립된 item (한 줄 sentence).
- 일반 텍스트 줄: 한 줄(\\n 단위) = 한 sentence. 마침표·쉼표는 경계 아님.
- 빈 줄: 무시.

heading 없으면 category_path는 모두 None.
"""

from __future__ import annotations
import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_LIST_UNORDERED_RE = re.compile(r"^[-*]\s+(.+)$")
_LIST_ORDERED_RE = re.compile(r"^\d+\.\s+(.+)$")


def parse_markdown(text: str) -> list[tuple[str | None, str]]:
    """마크다운 텍스트를 (경로, 항목) 리스트로 파싱.

    v12:
    - heading 없어도 개행(\\n) 단위로 분리 → 각 줄이 별개 sentence.
    - 연속된 일반 텍스트를 하나로 합치던 이전 동작 폐기 (사용자가 엔터 친 경계 그대로 존중).

    Returns:
        [(category_path | None, item_text), ...]
    """
    lines = text.split("\n")

    result: list[tuple[str | None, str]] = []
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
            continue

        # 리스트 항목 매칭
        um = _LIST_UNORDERED_RE.match(line)
        om = _LIST_ORDERED_RE.match(line)
        if um or om:
            item_text = um.group(1) if um else line
            result.append((current_path(), item_text.strip()))
            continue

        # 일반 텍스트 줄 — 각 줄이 독립 sentence
        result.append((current_path(), line))

    return result


def has_heading(text: str) -> bool:
    """텍스트에 heading이 하나라도 있는지 빠른 검사.
    Phase 2에서 평문(heading 없음) → structure-suggest 게이트 분기에 사용.
    """
    for raw_line in text.split("\n"):
        if _HEADING_RE.match(raw_line.strip()):
            return True
    return False
