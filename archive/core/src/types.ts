export interface Node {
  id: number;
  name: string;
  domain: string;
  status: 'active' | 'inactive';
  source: 'user' | 'ai';
  weight: number;
  safety: 0 | 1;
  safety_rule: string | null;
  created_at: string;
  updated_at: string;
}

export interface Edge {
  id: number;
  source_node_id: number;
  target_node_id: number;
  type: string;
  label: string | null;
  created_at: string;
  last_used: string | null;
}

export interface EdgeWithNames extends Edge {
  source_name: string;
  target_name: string;
}

export interface Alias {
  alias: string;
  node_id: number;
}

export interface Filter {
  id: string;
  name: string;
}

export interface FilterRule {
  filter_id: string;
  domain: string | null;
  node_id: number | null;
  action: 'exclude';
}

export interface SubgraphResult {
  start_nodes: string[];
  nodes: Node[];
  edges: EdgeWithNames[];
  safety_nodes: Node[];
  missing: string[];
}

export interface ContextResult {
  status: 'ok';
  prompt: string;
  nodes_used: string[];
  safety_nodes: string[];
  node_count: number;
  edge_count: number;
  missing?: string[];
}

export interface AddNodeInput {
  name: string;
  domain?: string;
  source?: 'user' | 'ai';
  safety?: boolean;
  safety_rule?: string;
}

export interface AddEdgeInput {
  source: string;
  target: string;
  type?: string;
  label?: string;
}

export interface BatchInput {
  nodes?: AddNodeInput[];
  edges?: AddEdgeInput[];
}

export interface BatchResult {
  status: 'ok';
  nodes_added: number;
  edges_added: number;
  nodes: { id: number; name: string; is_new: boolean }[];
  edges: { source: string; target: string; type: string; label: string | null }[];
}

export interface ListNodesFilter {
  domain?: string;
  status?: string;
  search?: string;
  limit?: number;
}

export interface DomainSummary {
  domain: string;
  count: number;
}

export interface ShowNodeResult {
  status: 'ok';
  node: Node;
  edges: EdgeWithNames[];
}

export interface DeactivateResult {
  status: 'ok';
  node: string;
  new_status: 'inactive';
  orphans?: string[];
  message?: string;
}

export interface DbAdapter {
  exec(sql: string): void;
  run(sql: string, ...params: unknown[]): { lastInsertRowid: number | bigint };
  get<T = Record<string, unknown>>(sql: string, ...params: unknown[]): T | undefined;
  all<T = Record<string, unknown>>(sql: string, ...params: unknown[]): T[];
  close(): void;
}
