import { useState } from 'react';
import styles from './Chat.module.css';

interface Props {
  draft: string;
  originalText: string;
  onConfirm: (markdown: string, images?: string[]) => void;
  onDismiss: () => void;
  images?: string[];
}

/**
 * v12: structure-suggest 초안 편집 카드.
 * LLM이 heading 한 줄을 붙여서 돌려준 마크다운 초안을 사용자에게 보여주고
 * 편집/확정/취소 중 하나를 선택하게 한다.
 */
export function MarkdownDraftCard({ draft, originalText, onConfirm, onDismiss, images }: Props) {
  const [value, setValue] = useState(draft);

  function handleConfirm() {
    if (!value.trim()) return;
    onConfirm(value.trim(), images);
  }

  function handleUseOriginal() {
    onConfirm(originalText, images);
  }

  return (
    <div className={styles.changeNoticeStrong}>
      <div className={styles.changeLabel}>✎ 이렇게 저장할까요?</div>
      <textarea
        className={styles.draftTextarea}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        rows={Math.min(12, Math.max(4, value.split('\n').length + 1))}
        spellCheck={false}
      />
      <div className={styles.changeActions}>
        <button className={styles.changeBtn} onClick={handleConfirm}>이대로 저장</button>
        <button className={styles.changeBtn} onClick={handleUseOriginal}>원문 그대로</button>
        <button className={styles.changeBtn} onClick={onDismiss}>취소</button>
      </div>
    </div>
  );
}
