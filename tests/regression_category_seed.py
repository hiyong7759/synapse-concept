"""PLAN-20260424-SYN-007 M0 — 인출 카테고리 시드 매칭 버그 재현 고정.

목적:
- PLAN-003 M3 dogfood 7 질문에서 `retrieve().start_categories` 가 100% 빈 배열이었던
  증상을 자동화 회귀 테스트로 잠금.
- 본 테스트는 **수정 전 실패 케이스를 잠금** — M3 (인출 경로 교체) 이후 assert 가
  뒤집혀 통과하는 것이 성공 기준 (최소 5/7 이상 `start_categories` 비지 않음).

현재 동작 (lock-in 대상, PLAN-007 M1 이후):
- `_match_start_categories` 가 `WHERE name = ?` exact match. 짧은 자연어 키워드
  (`연차`·`휴가`·`징계`) 가 긴 heading 이름과 매칭 실패
- M1 에서 `normalize_hash_syntax` 규칙 3 폐기로 이제 heading 줄 전체가
  categories 에 저장 (예: `제6장 휴일 및 휴가`, `제55조 (해고의 제한)`).
  그럼에도 exact match 한계로 여전히 매칭 불가
- 의미 토큰의 카테고리 매핑 (M2 `node_category_mentions`) 전까지 증상 지속
- 결과: 7 질문 전부 `start_categories=[]`

가정:
- `use_llm=False` — MLX 서버 독립 재현. 버그가 LLM 독립(exact match 한계)
  이므로 LLM off 에서도 증상 재현됨
- 저장 원본: `archive/docs/(주)더나은_취업규칙_개정(안)_20250430.md`
  (공백 포맷 원본 그대로 — PLAN-003 M3 dogfood 와 동일 입력)

검증:
1. 저장 정상성 — post_id 생성
2. M1 효과 — categories 에 공백 포함 긴 heading 이 저장됨
   (`제6장 휴일 및 휴가` 등 — 규칙 3 폐기로 본문 분리 안 됨)
3. 7 질문 retrieve → `start_categories == []` lock-in (현재 증상)
4. `start_nodes` 는 최소 1 건 이상 질문에서 채워짐 (노드 매칭은 생존)

실행: python3 -m tests.regression_category_seed
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


DOGFOOD_QUESTIONS = [
    "연차 휴가 며칠이야",
    "징계 사유 뭐 있어",
    "수습기간 얼마야",
    "회사 이름 뭐야",
    "임산부 보호",
    "야근 어땠지",
    "피곤",
]


def _passed(label: str, cond: bool, detail: str = "") -> bool:
    mark = "✓" if cond else "✗"
    tail = f"  ({detail})" if detail else ""
    print(f"  [{mark}] {label}{tail}")
    return cond


def _fresh_db_dir() -> str:
    d = tempfile.mkdtemp(prefix="synapse-plan007-m0-")
    os.environ["SYNAPSE_DATA_DIR"] = d
    import importlib
    import engine.db, engine.save, engine.retrieve
    importlib.reload(engine.db)
    importlib.reload(engine.save)
    importlib.reload(engine.retrieve)
    return d


def _load_chwi_gyuchik_text() -> str:
    path = ROOT / "archive" / "docs" / "(주)더나은_취업규칙_개정(안)_20250430.md"
    if not path.exists():
        raise FileNotFoundError(f"원본 없음: {path}")
    return path.read_text(encoding="utf-8")


def case_seed_reproduction() -> bool:
    print("=== CASE: PLAN-007 M0 — 현재 main 버그 재현 고정 ===")
    from engine import save as save_mod
    from engine import retrieve as retrieve_mod
    from engine.db import get_connection, DB_PATH

    db_dir = _fresh_db_dir()
    print(f"  [i] tempfile DB dir: {db_dir}")

    text = _load_chwi_gyuchik_text()
    print(f"  [i] 취업규칙 원본 {len(text)} chars 로드 (공백 포맷)")

    sr = save_mod.save(text, mode="markdown", use_llm=False, db_path=DB_PATH)
    print(f"  [i] save: post_id={sr.post_id}")

    ok = True
    ok &= _passed("저장 정상 — post_id 생성", sr.post_id is not None, f"post_id={sr.post_id}")

    # 1. categories 에 저장된 내용 진단 — heading 번호 조각만 존재
    conn = get_connection(DB_PATH)
    try:
        cat_names = [r["name"] for r in conn.execute("SELECT name FROM categories").fetchall()]
    finally:
        conn.close()

    has_chapter_6_full = "제6장 휴일 및 휴가" in cat_names
    has_article_55_full = any(n.startswith("제55조") and "(" in n for n in cat_names)
    has_any_spaced_name = any(" " in n for n in cat_names)
    semantic_tokens_present = any(n in cat_names for n in ("휴가", "연차", "징계", "휴일", "수습기간"))

    ok &= _passed(
        "M1 효과 — categories 에 공백 포함 긴 heading 저장됨",
        has_any_spaced_name,
        f"spaced_count={sum(1 for n in cat_names if ' ' in n)}",
    )
    ok &= _passed(
        "categories 에 '제6장 휴일 및 휴가' 전체 저장 (규칙 3 폐기 검증)",
        has_chapter_6_full,
        f"sample={[n for n in cat_names if '제6장' in n][:2]}",
    )
    ok &= _passed(
        "categories 에 '제55조 (…)' 괄호 포함 전체 저장",
        has_article_55_full,
        f"sample={[n for n in cat_names if '제55조' in n][:2]}",
    )
    ok &= _passed(
        "categories 에 의미 토큰 단독은 아직 없음 (M2 node_category_mentions 전까지)",
        not semantic_tokens_present,
        "휴가/연차/징계/휴일/수습기간 전부 단독으로는 categories.name 에 없음",
    )

    # 2. 7 질문 retrieve → start_categories lock-in
    empty_count = 0
    nonempty_nodes_count = 0
    per_q_summary: list[str] = []
    for q in DOGFOOD_QUESTIONS:
        r = retrieve_mod.retrieve(q, db_path=DB_PATH, use_llm=False)
        if r.start_categories == []:
            empty_count += 1
        if r.start_nodes:
            nonempty_nodes_count += 1
        per_q_summary.append(
            f"    '{q}' → nodes={len(r.start_nodes)} cats={r.start_categories}"
        )

    print("  [i] 질문별 결과:")
    for s in per_q_summary:
        print(s)

    ok &= _passed(
        "7 질문 전부 start_categories=[] lock-in",
        empty_count == len(DOGFOOD_QUESTIONS),
        f"empty={empty_count}/{len(DOGFOOD_QUESTIONS)}",
    )
    ok &= _passed(
        "start_nodes 는 최소 1 건 이상 질문에서 채워짐 (노드 매칭 생존)",
        nonempty_nodes_count >= 1,
        f"nonempty_nodes={nonempty_nodes_count}/{len(DOGFOOD_QUESTIONS)}",
    )
    return ok


def main() -> int:
    cases = [case_seed_reproduction]
    results = [c() for c in cases]
    passed = sum(results)
    print(f"\n요약: {passed}/{len(results)} 통과")
    print("\n📌 PLAN-007 성공 기준 (M3 이후):")
    print("  - 본 테스트의 '7 질문 전부 start_categories=[]' assert 가 뒤집혀 실패")
    print("  - 최소 5/7 질문에서 start_categories 가 의미 있는 서브트리 반환")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
