#!/usr/bin/env python3
"""Synapse DB 초기화 — SQLite 스키마 생성 + 기본 설정."""

import sqlite3
import os
import sys
import json

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'synapse.db')

SCHEMA = """
-- 노드: 수평한 단어/개념
CREATE TABLE IF NOT EXISTS nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    sid         TEXT UNIQUE,
    name        TEXT NOT NULL,
    domain      TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'inactive', 'deleted')),
    source      TEXT NOT NULL DEFAULT 'user' CHECK(source IN ('user', 'ai')),
    weight      INTEGER NOT NULL DEFAULT 0,
    safety      INTEGER NOT NULL DEFAULT 0,
    safety_rule TEXT,
    confidence  REAL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 엣지: 노드 사이의 연결 (개인 데이터)
-- type은 영어 관계명 (belong_to, role, skill, same, similar 등)
CREATE TABLE IF NOT EXISTS edges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id  INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    target_node_id  INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    type            TEXT NOT NULL,
    label           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_node_id, target_node_id, type)
);

-- 노출 원장: LLM에 전달된 이력
CREATE TABLE IF NOT EXISTS exposure_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    direction   TEXT NOT NULL CHECK(direction IN ('out', 'in')),
    target      TEXT NOT NULL CHECK(target IN ('structuring', 'lens', 'intake')),
    provider    TEXT NOT NULL DEFAULT 'anthropic',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_domain ON nodes(domain);
CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(status);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_exposure_node ON exposure_log(node_id);
"""


def init_db(db_path: str = DB_PATH) -> str:
    """DB 초기화. 이미 존재하면 스키마만 보장."""
    db_path = os.path.abspath(db_path)
    is_new = not os.path.exists(db_path)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.close()
    if is_new:
        os.chmod(db_path, 0o600)
    return db_path


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """DB 연결 반환. 없으면 자동 초기화."""
    db_path = os.path.abspath(db_path)
    if not os.path.exists(db_path):
        init_db(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_stats(db_path: str = DB_PATH) -> dict:
    """DB 통계 반환."""
    conn = get_connection(db_path)
    nodes_total = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
    nodes_active = conn.execute("SELECT COUNT(*) FROM nodes WHERE status = 'active'").fetchone()[0]
    edges_total = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    domains = conn.execute("SELECT DISTINCT domain FROM nodes WHERE status = 'active' AND domain != ''").fetchall()
    conn.close()
    return {
        "nodes_total": nodes_total,
        "nodes_active": nodes_active,
        "edges_total": edges_total,
        "domains": [r[0] for r in domains],
    }


if __name__ == "__main__":
    path = init_db()
    stats = get_stats()
    print(json.dumps({
        "status": "ok",
        "db_path": path,
        **stats,
    }, ensure_ascii=False, indent=2))
