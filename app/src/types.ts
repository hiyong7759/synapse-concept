export interface HistoryItem {
  role: 'user' | 'assistant';
  content: string;
}

export interface SaveResponse {
  // v12: 게시물 단위 저장 (post_id). 엣지·별칭 자동 생성 없음
  post_id: number | null;
  nodes_added: string[];
  node_ids_added: number[];
  mentions_added: number;
  edges_deactivated: [string, string | null, string][];
  // 하위 호환 필드 (항상 빈 배열)
  triples_added: [string, string | null, string][];
  edge_ids_added: number[];
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
  markdown_draft?: string;  // v12: structure-suggest 초안 (저장 보류)
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
  | { id: string; type: 'markdown_draft'; draft: string; originalText: string; images?: string[]; createdAt: string }
  | { id: string; type: 'searching'; loaderMode?: 'save' | 'retrieve' };
