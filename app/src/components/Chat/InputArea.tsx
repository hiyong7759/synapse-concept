import { useState, useRef } from 'react';
import type { KeyboardEvent, ChangeEvent } from 'react';
import styles from './Chat.module.css';

interface Props {
  onSend: (text: string, images?: string[]) => void;
  disabled?: boolean;
}

export function InputArea({ onSend, disabled }: Props) {
  const [value, setValue] = useState('');
  const [images, setImages] = useState<string[]>([]);       // base64 목록
  const [previews, setPreviews] = useState<string[]>([]);   // data URL (화면 표시용)
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleSend() {
    if (disabled) return;
    const text = value.trim();
    if (!text && images.length === 0) return;
    onSend(text, images.length > 0 ? images : undefined);
    setValue('');
    setImages([]);
    setPreviews([]);
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  }

  function handleInput() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }

  function handleFileChange(e: ChangeEvent<HTMLInputElement>) {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;

    files.forEach(file => {
      const reader = new FileReader();
      reader.onload = ev => {
        const dataUrl = ev.target?.result as string;
        // data URL에서 base64 부분만 추출 (Ollama는 순수 base64)
        const base64 = dataUrl.split(',')[1];
        setImages(prev => [...prev, base64]);
        setPreviews(prev => [...prev, dataUrl]);
      };
      reader.readAsDataURL(file);
    });
    // 같은 파일 재선택 가능하도록 초기화
    e.target.value = '';
  }

  function removeImage(idx: number) {
    setImages(prev => prev.filter((_, i) => i !== idx));
    setPreviews(prev => prev.filter((_, i) => i !== idx));
  }

  const canSend = !disabled && (value.trim().length > 0 || images.length > 0);

  return (
    <div className={styles.inputAreaWrap}>
      {/* 이미지 미리보기 */}
      {previews.length > 0 && (
        <div className={styles.imagePreviews}>
          {previews.map((src, i) => (
            <div key={i} className={styles.imageThumb}>
              <img src={src} alt={`첨부 ${i + 1}`} />
              <button className={styles.imageRemove} onClick={() => removeImage(i)}>✕</button>
            </div>
          ))}
        </div>
      )}

      <div className={styles.inputArea}>
        {/* 이미지 첨부 버튼 */}
        <button
          className={styles.attachBtn}
          onClick={() => fileInputRef.current?.click()}
          disabled={disabled}
          title="이미지 첨부"
        >
          📎
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: 'none' }}
          onChange={handleFileChange}
        />

        <textarea
          ref={textareaRef}
          className={styles.inputBox}
          placeholder="메시지 입력..."
          value={value}
          onChange={e => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          disabled={disabled}
          rows={1}
        />
        <button className={styles.inputSend} onClick={handleSend} disabled={!canSend}>
          <svg viewBox="0 0 24 24"><path d="M2 21l21-9L2 3v7l15 2-15 2v7z"/></svg>
        </button>
      </div>
    </div>
  );
}
