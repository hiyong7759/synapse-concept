"""마크다운 파서 — heading 경로 + 항목 분리.

입력 텍스트를 (category_path, item_text) 쌍 리스트로 변환.
heading이 없으면 평문으로 판단하여 [(None, 원본)] 반환.
"""

from __future__ import annotations
import re

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_LIST_UNORDERED_RE = re.compile(r"^[-*]\s+(.+)$")
_LIST_ORDERED_RE = re.compile(r"^\d+\.\s+(.+)$")


def parse_markdown(text: str) -> list[tuple[str | None, str]]:
    """마크다운 텍스트를 (경로, 항목) 리스트로 파싱.

    - heading(#)은 경로를 설정. 깊이 제한 없음.
    - 리스트 항목(-, 1.)은 개별 추출 대상.
    - heading 없으면 [(None, 원본텍스트)] 반환.
    - ``# 더나은.개발팀`` 점 구분은 한 줄 경로로 처리.

    Returns:
        [(category_path | None, item_text), ...]
    """
    lines = text.split("\n")

    # heading 존재 여부 먼저 확인
    has_heading = any(_HEADING_RE.match(line.strip()) for line in lines)
    if not has_heading:
        return [(None, text)]

    result: list[tuple[str | None, str]] = []
    # heading 스택: [(depth, name), ...] — 현재 경로 추적
    path_stack: list[tuple[int, str]] = []
    # heading 아래 리스트 항목이 없는 경우 평문 수집
    pending_text: list[str] = []

    def current_path() -> str | None:
        if not path_stack:
            return None
        return ".".join(name for _, name in path_stack)

    def flush_pending():
        if pending_text:
            text_block = " ".join(pending_text).strip()
            if text_block:
                result.append((current_path(), text_block))
            pending_text.clear()

    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue

        # heading 매칭
        hm = _HEADING_RE.match(line)
        if hm:
            flush_pending()
            depth = len(hm.group(1))  # # = 1, ## = 2, ...
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
            flush_pending()
            item_text = um.group(1) if um else line  # 순서 리스트는 번호 포함
            result.append((current_path(), item_text.strip()))
            continue

        # 일반 텍스트 (heading 아래 리스트가 아닌 본문)
        pending_text.append(line)

    flush_pending()
    return result
