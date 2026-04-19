export interface HistoryItem {
  role: 'user' | 'assistant';
  content: string;
}

export interface SaveResponse {
  // v15: 게시물 단위 저장. edges 테이블 폐기로 관련 필드 제거.
  post_id: number | null;
  nodes_added: string[];
  node_ids_added: number[];
  mentions_added: number;
  nodes_deactivated: string[];  // v15: 상태변경된 노드 식별자
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

/**
 * v15 하이퍼엣지 — 여러 노드를 동시에 묶는 바구니.
 * kind='sentence': 같은 문장에 공출현 / kind='category': 같은 카테고리 공유
 */
export interface Hyperedge {
  kind: 'sentence' | 'category';
  label: string;                // 문장 원문 또는 카테고리 경로
  node_ids: number[];
  node_names: string[];
  sentence_id?: number;         // kind='sentence'일 때
  category?: string;            // kind='category'일 때
}

export interface HyperedgesResponse {
  sentence_baskets: Hyperedge[];
  category_baskets: Hyperedge[];
}

export interface StatsResponse {
  nodes_total: number;
  nodes_active: number;
  node_mentions_total: number;
  categories_total: number;
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
