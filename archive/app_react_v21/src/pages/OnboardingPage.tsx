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

const now = () => new Date().toISOString();

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

// ── 1. 비서 질문 채팅 (기본 정보) ─────────────────────────────
const INITIAL_MESSAGES: Message[] = [
  { id: 'init-0', type: 'ai', text: '안녕하세요! 몇 가지만 여쭤볼게요.\n이름이 어떻게 되세요?', createdAt: new Date().toISOString() },
];

function StepChat({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
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

      // v12: 저장 성공 판정 = 노드 추가 또는 mention 기록
      const saved = !!res.save && (res.save.nodes_added.length > 0 || res.save.mentions_added > 0);

      if (saved && res.save) {
        const count = saveCount + 1;
        setSaveCount(count);

        const names = res.save.nodes_added;
        const confirmText = names.length > 0
          ? `${names.join(', ')} 기억했어요.`
          : '기억했어요.';

        if (count >= 3) {
          setMessages(prev => [
            ...prev,
            { id: uid(), type: 'ai', text: `${confirmText}\n\n기본 정보 입력이 완료됐어요. 이제 어떻게 검색되는지 보여드릴게요.`, createdAt: now() },
          ]);
        } else {
          const followUps = ['직업은 어떻게 되세요?', '주로 어디에 사세요?', '관심사나 취미가 있으신가요?'];
          const next = followUps[count - 1] ?? '더 궁금한 게 있으시면 말씀해 주세요.';
          setMessages(prev => [
            ...prev,
            { id: uid(), type: 'ai', text: `${confirmText}\n${next}`, createdAt: now() },
          ]);
        }
      } else if (res.markdown_draft) {
        // 평문 게이트가 활성화된 경우 — 온보딩에서는 그냥 안내
        setMessages(prev => [
          ...prev,
          { id: uid(), type: 'ai', text: '저장 형식을 다듬는 중이에요. 다시 한 번 말씀해 주세요.', createdAt: now() },
        ]);
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
        <span className={styles.headerTitle}>온보딩 1/3 · 기본 정보</span>
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
        <div className={[styles.dot, styles.dotActive].join(' ')} />
        <div className={styles.dot} />
        <div className={styles.dot} />
      </div>

      {saveCount >= 3 ? (
        <div style={{ padding: '0 16px 16px' }}>
          <button className={styles.primaryBtn} style={{ width: '100%' }} onClick={onNext}>
            다음: 검색 체험 →
          </button>
        </div>
      ) : (
        <InputArea onSend={handleSend} disabled={loading} />
      )}
    </>
  );
}

// ── 2. 인출 시뮬레이션 ────────────────────────────────────────
type SimPhase = 'intro' | 'storing' | 'stored' | 'querying' | 'queried' | 'done';

function StepSimulation({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [phase, setPhase] = useState<SimPhase>('intro');
  const [storeText, setStoreText] = useState('');
  const [storedNodes, setStoredNodes] = useState<string[]>([]);
  const [storedSentences, setStoredSentences] = useState<string[]>([]);
  const [queryText, setQueryText] = useState('');
  const [queryAnswer, setQueryAnswer] = useState<string | null>(null);
  const [queryFoundSentences, setQueryFoundSentences] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);

  async function handleStore() {
    if (!storeText.trim()) return;
    setPhase('storing');
    setLoading(true);
    try {
      const res = await api.chat(storeText.trim());
      const nodes = res.save?.nodes_added ?? [];
      setStoredNodes(nodes);
      setStoredSentences([storeText.trim()]);
      setPhase('stored');
    } finally {
      setLoading(false);
    }
  }

  async function handleQuery() {
    if (!queryText.trim()) return;
    setPhase('querying');
    setLoading(true);
    try {
      const res = await api.chat(queryText.trim());
      setQueryAnswer(res.answer ?? null);
      const sents = (res.retrieve?.context_triples ?? [])
        .map((t) => t[2] ? `${t[0]} ↔ ${t[2]}` : t[0])
        .filter((s, i, a) => a.indexOf(s) === i);
      setQueryFoundSentences(sents);
      setPhase('queried');
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className={styles.header}>
        <button className={styles.backBtn} onClick={onBack}>←</button>
        <span className={styles.headerTitle}>온보딩 2/3 · 검색 체험</span>
      </div>

      <div className={styles.chatArea} style={{ padding: '16px', gap: 14 }}>
        {phase === 'intro' && (
          <>
            <BubbleAI text="시냅스가 어떻게 동작하는지 직접 보여드릴게요.&#10;자유롭게 한 줄 적어보세요. 예) 오늘 카페에서 친구 만났어" />
            <textarea
              className={styles.simTextarea}
              placeholder="아무거나 적어보세요"
              value={storeText}
              onChange={(e) => setStoreText(e.target.value)}
              rows={3}
            />
            <button className={styles.primaryBtn} onClick={handleStore} disabled={!storeText.trim() || loading}>
              저장해보기
            </button>
          </>
        )}

        {phase === 'storing' && <BFSLoader />}

        {(phase === 'stored' || phase === 'querying' || phase === 'queried') && (
          <>
            <BubbleUser text={storedSentences[0]} />
            <BubbleAI text={
              storedNodes.length > 0
                ? `이 문장에서 다음 노드들을 추출했어요:\n${storedNodes.map(n => `• ${n}`).join('\n')}\n\n같은 문장에 함께 등장한 노드들끼리는 서로 맥락을 공유합니다.`
                : '저장은 됐는데 추출된 노드가 없어요. (LLM 서버가 꺼져있을 수 있어요)'
            } />
          </>
        )}

        {(phase === 'stored' || phase === 'querying' || phase === 'queried') && (
          <>
            <BubbleAI text="이제 검색해보세요. 방금 저장한 내용에서 떠오르는 키워드를 입력해보세요." />
            <textarea
              className={styles.simTextarea}
              placeholder={storedNodes[0] ? `예) ${storedNodes[0]} 어땠더라?` : '예) 오늘 뭐 했지?'}
              value={queryText}
              onChange={(e) => setQueryText(e.target.value)}
              rows={2}
              disabled={phase === 'querying'}
            />
            <button className={styles.primaryBtn} onClick={handleQuery} disabled={!queryText.trim() || loading || phase === 'querying'}>
              검색해보기
            </button>
          </>
        )}

        {phase === 'querying' && <BFSLoader />}

        {phase === 'queried' && (
          <>
            <BubbleUser text={queryText} />
            {queryFoundSentences.length > 0 ? (
              <BubbleAI text={`찾은 관련 흔적:\n${queryFoundSentences.map(s => `• ${s}`).join('\n')}${queryAnswer ? `\n\n${queryAnswer}` : ''}`} />
            ) : (
              <BubbleAI text={queryAnswer ?? '아직 데이터가 적어 못 찾았어요. 더 많이 저장할수록 더 정확하게 찾아져요.'} />
            )}
          </>
        )}
      </div>

      <div className={styles.progress} style={{ padding: '8px 0' }}>
        <div className={[styles.dot, styles.dotActive].join(' ')} />
        <div className={[styles.dot, styles.dotActive].join(' ')} />
        <div className={styles.dot} />
      </div>

      {phase === 'queried' && (
        <div style={{ padding: '0 16px 16px' }}>
          <button className={styles.primaryBtn} style={{ width: '100%' }} onClick={onNext}>
            그래프로 가기 →
          </button>
        </div>
      )}
    </>
  );
}

// ── 3. 실사용 전환 ────────────────────────────────────────────
function StepDone({ onHypergraph, onChat, onBack }: { onHypergraph: () => void; onChat: () => void; onBack: () => void }) {
  return (
    <>
      <div className={styles.header}>
        <button className={styles.backBtn} onClick={onBack}>←</button>
        <span className={styles.headerTitle}>온보딩 3/3 · 시작</span>
      </div>

      <div className={styles.welcome}>
        <div className={styles.welcomeDivider} />
        <div className={styles.welcomeLogo}>준비 완료</div>
        <div className={styles.welcomeTagline}>
          모든 게시물이 기억되고, 검색되고, 그래프로 자랍니다.
          <br /><br />
          <span style={{ fontSize: 12, color: 'var(--text-tertiary)' }}>
            상단의 <strong>검토</strong> 배지에서 시냅스가 발견한 관계를 승인할 수 있어요.
            그래야 그래프에 의미가 쌓입니다.
          </span>
        </div>
        <button className={styles.welcomeBtn} onClick={onHypergraph}>하이퍼그래프 보기</button>
        <button className={styles.welcomeBtn} style={{ background: 'transparent' }} onClick={onChat}>채팅으로 시작</button>
        <div className={styles.welcomeDivider} />
      </div>
    </>
  );
}

// ── OnboardingPage ─────────────────────────────────────────────
type Step = 'welcome' | 'chat' | 'simulation' | 'done';

export function OnboardingPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>('welcome');

  return (
    <div className={styles.page}>
      {step === 'welcome'    && <StepWelcome    onNext={() => setStep('chat')} />}
      {step === 'chat'       && <StepChat       onNext={() => setStep('simulation')} onBack={() => setStep('welcome')} />}
      {step === 'simulation' && <StepSimulation onNext={() => setStep('done')}       onBack={() => setStep('chat')} />}
      {step === 'done'       && <StepDone       onHypergraph={() => navigate('/hypergraph')} onChat={() => navigate('/chat/new')} onBack={() => setStep('simulation')} />}
    </div>
  );
}
