import styles from './Chat.module.css';

function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: true });
}

interface Props {
  text: string;
  images?: string[];
  createdAt?: string;
}

export function BubbleUser({ text, images, createdAt }: Props) {
  return (
    <div className={styles.msgUser}>
      {images && images.length > 0 && (
        <div className={styles.bubbleImages}>
          {images.map((b64, i) => (
            <img
              key={i}
              src={`data:image/jpeg;base64,${b64}`}
              alt={`첨부 ${i + 1}`}
              className={styles.bubbleImage}
            />
          ))}
        </div>
      )}
      {text && <div className={styles.bubbleUser}>{text}</div>}
      {createdAt && <span className={styles.ts}>{formatTime(createdAt)}</span>}
    </div>
  );
}
