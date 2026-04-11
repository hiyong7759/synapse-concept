import { useEffect, useState } from 'react';
import type { SaveResponse } from '../../types';
import { api } from '../../api';
import styles from './Chat.module.css';

const AUTO_FADE_MS = 15000;

function tripleToText(src: string, label: string | null, tgt: string): string {
  return label ? `${src} —(${label})→ ${tgt}` : `${src} → ${tgt}`;
}

interface Props {
  save: SaveResponse;
  onDismiss: () => void;
  onCorrect?: (editText: string) => void;
}

export function ChangeNotice({ save, onDismiss, onCorrect }: Props) {
  const [fading, setFading] = useState(false);
  const hasStateChange = save.edges_deactivated.length > 0;

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

  function handleCorrect() {
    const lines = save.triples_added.map(([s, l, t]) => tripleToText(s, l, t));
    const editText = lines.join('\n');
    if (onCorrect) {
      onCorrect(editText);
    }
    onDismiss();
  }

  const triples = save.triples_added;

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
        {triples.map(([src, label, tgt], i) => (
          <div key={i} className={styles.changeTriple}>
            <span className={styles.node}>{src}</span>
            {label && <span className={styles.edge}>—({label})→</span>}
            <span className={styles.node}>{tgt}</span>
          </div>
        ))}
        <div className={styles.changeActions}>
          <button className={styles.changeBtn} onClick={handleCancel}>취소</button>
          <button className={styles.changeBtn} onClick={handleCorrect}>정정</button>
        </div>
      </div>
    );
  }

  return (
    <div className={[styles.changeNotice, fading ? styles.changeNoticeFading : ''].join(' ')}>
      {triples.map(([src, label, tgt], i) => (
        <div key={i} className={styles.changeTriple}>
          <span className={styles.node}>{src}</span>
          {label && <span className={styles.edge}>—({label})→</span>}
          <span className={styles.node}>{tgt}</span>
        </div>
      ))}
      <div className={styles.changeActions}>
        <button className={styles.changeBtn} onClick={handleCancel}>취소</button>
        <button className={styles.changeBtn} onClick={handleCorrect}>정정</button>
      </div>
    </div>
  );
}
