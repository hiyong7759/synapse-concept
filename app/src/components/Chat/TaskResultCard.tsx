import { useState } from 'react';
import styles from './Chat.module.css';

interface Props {
  title: string;
  preview: string;
  fullText: string;
  onEditRequest?: (text: string) => void;
}

export function TaskResultCard({ title, preview, fullText, onEditRequest }: Props) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={styles.taskCard}>
      <div className={styles.taskHeader}>
        <span className={styles.taskIcon}>📄</span>
        <span className={styles.taskTitle}>{title}</span>
      </div>
      <div className={styles.taskDivider} />
      <div className={styles.taskPreview}>
        {expanded ? fullText : preview}
      </div>
      <div className={styles.taskActions}>
        <button className={styles.taskBtn} onClick={() => setExpanded(v => !v)}>
          {expanded ? '접기' : '전문 보기'}
        </button>
        {onEditRequest && (
          <button className={styles.taskBtn} onClick={() => onEditRequest(fullText)}>
            수정 요청
          </button>
        )}
      </div>
    </div>
  );
}
