export interface HistoryItem {
  role: 'user' | 'assistant';
  content: string;
}

export interface SaveResponse {
  triples_added: [string, string | null, string][];
  edge_ids_added: number[];
  nodes_added: string[];
  node_ids_added: number[];
  edges_deactivated: [string, string | null, string][];
  aliases_added: [string, string][];
}

export interface RetrieveResponse {
  start_nodes: string[];
  context_triples: [string, string | null, string][];
}

export interface ChatResponse {
  save?: SaveResponse;
  retrieve?: RetrieveResponse;
  answer?: string;
  question?: string;
}

export interface NodeItem {
  id: number;
  name: string;
  status: string;
  degree: number;
}

export interface EdgeItem {
  id: number;
  source_id: number;
  source_name: string;
  target_id: number;
  target_name: string;
  label: string | null;
}

export interface StatsResponse {
  nodes_total: number;
  nodes_active: number;
  edges_total: number;
  aliases_total: number;
}

export type Message =
  | { id: string; type: 'ai'; text: string; createdAt: string }
  | { id: string; type: 'user'; text: string; images?: string[]; createdAt: string }
  | { id: string; type: 'change_notice'; save: SaveResponse; createdAt: string }
  | { id: string; type: 'retrieve_result'; retrieve: RetrieveResponse; createdAt: string }
  | { id: string; type: 'clarify'; question: string; createdAt: string }
  | { id: string; type: 'searching'; loaderMode?: 'save' | 'retrieve' };
