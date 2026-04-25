import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api } from '../api';

interface Props {
  className?: string;
  intervalMs?: number;
}

/** v12 Phase 5: 어디서든 띄울 수 있는 /review 진입 배지. */
export function ReviewBadge({ className, intervalMs = 30000 }: Props) {
  const navigate = useNavigate();
  const [count, setCount] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const c = await api.reviewCount();
        if (!cancelled) setCount(c.total);
      } catch {
        /* 서버 미실행 시 무시 */
      }
    }
    load();
    const t = setInterval(load, intervalMs);
    return () => { cancelled = true; clearInterval(t); };
  }, [intervalMs]);

  const hasItems = (count ?? 0) > 0;

  return (
    <button
      className={className}
      onClick={() => navigate('/review')}
      title="검토 대기 항목"
      style={{
        position: 'relative',
        background: hasItems ? 'var(--accent-dim)' : 'none',
        border: `1px solid ${hasItems ? 'var(--accent)' : 'var(--border)'}`,
        color: hasItems ? 'var(--accent)' : 'var(--text-secondary)',
        padding: '4px 10px',
        fontSize: 12,
        cursor: 'pointer',
        borderRadius: 4,
        fontFamily: 'Noto Sans KR, sans-serif',
      }}
    >
      검토
      {hasItems && (
        <span
          style={{
            marginLeft: 6,
            background: 'var(--accent)',
            color: 'var(--bg)',
            borderRadius: 10,
            padding: '1px 6px',
            fontSize: 10,
            fontFamily: 'JetBrains Mono, monospace',
          }}
        >
          {count}
        </span>
      )}
    </button>
  );
}
