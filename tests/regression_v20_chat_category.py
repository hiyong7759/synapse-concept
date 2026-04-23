"""v20 chat 분류 입력 회귀 테스트 (PLAN-20260423-SYN-005 M2).

목적:
- normalize_hash_syntax 정규화 경계 케이스 43개 검증
- heading 자연 상속 (점 포함 heading 의 path_stack.clear 제거 효과)
- chat / markdown 동등성 (같은 의도 입력 = 같은 DB 상태)
- 실데이터 dogfood 시뮬레이션 (#건강, #건강.허리, #건강 본문, 다층 heading)

PLAN-005 M0 결정 (2026-04-24):
- 결정 1: 첫 # 만 분류, 두 번째 이후 # 은 평문
- 결정 2: normalize_hash_syntax(text: str) -> str, engine/markdown.py 위치
- 결정 3: DB 에는 정규화된 형태만 엄격히 저장
- 결정 4: 앞 공백·분류명 없는 # 평문 처리, 모호한 점 그대로, depth 건너뛰기 자연 상속

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
        # 1~4: PLAN 본문 표 핵심
        ("#건강", "# 건강"),
        ("# 건강", "# 건강"),
        ("#건강 허리 아픔", "# 건강\n허리 아픔"),
        ("# 건강 허리 아픔", "# 건강\n허리 아픔"),
        # 5~8: depth 1·3·7·10
        ("##허리", "## 허리"),
        ("### 깊은 분류", "### 깊은\n분류"),
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
        # 16~19: 점 / 언더스코어 / 구두점
        ("#건강.허리 오늘 아픔", "# 건강.허리\n오늘 아픔"),
        ("#제55조_연차휴가", "# 제55조_연차휴가"),
        ("#건강?", "# 건강?"),
        ("#건강!", "# 건강!"),
        # 20: depth 10 (점 계층)
        (
            "#A.B.C.D.E.F.G.H.I.J 본문",
            "# A.B.C.D.E.F.G.H.I.J\n본문",
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
    print("\n=== CASE C: 다중 # 한 줄 — 첫 # 만 분류 (PLAN-005 결정 1) (4개) ===")
    from engine.markdown import normalize_hash_syntax

    cases: list[tuple[str, str]] = [
        # 24~27: 두 번째 # 은 평문
        ("#건강 #허리 오늘 아픔", "# 건강\n#허리 오늘 아픔"),
        ("#A #B #C 본문", "# A\n#B #C 본문"),
        ("##A #B 본문", "## A\n#B 본문"),
        ("#A.B #C.D 본문", "# A.B\n#C.D 본문"),
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


# ─── E. chat / markdown 동등성 (4개) ────────────────────

def case_chat_markdown_equivalence() -> bool:
    print("\n=== CASE E: chat / markdown 동등성 — 같은 의도 = 같은 DB 상태 (4개) ===")
    _fresh_db_dir()
    from engine.save import save
    from engine.db import DB_PATH

    def dump(post_id: int) -> dict:
        conn = sqlite3.connect(DB_PATH)
        try:
            md = conn.execute("SELECT markdown FROM posts WHERE id=?", (post_id,)).fetchone()[0]
            sents = [
                r[0] for r in conn.execute(
                    "SELECT text FROM sentences WHERE post_id=? ORDER BY position", (post_id,)
                ).fetchall()
            ]
            cats = [
                r[0] for r in conn.execute(
                    """SELECT c.name FROM sentence_categories sc
                       JOIN categories c ON c.id = sc.category_id
                       JOIN sentences s ON s.id = sc.sentence_id
                       WHERE s.post_id = ?
                       ORDER BY sc.sentence_id, c.id""",
                    (post_id,),
                ).fetchall()
            ]
        finally:
            conn.close()
        return {"markdown": md, "sentences": sents, "sentence_cats": cats}

    ok = True

    # 36: chat #건강 허리 아픔 ≡ markdown # 건강\n허리 아픔
    r1 = save("#건강 허리 아픔", mode="chat", use_llm=False)
    r2 = save("# 건강\n허리 아픔", mode="markdown", use_llm=False)
    d1, d2 = dump(r1.post_id), dump(r2.post_id)
    ok &= _passed(
        "36: chat '#건강 허리 아픔' ≡ markdown '# 건강\\n허리 아픔'",
        d1["sentences"] == d2["sentences"] and d1["sentence_cats"] == d2["sentence_cats"],
        f"chat={d1}, md={d2}",
    )

    # 37: chat #건강 단독 → posts 1, sentences 0, category 1
    r3 = save("#건강", mode="chat", use_llm=False)
    conn = sqlite3.connect(DB_PATH)
    try:
        sc = conn.execute("SELECT COUNT(*) FROM sentences WHERE post_id=?", (r3.post_id,)).fetchone()[0]
        cat_exists = conn.execute("SELECT 1 FROM categories WHERE name='건강'").fetchone() is not None
    finally:
        conn.close()
    ok &= _passed(
        "37: '#건강' 단독 → posts 1, sentences 0, category '건강' 등록",
        sc == 0 and cat_exists,
        f"sentences={sc}, category 건강 존재={cat_exists}",
    )

    # 38: chat #건강.허리 오늘 아픔 → category 건강+허리 + sentence_categories 연결
    r4 = save("#건강.허리 오늘 아픔", mode="chat", use_llm=False)
    d4 = dump(r4.post_id)
    # categories 테이블에 건강, 허리 둘 다 (parent 관계)
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            """WITH RECURSIVE cp AS (
                   SELECT id, name, parent_id, name AS path
                   FROM categories WHERE parent_id IS NULL
                   UNION ALL
                   SELECT c.id, c.name, c.parent_id, cp.path || '.' || c.name
                   FROM categories c JOIN cp ON c.parent_id = cp.id
               )
               SELECT path FROM cp WHERE path LIKE '건강%' ORDER BY length(path)"""
        ).fetchall()
        paths = [r[0] for r in rows]
    finally:
        conn.close()
    ok &= _passed(
        "38: '#건강.허리 오늘 아픔' → 건강·건강.허리 모두 등록 + sentence 연결",
        "건강" in paths and "건강.허리" in paths and d4["sentences"] == ["오늘 아픔"]
        and "허리" in d4["sentence_cats"],
        f"paths={paths}, dump={d4}",
    )

    # 39: chat #건강.허리.무릎 어제 아픔 ≡ markdown # 건강.허리.무릎\n어제 아픔 (점 계층 + 본문 동등성)
    r5 = save("#건강.허리.무릎 어제 아픔", mode="chat", use_llm=False)
    r6 = save("# 건강.허리.무릎\n어제 아픔", mode="markdown", use_llm=False)
    d5, d6 = dump(r5.post_id), dump(r6.post_id)
    ok &= _passed(
        "39: 점 계층 깊이 3 + 본문 — chat ≡ markdown",
        d5["sentences"] == d6["sentences"] and d5["sentence_cats"] == d6["sentence_cats"],
        f"chat={d5}, md={d6}",
    )

    return ok


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
    """PLAN 본문 §M2 dogfood — 실제 사용 패턴 시뮬레이션."""
    print("\n=== CASE G: dogfood 시뮬레이션 — 실입력 패턴 ===")
    _fresh_db_dir()
    from engine.save import save
    from engine.db import DB_PATH

    ok = True

    # 시나리오 1: chat 빠른 메모 — 분류만
    r1 = save("#건강", mode="chat", use_llm=False)

    # 시나리오 2: chat 한 줄 — 분류 + 본문
    r2 = save("#건강 오늘 또 아픔", mode="chat", use_llm=False)

    # 시나리오 3: chat 점 계층
    r3 = save("#건강.허리 다리 저림", mode="chat", use_llm=False)

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

        # 시나리오 2: sentence '오늘 또 아픔' + sentence_categories 건강 연결
        sents2 = [
            r[0] for r in conn.execute(
                "SELECT text FROM sentences WHERE post_id=?", (r2.post_id,)
            ).fetchall()
        ]
        cats2 = [
            r[0] for r in conn.execute(
                """SELECT c.name FROM sentence_categories sc
                   JOIN categories c ON c.id = sc.category_id
                   JOIN sentences s ON s.id = sc.sentence_id
                   WHERE s.post_id = ?""",
                (r2.post_id,),
            ).fetchall()
        ]
        ok &= _passed(
            "시나리오 2: chat '#건강 오늘 또 아픔' → sentence '오늘 또 아픔' + 건강 카테고리",
            sents2 == ["오늘 또 아픔"] and cats2 == ["건강"],
            f"sents={sents2}, cats={cats2}",
        )

        # 시나리오 3: 점 계층 — 건강·허리 둘 다 카테고리 등록, sentence '다리 저림' 은 허리에 연결
        cats3 = [
            r[0] for r in conn.execute(
                """SELECT c.name FROM sentence_categories sc
                   JOIN categories c ON c.id = sc.category_id
                   JOIN sentences s ON s.id = sc.sentence_id
                   WHERE s.post_id = ?""",
                (r3.post_id,),
            ).fetchall()
        ]
        ok &= _passed(
            "시나리오 3: chat '#건강.허리 다리 저림' → sentence_cat = '허리'",
            cats3 == ["허리"],
            f"cats={cats3}",
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
        case_chat_markdown_equivalence,    # 4
        case_robustness,                   # 4
        case_dogfood_simulation,           # dogfood
    ]
    results = [c() for c in cases]
    passed = sum(results)
    print(f"\n요약: {passed}/{len(results)} 그룹 통과")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
