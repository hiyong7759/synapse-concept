"""v19 chat 모드 정립 회귀 테스트 (PLAN-20260422-SYN-003 M1).

목적:
- save(mode='chat'|'markdown') 시그니처·검증 동작 확인
- posts.input_mode 컬럼이 chat/markdown 값으로 정확히 저장되는지
- chat 모드에서 `#` 으로 시작하는 줄도 sentence 로 저장 (heading 해석 안 함)
- v18 → v19 마이그레이션 backfill 정합 (heading 포함 → markdown, 평문 → chat)

M2 이후 도입될 markdown 분기(kind 별 분기·save-pronoun skip) 는 본 테스트 범위 외.

실행: python3 -m tests.regression_v19_chat_mode
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
    d = tempfile.mkdtemp(prefix="synapse-v19-")
    os.environ["SYNAPSE_DATA_DIR"] = d
    # 기본 로드된 모듈을 쓰면 DB_PATH 가 고정되므로 reload
    import importlib
    import engine.db, engine.save
    importlib.reload(engine.db)
    importlib.reload(engine.save)
    return d


def case_mode_validation() -> bool:
    print("=== CASE 1: mode 파라미터 검증 ===")
    _fresh_db_dir()
    from engine.save import save

    ok = True
    # mode 누락
    try:
        save("x", use_llm=False)  # type: ignore[call-arg]
        ok &= _passed("mode 누락 → TypeError", False)
    except TypeError:
        ok &= _passed("mode 누락 → TypeError", True)

    # 잘못된 mode
    try:
        save("x", mode="auto", use_llm=False)
        ok &= _passed("mode='auto' → ValueError", False)
    except ValueError:
        ok &= _passed("mode='auto' → ValueError", True)

    # 정상 chat
    r = save("테스트", mode="chat", use_llm=False)
    ok &= _passed("mode='chat' 정상 저장", r.post_id is not None)

    # 정상 markdown
    r = save("# 제목\n본문", mode="markdown", use_llm=False)
    ok &= _passed("mode='markdown' 정상 저장", r.post_id is not None)
    return ok


def case_input_mode_column() -> bool:
    print("\n=== CASE 2: posts.input_mode 컬럼 저장값 ===")
    d = _fresh_db_dir()
    from engine.save import save
    from engine.db import DB_PATH

    r1 = save("chat 한 줄", mode="chat", use_llm=False)
    r2 = save("# 구조\n본문", mode="markdown", use_llm=False)

    conn = sqlite3.connect(DB_PATH)
    try:
        rows = {
            row[0]: row[1]
            for row in conn.execute("SELECT id, input_mode FROM posts").fetchall()
        }
    finally:
        conn.close()

    ok = True
    ok &= _passed("chat post → input_mode='chat'", rows.get(r1.post_id) == "chat", f"rows={rows}")
    ok &= _passed("markdown post → input_mode='markdown'", rows.get(r2.post_id) == "markdown", f"rows={rows}")
    return ok


def case_chat_preserves_hash() -> bool:
    """chat 모드에서 `#` 을 heading 으로 해석하지 않고 sentence 로 저장."""
    print("\n=== CASE 3: chat 모드 해시(#) 해시태그 처리 ===")
    d = _fresh_db_dir()
    from engine.save import save
    from engine.db import DB_PATH

    r = save("# 야근\n오늘 회의 길었어", mode="chat", use_llm=False)

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
    ok &= _passed("sentence 2건 생성 (heading 줄 포함)", len(texts) == 2, f"texts={texts}")
    ok &= _passed("첫 줄은 '# 야근' 원문 그대로", texts and texts[0] == "# 야근", f"texts[0]={texts[0] if texts else None!r}")
    return ok


def case_markdown_skips_heading_sentence() -> bool:
    """markdown 모드는 heading 줄을 sentence 로 저장하지 않음 (기존 동작 유지)."""
    print("\n=== CASE 4: markdown 모드 heading 은 sentence INSERT 안 함 ===")
    d = _fresh_db_dir()
    from engine.save import save
    from engine.db import DB_PATH

    r = save("# 건강\n허리 아픔", mode="markdown", use_llm=False)

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
    ok &= _passed("sentence 1건만 생성", len(texts) == 1, f"texts={texts}")
    ok &= _passed("heading 본문 '허리 아픔' 보존", texts == ["허리 아픔"], f"texts={texts}")
    return ok


def case_migration_backfill() -> bool:
    """가짜 v18 DB (input_mode 컬럼 없음) → init_db 호출 시 자동 백필."""
    print("\n=== CASE 5: v18 → v19 backfill 정합 ===")
    d = tempfile.mkdtemp(prefix="synapse-v19-mig-")
    db = os.path.join(d, "synapse.db")

    # 수동으로 v18 스키마 posts 테이블 생성 + 데이터 심기
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            markdown TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE sentences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            post_id INTEGER REFERENCES posts(id) ON DELETE CASCADE,
            position INTEGER NOT NULL DEFAULT 0,
            text TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user' CHECK(role IN ('user','assistant')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE node_mentions (
            node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (node_id, sentence_id)
        );
        CREATE TABLE node_categories (
            node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            category TEXT NOT NULL,
            origin TEXT NOT NULL DEFAULT 'user' CHECK(origin IN ('user','ai','system','external')),
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (node_id, category)
        );
        CREATE TABLE aliases (
            alias TEXT PRIMARY KEY,
            node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            origin TEXT NOT NULL DEFAULT 'user' CHECK(origin IN ('user','ai','system','external')),
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE unresolved_tokens (
            sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
            token TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (sentence_id, token)
        );
    """)
    conn.execute("INSERT INTO posts (markdown) VALUES ('평문 게시물 하나')")
    conn.execute("INSERT INTO posts (markdown) VALUES ('# 제목\n본문')")
    conn.execute("INSERT INTO sentences (post_id, position, text) VALUES (1, 0, '평문 게시물 하나')")
    conn.commit()
    conn.close()

    from engine.db import init_db
    init_db(db)

    conn = sqlite3.connect(db)
    try:
        rows = {
            row[0]: row[1]
            for row in conn.execute("SELECT id, input_mode FROM posts ORDER BY id").fetchall()
        }
        scount = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
    finally:
        conn.close()

    ok = True
    ok &= _passed("평문 post → 'chat' backfill", rows.get(1) == "chat", f"rows={rows}")
    ok &= _passed("heading post → 'markdown' backfill", rows.get(2) == "markdown", f"rows={rows}")
    ok &= _passed("sentences 보존 (FK 재연결)", scount == 1, f"count={scount}")
    return ok


def main() -> int:
    cases = [
        case_mode_validation,
        case_input_mode_column,
        case_chat_preserves_hash,
        case_markdown_skips_heading_sentence,
        case_migration_backfill,
    ]
    results = [c() for c in cases]
    passed = sum(results)
    print(f"\n요약: {passed}/{len(results)} 통과")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
