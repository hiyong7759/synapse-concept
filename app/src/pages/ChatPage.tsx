import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import type { Message, HistoryItem } from '../types';
import { api } from '../api';
import { getSession, saveSession, createSession, deriveTitle } from '../session';
import { uid } from '../utils';
import { BubbleAI } from '../components/Chat/BubbleAI';
import { BubbleUser } from '../components/Chat/BubbleUser';
import { ChangeNotice } from '../components/Chat/ChangeNotice';
import { BFSLoader } from '../components/Chat/BFSLoader';
import { ResultCard } from '../components/Chat/ResultCard';
import { InputArea } from '../components/Chat/InputArea';
import styles from '../components/Chat/Chat.module.css';
import pageStyles from './ChatPage.module.css';

function buildHistory(messages: Message[]): HistoryItem[] {
  const items: HistoryItem[] = [];
  for (const m of messages) {
    if (m.type === 'user' && m.text) items.push({ role: 'user', content: m.text });
    else if (m.type === 'ai') items.push({ role: 'assistant', content: m.text });
  }
  return items;
}

const INITIAL_AI: Message = { id: 'init', type: 'ai', text: '안녕하세요. 무엇이든 말씀해 주세요.' };

export function ChatPage() {
  const navigate = useNavigate();
  const { sessionId } = useParams<{ sessionId: string }>();

  // 세션 로드 (없으면 새로 생성)
  const [sessionIdState] = useState<string>(() => {
    if (sessionId) return sessionId;
    const s = createSession();
    saveSession(s);
    return s.id;
  });

  const [messages, setMessages] = useState<Message[]>(() => {
    const s = getSession(sessionIdState);
    return s && s.messages.length > 0 ? s.messages : [INITIAL_AI];
  });

  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  // 메시지 변경 시 세션 자동 저장
  useEffect(() => {
    const s = getSession(sessionIdState);
    if (!s) return;
    const updated = {
      ...s,
      messages,
      title: deriveTitle(messages),
      updatedAt: new Date().toISOString(),
    };
    saveSession(updated);
  }, [messages, sessionIdState]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const dismissMessage = useCallback((id: string) => {
    setMessages(prev => prev.filter(m => m.id !== id));
  }, []);

  async function handleSend(text: string, images?: string[]) {
    const userMsg: Message = { id: uid(), type: 'user', text, images };
    const searchingId = uid();
    const history = buildHistory(messagesRef.current);

    const loaderMode = images && images.length > 0 ? 'save' : 'retrieve';
    setMessages(prev => [...prev, userMsg, { id: searchingId, type: 'searching', loaderMode }]);
    setLoading(true);

    try {
      const res = await api.chat(text, images, history);
      setMessages(prev => prev.filter(m => m.id !== searchingId));

      if (res.mode === 'save' && res.save) {
        setMessages(prev => [...prev, { id: uid(), type: 'change_notice', save: res.save! }]);
      } else if (res.mode === 'retrieve' && res.retrieve) {
        setMessages(prev => [
          ...prev,
          { id: uid(), type: 'retrieve_result', retrieve: res.retrieve! },
          ...(res.retrieve!.answer
            ? [{ id: uid(), type: 'ai' as const, text: res.retrieve!.answer! }]
            : []),
        ]);
      } else if (res.mode === 'clarify' && res.question) {
        setMessages(prev => [...prev, { id: uid(), type: 'clarify', question: res.question! }]);
      }
    } catch {
      setMessages(prev => [
        ...prev.filter(m => m.id !== searchingId),
        { id: uid(), type: 'ai', text: '서버 연결 실패. API 서버가 실행 중인지 확인하세요.' },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={pageStyles.page}>
      {/* 상단 바 */}
      <div className={styles.topbar}>
        <button className={styles.topbarBtn} onClick={() => navigate('/')}>← 목록</button>
        <div className={styles.topbarLogo}>Synapse</div>
        <div className={styles.topbarActions}>
          <button className={styles.topbarBtn} onClick={() => navigate('/graph')}>⬡ 그래프</button>
        </div>
      </div>

      {/* 채팅 영역 */}
      <div className={styles.chatArea}>
        {messages.map(msg => {
          switch (msg.type) {
            case 'ai':
              return <BubbleAI key={msg.id} text={msg.text} />;
            case 'user':
              return <BubbleUser key={msg.id} text={msg.text} images={msg.images} />;
            case 'change_notice':
              return <ChangeNotice key={msg.id} save={msg.save} onDismiss={() => dismissMessage(msg.id)} />;
            case 'retrieve_result':
              return <ResultCard key={msg.id} retrieve={msg.retrieve} />;
            case 'clarify':
              return <BubbleAI key={msg.id} text={msg.question} />;
            case 'searching':
              return <BFSLoader key={msg.id} mode={msg.loaderMode} />;
          }
        })}
        <div ref={bottomRef} />
      </div>

      <InputArea onSend={handleSend} disabled={loading} />
    </div>
  );
}
