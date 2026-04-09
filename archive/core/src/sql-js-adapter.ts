import initSqlJs, { type Database as SqlJsDatabase } from 'sql.js';
import type { DbAdapter } from './types.js';
import { SCHEMA } from './schema.js';

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
