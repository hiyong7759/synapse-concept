import styles from './Chat.module.css';

interface Props {
  text: string;
  images?: string[];
  time?: string;
}

export function BubbleUser({ text, images, time }: Props) {
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
      {time && <span className={styles.ts}>{time}</span>}
    </div>
  );
}
