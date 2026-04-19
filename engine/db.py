"""Synapse DB — SQLite v15 스키마.

v15 변경점:
- edges 테이블 폐기. 노드 간 연결은 node_mentions(문장 바구니) + node_categories(카테고리 바구니)
  + aliases(별칭 바구니) 세 종류의 하이퍼엣지로만 표현.
- 의미 관계(cause/avoid/similar)는 sentences.text 원문에 이미 담겨 있고, 해석은 외부 지능체 몫.
- v14 DB → v15 자동 마이그레이션: edges 테이블만 DROP, 다른 테이블 전부 보존.

v13 변경점 (참고):
- sentences.retention 컬럼 폐기 (memory/daily 분류 제거)

v12 변경점 (참고):
- 신규 테이블 posts: 게시물 = 맥락 그룹 (원본 마크다운 보관)
- sentences에 post_id, position 컬럼 추가

마이그레이션 정책:
- v14 → v15: edges DROP만 수행 (기존 노드·문장·카테고리 데이터 보존). 자동 백업 생성.
- 그 이전 구 스키마 → v15: DB 파일 자동 백업 후 재생성.
"""

import os
import shutil
import sqlite3
import time

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
    origin     TEXT    NOT NULL DEFAULT 'user' CHECK(origin IN ('user', 'ai', 'rule')),
    created_at TEXT    NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (node_id, category)
);

CREATE TABLE IF NOT EXISTS aliases (
    alias   TEXT    PRIMARY KEY,
    node_id INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    origin  TEXT    NOT NULL DEFAULT 'user' CHECK(origin IN ('user', 'ai', 'rule')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
    """v15 스키마 여부 확인: edges 테이블 없음 + origin 컬럼 존재 + 필수 테이블."""
    tables = _get_tables(conn)
    for required in ("sentences", "nodes", "node_mentions", "node_categories",
                     "aliases", "unresolved_tokens", "posts"):
        if required not in tables:
            return False
    if "sessions" in tables:
        return False
    # v15: edges 테이블이 있으면 구 스키마 (v14 이하)
    if "edges" in tables:
        return False
    if "category" in _get_cols(conn, "nodes"):
        return False
    sent_cols = _get_cols(conn, "sentences")
    for required_col in ("role", "post_id", "position"):
        if required_col not in sent_cols:
            return False
    # retention 컬럼이 남아있으면 구 스키마로 판정 (v13 이후 폐기)
    if "retention" in sent_cols:
        return False
    # v15: node_categories / aliases 에 origin 컬럼 있어야 함 (v14 설계 원칙)
    if "origin" not in _get_cols(conn, "node_categories"):
        return False
    if "origin" not in _get_cols(conn, "aliases"):
        return False
    return True


def _can_add_origin_columns(conn: sqlite3.Connection) -> bool:
    """edges 이미 제거됐고 origin 컬럼만 빠졌는지 확인."""
    tables = _get_tables(conn)
    if "edges" in tables:
        return False
    for required in ("sentences", "nodes", "node_mentions", "node_categories",
                     "aliases", "unresolved_tokens", "posts"):
        if required not in tables:
            return False
    nc_cols = _get_cols(conn, "node_categories")
    al_cols = _get_cols(conn, "aliases")
    return "origin" not in nc_cols or "origin" not in al_cols


def _migrate_add_origin_columns(db_path: str) -> None:
    """node_categories / aliases 에 origin 컬럼 추가 (기본값 'user')."""
    backup = _backup_db(db_path)
    print(f"[db] v15 origin 컬럼 추가 마이그레이션. 백업={backup}")
    conn = sqlite3.connect(db_path)
    try:
        nc_cols = _get_cols(conn, "node_categories")
        al_cols = _get_cols(conn, "aliases")
        if "origin" not in nc_cols:
            conn.execute(
                "ALTER TABLE node_categories "
                "ADD COLUMN origin TEXT NOT NULL DEFAULT 'user'"
            )
        if "origin" not in al_cols:
            conn.execute(
                "ALTER TABLE aliases "
                "ADD COLUMN origin TEXT NOT NULL DEFAULT 'user'"
            )
        conn.commit()
    finally:
        conn.close()


def _backup_db(db_path: str) -> str:
    """DB 파일을 타임스탬프 붙여 복사."""
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    backup_path = f"{db_path}.backup-{timestamp}"
    shutil.copy2(db_path, backup_path)
    return backup_path


def _can_migrate_v14_to_v15(conn: sqlite3.Connection) -> bool:
    """edges 테이블만 제거하면 v15 스키마와 일치하는지 확인."""
    tables = _get_tables(conn)
    if "edges" not in tables:
        return False
    for required in ("sentences", "nodes", "node_mentions", "node_categories",
                     "aliases", "unresolved_tokens", "posts"):
        if required not in tables:
            return False
    if "category" in _get_cols(conn, "nodes"):
        return False
    sent_cols = _get_cols(conn, "sentences")
    for required_col in ("role", "post_id", "position"):
        if required_col not in sent_cols:
            return False
    if "retention" in sent_cols:
        return False
    return True


def _migrate_v14_to_v15(db_path: str) -> None:
    """edges 테이블 DROP. 다른 테이블은 그대로 보존. 백업 먼저."""
    backup = _backup_db(db_path)
    print(f"[db] v14 → v15 마이그레이션: edges 테이블 DROP. 백업={backup}")
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            DROP INDEX IF EXISTS idx_edges_src;
            DROP INDEX IF EXISTS idx_edges_tgt;
            DROP INDEX IF EXISTS idx_edges_sentence;
            DROP TABLE IF EXISTS edges;
        """)
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str = DB_PATH) -> str:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        try:
            # v14 → v15 무손실 마이그레이션: edges 테이블만 제거
            if _can_migrate_v14_to_v15(conn):
                conn.close()
                conn = None
                _migrate_v14_to_v15(db_path)
                conn = sqlite3.connect(db_path)
            # origin 컬럼만 빠진 경우 무손실 ALTER 추가
            if conn is not None and _can_add_origin_columns(conn):
                conn.close()
                conn = None
                _migrate_add_origin_columns(db_path)
                conn = sqlite3.connect(db_path)
            # 그래도 v15 스키마가 아니면 구형 DB로 판정 → 백업 후 재생성
            if not _is_current_schema(conn):
                conn.close()
                conn = None
                backup = _backup_db(db_path)
                os.remove(db_path)
                print(f"[db] 구 스키마 감지 → 백업({backup}) 후 v15 재생성: {db_path}")
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
