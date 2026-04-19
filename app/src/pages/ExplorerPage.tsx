import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { SentenceItem, SentenceImpact } from '../api';
import styles from './ExplorerPage.module.css';

const PAGE_SIZE = 20;

type Tab = 'all' | 'user' | 'assistant';

export function ExplorerPage() {
  const navigate = useNavigate();
  const [query, setQuery] = useState('');
  const [tab, setTab] = useState<Tab>('all');
  const [items, setItems] = useState<SentenceItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [hasMore, setHasMore] = useState(true);

  // 편집/삭제
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editText, setEditText] = useState('');
  const [deleteTarget, setDeleteTarget] = useState<SentenceImpact | null>(null);

  const offsetRef = useRef(0);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const fetchSentences = useCallback(async (reset = false) => {
    if (loading) return;
    setLoading(true);
    const offset = reset ? 0 : offsetRef.current;
    try {
      const res = await api.sentences({
        q: query,
        role: tab === 'all' ? '' : tab,
        offset,
        limit: PAGE_SIZE,
      });
      if (reset) {
        setItems(res.items);
      } else {
        setItems(prev => [...prev, ...res.items]);
      }
      setTotal(res.total);
      offsetRef.current = offset + res.items.length;
      setHasMore(offset + res.items.length < res.total);
    } catch {
      // API 미연결 시 빈 상태
    } finally {
      setLoading(false);
    }
  }, [query, tab, loading]);

  // 초기 로드 + 필터 변경 시 리셋
  useEffect(() => {
    offsetRef.current = 0;
    fetchSentences(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query, tab]);

  // 무한 스크롤
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      entries => { if (entries[0].isIntersecting && hasMore && !loading) fetchSentences(); },
      { threshold: 0.5 },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [hasMore, loading, fetchSentences]);

  function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    offsetRef.current = 0;
    fetchSentences(true);
  }

  async function handleDelete(id: number) {
    const impact = await api.sentenceImpact(id);
    setDeleteTarget(impact);
  }

  async function confirmDelete() {
    if (!deleteTarget) return;
    await api.sentenceDelete(deleteTarget.sentence_id);
    setItems(prev => prev.filter(s => s.id !== deleteTarget.sentence_id));
    setTotal(prev => prev - 1);
    setDeleteTarget(null);
  }

  async function handleEditSave(id: number) {
    await api.sentenceUpdate(id, editText);
    setItems(prev => prev.map(s => s.id === id ? { ...s, text: editText } : s));
    setEditingId(null);
  }

  function formatDate(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' });
  }

  function formatTime(iso: string): string {
    const d = new Date(iso);
    return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: true });
  }

  // 날짜별 그룹핑
  const grouped: [string, SentenceItem[]][] = [];
  let lastDate = '';
  for (const item of items) {
    const date = formatDate(item.created_at);
    if (date !== lastDate) {
      grouped.push([date, [item]]);
      lastDate = date;
    } else {
      grouped[grouped.length - 1][1].push(item);
    }
  }

  return (
    <div className={styles.page}>
      {/* 상단 바 */}
      <div className={styles.topbar}>
        <div className={styles.topbarLogo}>SYNAPSE</div>
        <div className={styles.topbarActions}>
          <button className={styles.topbarBtn} onClick={() => navigate('/chat/new')}>+ 새 대화</button>
          <button className={styles.topbarBtn} onClick={() => navigate('/hypergraph')}>하이퍼그래프</button>
        </div>
      </div>

      {/* 검색 */}
      <form className={styles.searchBar} onSubmit={handleSearch}>
        <input
          className={styles.searchInput}
          placeholder="키워드, 날짜, 주제..."
          value={query}
          onChange={e => setQuery(e.target.value)}
        />
        <button className={styles.searchBtn} type="submit">검색</button>
      </form>

      {/* 탭 필터 */}
      <div className={styles.tabs}>
        {(['all', 'user', 'assistant'] as Tab[]).map(t => (
          <button
            key={t}
            className={[styles.tab, tab === t ? styles.tabActive : ''].join(' ')}
            onClick={() => setTab(t)}
          >
            {t === 'all' ? '전체' : t === 'user' ? '내 말' : '비서'}
          </button>
        ))}
        <span className={styles.totalCount}>{total}건</span>
      </div>

      {/* 문장 목록 */}
      <div className={styles.sentenceList}>
        {grouped.map(([date, sentences]) => (
          <div key={date}>
            <div className={styles.dateHeader}>{date}</div>
            {sentences.map(s => (
              <div key={s.id} className={styles.sentenceRow}>
                <div className={styles.sentenceIcon}>
                  {s.role === 'user' ? '💬' : '🤖'}
                </div>
                <div className={styles.sentenceBody}>
                  {editingId === s.id ? (
                    <div className={styles.editArea}>
                      <textarea
                        className={styles.editInput}
                        value={editText}
                        onChange={e => setEditText(e.target.value)}
                        rows={3}
                      />
                      <div className={styles.editActions}>
                        <button className={styles.editBtn} onClick={() => setEditingId(null)}>취소</button>
                        <button className={styles.editBtn} onClick={() => handleEditSave(s.id)}>저장</button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className={styles.sentenceText}>{s.text}</div>
                      <div className={styles.sentenceMeta}>
                        <span className={styles.sentenceTime}>{formatTime(s.created_at)}</span>
                      </div>
                    </>
                  )}
                </div>
                {s.role === 'user' && editingId !== s.id && (
                  <div className={styles.sentenceActions}>
                    <button
                      className={styles.actionBtn}
                      onClick={() => { setEditingId(s.id); setEditText(s.text); }}
                      title="수정"
                    >✏️</button>
                    <button
                      className={styles.actionBtn}
                      onClick={() => handleDelete(s.id)}
                      title="삭제"
                    >🗑</button>
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}

        {items.length === 0 && !loading && (
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>◇</div>
            <div className={styles.emptyText}>대화 기록이 없습니다</div>
            <button className={styles.emptyBtn} onClick={() => navigate('/chat/new')}>대화 시작하기</button>
          </div>
        )}

        {/* 무한 스크롤 감시 */}
        <div ref={sentinelRef} style={{ height: 1 }} />
        {loading && <div className={styles.loadingDots}>...</div>}
      </div>

      {/* 삭제 확인 모달 */}
      {deleteTarget && (
        <div className={styles.modalOverlay} onClick={() => setDeleteTarget(null)}>
          <div className={styles.modal} onClick={e => e.stopPropagation()}>
            <div className={styles.modalTitle}>이 문장을 삭제하면</div>
            {deleteTarget.affected_edges.length > 0 ? (
              <>
                <div className={styles.modalSubtitle}>제거될 그래프 관계:</div>
                <ul className={styles.impactList}>
                  {deleteTarget.affected_edges.map((e, i) => (
                    <li key={i}>
                      {e.source} {e.label ? `—(${e.label})→` : '→'} {e.target}
                    </li>
                  ))}
                </ul>
              </>
            ) : (
              <div className={styles.modalSubtitle}>영향 받는 그래프 관계가 없습니다.</div>
            )}
            <div className={styles.modalActions}>
              <button className={styles.modalBtn} onClick={() => setDeleteTarget(null)}>취소</button>
              <button className={[styles.modalBtn, styles.modalBtnDanger].join(' ')} onClick={confirmDelete}>삭제</button>
            </div>
          </div>
        </div>
      )}

      {/* 하단 온보딩 링크 */}
      <div className={styles.footer}>
        <button className={styles.footerLink} onClick={() => navigate('/onboarding')}>
          온보딩 다시 하기
        </button>
      </div>
    </div>
  );
}
