import initSqlJs, { type Database as SqlJsDatabase } from 'sql.js';
import type { DbAdapter } from './types.js';

const SCHEMA = `
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
CREATE INDEX IF NOT EXISTS idx_aliases ON aliases(alias);
`;

export interface SqlJsAdapterOptions {
  wasmUrl?: string;
  data?: ArrayLike<number>;
  onSave?: (data: Uint8Array) => void;
}

export class SqlJsAdapter implements DbAdapter {
  private db!: SqlJsDatabase;
  private onSave?: (data: Uint8Array) => void;

  private constructor() {}

  static async create(options: SqlJsAdapterOptions = {}): Promise<SqlJsAdapter> {
    const adapter = new SqlJsAdapter();
    const SQL = await initSqlJs({
      locateFile: (file: string) => options.wasmUrl ?? `https://sql.js.org/dist/${file}`,
    });

    adapter.db = options.data ? new SQL.Database(options.data) : new SQL.Database();
    adapter.onSave = options.onSave;

    adapter.exec('PRAGMA foreign_keys = ON');
    adapter.exec(SCHEMA);

    return adapter;
  }

  exec(sql: string): void {
    this.db.run(sql);
  }

  run(sql: string, ...params: unknown[]): { lastInsertRowid: number | bigint } {
    this.db.run(sql, params as any[]);
    const row = this.db.exec('SELECT last_insert_rowid() as id');
    const id = row.length > 0 ? (row[0].values[0][0] as number) : 0;
    return { lastInsertRowid: id };
  }

  get<T = Record<string, unknown>>(sql: string, ...params: unknown[]): T | undefined {
    const stmt = this.db.prepare(sql);
    stmt.bind(params as any[]);
    if (stmt.step()) {
      const columns = stmt.getColumnNames();
      const values = stmt.get();
      const row: Record<string, unknown> = {};
      for (let i = 0; i < columns.length; i++) {
        row[columns[i]] = values[i];
      }
      stmt.free();
      return row as T;
    }
    stmt.free();
    return undefined;
  }

  all<T = Record<string, unknown>>(sql: string, ...params: unknown[]): T[] {
    const stmt = this.db.prepare(sql);
    stmt.bind(params as any[]);
    const results: T[] = [];
    const columns = stmt.getColumnNames();
    while (stmt.step()) {
      const values = stmt.get();
      const row: Record<string, unknown> = {};
      for (let i = 0; i < columns.length; i++) {
        row[columns[i]] = values[i];
      }
      results.push(row as T);
    }
    stmt.free();
    return results;
  }

  export(): Uint8Array {
    return this.db.export();
  }

  save(): void {
    if (this.onSave) {
      this.onSave(this.export());
    }
  }

  close(): void {
    this.save();
    this.db.close();
  }
}
