"""v20 chat 분류 입력 회귀 테스트 (PLAN-20260423-SYN-005 M2 + PLAN-20260424-SYN-007 M1 반영).

목적:
- normalize_hash_syntax 정규화 경계 케이스 검증
- heading 자연 상속 (점 포함 heading 의 path_stack.clear 제거 효과)
- 실데이터 dogfood 시뮬레이션 (#건강, #건강.허리, 다층 heading 등)

PLAN-005 M0 결정 (2026-04-24):
- 결정 1: 첫 # 만 분류, 두 번째 이후 # 은 평문
- 결정 2: normalize_hash_syntax(text: str) -> str, engine/markdown.py 위치
- 결정 3: DB 에는 정규화된 형태만 엄격히 저장
- 결정 4: 앞 공백·분류명 없는 # 평문 처리, 모호한 점 그대로, depth 건너뛰기 자연 상속

PLAN-007 M1 업데이트 (2026-04-24):
- **규칙 3 "분류명 뒤 첫 공백 → 개행 분리" 폐기** (표준 마크다운 heading 복귀)
- heading 줄 전체가 분류명 (공백·괄호·특수문자 허용)
- chat 모드 한 줄 편의는 LLM 변환 핫키로 대체 예정 (본 PLAN 범위 밖)
- CASE E (chat/markdown 단순 등가성) 은 규칙 3 전제였으므로 제거. 핫키 도입 후 재검토

실행: python3 tests/regression_v20_chat_category.py
"""
from __future__ import annotations
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _passed(label: str, cond: bool, detail: str = "") -> bool:
    mark = "✓" if cond else "✗"
    tail = f"  ({detail})" if detail else ""
    print(f"  [{mark}] {label}{tail}")
    return cond


def _fresh_db_dir() -> str:
    d = tempfile.mkdtemp(prefix="synapse-v20-")
    os.environ["SYNAPSE_DATA_DIR"] = d
    import importlib
    import engine.db
    import engine.save
    importlib.reload(engine.db)
    importlib.reload(engine.save)
    return d


# ─── A. 정규화 — `#` 위치/공백 (15개) ─────────────────────

def case_normalization_basic() -> bool:
    print("=== CASE A: normalize_hash_syntax — 기본 정규화 (15개) ===")
    from engine.markdown import normalize_hash_syntax

    cases: list[tuple[str, str]] = [
        # 1~4: PLAN 본문 표 핵심 (M1: 규칙 3 폐기로 한 줄 전체가 heading)
        ("#건강", "# 건강"),
        ("# 건강", "# 건강"),
        ("#건강 허리 아픔", "# 건강 허리 아픔"),
        ("# 건강 허리 아픔", "# 건강 허리 아픔"),
        # 5~8: depth 1·3·7·10
        ("##허리", "## 허리"),
        ("### 깊은 분류", "### 깊은 분류"),
        ("#######일곱개", "####### 일곱개"),
        ("##########열개", "########## 열개"),
        # 9~12: 줄 머리 게이트
        ("오늘 #야근 했다", "오늘 #야근 했다"),
        ("텍스트\n#건강", "텍스트\n# 건강"),
        ("\n\n#건강", "\n\n# 건강"),
        ("   #건강", "   #건강"),
        # 13~15: 분류명 없음
        ("#", "#"),
        ("# ", "# "),
        ("#\n본문", "#\n본문"),
    ]
    ok = True
    for inp, expected in cases:
        got = normalize_hash_syntax(inp)
        ok &= _passed(f"{inp!r:32} → {got!r}", got == expected, f"expected={expected!r}")
    return ok


# ─── B. 분류명 안의 특수문자 (8개) ────────────────────────

def case_normalization_special_chars() -> bool:
    print("\n=== CASE B: 분류명 특수문자 — 사용자 책임 원칙 (8개) ===")
    from engine.markdown import normalize_hash_syntax

    cases: list[tuple[str, str]] = [
        # 16~19: 점 / 언더스코어 / 구두점 (M1: 규칙 3 폐기로 한 줄 전체가 heading)
        ("#건강.허리 오늘 아픔", "# 건강.허리 오늘 아픔"),
        ("#제55조_연차휴가", "# 제55조_연차휴가"),
        ("#건강?", "# 건강?"),
        ("#건강!", "# 건강!"),
        # 20: depth 10 (점 계층)
        (
            "#A.B.C.D.E.F.G.H.I.J 본문",
            "# A.B.C.D.E.F.G.H.I.J 본문",
        ),
        # 21~23: 모호한 점 (사용자 책임 — 그대로 저장)
        ("#A..B", "# A..B"),
        ("#.시작점", "# .시작점"),
        ("#건강.", "# 건강."),
    ]
    ok = True
    for inp, expected in cases:
        got = normalize_hash_syntax(inp)
        ok &= _passed(f"{inp!r:36} → {got!r}", got == expected, f"expected={expected!r}")
    return ok


