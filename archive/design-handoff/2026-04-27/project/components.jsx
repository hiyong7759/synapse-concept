/* global React */
const { useState, useEffect, useRef, useMemo } = React;

// ─── BRAND MARK ─────────────────────────────────────────────────────────
function SynapseMark({ size = 24, glow = false }) {
  const r = size * 0.18;
  const cx1 = size * 0.18, cx2 = size * 0.82, cy = size * 0.5;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} style={{ display: 'block', filter: glow ? 'drop-shadow(0 0 6px rgba(200,169,110,0.6))' : 'none' }}>
      <path d={`M ${cx1} ${cy} Q ${size * 0.5} ${size * 0.05}, ${cx2} ${cy}`}
        fill="none" stroke="var(--accent)" strokeWidth={size * 0.04} strokeLinecap="round" />
      <circle cx={cx1} cy={cy} r={r} fill="var(--accent)" />
      <circle cx={cx2} cy={cy} r={r} fill="var(--accent)" />
      <circle cx={cx1} cy={cy} r={r * 0.4} fill="var(--bg)" />
      <circle cx={cx2} cy={cy} r={r * 0.4} fill="var(--bg)" />
    </svg>
  );
}

function SynapseLogoLockup({ size = 32 }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <SynapseMark size={size} glow />
      <span style={{ fontFamily: 'var(--font-display)', fontSize: size * 0.78, fontWeight: 600, letterSpacing: '0.02em', color: 'var(--text)' }}>
        Synapse
      </span>
    </div>
  );
}

// ─── BUTTONS ────────────────────────────────────────────────────────────
function Button({ children, variant = 'ghost', size = 'md', icon, onClick, disabled, kbd, style }) {
  const [hover, setHover] = useState(false);
  const sizes = {
    sm: { padding: '4px 10px', fontSize: 12, height: 26 },
    md: { padding: '6px 12px', fontSize: 13, height: 32 },
    lg: { padding: '8px 16px', fontSize: 14, height: 38 },
  };
  const variants = {
    primary: {
      bg: hover ? 'var(--accent-2)' : 'var(--accent)',
      color: '#1a1408',
      border: '1px solid var(--accent)',
      shadow: hover ? 'var(--glow-amber-sm)' : 'none',
    },
    secondary: {
      bg: hover ? 'var(--surface-3)' : 'var(--surface-2)',
      color: 'var(--text)',
      border: '1px solid var(--border-2)',
    },
    ghost: {
      bg: hover ? 'var(--surface-2)' : 'transparent',
      color: 'var(--text-2)',
      border: '1px solid transparent',
    },
    outline: {
      bg: hover ? 'var(--accent-soft)' : 'transparent',
      color: 'var(--accent)',
      border: '1px solid var(--accent-line)',
    },
    danger: {
      bg: hover ? 'rgba(200,93,93,0.18)' : 'transparent',
      color: 'var(--danger)',
      border: '1px solid transparent',
    },
  };
  const v = variants[variant];
  const s = sizes[size];
  return (
    <button
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onClick={onClick}
      disabled={disabled}
      style={{
        ...s,
        background: v.bg,
        color: v.color,
        border: v.border,
        boxShadow: v.shadow,
        borderRadius: 'var(--r-md)',
        fontFamily: 'var(--font-body)',
        fontWeight: 500,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        transition: 'all var(--dur-fast) var(--ease)',
        ...style,
      }}
    >
      {icon}
      <span>{children}</span>
      {kbd && <kbd style={{
        marginLeft: 4, fontFamily: 'var(--font-mono)', fontSize: 10,
        padding: '1px 5px', borderRadius: 3,
        background: 'rgba(0,0,0,0.3)', color: 'inherit', opacity: 0.7,
        border: '1px solid rgba(255,255,255,0.08)'
      }}>{kbd}</kbd>}
    </button>
  );
}

// ─── BADGES & CHIPS ─────────────────────────────────────────────────────
function Badge({ children, tone = 'neutral', icon }) {
  const tones = {
    neutral: { bg: 'var(--surface-3)', color: 'var(--text-2)', border: 'var(--border)' },
    insight: { bg: 'var(--accent-soft)', color: 'var(--accent)', border: 'var(--accent-line)' },
    success: { bg: 'rgba(93,171,138,0.12)', color: 'var(--success)', border: 'rgba(93,171,138,0.3)' },
    danger: { bg: 'rgba(200,93,93,0.12)', color: 'var(--danger)', border: 'rgba(200,93,93,0.3)' },
    mono: { bg: 'transparent', color: 'var(--text-3)', border: 'var(--border)' },
  };
  const t = tones[tone];
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      padding: '2px 7px', borderRadius: 'var(--r-sm)',
      background: t.bg, color: t.color, border: `1px solid ${t.border}`,
      fontSize: 11, fontFamily: tone === 'mono' ? 'var(--font-mono)' : 'var(--font-body)',
      fontWeight: 500, letterSpacing: tone === 'mono' ? '0.04em' : '0',
      textTransform: tone === 'mono' ? 'uppercase' : 'none',
    }}>
      {icon}{children}
    </span>
  );
}

