import type { ChatSession, Message } from './types';

const STORAGE_KEY = 'synapse_sessions';

let _cache: ChatSession[] | null = null;

export function loadSessions(): ChatSession[] {
  if (_cache !== null) return _cache;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    _cache = raw ? JSON.parse(raw) : [];
    return _cache!;
  } catch {
    return (_cache = []);
  }
}

function stripImages(messages: Message[]): Message[] {
  return messages.map(m =>
    m.type === 'user' && m.images?.length ? { ...m, images: [] } : m
  );
}

export function saveSession(session: ChatSession): void {
  const sessions = loadSessions();
  const slim = { ...session, messages: stripImages(session.messages) };
  const idx = sessions.findIndex(s => s.id === session.id);
  if (idx >= 0) {
    sessions[idx] = slim;
  } else {
    sessions.unshift(slim); // 최신 세션을 맨 앞에
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  } catch {
    // quota 초과 시 가장 오래된 세션 제거 후 재시도
    sessions.splice(Math.floor(sessions.length / 2));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  }
  _cache = sessions;
}

export function deleteSession(id: string): void {
  const sessions = loadSessions().filter(s => s.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
  _cache = sessions;
}

export function getSession(id: string): ChatSession | null {
  return loadSessions().find(s => s.id === id) ?? null;
}

export function createSession(): ChatSession {
  const now = new Date().toISOString();
  return {
    id: Math.random().toString(36).slice(2) + Date.now().toString(36),
    title: '새 대화',
    messages: [],
    createdAt: now,
    updatedAt: now,
  };
}

export function deriveTitle(messages: Message[]): string {
  const first = messages.find(m => m.type === 'user' && m.text);
  if (!first || first.type !== 'user') return '새 대화';
  const text = first.text.trim().replace(/\n/g, ' ');
  return text.length > 30 ? text.slice(0, 30) + '…' : text;
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const diff = now.getTime() - d.getTime();
  const minutes = Math.floor(diff / 60000);
  const hours = Math.floor(diff / 3600000);
  const days = Math.floor(diff / 86400000);

  if (minutes < 1) return '방금 전';
  if (minutes < 60) return `${minutes}분 전`;
  if (hours < 24) return `${hours}시간 전`;
  if (days < 7) return `${days}일 전`;
  return d.toLocaleDateString('ko-KR', { month: 'short', day: 'numeric' });
}
