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

export const api = {
  chat: (text: string, images?: string[], history?: HistoryItem[]) =>
    post<ChatResponse>('/chat', { text, images: images ?? [], history: history ?? [] }),
  rollback: (edge_ids: number[], node_ids: number[]) =>
    post<{ edges_deleted: number; nodes_deleted: number }>('/rollback', { edge_ids, node_ids }),
  stats: () => get<StatsResponse>('/stats'),
  nodes: () => get<NodeItem[]>('/nodes'),
  edges: () => get<EdgeItem[]>('/edges'),
};
