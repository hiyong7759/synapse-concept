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
  retention: string;
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
};
