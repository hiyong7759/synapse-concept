import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';
import type { ReviewAllResponse } from '../api';
import {
  labelOfCategory, descOfCategory,
  labelOfRelation, descOfRelation,
} from '../categories';
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

/**
 * v12 Phase 5: /review 페이지.
 * 모든 제안은 /GET review로 런타임 도출.
 * 사용자 옵션 클릭 → POST /review/apply → 최종 테이블 INSERT.
 */
export function ReviewPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<ReviewAllResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [freeInputs, setFreeInputs] = useState<Record<string, string>>({});

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

  async function apply(type: string, params: Record<string, unknown>) {
    await api.reviewApply(type, params);
    await reload();
  }

  function setFree(key: string, value: string) {
    setFreeInputs((prev) => ({ ...prev, [key]: value }));
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
          return (
            <div key={key} className={styles.card}>
              <div className={styles.section}>{SECTION_LABEL.missing_basic_info} <span className={styles.meta}>({item.label})</span></div>
              <div className={styles.question}>{item.question}</div>
              <div className={styles.options}>
                <input
                  className={styles.freeInput}
                  placeholder="답변 입력"
                  value={freeInputs[key] ?? ''}
                  onChange={(e) => setFree(key, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && freeInputs[key]?.trim()) {
                      apply('basic_info', { answer: freeInputs[key].trim() });
                      setFree(key, '');
                    }
                  }}
                />
                <button className={styles.optBtn} onClick={() => {
                  const v = (freeInputs[key] ?? '').trim();
                  if (v) {
                    apply('basic_info', { answer: v });
                    setFree(key, '');
                  }
                }}>저장</button>
              </div>
            </div>
          );
        })}

        {data?.unresolved?.map((item) => {
          const key = `u:${item.sentence_id}:${item.token}`;
          const postLabel = item.post_id != null
            ? `게시물 #${item.post_id} · ${item.post_created_at?.slice(0, 16) ?? ''}`
            : '대화';
          return (
            <div key={key} className={styles.card}>
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
                    apply('token', { sentence_id: item.sentence_id, token: item.token, value: opt })
                  }>{opt}</button>
                ))}
                <input
                  className={styles.freeInput}
                  placeholder="직접 입력"
                  value={freeInputs[key] ?? ''}
                  onChange={(e) => setFree(key, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && freeInputs[key]?.trim()) {
                      apply('token', { sentence_id: item.sentence_id, token: item.token, value: freeInputs[key].trim() });
                      setFree(key, '');
                    }
                  }}
                />
                <button className={styles.dismissBtn} onClick={() =>
                  apply('token_dismiss', { sentence_id: item.sentence_id, token: item.token })
                }>알 수 없음</button>
              </div>
            </div>
          );
        })}

        {data?.uncategorized?.map((item) => {
          const key = `c:${item.node_id}`;
          return (
            <div key={key} className={styles.card}>
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
                      onClick={() => apply('category', { node_id: item.node_id, category: opt })}
                    >
                      {labelOfCategory(opt)}
                      <span className={styles.optCode}>{opt}</span>
                    </button>
                  );
                })}
                <input
                  className={styles.freeInput}
                  placeholder="직접 입력 (예: 병원.2026-04-18)"
                  value={freeInputs[key] ?? ''}
                  onChange={(e) => setFree(key, e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && freeInputs[key]?.trim()) {
                      apply('category', { node_id: item.node_id, category: freeInputs[key].trim() });
                      setFree(key, '');
                    }
                  }}
                />
              </div>
            </div>
          );
        })}

        {data?.cooccur_pairs?.map((item) => {
          const key = `co:${item.source_id}:${item.target_id}`;
          return (
            <div key={key} className={styles.card}>
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
                      onClick={() => apply('edge', {
                        source_id: item.source_id,
                        target_id: item.target_id,
                        label: opt,
                      })}
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
            <div key={key} className={styles.card}>
              <div className={styles.section}>{SECTION_LABEL.suspected_typos}</div>
              <div className={styles.question}>{item.question}</div>
              <div className={styles.context}>
                {item.node_a_name} (언급 {item.mention_count_a}건) · {item.node_b_name} (언급 {item.mention_count_b}건)
              </div>
              <div className={styles.options}>
                <button className={styles.optBtn} onClick={() => {
                  // 언급 많은 쪽을 keep
                  const keep = item.mention_count_a >= item.mention_count_b ? item.node_a_id : item.node_b_id;
                  const remove = keep === item.node_a_id ? item.node_b_id : item.node_a_id;
                  apply('merge', { keep_id: keep, remove_id: remove });
                }}>같음 (병합)</button>
                <button className={styles.dismissBtn} onClick={() =>
                  // 무시 — 둘 다 그대로 두려면 별도 처리 필요. 현재는 그냥 reload (제안 사라지진 않음)
                  reload()
                }>다름 (무시)</button>
              </div>
            </div>
          );
        })}

        {data?.stale_nodes?.map((item) => {
          const key = `s:${item.node_id}`;
          return (
            <div key={key} className={styles.card}>
              <div className={styles.section}>{SECTION_LABEL.stale_nodes}</div>
              <div className={styles.question}>{item.question}</div>
              <div className={styles.context}>마지막 갱신: {item.updated_at} · 언급 {item.mention_count}건</div>
              <div className={styles.options}>
                <button className={styles.optBtn} onClick={reload}>유지</button>
                <button className={styles.dismissBtn} onClick={() =>
                  apply('archive', { node_id: item.node_id })
                }>아카이브</button>
              </div>
            </div>
          );
        })}

        {data?.gaps?.map((item, i) => {
          const key = `g:${i}`;
          return (
            <div key={key} className={styles.card}>
              <div className={styles.section}>{SECTION_LABEL.gaps}</div>
              <div className={styles.question}>{item.question}</div>
              <div className={styles.context}>{item.from} ~ {item.to} · {item.days}일</div>
              <div className={styles.options}>
                <button className={styles.optBtn} onClick={() => navigate('/chat/new')}>채팅으로 기록 추가</button>
                <button className={styles.dismissBtn} onClick={reload}>특별한 일 없었음</button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