# ─── C. 다중 `#` 한 줄 — 첫 # 만 분류 (4개) ────────────────

def case_normalization_multiple_hash() -> bool:
    print("\n=== CASE C: 다중 # 한 줄 — 첫 # 만 분류, 나머지는 평문 (4개) ===")
    from engine.markdown import normalize_hash_syntax

    # M1 (PLAN-007): 규칙 3 폐기로 두 번째 이후 # 은 같은 줄에 평문으로 남음.
    # heading 이름 안에 `#` 문자가 포함되는 형태가 되지만, 이는 사용자 책임
    # (분류명 뒤 공백을 쓰는 건 LLM 변환 핫키 도입 전까지 비권장).
    cases: list[tuple[str, str]] = [
        ("#건강 #허리 오늘 아픔", "# 건강 #허리 오늘 아픔"),
        ("#A #B #C 본문", "# A #B #C 본문"),
        ("##A #B 본문", "## A #B 본문"),
        ("#A.B #C.D 본문", "# A.B #C.D 본문"),
    ]
    ok = True
    for inp, expected in cases:
        got = normalize_hash_syntax(inp)
        ok &= _passed(f"{inp!r:36} → {got!r}", got == expected, f"expected={expected!r}")
    return ok


# ─── D. heading 자연 상속 — path_stack.clear 제거 효과 (8개) ──

def case_heading_natural_inheritance() -> bool:
    print("\n=== CASE D: heading 자연 상속 — 점 포함 heading 도 부모 보존 (8개) ===")
    from engine.markdown import parse_markdown

    cases: list[tuple[str, str, str]] = [
        # (입력, 마지막 heading 의 category_path 기대값, 라벨)
        ("# 분류1\n## 분류2.분류3", "분류1.분류2.분류3", "28: # A + ## B.C → A.B.C"),
        ("# A\n## B.C\n### D", "A.B.C.D", "29: # A + ## B.C + ### D → A.B.C.D"),
        ("# 분류1.분류2\n## 분류3", "분류1.분류2.분류3", "30: # A.B + ## C → A.B.C"),
        ("# A\n# B.C", "B.C", "31: # A + # B.C (형제) → B.C"),
        ("# A\n## B\n# C.D", "C.D", "32: # A + ## B + # C.D (depth 1 복귀) → C.D"),
        ("# A\n### C", "A.C", "33: # A + ### C (depth 건너뜀) → A.C"),
        ("# A.B.C\n## D.E", "A.B.C.D.E", "34: # A.B.C + ## D.E → A.B.C.D.E"),
        (
            "# A\n## B\n### C\n#### D\n##### E\n###### F\n####### G\n######## H\n######### I\n########## J",
            "A.B.C.D.E.F.G.H.I.J",
            "35: depth 10 → A.B.C.D.E.F.G.H.I.J",
        ),
    ]
    ok = True
    for inp, expected_path, label in cases:
        items = parse_markdown(inp)
        # 마지막 heading 의 path
        last_heading = next(
            (path for path, kind, _ in reversed(items) if kind == "heading"),
            None,
        )
        ok &= _passed(label, last_heading == expected_path, f"got={last_heading!r}, expected={expected_path!r}")
    return ok


# ─── E. (폐기 — PLAN-007 M1) ────────────────────────────
# chat / markdown 단순 등가성 테스트는 "첫 공백 = 개행" 규칙(PLAN-005 M1) 을
# 전제로 설계됐음. PLAN-007 M1 에서 해당 규칙이 폐기되고 표준 마크다운 heading
# 으로 복귀하면서 chat 한 줄 입력과 markdown 멀티라인 입력은 **의도적으로
# 다르게** 처리됨. chat 편의는 LLM 변환 핫키(별도 작업) 가 담당.
# 핫키 도입 후 "의미 등가성" 기준으로 테스트를 재작성할 것.


# ─── F. 회귀 방지 (4개) ────────────────────────────────

def case_robustness() -> bool:
    print("\n=== CASE F: 회귀 방지 — 깨지지 않아야 함 (4개) ===")
    from engine.markdown import normalize_hash_syntax, parse_markdown

    ok = True
    # 40: 빈 문자열
    ok &= _passed("40: 빈 문자열", normalize_hash_syntax("") == "", f"got={normalize_hash_syntax('')!r}")
    # 41: 공백만
    ok &= _passed("41: 공백만 ('   ')", normalize_hash_syntax("   ") == "   ", f"got={normalize_hash_syntax('   ')!r}")
    # 42: # 없는 일반 텍스트
    txt = "오늘 점심 라면 먹었다"
    ok &= _passed("42: # 없는 평문 보존", normalize_hash_syntax(txt) == txt, f"got={normalize_hash_syntax(txt)!r}")
    # 43: 여러 줄 평문 (heading 없음)
    multi = "어제 회의\n오늘 점검\n내일 발표"
    ok &= _passed(
        "43: 여러 줄 평문 (heading 없음) 보존",
        normalize_hash_syntax(multi) == multi,
        f"got={normalize_hash_syntax(multi)!r}",
    )
    return ok


