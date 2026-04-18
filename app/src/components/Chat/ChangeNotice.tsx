import { useEffect, useState } from 'react';
import type { SaveResponse } from '../../types';
import { api } from '../../api';
import styles from './Chat.module.css';

const AUTO_FADE_MS = 15000;

interface Props {
  save: SaveResponse;
  onDismiss: () => void;
}

export function ChangeNotice({ save, onDismiss }: Props) {
  const [fading, setFading] = useState(false);
  const hasStateChange = save.edges_deactivated.length > 0;
  const nodesAddedCount = save.nodes_added.length;
  const mentionsAdded = save.mentions_added ?? 0;

  // 단순 추가일 때만 자동 fade-out (상태 변경은 명시적 확인 필요)
  useEffect(() => {
    if (hasStateChange) return;
    const fadeTimer = setTimeout(() => setFading(true), AUTO_FADE_MS - 300);
    const dismissTimer = setTimeout(onDismiss, AUTO_FADE_MS);
    return () => { clearTimeout(fadeTimer); clearTimeout(dismissTimer); };
  }, [hasStateChange, onDismiss]);

  async function handleCancel() {
    await api.rollback(save.edge_ids_added, save.node_ids_added);
    onDismiss();
  }

  // v12: 자동 저장 결과 = 노드 추가 + 문장 역참조. 엣지는 /review에서 편입.
  const summary: string[] = [];
  if (nodesAddedCount > 0) summary.push(`신규 노드 ${nodesAddedCount}개`);
  if (mentionsAdded > 0) summary.push(`언급 기록 ${mentionsAdded}건`);
  const hasSummary = summary.length > 0;

  if (hasStateChange) {
    return (
      <div className={styles.changeNoticeStrong}>
        <div className={styles.changeLabel}>⚡ 상태 변경</div>
        {save.edges_deactivated.map(([src, label, tgt], i) => (
          <div key={i} className={styles.changeTriple}>
            <span className={styles.node}>{src}</span>
            {label && <span className={styles.edge}>—({label})→</span>}
            <span className={styles.node}>{tgt}</span>
            <span className={styles.inactiveBadge}>비활성</span>
          </div>
        ))}
        {hasSummary && (
          <div className={styles.changeSummary}>{summary.join(' · ')}</div>
        )}
        <div className={styles.changeActions}>
          <button className={styles.changeBtn} onClick={handleCancel}>취소</button>
        </div>
      </div>
    );
  }

  if (!hasSummary) {
    return null;
  }

  return (
    <div className={[styles.changeNotice, fading ? styles.changeNoticeFading : ''].join(' ')}>
      <div className={styles.changeSummary}>
        {summary.join(' · ')}
        <span className={styles.changeHint}> (의미 관계 엣지는 /review에서 편입)</span>
      </div>
      {save.nodes_added.length > 0 && (
        <div className={styles.changeNodes}>
          {save.nodes_added.map((name) => (
            <span key={name} className={styles.node}>{name}</span>
          ))}
        </div>
      )}
      <div className={styles.changeActions}>
        <button className={styles.changeBtn} onClick={handleCancel}>취소</button>
      </div>
    </div>
  );
}
