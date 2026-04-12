"""Synapse DB — SQLite v10 세션리스 스키마 + node_categories 다대다 + 마이그레이션 + 연결 관리."""

import os
import sqlite3

DATA_DIR = os.environ.get("SYNAPSE_DATA_DIR", os.path.expanduser("~/.synapse"))
DB_PATH = os.path.join(DATA_DIR, "synapse.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sentences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    text            TEXT    NOT NULL,
    role            TEXT    NOT NULL DEFAULT 'user' CHECK(role IN ('user', 'assistant')),
    retention       TEXT    NOT NULL DEFAULT 'memory' CHECK(retention IN ('memory', 'daily')),
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS nodes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'inactive')),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS node_categories (
    node_id    INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    category   TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (node_id, category)
);

CREATE TABLE IF NOT EXISTS edges (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    target_node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    label          TEXT,
    sentence_id    INTEGER REFERENCES sentences(id) ON DELETE SET NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    last_used      TEXT
);

CREATE TABLE IF NOT EXISTS aliases (
    alias   TEXT    PRIMARY KEY,
    node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sentences_role     ON sentences(role);
CREATE INDEX IF NOT EXISTS idx_nodes_name         ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_status      ON nodes(status);
CREATE INDEX IF NOT EXISTS idx_nc_category       ON node_categories(category);
CREATE INDEX IF NOT EXISTS idx_nc_node           ON node_categories(node_id);
CREATE INDEX IF NOT EXISTS idx_edges_src         ON edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_tgt         ON edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_sentence    ON edges(sentence_id);
CREATE INDEX IF NOT EXISTS idx_aliases           ON aliases(alias);
"""


def _get_tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}


def _get_cols(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _is_current_schema(conn: sqlite3.Connection) -> bool:
    """현재 스키마 여부 확인: node_categories 테이블 존재 + nodes.category 없음."""
    tables = _get_tables(conn)
    if "sentences" not in tables:
        return False
    if "sessions" in tables:
        return False
    if "node_categories" not in tables:
        return False
    sent_cols = _get_cols(conn, "sentences")
    if "role" not in sent_cols or "retention" not in sent_cols:
        return False
    if "sentence_id" not in _get_cols(conn, "edges"):
        return False
    if "category" in _get_cols(conn, "nodes"):
        return False
    return True


def _needs_category_migration(conn: sqlite3.Connection) -> bool:
    """v9 스키마(nodes.category 존재)에서 v10(node_categories 테이블)으로 마이그레이션 필요 여부."""
    if "sentences" not in _get_tables(conn):
        return False
    return "category" in _get_cols(conn, "nodes")


def _migrate_category_to_table(conn: sqlite3.Connection) -> None:
    """nodes.category → node_categories 테이블로 마이그레이션."""
    print("[db] category 마이그레이션: nodes.category → node_categories 테이블")
    conn.execute("PRAGMA foreign_keys = OFF")

    # 1. node_categories 테이블 생성
    conn.execute("""
        CREATE TABLE IF NOT EXISTS node_categories (
            node_id    INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
            category   TEXT    NOT NULL,
            created_at TEXT    NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (node_id, category)
        )
    """)

    # 2. 기존 category 데이터 이전
    conn.execute("""
        INSERT OR IGNORE INTO node_categories (node_id, category)
        SELECT id, category FROM nodes WHERE category IS NOT NULL
    """)

    # 3. nodes 테이블 재생성 (category 컬럼 없이)
    conn.execute("""
        CREATE TABLE nodes_new (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT    NOT NULL,
            status     TEXT    NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'inactive')),
            created_at TEXT    NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("INSERT INTO nodes_new (id, name, status, created_at, updated_at) SELECT id, name, status, created_at, updated_at FROM nodes")
    conn.execute("DROP TABLE nodes")
    conn.execute("ALTER TABLE nodes_new RENAME TO nodes")

    # 4. 인덱스 재생성
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_name    ON nodes(name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_status  ON nodes(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nc_category   ON node_categories(category)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_nc_node       ON node_categories(node_id)")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    migrated = conn.execute("SELECT COUNT(*) FROM node_categories").fetchone()[0]
    print(f"[db] 마이그레이션 완료: {migrated}건 category 이전됨")


def init_db(db_path: str = DB_PATH) -> str:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        try:
            if _needs_category_migration(conn):
                _migrate_category_to_table(conn)
            elif not _is_current_schema(conn):
                conn.close()
                conn = None
                os.remove(db_path)
                print(f"[db] 구 스키마 감지 → 삭제 후 재생성: {db_path}")
        finally:
            if conn:
                conn.close()
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.close()
    return db_path


_initialized: set[str] = set()


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    if db_path not in _initialized:
        init_db(db_path)
        _initialized.add(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_stats(db_path: str = DB_PATH) -> dict:
    conn = get_connection(db_path)
    try:
        nodes_total    = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        nodes_active   = conn.execute("SELECT COUNT(*) FROM nodes WHERE status='active'").fetchone()[0]
        edges_total    = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        categories_total = conn.execute("SELECT COUNT(*) FROM node_categories").fetchone()[0]
        aliases_total  = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        sentences_total = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
        sentences_user = conn.execute("SELECT COUNT(*) FROM sentences WHERE role='user'").fetchone()[0]
        sentences_assistant = conn.execute("SELECT COUNT(*) FROM sentences WHERE role='assistant'").fetchone()[0]
    finally:
        conn.close()
    return {
        "nodes_total":          nodes_total,
        "nodes_active":         nodes_active,
        "edges_total":          edges_total,
        "categories_total":     categories_total,
        "aliases_total":        aliases_total,
        "sentences_total":      sentences_total,
        "sentences_user":       sentences_user,
        "sentences_assistant":  sentences_assistant,
    }


if __name__ == "__main__":
    import json
    path = init_db()
    print(json.dumps({"db_path": path, **get_stats()}, ensure_ascii=False, indent=2))
