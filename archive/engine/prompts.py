"""시스템 프롬프트 로더.

각 태스크의 시스템 프롬프트를 docs/{TASK}_SYSTEMPROMPT.md 에서 읽어 캐싱한다.
- 태스크 이름 → 파일명 매핑: lower_case_with_dashes → UPPER_SNAKE_CASE
  예) "retrieve-filter" → "RETRIEVE_FILTER_SYSTEMPROMPT.md"
- 파일 위치: 이 모듈 기준 ../docs/
"""
from __future__ import annotations
import os
from functools import lru_cache

_DOCS_DIR = os.path.join(os.path.dirname(__file__), "..", "docs")


def _filename(task: str) -> str:
    return task.upper().replace("-", "_") + "_SYSTEMPROMPT.md"


@lru_cache(maxsize=None)
def load_prompt(task: str) -> str:
    """태스크명으로 시스템 프롬프트를 로드. 파일 없으면 빈 문자열."""
    path = os.path.join(_DOCS_DIR, _filename(task))
    if not os.path.exists(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read().strip()
