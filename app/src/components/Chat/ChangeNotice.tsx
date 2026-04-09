import type { SaveResponse } from '../../types';
import { api } from '../../api';
import styles from './Chat.module.css';

interface Props {
  save: SaveResponse;
  onDismiss: () => void;
}

export function ChangeNotice({ save, onDismiss }: Props) {
  const hasStateChange = save.edges_deactivated.length > 0;

  async function handleCancel() {
    await api.rollback(save.edge_ids_added, save.node_ids_added);
    onDismiss();
  }

  const triples = save.triples_added;

  if (hasStateChange) {
    return (
      <div className={styles.changeNoticeStrong}>
        <div className={styles.changeLabel}>⚡ 상태 변경됨</div>
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
          <button className={styles.changeBtn} onClick={onDismiss}>정정</button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.changeNotice}>
      {triples.map(([src, label, tgt], i) => (
        <div key={i} className={styles.changeTriple}>
          <span className={styles.node}>{src}</span>
          {label && <span className={styles.edge}>—({label})→</span>}
          <span className={styles.node}>{tgt}</span>
        </div>
      ))}
      <div className={styles.changeActions}>
        <button className={styles.changeBtn} onClick={handleCancel}>취소</button>
        <button className={styles.changeBtn} onClick={onDismiss}>정정</button>
      </div>
    </div>
  );
}
