import { useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { loadSessions, createSession, saveSession, deleteSession, formatDate } from '../session';
import type { ChatSession } from '../types';
import styles from './SessionsPage.module.css';

export function SessionsPage() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<ChatSession[]>(() => loadSessions());

  function handleNew() {
    const session = createSession();
    saveSession(session);
    navigate(`/chat/${session.id}`);
  }

  const handleDelete = useCallback((e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    deleteSession(id);
    setSessions(loadSessions());
  }, []);

  return (
    <div className={styles.page}>
      {/* 헤더 */}
      <div className={styles.header}>
        <div className={styles.logo}>Synapse</div>
        <div className={styles.headerActions}>
          <button className={styles.graphBtn} onClick={() => navigate('/graph')}>
            ⬡ 그래프
          </button>
          <button className={styles.newBtn} onClick={handleNew}>
            ＋ 새 채팅
          </button>
        </div>
      </div>

      {/* 세션 목록 */}
      {sessions.length === 0 ? (
        <div className={styles.empty}>
          <div className={styles.emptyIcon}>💬</div>
          <div className={styles.emptyTitle}>대화 내역이 없습니다</div>
          <div className={styles.emptyHint}>
            새 채팅을 시작하면<br />여기에 목록이 나타납니다
          </div>
          <button className={styles.emptyBtn} onClick={handleNew}>
            첫 대화 시작하기
          </button>
        </div>
      ) : (
        <div className={styles.list}>
          {sessions.map(s => (
            <div
              key={s.id}
              className={styles.sessionItem}
              onClick={() => navigate(`/chat/${s.id}`)}
            >
              <div className={styles.sessionIcon}>💬</div>
              <div className={styles.sessionInfo}>
                <div className={styles.sessionTitle}>{s.title}</div>
                <div className={styles.sessionMeta}>
                  <span>{formatDate(s.updatedAt)}</span>
                  <span>·</span>
                  <span>{s.messages.filter(m => m.type === 'user').length}개 메시지</span>
                </div>
              </div>
              <button
                className={styles.deleteBtn}
                onClick={e => handleDelete(e, s.id)}
                title="삭제"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 하단 */}
      <div className={styles.footer}>
        <button className={styles.onboardingLink} onClick={() => navigate('/onboarding')}>
          온보딩 다시 시작
        </button>
      </div>
    </div>
  );
}