// ─── INPUTS ─────────────────────────────────────────────────────────────
function TextInput({ placeholder, value, onChange, mono, style }) {
  const [focus, setFocus] = useState(false);
  return (
    <input
      type="text"
      value={value || ''}
      onChange={onChange}
      placeholder={placeholder}
      onFocus={() => setFocus(true)}
      onBlur={() => setFocus(false)}
      style={{
        width: '100%',
        background: 'var(--surface-2)',
        border: `1px solid ${focus ? 'var(--accent-line)' : 'var(--border-2)'}`,
        borderRadius: 'var(--r-md)',
        padding: '8px 12px',
        color: 'var(--text)',
        fontFamily: mono ? 'var(--font-mono)' : 'var(--font-body)',
        fontSize: 13,
        outline: 'none',
        transition: 'border-color var(--dur-fast) var(--ease)',
        ...style,
      }}
    />
  );
}

// ─── CARD ───────────────────────────────────────────────────────────────
function Card({ children, accent, glow, style }) {
  return (
    <div style={{
      background: 'var(--surface)',
      border: `1px solid ${accent ? 'var(--accent-line)' : 'var(--border)'}`,
      borderRadius: 'var(--r-lg)',
      boxShadow: glow ? 'var(--glow-amber)' : 'var(--shadow-1)',
      ...style,
    }}>
      {children}
    </div>
  );
}

// ─── NODE GLYPH ─────────────────────────────────────────────────────────
function Node({ size = 8, hub, insight, dim, label, labelSide = 'right' }) {
  const fill = insight ? 'var(--node-insight)' : hub ? 'var(--accent)' : 'var(--node)';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 6,
      flexDirection: labelSide === 'left' ? 'row-reverse' : 'row',
      opacity: dim ? 0.35 : 1,
    }}>
      <span style={{
        width: hub ? size + 4 : size, height: hub ? size + 4 : size,
        borderRadius: '50%', background: fill,
        boxShadow: hub ? '0 0 10px rgba(200,169,110,0.5)' : insight ? '0 0 14px rgba(217,188,131,0.7)' : 'none',
        outline: insight ? '2px solid var(--accent-line)' : 'none',
        outlineOffset: 2,
      }} />
      {label && <span style={{
        fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-2)',
        whiteSpace: 'nowrap',
      }}>{label}</span>}
    </span>
  );
}

// ─── ICONS (minimal stroke set) ─────────────────────────────────────────
const Icon = {
  Plus: (p) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...p}><path d="M7 2v10M2 7h10" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/></svg>,
  Check: (p) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...p}><path d="M2.5 7l3 3 6-6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  Sparkle: (p) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...p}><path d="M7 1l1.4 4.6L13 7l-4.6 1.4L7 13l-1.4-4.6L1 7l4.6-1.4L7 1z" fill="currentColor"/></svg>,
  Cog: (p) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...p}><circle cx="7" cy="7" r="2.2" stroke="currentColor" strokeWidth="1.3"/><path d="M7 1v2M7 11v2M1 7h2M11 7h2M2.8 2.8l1.4 1.4M9.8 9.8l1.4 1.4M2.8 11.2l1.4-1.4M9.8 4.2l1.4-1.4" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>,
  Graph: (p) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...p}><circle cx="3" cy="3" r="1.8" stroke="currentColor" strokeWidth="1.2"/><circle cx="11" cy="4" r="1.8" stroke="currentColor" strokeWidth="1.2"/><circle cx="7" cy="11" r="1.8" stroke="currentColor" strokeWidth="1.2"/><path d="M4.4 3.8L9.6 5M9.6 5.5L7.8 9.4M4 4.5l2.5 5" stroke="currentColor" strokeWidth="1" strokeLinecap="round"/></svg>,
  Search: (p) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...p}><circle cx="6" cy="6" r="3.5" stroke="currentColor" strokeWidth="1.3"/><path d="M9 9l3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>,
  Menu: (p) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...p}><path d="M2 4h10M2 7h10M2 10h10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/></svg>,
  Send: (p) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...p}><path d="M2 7l10-5-3.5 11L7 8.5 2 7z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" fill="none"/></svg>,
  Promote: (p) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...p}><path d="M7 11V3M3.5 6.5L7 3l3.5 3.5" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/></svg>,
  Trash: (p) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...p}><path d="M2.5 4h9M5 4V2.5h4V4M4 4l.5 8h5L10 4M6 6.5v3.5M8 6.5v3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>,
  Collapse: (p) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...p}><rect x="2" y="2" width="10" height="10" rx="1.5" stroke="currentColor" strokeWidth="1.2"/><path d="M5 7h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round"/></svg>,
  Spinner: (p) => <svg width="14" height="14" viewBox="0 0 14 14" fill="none" {...p}><circle cx="7" cy="7" r="5" stroke="currentColor" strokeWidth="1.4" strokeDasharray="6 24" strokeLinecap="round"><animateTransform attributeName="transform" type="rotate" from="0 7 7" to="360 7 7" dur="1s" repeatCount="indefinite"/></circle></svg>,
};

// Export
Object.assign(window, {
  SynapseMark, SynapseLogoLockup,
  Button, Badge, TextInput, Card, Node, Icon,
});
