import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { ReviewAllResponse } from '../api';
import {
  labelOfCategory, descOfCategory,
  labelOfRelation, descOfRelation,
} from '../categories';
import { useToast } from '../components/Toast';
import styles from './ReviewPage.module.css';

type SectionKey =
  | 'unresolved'
  | 'uncategorized'
  | 'cooccur_pairs'
  | 'suspected_typos'
  | 'missing_basic_info'
  | 'stale_nodes'
  | 'gaps';

const SECTION_LABEL: Record<SectionKey, string> = {
  unresolved:         '🔍 미해결 지시어',
  uncategorized:      '🏷  미분류 노드',
  cooccur_pairs:      '🔗 공출현 노드 쌍',
  suspected_typos:    '⚠ 오타 의심',
  missing_basic_info: '👤 기본 정보 누락',
  stale_nodes:        '⏳ 오래된 노드',
  gaps:               '📅 기록 공백',
};

const SUCCESS_FADE_MS = 420;

/**
 * v12 Phase 5: /review 페이지.
 * 모든 제안은 /GET review로 런타임 도출.
 * 사용자 옵션 클릭 → POST /review/apply → 최종 테이블 INSERT.
 */
export function ReviewPage() {
  const navigate = useNavigate();
  const toast = useToast();
  const [data, setData] = useState<ReviewAllResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [freeInputs, setFreeInputs] = useState<Record<string, string>>({});
  const [successKeys, setSuccessKeys] = useState<Set<string>>(new Set());

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.review();
      setData(res);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { reload(); }, [reload]);

  async function apply(
    key: string,
    type: string,
    params: Record<string, unknown>,
    successMsg: string,
  ) {
    try {
      await api.reviewApply(type, params);
      toast.show(`✓ ${successMsg}`, 'success');
      setSuccessKeys((prev) => {
        const next = new Set(prev);
        next.add(key);
        return next;
      });
      setTimeout(() => {
        setSuccessKeys((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
        reload();
      }, SUCCESS_FADE_MS);
    } catch {
      toast.show('저장 실패', 'error');
    }
  }

  function dismiss(key: string, message: string) {
    toast.show(message, 'info');
    setSuccessKeys((prev) => {
      const next = new Set(prev);
      next.add(key);
      return next;
    });
    setTimeout(() => {
      setSuccessKeys((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
      reload();
    }, SUCCESS_FADE_MS);
  }

  function setFree(key: string, value: string) {
    setFreeInputs((prev) => ({ ...prev, [key]: value }));
  }

  function cardClass(key: string) {
    return successKeys.has(key)
      ? `${styles.card} ${styles.cardSuccess}`
      : styles.card;
  }

  const sections: SectionKey[] = [
    'missing_basic_info',
    'unresolved',
    'uncategorized',
    'cooccur_pairs',
    'suspected_typos',
    'stale_nodes',
    'gaps',
  ];

  return (
    <div className={styles.page}>
      <div className={styles.topbar}>
        <button className={styles.topbarBtn} onClick={() => navigate('/')}>← 탐색</button>
        <div className={styles.topbarLogo}>REVIEW</div>
        <div className={styles.topbarActions}>
          <button className={styles.topbarBtn} onClick={() => navigate('/graph')}>그래프</button>
          <button className={styles.topbarBtn} onClick={reload} disabled={loading}>
            {loading ? '...' : '↻'}
          </button>
        </div>
      </div>

      <div className={styles.body}>
        {loading && !data && <div className={styles.empty}>불러오는 중...</div>}

        {data && sections.every((s) => {
          const v = data[s];
          if (!v) return true;
          return Array.isArray(v) ? v.length === 0 : false;
        }) && (
          <div className={styles.empty}>검토할 항목이 없습니다.</div>
        )}

        {data?.missing_basic_info?.map((item) => {
          const key = `b:${item.field}`;
          const value = freeInputs[key] ?? '';
          const submit = () => {
            const v = value.trim();
            if (!v) return;
            apply(key, 'basic_info', { answer: v }, '기본 정보 저장됨');
            setFree(key, '');
          };
          return (
            <div key={key} className={cardClass(key)}>
              <div className={styles.section}>{SECTION_LABEL.missing_basic_info} <span className={styles.meta}>({item.label})</span></div>
              <div className={styles.question}>{item.question}</div>
              <div className={styles.options}>
                <input
                  className={styles.freeInput}
                  placeholder="답변 입력"
                  value={value}
                  onChange={(e) => setFree(key, e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
                />
                <button className={styles.optBtn} onClick={submit}>저장</button>
              </div>
            </div>
          );
        })}

        {data?.unresolved?.map((item) => {
          const key = `u:${item.sentence_id}:${item.token}`;
          const value = freeInputs[key] ?? '';
          const submitFree = () => {
            const v = value.trim();
            if (!v) return;
            apply(key, 'token', { sentence_id: item.sentence_id, token: item.token, value: v }, `"${item.token}" 해소됨`);
            setFree(key, '');
          };
          const postLabel = item.post_id != null
            ? `게시물 #${item.post_id} · ${item.post_created_at?.slice(0, 16) ?? ''}`
            : '대화';
          return (
            <div key={key} className={cardClass(key)}>
              <div className={styles.section}>
                {SECTION_LABEL.unresolved}
                <span className={styles.meta}>({postLabel})</span>
              </div>
              {item.post_markdown && (
                <details className={styles.postSource}>
                  <summary>원본 게시물 보기</summary>
                  <pre className={styles.postMarkdown}>{item.post_markdown}</pre>
                </details>
              )}
              <div className={styles.question}>{item.question}</div>
              <div className={styles.context}>
                <span className={styles.contextLabel}>해당 문장:</span> {item.sentence_text}
              </div>
              <div className={styles.options}>
                {item.options.map((opt) => (
                  <button key={opt} className={styles.optBtn} onClick={() =>
                    apply(key, 'token', { sentence_id: item.sentence_id, token: item.token, value: opt }, `"${item.token}" → ${opt}`)
                  }>{opt}</button>
                ))}
                <input
                  className={styles.freeInput}
                  placeholder="직접 입력"
                  value={value}
                  onChange={(e) => setFree(key, e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') submitFree(); }}
                />
                <button className={styles.optBtn} onClick={submitFree}>저장</button>
                <button className={styles.dismissBtn} onClick={() =>
                  apply(key, 'token_dismiss', { sentence_id: item.sentence_id, token: item.token }, `"${item.token}" 건너뜀`)
                }>알 수 없음</button>
              </div>
            </div>
          );
        })}

        {data?.uncategorized?.map((item) => {
          const key = `c:${item.node_id}`;
          const value = freeInputs[key] ?? '';
          const submitFree = () => {
            const v = value.trim();
            if (!v) return;
            apply(key, 'category', { node_id: item.node_id, category: v }, `카테고리 "${v}" 추가됨`);
            setFree(key, '');
          };
          return (
            <div key={key} className={cardClass(key)}>
              <div className={styles.section}>{SECTION_LABEL.uncategorized}</div>
              <div className={styles.question}>{item.question}</div>
              <div className={styles.options}>
                {item.options.map((opt) => {
                  const desc = descOfCategory(opt);
                  return (
                    <button
                      key={opt}
                      className={styles.optBtn}
                      title={desc ? `${opt} — ${desc}` : opt}
                      onClick={() => apply(key, 'category', { node_id: item.node_id, category: opt }, `카테고리 "${labelOfCategory(opt)}" 추가됨`)}
                    >
                      {labelOfCategory(opt)}
                      <span className={styles.optCode}>{opt}</span>
                    </button>
                  );
                })}
                <input
                  className={styles.freeInput}
                  placeholder="직접 입력 (예: 병원.2026-04-18)"
                  value={value}
                  onChange={(e) => setFree(key, e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') submitFree(); }}
                />
                <button className={styles.optBtn} onClick={submitFree}>저장</button>
              </div>
            </div>
          );
        })}

        {data?.cooccur_pairs?.map((item) => {
          const key = `co:${item.source_id}:${item.target_id}`;
          return (
            <div key={key} className={cardClass(key)}>
              <div className={styles.section}>{SECTION_LABEL.cooccur_pairs} <span className={styles.meta}>({item.cooccur_count}회 함께 등장)</span></div>
              <div className={styles.question}>{item.question}</div>
              {item.sample_sentence && <div className={styles.context}>{item.sample_sentence}</div>}
              <div className={styles.options}>
                {item.options.map((opt) => {
                  const desc = descOfRelation(opt);
                  return (
                    <button
                      key={opt}
                      className={styles.optBtn}
                      title={desc ? `${opt} — ${desc}` : opt}
                      onClick={() => apply(key, 'edge', {
                        source_id: item.source_id,
                        target_id: item.target_id,
                        label: opt,
                      }, `"${labelOfRelation(opt)}" 관계 생성됨`)}
                    >
                      {labelOfRelation(opt)}
                      <span className={styles.optCode}>{opt}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}

        {data?.suspected_typos?.map((item) => {
          const key = `t:${item.node_a_id}:${item.node_b_id}`;
          return (
            <div key={key} className={cardClass(key)}>
              <div className={styles.section}>{SECTION_LABEL.suspected_typos}</div>
              <div className={styles.question}>{item.question}</div>
              <div className={styles.context}>
                {item.node_a_name} (언급 {item.mention_count_a}건) · {item.node_b_name} (언급 {item.mention_count_b}건)
              </div>
              <div className={styles.options}>
                <button className={styles.optBtn} onClick={() => {
                  const keep = item.mention_count_a >= item.mention_count_b ? item.node_a_id : item.node_b_id;
                  const remove = keep === item.node_a_id ? item.node_b_id : item.node_a_id;
                  const keepName = keep === item.node_a_id ? item.node_a_name : item.node_b_name;
                  apply(key, 'merge', { keep_id: keep, remove_id: remove }, `"${keepName}"(으)로 병합됨`);
                }}>같음 (병합)</button>
                <button className={styles.dismissBtn} onClick={() =>
                  dismiss(key, '다름으로 표시')
                }>다름 (무시)</button>
              </div>
            </div>
          );
        })}

        {data?.stale_nodes?.map((item) => {
          const key = `s:${item.node_id}`;
          return (
            <div key={key} className={cardClass(key)}>
              <div className={styles.section}>{SECTION_LABEL.stale_nodes}</div>
              <div className={styles.question}>{item.question}</div>
              <div className={styles.context}>마지막 갱신: {item.updated_at} · 언급 {item.mention_count}건</div>
              <div className={styles.options}>
                <button className={styles.optBtn} onClick={() => dismiss(key, '유지됨')}>유지</button>
                <button className={styles.dismissBtn} onClick={() =>
                  apply(key, 'archive', { node_id: item.node_id }, '아카이브됨')
                }>아카이브</button>
              </div>
            </div>
          );
        })}

        {data?.gaps?.map((item, i) => {
          const key = `g:${i}`;
          return (
            <div key={key} className={cardClass(key)}>
              <div className={styles.section}>{SECTION_LABEL.gaps}</div>
              <div className={styles.question}>{item.question}</div>
              <div className={styles.context}>{item.from} ~ {item.to} · {item.days}일</div>
              <div className={styles.options}>
                <button className={styles.optBtn} onClick={() => navigate('/chat/new')}>채팅으로 기록 추가</button>
                <button className={styles.dismissBtn} onClick={() => dismiss(key, '특별한 일 없었음')}>특별한 일 없었음</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
