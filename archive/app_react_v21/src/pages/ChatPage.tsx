import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Message, HistoryItem } from '../types';
import { api } from '../api';
import { uid } from '../utils';
import { BubbleAI } from '../components/Chat/BubbleAI';
import { BubbleUser } from '../components/Chat/BubbleUser';
import { ChangeNotice } from '../components/Chat/ChangeNotice';
import { MarkdownDraftCard } from '../components/Chat/MarkdownDraftCard';
import { ReviewBadge } from '../components/ReviewBadge';
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

const INITIAL_AI: Message = { id: 'init', type: 'ai', text: '안녕하세요. 무엇이든 말씀해 주세요.', createdAt: new Date().toISOString() };

export function ChatPage() {
  const navigate = useNavigate();

  const [messages, setMessages] = useState<Message[]>([INITIAL_AI]);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const dismissMessage = useCallback((id: string) => {
    setMessages(prev => prev.filter(m => m.id !== id));
  }, []);

  async function handleSend(text: string, images?: string[]) {
    const now = new Date().toISOString();
    const userMsg: Message = { id: uid(), type: 'user', text, images, createdAt: now };
    const searchingId = uid();
    const history = buildHistory(messagesRef.current);

    setMessages(prev => [...prev, userMsg, { id: searchingId, type: 'searching' }]);
    setLoading(true);

    try {
      const res = await api.chat(text, images, history);
      const responseTime = new Date().toISOString();
      setMessages(prev => prev.filter(m => m.id !== searchingId));

      // 통합 파이프라인: save + retrieve + answer가 함께 올 수 있음
      if (res.question) {
        // 모호성 되물음
        setMessages(prev => [...prev, { id: uid(), type: 'clarify', question: res.question!, createdAt: responseTime }]);
      } else if (res.markdown_draft) {
        // v12: structure-suggest 초안 반환 → 사용자 확정 대기
        setMessages(prev => [
          ...prev,
          {
            id: uid(),
            type: 'markdown_draft',
            draft: res.markdown_draft!,
            originalText: text,
            images,
            createdAt: responseTime,
          },
        ]);
      } else {
        const newMsgs: Message[] = [];

        // 인출 결과 표시
        if (res.retrieve && res.retrieve.context_triples.length > 0) {
          newMsgs.push({ id: uid(), type: 'retrieve_result', retrieve: res.retrieve, createdAt: responseTime });
        }

        // 저장 변경 알림 (v12: nodes_added / mentions_added / edges_deactivated 중 하나라도 있으면)
        if (
          res.save &&
          (res.save.nodes_added.length > 0 ||
            res.save.mentions_added > 0 ||
            res.save.edges_deactivated.length > 0)
        ) {
          newMsgs.push({ id: uid(), type: 'change_notice', save: res.save, createdAt: responseTime });
        }

        // 비서 답변
        if (res.answer) {
          newMsgs.push({ id: uid(), type: 'ai', text: res.answer, createdAt: responseTime });
        }

        if (newMsgs.length > 0) {
          setMessages(prev => [...prev, ...newMsgs]);
        }
      }
    } catch {
      setMessages(prev => [
        ...prev.filter(m => m.id !== searchingId),
        { id: uid(), type: 'ai', text: '서버 연결 실패. API 서버가 실행 중인지 확인하세요.', createdAt: new Date().toISOString() },
      ]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={pageStyles.page}>
      {/* 상단 바 */}
      <div className={styles.topbar}>
        <button className={styles.topbarBtn} onClick={() => navigate('/')}>← 탐색</button>
        <div className={styles.topbarLogo}>SYNAPSE</div>
        <div className={styles.topbarActions}>
          <ReviewBadge />
          <button className={styles.topbarBtn} onClick={() => navigate('/hypergraph')}>하이퍼그래프</button>
        </div>
      </div>

      {/* 채팅 영역 */}
      <div className={styles.chatArea}>
        {messages.map(msg => {
          switch (msg.type) {
            case 'ai':
              return <BubbleAI key={msg.id} text={msg.text} createdAt={msg.createdAt} />;
            case 'user':
              return <BubbleUser key={msg.id} text={msg.text} images={msg.images} createdAt={msg.createdAt} />;
            case 'change_notice':
              return <ChangeNotice key={msg.id} save={msg.save} onDismiss={() => dismissMessage(msg.id)} />;
            case 'retrieve_result':
              return <ResultCard key={msg.id} retrieve={msg.retrieve} />;
            case 'clarify':
              return <BubbleAI key={msg.id} text={msg.question} createdAt={msg.createdAt} />;
            case 'markdown_draft':
              return (
                <MarkdownDraftCard
                  key={msg.id}
                  draft={msg.draft}
                  originalText={msg.originalText}
                  images={msg.images}
                  onDismiss={() => dismissMessage(msg.id)}
                  onConfirm={(md, imgs) => {
                    dismissMessage(msg.id);
                    handleSend(md, imgs);
                  }}
                />
              );
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
