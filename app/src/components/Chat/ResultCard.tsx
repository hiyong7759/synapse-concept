import type { RetrieveResponse } from '../../types';
import styles from './Chat.module.css';

interface Props {
  retrieve: RetrieveResponse;
}

export function ResultCard({ retrieve }: Props) {
  const tripleLines = retrieve.context_triples.map(([s, l, t]) =>
    `${s}${l ? ` —(${l})→ ` : ' → '}${t}`
  );

  return (
    <div className={styles.resultCard}>
      <div className={styles.resultCardTitle}>
        <span>◈</span>
        <span>그래프 인출 ({retrieve.context_triples.length}개 트리플)</span>
      </div>
      <div className={styles.resultCardDivider} />
      <div className={styles.resultCardPreview}>
        {tripleLines.length > 0 ? tripleLines.join('\n') : '관련 컨텍스트 없음'}
      </div>
    </div>
  );
}
