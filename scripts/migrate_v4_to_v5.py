#!/usr/bin/env python3
"""Synapse DB v4 → v5 migration.

Changes:
  - DROP: nodes.sid, nodes.confidence, exposure_log table
  - CHANGE: nodes.status CHECK (active|inactive|deleted) → (active|inactive)
  - ADD: edges.last_used, aliases table, filters table, filter_rules table
"""

import sqlite3
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from init_db import DB_PATH


def migrate(db_path: str = DB_PATH):
    if not os.path.exists(db_path):
        print(f"DB not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")

    try:
        # 1. Convert status='deleted' → 'inactive'
        deleted_count = conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE status = 'deleted'"
        ).fetchone()[0]
        if deleted_count:
            conn.execute("UPDATE nodes SET status = 'inactive' WHERE status = 'deleted'")
            print(f"  converted {deleted_count} deleted → inactive")

        # 2. Rebuild nodes table (drop sid, confidence, change status CHECK)
        conn.executescript("""
            CREATE TABLE nodes_v5 (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                domain      TEXT NOT NULL DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'inactive')),
                source      TEXT NOT NULL DEFAULT 'user' CHECK(source IN ('user', 'ai')),
                weight      INTEGER NOT NULL DEFAULT 0,
                safety      INTEGER NOT NULL DEFAULT 0,
                safety_rule TEXT,
                created_at  TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            INSERT INTO nodes_v5 (id, name, domain, status, source, weight, safety, safety_rule, created_at, updated_at)
                SELECT id, name, domain, status, source, weight, safety, safety_rule, created_at, updated_at
                FROM nodes;

            DROP TABLE nodes;
            ALTER TABLE nodes_v5 RENAME TO nodes;
        """)
        print("  nodes: dropped sid, confidence, updated status CHECK")

        # 3. Add edges.last_used
        cols = [r[1] for r in conn.execute("PRAGMA table_info(edges)").fetchall()]
        if 'last_used' not in cols:
            conn.execute("ALTER TABLE edges ADD COLUMN last_used TEXT")
            print("  edges: added last_used")

        # 4. Drop exposure_log
        conn.execute("DROP TABLE IF EXISTS exposure_log")
        conn.execute("DROP INDEX IF EXISTS idx_exposure_node")
        print("  dropped exposure_log")

        # 5. Create aliases
        conn.execute("""
            CREATE TABLE IF NOT EXISTS aliases (
                alias   TEXT NOT NULL,
                node_id INTEGER NOT NULL,
                PRIMARY KEY (alias, node_id),
                FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE
            )
        """)
        print("  created aliases table")

        # 6. Create filters + filter_rules
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS filters (
                id   TEXT PRIMARY KEY,
                name TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS filter_rules (
                filter_id TEXT NOT NULL,
                domain    TEXT,
                node_id   INTEGER,
                action    TEXT NOT NULL DEFAULT 'exclude',
                FOREIGN KEY (filter_id) REFERENCES filters(id) ON DELETE CASCADE
            );
        """)
        print("  created filters, filter_rules tables")

        # 7. Recreate indexes
        conn.executescript("""
            CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
            CREATE INDEX IF NOT EXISTS idx_nodes_domain ON nodes(domain);
            CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(status);
            CREATE INDEX IF NOT EXISTS idx_aliases ON aliases(alias);
        """)
        print("  recreated indexes")

        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA integrity_check")
        conn.commit()
        print("migration complete")

    except Exception as e:
        conn.rollback()
        print(f"migration failed: {e}")
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    print(f"migrating: {path}")
    migrate(path)
