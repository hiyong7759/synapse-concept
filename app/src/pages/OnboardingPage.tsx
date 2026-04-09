import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Message } from '../types';
import { api } from '../api';
import { createSession, saveSession } from '../session';
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

// ── 1. 자동 연동 ──────────────────────────────────────────────
const CONNECT_ITEMS = [
  { icon: '🏦', label: '금융 (마이데이터)' },
  { icon: '🏥', label: '건강 (마이데이터)' },
  { icon: '👤', label: '연락처' },
  { icon: '📅', label: '캘린더' },
];

function Step1Connect({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [toggles, setToggles] = useState<boolean[]>([true, true, true, true]);

  function toggle(i: number) {
    setToggles(prev => prev.map((v, idx) => idx === i ? !v : v));
  }

  return (
    <>
      <div className={styles.header}>
        <button className={styles.backBtn} onClick={onBack}>←</button>
        <span className={styles.headerTitle}>온보딩</span>
        <span className={styles.stepLabel}>1 / 3</span>
      </div>
      <div className={styles.body}>
        <div className={styles.heading}>자동으로 연결할게요</div>
        <div className={styles.toggleList}>
          {CONNECT_ITEMS.map((item, i) => (
            <div key={i} className={styles.toggleItem}>
              <span className={styles.toggleIcon}>{item.icon}</span>
              <span className={styles.toggleLabel}>{item.label}</span>
              <button
                className={[styles.toggle, toggles[i] ? styles.toggleOn : styles.toggleOff].join(' ')}
                onClick={() => toggle(i)}
                aria-label={`${item.label} ${toggles[i] ? '켜짐' : '꺼짐'}`}
              />
            </div>
          ))}
        </div>
        <div className={styles.note}>연동하지 않아도 나중에 설정에서 할 수 있습니다.</div>
        <div className={styles.spacer} />
        <button className={styles.primaryBtn} onClick={onNext}>연결하고 다음으로</button>
        <div className={styles.skipBtn} onClick={onNext}>건너뛰기</div>
        <div className={styles.progress}>
          <div className={[styles.dot, styles.dotActive].join(' ')} />
          <div className={styles.dot} />
          <div className={styles.dot} />
        </div>
      </div>
    </>
  );
}

// ── 2. 파일 업로드 ────────────────────────────────────────────
function Step2Upload({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  return (
    <>
      <div className={styles.header}>
        <button className={styles.backBtn} onClick={onBack}>←</button>
        <span className={styles.headerTitle}>온보딩</span>
        <span className={styles.stepLabel}>2 / 3</span>
      </div>
      <div className={styles.body}>
        <div className={styles.heading}>파일이나 이미지가 있으면 올려주세요</div>
        <div className={styles.dropzone}>
          <div className={styles.dropzoneIcon}>+</div>
          <div className={styles.dropzoneLabel}>파일 / 이미지 추가</div>
          <div className={styles.dropzoneHint}>명함·이력서·처방전 등<br />올려주시면 읽어드려요</div>
        </div>
        <div className={styles.note}>지원 형식: JPG, PNG, PDF, DOCX</div>
        <div className={styles.spacer} />
        <button className={styles.primaryBtn} onClick={onNext}>다음으로</button>
        <div className={styles.skipBtn} onClick={onNext}>건너뛰기</div>
        <div className={styles.progress}>
          <div className={styles.dot} />
          <div className={[styles.dot, styles.dotActive].join(' ')} />
          <div className={styles.dot} />
        </div>
      </div>
    </>
  );
}

// ── 3. 비서 질문 채팅 ─────────────────────────────────────────
const INITIAL_MESSAGES: Message[] = [
  { id: 'init-0', type: 'ai', text: '안녕하세요! 몇 가지만 여쭤볼게요.\n이름이 어떻게 되세요?' },
];

function Step3Chat({ onDone, onBack }: { onDone: () => void; onBack: () => void }) {
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
      { id: uid(), type: 'user', text },
      { id: searchingId, type: 'searching' },
    ]);
    setLoading(true);

    try {
      const res = await api.chat(text);
      setMessages(prev => prev.filter(m => m.id !== searchingId));

      if (res.mode === 'save' && res.save) {
        const count = saveCount + 1;
        setSaveCount(count);

        // 저장 확인 메시지
        const names = res.save.nodes_added;
        const confirmText = names.length > 0
          ? `${names.join(', ')} 기억했어요.`
          : '기억했어요.';

        // 3개 저장 후 완료 유도
        if (count >= 3) {
          setMessages(prev => [
            ...prev,
            { id: uid(), type: 'ai', text: `${confirmText}\n\n기본 정보 입력이 완료됐어요. 이제 채팅을 시작해볼까요?` },
          ]);
        } else {
          const followUps = ['직업은 어떻게 되세요?', '주로 어디에 사세요?', '관심사나 취미가 있으신가요?'];
          const next = followUps[count - 1] ?? '더 궁금한 게 있으시면 말씀해 주세요.';
          setMessages(prev => [
            ...prev,
            { id: uid(), type: 'ai', text: `${confirmText}\n${next}` },
          ]);
        }
      } else if (res.mode === 'clarify' && res.question) {
        setMessages(prev => [...prev, { id: uid(), type: 'ai', text: res.question! }]);
      } else {
        setMessages(prev => [...prev, { id: uid(), type: 'ai', text: '좋아요, 계속 말씀해 주세요.' }]);
      }
    } catch {
      setMessages(prev => [
        ...prev.filter(m => m.id !== searchingId),
        { id: uid(), type: 'ai', text: '서버 연결 실패. API 서버가 실행 중인지 확인해 주세요.' },
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
        <span className={styles.stepLabel}>3 / 3</span>
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
type Step = 'welcome' | 'step1' | 'step2' | 'step3';

export function OnboardingPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState<Step>('welcome');

  function handleDone() {
    const session = createSession();
    saveSession(session);
    navigate(`/chat/${session.id}`);
  }

  return (
    <div className={styles.page}>
      {step === 'welcome' && <StepWelcome onNext={() => setStep('step1')} />}
      {step === 'step1' && <Step1Connect onNext={() => setStep('step2')} onBack={() => setStep('welcome')} />}
      {step === 'step2' && <Step2Upload onNext={() => setStep('step3')} onBack={() => setStep('step1')} />}
      {step === 'step3' && <Step3Chat onDone={handleDone} onBack={() => setStep('step2')} />}
    </div>
  );
}
