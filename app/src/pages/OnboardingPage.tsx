import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Message } from '../types';
import { api } from '../api';
import { uid } from '../utils';
import { BubbleAI } from '../components/Chat/BubbleAI';
import { BubbleUser } from '../components/Chat/BubbleUser';
import { BFSLoader } from '../components/Chat/BFSLoader';
import { InputArea } from '../components/Chat/InputArea';
import styles from './OnboardingPage.module.css';

// ── 0. 환영 화면 ──────────────────────────────────────────────
function StepWelcome({ onNext }: { onNext: () => void }) {
  return (
    <div className={styles.welcome}>
      <div className={styles.welcomeDivider} />
      <div className={styles.welcomeLogo}>Synapse</div>
      <div className={styles.welcomeTagline}>나의 맥락을 매번 설명하지 않아도 되는 세상</div>
      <button className={styles.welcomeBtn} onClick={onNext}>시작하기</button>
      <div className={styles.welcomePrivacy}>
        <span>🔒</span>
        <span>데이터는 이 기기에만 저장됩니다</span>
      </div>
      <div className={styles.welcomeDivider} />
    </div>
  );
}

// ── 비서 질문 채팅 (대화형 온보딩) ────────────────────────────
const now = () => new Date().toISOString();

const INITIAL_MESSAGES: Message[] = [
  { id: 'init-0', type: 'ai', text: '안녕하세요! 몇 가지만 여쭤볼게요.\n이름이 어떻게 되세요?', createdAt: new Date().toISOString() },
];

function StepChat({ onDone, onBack }: { onDone: () => void; onBack: () => void }) {
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [loading, setLoading] = useState(false);
  const [saveCount, setSaveCount] = useState(0);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = useCallback(async (text: string) => {
    const searchingId = uid();
    setMessages(prev => [
      ...prev,
      { id: uid(), type: 'user', text, createdAt: now() },
      { id: searchingId, type: 'searching' },
    ]);
    setLoading(true);

    try {
      const res = await api.chat(text);
      setMessages(prev => prev.filter(m => m.id !== searchingId));

      if (res.save && res.save.triples_added.length > 0) {
        const count = saveCount + 1;
        setSaveCount(count);

        const names = res.save.nodes_added;
        const confirmText = names.length > 0
          ? `${names.join(', ')} 기억했어요.`
          : '기억했어요.';

        if (count >= 3) {
          setMessages(prev => [
            ...prev,
            { id: uid(), type: 'ai', text: `${confirmText}\n\n기본 정보 입력이 완료됐어요. 이제 채팅을 시작해볼까요?`, createdAt: now() },
          ]);
        } else {
          const followUps = ['직업은 어떻게 되세요?', '주로 어디에 사세요?', '관심사나 취미가 있으신가요?'];
          const next = followUps[count - 1] ?? '더 궁금한 게 있으시면 말씀해 주세요.';
          setMessages(prev => [
            ...prev,
            { id: uid(), type: 'ai', text: `${confirmText}\n${next}`, createdAt: now() },
          ]);
        }
      } else if (res.question) {
        setMessages(prev => [...prev, { id: uid(), type: 'ai', text: res.question!, createdAt: now() }]);
      } else if (res.answer) {
        setMessages(prev => [...prev, { id: uid(), type: 'ai', text: res.answer!, createdAt: now() }]);
      } else {
        setMessages(prev => [...prev, { id: uid(), type: 'ai', text: '좋아요, 계속 말씀해 주세요.', createdAt: now() }]);
      }
    } catch {
      setMessages(prev => [
        ...prev.filter(m => m.id !== searchingId),
        { id: uid(), type: 'ai', text: '서버 연결 실패. API 서버가 실행 중인지 확인해 주세요.', createdAt: now() },
      ]);
    } finally {
      setLoading(false);
    }
  }, [saveCount]);

  return (
    <>
      <div className={styles.header}>
        <button className={styles.backBtn} onClick={onBack}>←</button>
        <span className={styles.headerTitle}>온보딩</span>
      </div>

      <div className={styles.chatArea}>
        {messages.map(msg => {
          switch (msg.type) {
            case 'ai': return <BubbleAI key={msg.id} text={msg.text} />;
            case 'user': return <BubbleUser key={msg.id} text={msg.text} />;
            case 'searching': return <BFSLoader key={msg.id} />;
            default: return null;
          }
        })}
        <div ref={bottomRef} />
      </div>

      <div className={styles.progress} style={{ padding: '8px 0' }}>
        <div className={styles.dot} />
        <div className={styles.dot} />
        <div className={[styles.dot, styles.dotActive].join(' ')} />
      </div>

      {saveCount >= 3 ? (
        <div style={{ padding: '0 16px 16px' }}>
          <button className={styles.primaryBtn} style={{ width: '100%' }} onClick={onDone}>
            채팅 시작하기 →
          </button>
        </div>
      ) : (
        <>
          <InputArea onSend={handleSend} disabled={loading} />
        </>
      )}
    </>
  );
}

// ── OnboardingPage ─────────────────────────────────────────────
type Step = 'welcome' | 'chat';

export function OnboardingPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>('welcome');

  function handleDone() {
    navigate('/chat/new');
  }

  return (
    <div className={styles.page}>
      {step === 'welcome' && <StepWelcome onNext={() => setStep('chat')} />}
      {step === 'chat' && <StepChat onDone={handleDone} onBack={() => setStep('welcome')} />}
    </div>
  );
}
