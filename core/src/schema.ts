export const SCHEMA = `
CREATE TABLE IF NOT EXISTS nodes (
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

CREATE TABLE IF NOT EXISTS edges (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_node_id  INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    target_node_id  INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    type            TEXT NOT NULL,
    label           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    last_used       TEXT,
    UNIQUE(source_node_id, target_node_id, type)
);

CREATE TABLE IF NOT EXISTS aliases (
    alias   TEXT NOT NULL,
    node_id INTEGER NOT NULL,
    PRIMARY KEY (alias, node_id),
    FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE
);

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

CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_domain ON nodes(domain);
CREATE INDEX IF NOT EXISTS idx_nodes_status ON nodes(status);
CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_pair ON edges(source_node_id, target_node_id);
CREATE INDEX IF NOT EXISTS idx_aliases ON aliases(alias);
`;
