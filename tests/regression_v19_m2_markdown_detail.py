"""v19 M2 markdown 모드 확장 회귀 테스트 (PLAN-20260422-SYN-003 M2).

목적:
- parse_markdown 이 (category_path, kind, text) 3-tuple 을 반환
- key_value 파싱: `- key:: value` → kind='key_value', text="key:: value"
- markdown 모드 저장 시 save-pronoun 이 호출되지 않음 (LLM 스텁으로 검증)
- markdown 모드 메타 필터 대상이 list · free 만 (heading · key_value 제외)
- heading 은 sentence INSERT 안 함 (카테고리 path 만 등록)
- key_value 는 sentence 원문 "key:: value" 보존

실행: python3 -m tests.regression_v19_m2_markdown_detail
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
    d = tempfile.mkdtemp(prefix="synapse-v19-m2-")
    os.environ["SYNAPSE_DATA_DIR"] = d
    import importlib
    import engine.db, engine.save
    importlib.reload(engine.db)
    importlib.reload(engine.save)
    return d


def case_parse_markdown_tuple_shape() -> bool:
    print("=== CASE 1: parse_markdown 반환 형식 (category_path, kind, text) ===")
    from engine.markdown import parse_markdown

    text = (
        "# 건강\n"
        "## 허리\n"
        "- 팀장:: 박지수\n"
        "- 오늘 피곤함\n"
        "어제보다 나아짐"
    )
    items = parse_markdown(text)
    ok = True
    ok &= _passed("5 요소 반환", len(items) == 5, f"len={len(items)}")
    if not ok:
        return ok

    # heading 은 "path 가 갱신된 뒤" 의 현재 경로를 들고 나온다 — save.py 가 바로
    # 그 path 를 _upsert_category_path 로 재귀 upsert 하기 때문.
    expected = [
        ("건강", "heading", "건강"),
        ("건강.허리", "heading", "허리"),
        ("건강.허리", "key_value", "팀장:: 박지수"),
        ("건강.허리", "list", "오늘 피곤함"),
        ("건강.허리", "free", "어제보다 나아짐"),
    ]
    for i, (exp, got) in enumerate(zip(expected, items)):
        ok &= _passed(f"items[{i}] == {exp}", got == exp, f"got={got}")
    return ok


def case_key_value_parser_edge_cases() -> bool:
    print("\n=== CASE 2: `- key:: value` 파서 경계 케이스 ===")
    from engine.markdown import parse_markdown

    ok = True
    # 공백 trim
    items = parse_markdown("- 모델::   Gemma 4 E2B   ")
    ok &= _passed(
        "공백 trim", items == [(None, "key_value", "모델:: Gemma 4 E2B")], f"items={items}"
    )
    # key 없으면 일반 list (정규식이 non-greedy 라서 key 가 빈 문자열은 매칭 안 됨)
    items = parse_markdown("- :: 값만")
    ok &= _passed(
        "key 빈 상태는 일반 list",
        items and items[0][1] == "list",
        f"items={items}",
    )
    # value 없으면 일반 list
    items = parse_markdown("- 키만:: ")
    ok &= _passed(
        "value 빈 상태는 일반 list",
        items and items[0][1] == "list",
        f"items={items}",
    )
    # `::` 없으면 일반 list
    items = parse_markdown("- 그냥 리스트 항목")
    ok &= _passed(
        "`::` 없으면 일반 list",
        items and items[0][1] == "list",
        f"items={items}",
    )
    return ok


def case_markdown_skips_save_pronoun() -> bool:
    """markdown 모드 저장 시 save-pronoun 이 호출되지 않는지 monkeypatch 로 검증."""
    print("\n=== CASE 3: markdown 모드 save-pronoun 전체 skip ===")
    _fresh_db_dir()

    import engine.save as save_mod
    calls = {"pronoun": 0, "meta": 0, "meta_input_count": 0}

    def fake_pronoun(text, context="", today=""):
        calls["pronoun"] += 1
        return {"text": text, "unresolved": []}

    def fake_meta_filter(items):
        calls["meta"] += 1
        calls["meta_input_count"] = len(items)
        return set()

    save_mod.save_pronoun = fake_pronoun
    save_mod.llm_meta_filter = fake_meta_filter

    text = (
        "# 건강\n"
        "- 팀장:: 박지수\n"
        "- 오늘 피곤\n"
        "어제보다 나아짐"
    )
    save_mod.save(text, mode="markdown", use_llm=True)

    ok = True
    ok &= _passed("save-pronoun 호출 0회", calls["pronoun"] == 0, f"pronoun={calls['pronoun']}")
    ok &= _passed("메타 필터는 호출됨 (게시물 1회)", calls["meta"] == 1, f"meta={calls['meta']}")
    # heading · key_value 제외, list + free = 2
    ok &= _passed(
        "메타 필터 input = list · free 만 (2건)",
        calls["meta_input_count"] == 2,
        f"input_count={calls['meta_input_count']}",
    )
    return ok


def case_chat_still_calls_pronoun() -> bool:
    """chat 모드는 이전처럼 save-pronoun 호출."""
    print("\n=== CASE 4: chat 모드 save-pronoun 호출 유지 ===")
    _fresh_db_dir()

    import engine.save as save_mod
    calls = {"pronoun": 0, "meta_input_count": 0}

    def fake_pronoun(text, context="", today=""):
        calls["pronoun"] += 1
        return {"text": text, "unresolved": []}

    def fake_meta_filter(items):
        calls["meta_input_count"] = len(items)
        return set()

    save_mod.save_pronoun = fake_pronoun
    save_mod.llm_meta_filter = fake_meta_filter

    save_mod.save("한 줄\n또 한 줄", mode="chat", use_llm=True)

    ok = True
    ok &= _passed("save-pronoun 2회 (줄마다)", calls["pronoun"] == 2, f"pronoun={calls['pronoun']}")
    ok &= _passed(
        "메타 필터 input = 전체 2건",
        calls["meta_input_count"] == 2,
        f"input_count={calls['meta_input_count']}",
    )
    return ok


def case_key_value_sentence_preserves_original() -> bool:
    """key_value 항목의 sentence.text 가 'key:: value' 원문 그대로인지."""
    print("\n=== CASE 5: key_value sentence 원문 보존 ===")
    d = _fresh_db_dir()
    from engine.save import save
    from engine.db import DB_PATH

    r = save("# 건강\n- 팀장:: 박지수\n- 모델:: Gemma 4 E2B", mode="markdown", use_llm=False)

    conn = sqlite3.connect(DB_PATH)
    try:
        texts = [
            row[0]
            for row in conn.execute(
                "SELECT text FROM sentences WHERE post_id=? ORDER BY position",
                (r.post_id,),
            ).fetchall()
        ]
    finally:
        conn.close()

    ok = True
    ok &= _passed("sentence 2건 (heading 제외)", len(texts) == 2, f"texts={texts}")
    ok &= _passed(
        "key_value 1 원문 '팀장:: 박지수'",
        texts and texts[0] == "팀장:: 박지수",
        f"texts[0]={texts[0] if texts else None!r}",
    )
    ok &= _passed(
        "key_value 2 원문 '모델:: Gemma 4 E2B'",
        len(texts) > 1 and texts[1] == "모델:: Gemma 4 E2B",
        f"texts[1]={texts[1] if len(texts) > 1 else None!r}",
    )
    return ok


def case_key_value_kiwi_extracts_nodes() -> bool:
    """key_value sentence 에 대해서도 Kiwi 형태소·노드 등록이 작동."""
    print("\n=== CASE 6: key_value sentence 에서 Kiwi 노드 추출 ===")
    d = _fresh_db_dir()
    from engine.save import save
    from engine.db import DB_PATH

    r = save("# 건강\n- 팀장:: 박지수", mode="markdown", use_llm=False)

    conn = sqlite3.connect(DB_PATH)
    try:
        names = {
            row[0]
            for row in conn.execute(
                """SELECT n.name FROM nodes n
                   JOIN node_sentence_mentions m ON m.node_id=n.id
                   JOIN sentences s ON s.id=m.sentence_id
                   WHERE s.post_id=?""",
                (r.post_id,),
            ).fetchall()
        }
    finally:
        conn.close()

    ok = True
    ok &= _passed("'팀장' 노드 생성", "팀장" in names, f"names={names}")
    ok &= _passed("'박지수' 노드 생성", "박지수" in names, f"names={names}")
    return ok


def case_heading_category_path_registered() -> bool:
    """heading 경로가 categories 테이블에 등록되고 sentence_categories 로 연결."""
    print("\n=== CASE 7: heading 카테고리 path 등록 + sentence_categories 연결 ===")
    d = _fresh_db_dir()
    from engine.save import save
    from engine.db import DB_PATH

    save("# 건강\n## 허리\n- 오늘 피곤함", mode="markdown", use_llm=False)

    conn = sqlite3.connect(DB_PATH)
    try:
        cats = {
            row[0]: row[1]
            for row in conn.execute("SELECT name, id FROM categories").fetchall()
        }
        sc_count = conn.execute("SELECT COUNT(*) FROM sentence_categories").fetchone()[0]
    finally:
        conn.close()

    ok = True
    ok &= _passed("'건강' 카테고리 생성", "건강" in cats, f"cats={cats}")
    ok &= _passed("'허리' 카테고리 생성", "허리" in cats, f"cats={cats}")
    ok &= _passed("sentence_categories 1건 이상", sc_count >= 1, f"sc_count={sc_count}")
    return ok


def main() -> int:
    cases = [
        case_parse_markdown_tuple_shape,
        case_key_value_parser_edge_cases,
        case_markdown_skips_save_pronoun,
        case_chat_still_calls_pronoun,
        case_key_value_sentence_preserves_original,
        case_key_value_kiwi_extracts_nodes,
        case_heading_category_path_registered,
    ]
    results = [c() for c in cases]
    passed = sum(results)
    print(f"\n요약: {passed}/{len(results)} 통과")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
