"""Synapse DB — SQLite v9 세션리스 스키마 + 연결 관리."""

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
    category   TEXT,
    status     TEXT    NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'inactive')),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
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
CREATE INDEX IF NOT EXISTS idx_edges_src         ON edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_tgt         ON edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_sentence    ON edges(sentence_id);
CREATE INDEX IF NOT EXISTS idx_aliases           ON aliases(alias);
"""


def _is_current_schema(conn: sqlite3.Connection) -> bool:
    """현재 스키마 여부 확인: sentences.role + nodes.category + edges.sentence_id 컬럼 존재. sessions 테이블 없음."""
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "sentences" not in tables:
        return False
    if "sessions" in tables:
        return False
    sent_cols = [r[1] for r in conn.execute("PRAGMA table_info(sentences)").fetchall()]
    if "role" not in sent_cols or "retention" not in sent_cols:
        return False
    edge_cols = [r[1] for r in conn.execute("PRAGMA table_info(edges)").fetchall()]
    if "sentence_id" not in edge_cols:
        return False
    node_cols = [r[1] for r in conn.execute("PRAGMA table_info(nodes)").fetchall()]
    return "category" in node_cols


def init_db(db_path: str = DB_PATH) -> str:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        check = sqlite3.connect(db_path)
        old_schema = not _is_current_schema(check)
        check.close()
        if old_schema:
            os.remove(db_path)
            print(f"[db] 구 스키마 감지 → 삭제 후 재생성: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.close()
    return db_path


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    if not os.path.exists(db_path):
        init_db(db_path)
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
        "aliases_total":        aliases_total,
        "sentences_total":      sentences_total,
        "sentences_user":       sentences_user,
        "sentences_assistant":  sentences_assistant,
    }


if __name__ == "__main__":
    import json
    path = init_db()
    print(json.dumps({"db_path": path, **get_stats()}, ensure_ascii=False, indent=2))
