"""Synapse DB — SQLite v12 스키마.

v12 변경점 (Phase 2):
- 신규 테이블 posts: 게시물 = 맥락 그룹 (원본 마크다운 보관)
- sentences에 post_id, position 컬럼 추가
- user sentences는 post_id 필수, assistant sentences는 NULL 허용

v11 → v12: DB 날려도 됨 원칙으로 drop 후 재생성.
"""

import os
import sqlite3

DATA_DIR = os.environ.get("SYNAPSE_DATA_DIR", os.path.expanduser("~/.synapse"))
DB_PATH = os.path.join(DATA_DIR, "synapse.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS posts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    markdown   TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS sentences (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id         INTEGER REFERENCES posts(id) ON DELETE CASCADE,
    position        INTEGER NOT NULL DEFAULT 0,
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

CREATE TABLE IF NOT EXISTS node_mentions (
    node_id     INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (node_id, sentence_id)
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

CREATE TABLE IF NOT EXISTS unresolved_tokens (
    sentence_id INTEGER NOT NULL REFERENCES sentences(id) ON DELETE CASCADE,
    token       TEXT    NOT NULL,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (sentence_id, token)
);

CREATE INDEX IF NOT EXISTS idx_sentences_role       ON sentences(role);
CREATE INDEX IF NOT EXISTS idx_sentences_post       ON sentences(post_id, position);
CREATE INDEX IF NOT EXISTS idx_nodes_name           ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_status         ON nodes(status);
CREATE INDEX IF NOT EXISTS idx_mentions_node        ON node_mentions(node_id);
CREATE INDEX IF NOT EXISTS idx_mentions_sentence    ON node_mentions(sentence_id);
CREATE INDEX IF NOT EXISTS idx_nc_category          ON node_categories(category);
CREATE INDEX IF NOT EXISTS idx_nc_node              ON node_categories(node_id);
CREATE INDEX IF NOT EXISTS idx_edges_src            ON edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_tgt            ON edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_sentence       ON edges(sentence_id);
CREATE INDEX IF NOT EXISTS idx_aliases              ON aliases(alias);
CREATE INDEX IF NOT EXISTS idx_unresolved_sentence  ON unresolved_tokens(sentence_id);
"""


def _get_tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}


def _get_cols(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _is_current_schema(conn: sqlite3.Connection) -> bool:
    """v12 스키마 여부 확인: posts + sentences.post_id·position 존재."""
    tables = _get_tables(conn)
    for required in ("sentences", "nodes", "node_mentions", "node_categories",
                     "edges", "aliases", "unresolved_tokens", "posts"):
        if required not in tables:
            return False
    if "sessions" in tables:
        return False
    if "category" in _get_cols(conn, "nodes"):
        return False
    sent_cols = _get_cols(conn, "sentences")
    for required_col in ("role", "retention", "post_id", "position"):
        if required_col not in sent_cols:
            return False
    if "sentence_id" not in _get_cols(conn, "edges"):
        return False
    return True


def init_db(db_path: str = DB_PATH) -> str:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        try:
            if not _is_current_schema(conn):
                conn.close()
                conn = None
                os.remove(db_path)
                print(f"[db] 구 스키마 감지 → 삭제 후 v12 재생성: {db_path}")
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
        posts_total       = conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0]
        nodes_total       = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        nodes_active      = conn.execute("SELECT COUNT(*) FROM nodes WHERE status='active'").fetchone()[0]
        mentions_total    = conn.execute("SELECT COUNT(*) FROM node_mentions").fetchone()[0]
        edges_total       = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        categories_total  = conn.execute("SELECT COUNT(*) FROM node_categories").fetchone()[0]
        aliases_total     = conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0]
        sentences_total   = conn.execute("SELECT COUNT(*) FROM sentences").fetchone()[0]
        sentences_user    = conn.execute("SELECT COUNT(*) FROM sentences WHERE role='user'").fetchone()[0]
        sentences_asst    = conn.execute("SELECT COUNT(*) FROM sentences WHERE role='assistant'").fetchone()[0]
        unresolved_total  = conn.execute("SELECT COUNT(*) FROM unresolved_tokens").fetchone()[0]
    finally:
        conn.close()
    return {
        "posts_total":          posts_total,
        "nodes_total":          nodes_total,
        "nodes_active":         nodes_active,
        "node_mentions_total":  mentions_total,
        "edges_total":          edges_total,
        "categories_total":     categories_total,
        "aliases_total":        aliases_total,
        "sentences_total":      sentences_total,
        "sentences_user":       sentences_user,
        "sentences_assistant":  sentences_asst,
        "unresolved_total":     unresolved_total,
    }


if __name__ == "__main__":
    import json
    path = init_db()
    print(json.dumps({"db_path": path, **get_stats()}, ensure_ascii=False, indent=2))