# ─── G. 실데이터 dogfood 시뮬레이션 ─────────────────────

def case_dogfood_simulation() -> bool:
    """실제 사용 패턴 시뮬레이션.

    PLAN-007 M1 업데이트: chat 한 줄 입력 (시나리오 2, 3) 케이스는 제거됨.
    규칙 3 폐기로 이제 `#분류 본문` 한 줄은 `분류 본문` 전체가 heading 으로
    저장됨. chat 한 줄 편의는 LLM 변환 핫키 (별도 작업) 도입 후 재검증.
    """
    print("\n=== CASE G: dogfood 시뮬레이션 — 실입력 패턴 ===")
    _fresh_db_dir()
    from engine.save import save
    from engine.db import DB_PATH

    ok = True

    # 시나리오 1: chat 빠른 메모 — 분류만
    r1 = save("#건강", mode="chat", use_llm=False)

    # 시나리오 4: markdown 다층 heading
    r4 = save(
        "# 직장.더나은\n## 개발팀\n- 팀장 박지수\n- 프론트 김민수\n팀 회식 연기됨",
        mode="markdown",
        use_llm=False,
    )

    # 시나리오 5: markdown 자연 상속 (점 포함 heading)
    r5 = save(
        "# 건강\n## 허리.디스크\n- 진단 L4-L5\n오늘부터 약 복용",
        mode="markdown",
        use_llm=False,
    )

    conn = sqlite3.connect(DB_PATH)
    try:
        # 시나리오 1: posts.markdown == '# 건강' (정규화)
        md1 = conn.execute("SELECT markdown FROM posts WHERE id=?", (r1.post_id,)).fetchone()[0]
        ok &= _passed(
            "시나리오 1: '#건강' → posts.markdown 정규화 후 '# 건강'",
            md1 == "# 건강",
            f"posts.markdown={md1!r}",
        )

        # 시나리오 4: markdown 다층 — '직장' '더나은' '개발팀' 카테고리 모두 생성, sentences 4건
        sents4 = [
            r[0] for r in conn.execute(
                "SELECT text FROM sentences WHERE post_id=? ORDER BY position", (r4.post_id,)
            ).fetchall()
        ]
        rows4 = conn.execute(
            "SELECT name FROM categories WHERE name IN ('직장','더나은','개발팀')"
        ).fetchall()
        cat_names4 = sorted(r[0] for r in rows4)
        ok &= _passed(
            "시나리오 4: markdown 다층 heading — 카테고리 3개 + sentences (list+free)",
            cat_names4 == ["개발팀", "더나은", "직장"] and len(sents4) >= 3,
            f"cats={cat_names4}, sents={sents4}",
        )

        # 시나리오 5: 자연 상속 — '건강' '허리' '디스크' 모두 등록, '오늘부터 약 복용' 은 허리.디스크에 연결
        rows5 = conn.execute(
            "SELECT name FROM categories WHERE name IN ('건강','허리','디스크')"
        ).fetchall()
        cat_names5 = sorted(r[0] for r in rows5)
        cats5 = [
            r[0] for r in conn.execute(
                """SELECT DISTINCT c.name FROM sentence_categories sc
                   JOIN categories c ON c.id = sc.category_id
                   JOIN sentences s ON s.id = sc.sentence_id
                   WHERE s.post_id = ?""",
                (r5.post_id,),
            ).fetchall()
        ]
        ok &= _passed(
            "시나리오 5: markdown '# 건강 + ## 허리.디스크' → 3 카테고리 자연 상속",
            cat_names5 == ["건강", "디스크", "허리"] and "디스크" in cats5,
            f"cats_table={cat_names5}, sentence_cats={cats5}",
        )
    finally:
        conn.close()

    return ok


# ─── 메인 ─────────────────────────────────────────────

def main() -> int:
    cases = [
        case_normalization_basic,        # 15
        case_normalization_special_chars,  # 8
        case_normalization_multiple_hash,  # 4
        case_heading_natural_inheritance,  # 8
        # case_chat_markdown_equivalence,  # PLAN-007 M1 폐기 (규칙 3 전제)
        case_robustness,                   # 4
        case_dogfood_simulation,           # dogfood
    ]
    results = [c() for c in cases]
    passed = sum(results)
    print(f"\n요약: {passed}/{len(results)} 그룹 통과")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
