"""PLAN-20260424-SYN-007 M4 — 백그라운드 워커 v21 회귀.

목적:
- `node_categories` 폐기 이후 `engine/workers.py:category_worker` 가
  `node_category_mentions(origin='ai')` 로 정상 insert 하는지 검증.
- `_recent_sentences` 가 `node_sentence_mentions` 리네임 이후에도 동작하는지.
- 시드 카테고리 역매핑 (예: "BOD.medical" → categories.id) 성공·실패 케이스.

실행: python3 -m tests.regression_workers_v21
"""
from __future__ import annotations
import os
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


def _fresh_db() -> None:
    d = tempfile.mkdtemp(prefix="synapse-workers-v21-")
    os.environ["SYNAPSE_DATA_DIR"] = d
    import importlib
    import engine.db, engine.save, engine.workers
    importlib.reload(engine.db)
    importlib.reload(engine.save)
    importlib.reload(engine.workers)


def case_recent_sentences_rename() -> bool:
    print("=== CASE 1: _recent_sentences (node_sentence_mentions 리네임 fix) ===")
    _fresh_db()
    from engine.save import save
    from engine.workers import _recent_sentences
    from engine.db import get_connection, DB_PATH

    sr = save("오늘 병원 갔다", mode="chat", use_llm=False, db_path=DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        rows = conn.execute("SELECT id FROM nodes WHERE name='병원'").fetchone()
        node_id = rows["id"] if rows else None
    finally:
        conn.close()

    ok = True
    ok &= _passed("병원 노드 저장됨", node_id is not None, f"node_id={node_id}")
    if node_id:
        sents = _recent_sentences(DB_PATH, node_id)
        ok &= _passed(
            "_recent_sentences 가 node_sentence_mentions JOIN 으로 문장 반환",
            sents == ["오늘 병원 갔다"],
            f"sents={sents}",
        )
    return ok


def case_category_worker_seed_remap() -> bool:
    print("\n=== CASE 2: category_worker 시드 역매핑 ('BOD.medical' → id) ===")
    _fresh_db()
    from engine.save import save
    from engine.workers import category_worker
    from engine.db import get_connection, DB_PATH

    sr = save("오늘 병원 갔다", mode="chat", use_llm=False, db_path=DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        node_id = conn.execute(
            "SELECT id FROM nodes WHERE name='병원'"
        ).fetchone()["id"]
    finally:
        conn.close()

    # mock LLM — "BOD.medical" 대분류.소분류 반환
    def mock_llm(name: str, sentences: list[str]) -> list[str]:
        return ["BOD.medical"] if name == "병원" else []

    inserted = category_worker([node_id], db_path=DB_PATH, llm_fn=mock_llm)

    conn = get_connection(DB_PATH)
    try:
        rows = conn.execute(
            """SELECT c.name, p.name AS parent_name, ncm.origin
               FROM node_category_mentions ncm
               JOIN categories c ON c.id = ncm.category_id
               LEFT JOIN categories p ON p.id = c.parent_id
               WHERE ncm.node_id = ?""",
            (node_id,),
        ).fetchall()
    finally:
        conn.close()

    ok = True
    ok &= _passed(
        "category_worker insert 건수 = 1",
        inserted == 1,
        f"inserted={inserted}",
    )
    ok &= _passed(
        "node_category_mentions 에 medical(BOD 부모) + origin='ai' 기록",
        any(r["name"] == "medical" and r["parent_name"] == "BOD" and r["origin"] == "ai"
            for r in rows),
        f"rows={[dict(r) for r in rows]}",
    )
    return ok


def case_category_worker_invalid_skip() -> bool:
    print("\n=== CASE 3: 존재하지 않는 카테고리는 skip ===")
    _fresh_db()
    from engine.save import save
    from engine.workers import category_worker
    from engine.db import get_connection, DB_PATH

    save("오늘 병원 갔다", mode="chat", use_llm=False, db_path=DB_PATH)
    conn = get_connection(DB_PATH)
    try:
        node_id = conn.execute(
            "SELECT id FROM nodes WHERE name='병원'"
        ).fetchone()["id"]
    finally:
        conn.close()

    def bad_llm(name: str, sentences: list[str]) -> list[str]:
        # 3 개 중 2 개는 시드에 없어 skip, 1 개만 insert
        return ["INVALID.xxx", "BOD.nonexistent", "BOD.medical"]

    inserted = category_worker([node_id], db_path=DB_PATH, llm_fn=bad_llm)

    conn = get_connection(DB_PATH)
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM node_category_mentions WHERE node_id=?",
            (node_id,),
        ).fetchone()[0]
    finally:
        conn.close()

    ok = True
    ok &= _passed(
        "invalid 2 건 skip + medical 1 건만 insert",
        inserted == 1 and count == 1,
        f"inserted={inserted}, ncm_count={count}",
    )
    return ok


def case_category_worker_no_node_categories_table() -> bool:
    """node_categories 테이블이 실제로 DROP 되었는지 — 워커가 node_category_mentions 만 쓰는지."""
    print("\n=== CASE 4: node_categories 테이블 폐기 확인 ===")
    _fresh_db()
    from engine.db import get_connection, init_db
    init_db()
    conn = get_connection()
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    finally:
        conn.close()
    ok = True
    ok &= _passed(
        "node_categories 테이블 부재 (v21 폐기)",
        "node_categories" not in tables,
        f"tables={sorted(tables)}",
    )
    ok &= _passed(
        "node_category_mentions 테이블 존재",
        "node_category_mentions" in tables,
    )
    ok &= _passed(
        "node_sentence_mentions 테이블 존재 (node_mentions 리네임)",
        "node_sentence_mentions" in tables and "node_mentions" not in tables,
    )
    return ok


def main() -> int:
    cases = [
        case_recent_sentences_rename,
        case_category_worker_seed_remap,
        case_category_worker_invalid_skip,
        case_category_worker_no_node_categories_table,
    ]
    results = [c() for c in cases]
    passed = sum(results)
    print(f"\n요약: {passed}/{len(results)} 통과")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
