import Database from 'better-sqlite3';
import type { DbAdapter } from './types.js';
import { SCHEMA } from './schema.js';

export class BetterSqliteAdapter implements DbAdapter {
  private db: Database.Database;

  constructor(dbPath: string) {
    this.db = new Database(dbPath);
    this.db.pragma('journal_mode = WAL');
    this.db.pragma('foreign_keys = ON');
    this.db.exec(SCHEMA);
  }

  exec(sql: string): void {
    this.db.exec(sql);
  }

  run(sql: string, ...params: unknown[]): { lastInsertRowid: number | bigint } {
    const stmt = this.db.prepare(sql);
    const result = stmt.run(...params);
    return { lastInsertRowid: result.lastInsertRowid };
  }

  get<T = Record<string, unknown>>(sql: string, ...params: unknown[]): T | undefined {
    const stmt = this.db.prepare(sql);
    return stmt.get(...params) as T | undefined;
  }

  all<T = Record<string, unknown>>(sql: string, ...params: unknown[]): T[] {
    const stmt = this.db.prepare(sql);
    return stmt.all(...params) as T[];
  }

  close(): void {
    this.db.close();
  }
}
