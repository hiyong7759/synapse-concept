import type { ChatResponse, HistoryItem, NodeItem, EdgeItem, StatsResponse } from './types';

const BASE = 'http://localhost:8000';

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

async function put<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

async function del<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: 'DELETE' });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

export interface SentenceItem {
  id: number;
  text: string;
  role: 'user' | 'assistant';
  created_at: string;
}

export interface SentencesResponse {
  total: number;
  offset: number;
  limit: number;
  items: SentenceItem[];
}

export interface SentenceImpact {
  sentence_id: number;
  affected_edges: { id: number; source: string; label: string | null; target: string }[];
}

export interface NodeCategoriesResponse {
  node_id: number;
  node_name: string;
  categories: { category: string; created_at: string }[];
}

export interface CategoryItem {
  category: string;
  node_count: number;
}

// /review 섹션별 응답
export interface ReviewUnresolvedItem {
  sentence_id: number;
  token: string;
  sentence_text: string;
  post_id: number | null;
  post_position: number;
  post_markdown: string;
  post_created_at: string | null;
  question: string;
  options: string[];
  allow_free_input: boolean;
}

export interface ReviewUncategorizedItem {
  node_id: number;
  node_name: string;
  question: string;
  options: string[];
  allow_free_input: boolean;
}

export interface ReviewCooccurItem {
  source_id: number;
  source_name: string;
  target_id: number;
  target_name: string;
  cooccur_count: number;
  sample_sentence: string | null;
  question: string;
  options: string[];
  allow_free_input: boolean;
}

export interface ReviewTypoItem {
  node_a_id: number;
  node_a_name: string;
  node_b_id: number;
  node_b_name: string;
  mention_count_a: number;
  mention_count_b: number;
  question: string;
  options: string[];
}

export interface ReviewStaleItem {
  node_id: number;
  node_name: string;
  updated_at: string;
  mention_count: number;
  question: string;
  options: string[];
}

export interface ReviewGapItem {
  from: string;
  to: string;
  days: number;
  question: string;
  options: string[];
  allow_free_input: boolean;
}

export interface ReviewDailyResponse {
  date: string;
  sentence_count: number;
  sentences: { id: number; text: string; role: string; post_id: number | null; position: number }[];
}

export interface ReviewBasicInfoItem {
  field: string;
  label: string;
  question: string;
  options: string[];
  allow_free_input: boolean;
}

export interface ReviewAllResponse {
  unresolved?: ReviewUnresolvedItem[];
  uncategorized?: ReviewUncategorizedItem[];
  cooccur_pairs?: ReviewCooccurItem[];
  suspected_typos?: ReviewTypoItem[];
  missing_basic_info?: ReviewBasicInfoItem[];
  stale_nodes?: ReviewStaleItem[];
  daily?: ReviewDailyResponse;
  gaps?: ReviewGapItem[];
}

export interface ReviewCount {
  total: number;
  unresolved: number;
  uncategorized: number;
  cooccur_pairs: number;
  suspected_typos: number;
  missing_basic_info: number;
}

export const api = {
  chat: (text: string, images?: string[], history?: HistoryItem[]) =>
    post<ChatResponse>('/chat', { text, images: images ?? [], history: history ?? [] }),
  rollback: (edge_ids: number[], node_ids: number[]) =>
    post<{ edges_deleted: number; nodes_deleted: number }>('/rollback', { edge_ids, node_ids }),
  stats: () => get<StatsResponse>('/stats'),
  nodes: () => get<NodeItem[]>('/nodes'),
  edges: () => get<EdgeItem[]>('/edges'),

  // 대화 탐색
  sentences: (params: { q?: string; date_from?: string; date_to?: string; role?: string; offset?: number; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    if (params.date_from) qs.set('date_from', params.date_from);
    if (params.date_to) qs.set('date_to', params.date_to);
    if (params.role) qs.set('role', params.role);
    if (params.offset) qs.set('offset', String(params.offset));
    if (params.limit) qs.set('limit', String(params.limit));
    return get<SentencesResponse>(`/sentences?${qs.toString()}`);
  },
  sentenceImpact: (id: number) => get<SentenceImpact>(`/sentences/${id}/impact`),
  sentenceUpdate: (id: number, text: string) => put<unknown>(`/sentences/${id}`, { text }),
  sentenceDelete: (id: number) => del<unknown>(`/sentences/${id}`),

  // 카테고리 편집 (Phase 4)
  nodeCategories: (nodeId: number) => get<NodeCategoriesResponse>(`/nodes/${nodeId}/categories`),
  categoryAdd: (nodeId: number, category: string) =>
    post<{ ok: boolean }>(`/nodes/${nodeId}/categories`, { category }),
  categoryRemove: (nodeId: number, category: string) =>
    del<{ ok: boolean }>(`/nodes/${nodeId}/categories/${encodeURIComponent(category)}`),
  categoryRename: (nodeId: number, from: string, to: string) =>
    put<{ ok: boolean }>(`/nodes/${nodeId}/categories`, { from, to }),
  categoriesAll: () => get<CategoryItem[]>('/categories'),

  // /review (Phase 5)
  review: (sections?: string[]) => {
    const qs = sections && sections.length ? `?sections=${sections.join(',')}` : '';
    return get<ReviewAllResponse>(`/review${qs}`);
  },
  reviewCount: () => get<ReviewCount>('/review/count'),
  reviewAliasSuggestions: (nodeId: number) =>
    get<{ node_id: number; node_name: string; question: string; options: string[]; allow_free_input: boolean }>(
      `/review/alias-suggestions/${nodeId}`,
    ),
  reviewApply: (type: string, params: Record<string, unknown>) =>
    post<{ ok: boolean; [k: string]: unknown }>(`/review/apply`, { type, params }),
};
