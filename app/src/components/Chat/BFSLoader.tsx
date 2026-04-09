import styles from './Chat.module.css';

interface Props { mode?: 'save' | 'retrieve' }

export function BFSLoader({ mode = 'retrieve' }: Props) {
  const isSave = mode === 'save';
  return (
    <div className={styles.bfsBubble}>
      <div className={styles.bfsStatus}>
        <span className={styles.bfsDot} />
        <span className={styles.bfsDot} />
        <span className={styles.bfsDot} />
        <span>{isSave ? '그래프 저장 중...' : '그래프 탐색 중...'}</span>
      </div>
      <div className={styles.miniGraph}>
        <div className={styles.miniGraphRow}>
          <span className={styles.graphNode}>{isSave ? 'SAVE' : 'BFS'}</span>
          <span className={styles.graphEdgeLine}>───────</span>
          <span className={`${styles.graphNode} ${styles.dim}`}>...</span>
        </div>
      </div>
    </div>
  );
}
