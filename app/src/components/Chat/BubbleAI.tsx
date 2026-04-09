import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import type { Components } from 'react-markdown';
import styles from './Chat.module.css';

// ── 파일 확장자 추론 ───────────────────────────────────────────
function inferExt(lang: string): string {
  const map: Record<string, string> = {
    python: 'py', javascript: 'js', typescript: 'ts', tsx: 'tsx', jsx: 'jsx',
    bash: 'sh', shell: 'sh', sh: 'sh', json: 'json', yaml: 'yml', yml: 'yml',
    css: 'css', html: 'html', sql: 'sql', rust: 'rs', go: 'go', java: 'java',
    cpp: 'cpp', c: 'c', markdown: 'md', md: 'md', toml: 'toml',
  };
  return map[lang.toLowerCase()] ?? 'txt';
}

// ── 코드 블록 컴포넌트 ────────────────────────────────────────
function CodeBlock({ lang, code }: { lang: string; code: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  }

  function handleDownload() {
    const ext = inferExt(lang);
    const blob = new Blob([code], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `artifact.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className={styles.codeBlock}>
      <div className={styles.codeHeader}>
        <span className={styles.codeLang}>{lang || 'text'}</span>
        <div className={styles.codeActions}>
          <button className={styles.codeBtn} onClick={handleCopy}>
            {copied ? '✓ 복사됨' : '복사'}
          </button>
          <button className={styles.codeBtn} onClick={handleDownload}>
            ↓ 저장
          </button>
        </div>
      </div>
      <SyntaxHighlighter
        style={oneDark}
        language={lang || 'text'}
        PreTag="div"
        customStyle={{
          margin: 0,
          borderRadius: '0 0 6px 6px',
          fontSize: '12px',
          lineHeight: '1.6',
          background: '#0D0E11',
          padding: '14px 16px',
        }}
        codeTagProps={{ style: { fontFamily: 'JetBrains Mono, monospace' } }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  );
}

// ── Markdown 컴포넌트 매핑 ────────────────────────────────────
const mdComponents: Components = {
  // 코드 — 인라인 vs 블록 구분
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className ?? '');
    const isBlock = match !== null || String(children).includes('\n');

    if (isBlock) {
      return (
        <CodeBlock
          lang={match ? match[1] : ''}
          code={String(children).replace(/\n$/, '')}
        />
      );
    }
    return (
      <code className={styles.inlineCode} {...props}>
        {children}
      </code>
    );
  },

  // 헤딩
  h1: ({ children }) => <h1 className={styles.mdH1}>{children}</h1>,
  h2: ({ children }) => <h2 className={styles.mdH2}>{children}</h2>,
  h3: ({ children }) => <h3 className={styles.mdH3}>{children}</h3>,

  // 단락
  p: ({ children }) => <p className={styles.mdP}>{children}</p>,

  // 리스트
  ul: ({ children }) => <ul className={styles.mdUl}>{children}</ul>,
  ol: ({ children }) => <ol className={styles.mdOl}>{children}</ol>,
  li: ({ children }) => <li className={styles.mdLi}>{children}</li>,

  // 표
  table: ({ children }) => (
    <div className={styles.mdTableWrap}>
      <table className={styles.mdTable}>{children}</table>
    </div>
  ),
  th: ({ children }) => <th className={styles.mdTh}>{children}</th>,
  td: ({ children }) => <td className={styles.mdTd}>{children}</td>,

  // 인용
  blockquote: ({ children }) => (
    <blockquote className={styles.mdBlockquote}>{children}</blockquote>
  ),

  // 수평선
  hr: () => <hr className={styles.mdHr} />,

  // 링크
  a: ({ href, children }) => (
    <a className={styles.mdLink} href={href} target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),

  // 강조
  strong: ({ children }) => <strong className={styles.mdStrong}>{children}</strong>,
  em: ({ children }) => <em className={styles.mdEm}>{children}</em>,
};

// ── BubbleAI ─────────────────────────────────────────────────
interface Props {
  text: string;
  time?: string;
}

export function BubbleAI({ text, time }: Props) {
  return (
    <div className={styles.msgAi}>
      <div className={styles.bubbleAi}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
          {text}
        </ReactMarkdown>
      </div>
      {time && <span className={styles.ts}>{time}</span>}
    </div>
  );
}
