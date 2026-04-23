"""v18 상태 레이어 제거 회귀 테스트 (PLAN-20260422-SYN-002 M3).

목적: `sentences.status` · `extract-state` 폐기 이후에도 시점 해석이
올바르게 인출 LLM 단계로 이관됐는지 확인.

검증 항목:
1. 상태 전이 연속 시나리오: 허리 아팠음 → 나았음 → 또 아픔
   - 답변에 3건 모두 시간 순으로 포함
   - 최근 사실(또 아픔) 이 마지막 줄 (프롬프트 규칙상 '최근 우선' 위치)
2. 과거 사건 영구 유지: 진단받은 사실이 오래 전이어도 조회 가능
3. chat UX 저장 지연: --no-llm 기준 저장 시간 참고값

LLM 의존 검증(retrieve-filter·chat) 은 MLX 서버 필요하므로 옵션 실행.
기본은 --no-llm 경로만으로 순서·포함 여부 검증.

실행: python3 -m tests.regression_v18_state_removed
"""
from __future__ import annotations
import os
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.save import save
from engine.retrieve import retrieve
from engine.db import DB_PATH, init_db


def _reset_db() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    init_db(DB_PATH)


def _set_created_at(sentence_id: int, iso_datetime: str) -> None:
    """sentence.created_at 강제 조작 (테스트 전용)."""
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute(
            "UPDATE sentences SET created_at=? WHERE id=?",
            (iso_datetime, sentence_id),
        )
        conn.commit()
    finally:
        conn.close()


def _passed(label: str, cond: bool, detail: str = "") -> bool:
    mark = "✓" if cond else "✗"
    tail = f"  ({detail})" if detail else ""
    print(f"  [{mark}] {label}{tail}")
    return cond


def case_state_transition() -> bool:
    """허리 아픔 → 나음 → 또 아픔 연속 시나리오."""
    print("=== CASE 1: 상태 전이 연속 시나리오 ===")
    _reset_db()

    t0 = time.perf_counter()
    r1 = save("허리 아팠음", mode="chat", use_llm=False)
    r2 = save("허리 나았음", mode="chat", use_llm=False)
    r3 = save("허리 또 아픔", mode="chat", use_llm=False)
    dt = time.perf_counter() - t0
    print(f"  (저장 3건, {dt:.3f}s)")

    _set_created_at(r1.sentence_ids[0], "2026-01-10 09:00:00")
    _set_created_at(r2.sentence_ids[0], "2026-03-15 09:00:00")
    _set_created_at(r3.sentence_ids[0], "2026-04-20 09:00:00")

    r = retrieve("허리 어때?", use_llm=False)
    lines = [ln for ln in r.answer.splitlines() if ln.strip()]

    ok = True
    ok &= _passed(
        "답변에 3건 모두 포함",
        all(any(key in ln for ln in lines) for key in ("허리 아팠음", "허리 나았음", "허리 또 아픔")),
        f"lines={lines}",
    )
    ok &= _passed(
        "시간 순 오름차순 (오래된 것 → 최근)",
        (any("허리 아팠음" in ln for ln in lines[:1])
         and any("허리 또 아픔" in ln for ln in lines[-1:])),
        f"첫 줄={lines[0] if lines else None}, 마지막 줄={lines[-1] if lines else None}",
    )
    ok &= _passed(
        "각 줄에 [YYYY-MM-DD] 날짜 힌트",
        all(ln.startswith("[") and "]" in ln for ln in lines),
    )
    return ok


def case_past_event_retention() -> bool:
    """과거 사건(진단) 이 시간 경과 후에도 조회 가능."""
    print("\n=== CASE 2: 과거 사건 영구 유지 ===")
    _reset_db()

    r = save("우울증 진단받았어", mode="chat", use_llm=False)
    _set_created_at(r.sentence_ids[0], "2025-09-01 09:00:00")  # 7개월 전

    r = save("요즘은 많이 나아졌어", mode="chat", use_llm=False)
    _set_created_at(r.sentence_ids[0], "2026-04-20 09:00:00")

    r = retrieve("우울증 기록 있어?", use_llm=False)

    ok = True
    ok &= _passed(
        "과거 진단 사실 인출됨",
        "우울증 진단받았어" in (r.answer or ""),
        f"answer={r.answer!r}",
    )
    return ok


def case_status_column_absent() -> bool:
    """sentences 테이블에 status 컬럼이 없는지 직접 확인."""
    print("\n=== CASE 3: 스키마 v18 확인 ===")
    _reset_db()
    conn = sqlite3.connect(DB_PATH)
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(sentences)").fetchall()]
    finally:
        conn.close()
    return _passed("sentences.status 컬럼 폐기", "status" not in cols, f"cols={cols}")


def case_save_latency() -> bool:
    """chat UX 저장 지연 (--no-llm 기준) 참고 측정."""
    print("\n=== CASE 4: 저장 지연 참고 측정 (--no-llm) ===")
    _reset_db()
    N = 5
    t0 = time.perf_counter()
    for i in range(N):
        save(f"테스트 메시지 {i} — 오늘 날씨 좋네", mode="chat", use_llm=False)
    avg = (time.perf_counter() - t0) / N
    print(f"  --no-llm 평균 저장 시간: {avg*1000:.1f}ms")
    return _passed(
        "--no-llm 저장 1건 ≤ 500ms (Kiwi 단독 경로)",
        avg <= 0.5,
        f"avg={avg*1000:.1f}ms",
    )


def main() -> int:
    cases = [
        case_state_transition,
        case_past_event_retention,
        case_status_column_absent,
        case_save_latency,
    ]
    results = [c() for c in cases]
    passed = sum(results)
    print(f"\n요약: {passed}/{len(results)} 통과")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
