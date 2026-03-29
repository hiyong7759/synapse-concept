import { BetterSqliteAdapter } from './db-adapter.js';
import { GraphStore } from './graph-store.js';
import { GraphSearch } from './graph-search.js';
import type { DbAdapter } from './types.js';

export class Synapse {
  public store: GraphStore;
  public search: GraphSearch;

  constructor(private db: DbAdapter) {
    this.store = new GraphStore(db);
    this.search = new GraphSearch(db);
  }

  close(): void {
    this.db.close();
  }
}

export function createSynapse(dbPath: string): Synapse {
  const adapter = new BetterSqliteAdapter(dbPath);
  return new Synapse(adapter);
}

export { GraphStore } from './graph-store.js';
export { GraphSearch } from './graph-search.js';
export { BetterSqliteAdapter } from './db-adapter.js';
export { SqlJsAdapter } from './sql-js-adapter.js';
export type { SqlJsAdapterOptions } from './sql-js-adapter.js';
export { formatPrompt } from './prompt-builder.js';
export type * from './types.js';
