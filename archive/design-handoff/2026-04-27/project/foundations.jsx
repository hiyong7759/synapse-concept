/* global React */
const { useState: useState_f } = React;

// ─── BRAND COVER ────────────────────────────────────────────────────────
function BrandCover() {
  return (
    <div style={{
      position: 'relative',
      width: '100%', height: '100%',
      background: 'radial-gradient(ellipse at 20% 30%, rgba(200,169,110,0.08), transparent 50%), radial-gradient(ellipse at 80% 80%, rgba(110,157,200,0.04), transparent 50%), var(--bg)',
      padding: '64px',
      display: 'flex', flexDirection: 'column', justifyContent: 'space-between',
      overflow: 'hidden',
    }}>
      {/* Dot grid bg */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: 'radial-gradient(circle, rgba(200,169,110,0.06) 1px, transparent 1px)',
        backgroundSize: '32px 32px',
        opacity: 0.5,
        maskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)',
      }} />

      <div style={{ position: 'relative', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', letterSpacing: '0.15em', textTransform: 'uppercase' }}>
          [ Design System / v1.0 / 2026 ]
        </span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', letterSpacing: '0.1em' }}>
          ──── 나만 아는 비서
        </span>
      </div>

      <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', gap: 32 }}>
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 32 }}>
          <SynapseMark size={120} glow />
          <div>
            <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 96, fontWeight: 600, margin: 0, lineHeight: 0.95, letterSpacing: '-0.02em', color: 'var(--text)' }}>
              Synapse
            </h1>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 13, color: 'var(--accent)', letterSpacing: '0.2em', marginTop: 12, textTransform: 'uppercase' }}>
              ─ Design System ─
            </div>
          </div>
        </div>
        <p style={{ fontFamily: 'var(--font-display)', fontSize: 24, fontStyle: 'italic', color: 'var(--text-2)', margin: 0, maxWidth: 640, lineHeight: 1.4 }}>
          말하면 쌓이고, 물으면 엮이고, 엮인 것이 다시 재료가 된다.
        </p>
      </div>

      <div style={{ position: 'relative', display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', letterSpacing: '0.1em' }}>
        <div style={{ display: 'flex', gap: 48 }}>
          <div>
            <div style={{ color: 'var(--text-4)', marginBottom: 4 }}>PALETTE</div>
            <div style={{ display: 'flex', gap: 6 }}>
              {['#0A0B0E', '#141519', '#252730', '#C8A96E', '#E8E4D9', '#5DAB8A'].map(c => (
                <span key={c} style={{ width: 14, height: 14, background: c, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 2 }} />
              ))}
            </div>
          </div>
          <div>
            <div style={{ color: 'var(--text-4)', marginBottom: 4 }}>TYPE</div>
            <div style={{ color: 'var(--text-2)', fontFamily: 'var(--font-body)', fontSize: 12 }}>Playfair · Noto Sans KR · JetBrains</div>
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ color: 'var(--text-4)', marginBottom: 4 }}>ON-DEVICE / OFFLINE-FIRST</div>
          <div style={{ color: 'var(--text-2)' }}>Flutter · Gemma 4 E2B · sqflite</div>
        </div>
      </div>
    </div>
  );
}

// ─── BRAND MARK CARD ────────────────────────────────────────────────────
function BrandMarkCard() {
  return (
    <div style={{ width: '100%', height: '100%', padding: 40, background: 'var(--bg)', display: 'flex', flexDirection: 'column', gap: 24 }}>
      <SectionLabel num="01" title="LOGO SUITE" />
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, flex: 1 }}>
        {/* Primary lockup */}
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-lg)', padding: 24, display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <SynapseLogoLockup size={56} />
          </div>
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, marginTop: 16 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Primary lockup</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>Headers, splash, app stores. Min width 120px.</div>
          </div>
        </div>
        {/* Symbol mark */}
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-lg)', padding: 24, display: 'flex', flexDirection: 'column' }}>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <SynapseMark size={84} glow />
          </div>
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12, marginTop: 16 }}>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Symbol mark</div>
            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 4 }}>App icon, favicon, navbar. Two neurons + synapse arc.</div>
          </div>
        </div>
      </div>

      {/* Scale */}
      <div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 12 }}>Scale ladder</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 32, padding: '20px 24px', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-lg)' }}>
          {[64, 40, 24, 16].map(s => (
            <div key={s} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
              <SynapseMark size={s} glow={s >= 40} />
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-3)' }}>{s}px</span>
            </div>
          ))}
          <div style={{ flex: 1, borderLeft: '1px solid var(--border)', paddingLeft: 24, fontSize: 12, color: 'var(--text-3)', lineHeight: 1.6 }}>
            로고 마크는 <span style={{ color: 'var(--accent)' }}>두 개의 시냅스 노드</span>가 발화하는 순간을 형상화. 작은 크기에서도 형태가 유지되도록 단순화.
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── COLOR CARD ─────────────────────────────────────────────────────────
function ColorCard() {
  const palette = [
    { name: 'Background', token: '--bg', hex: '#0A0B0E', use: '루트 배경. 별이 없는 깊은 밤.' },
    { name: 'Surface', token: '--surface', hex: '#141519', use: '카드, 사이드바, 패널.' },
    { name: 'Surface-2', token: '--surface-2', hex: '#1A1C22', use: '입력 필드, hover 상태.' },
    { name: 'Border', token: '--border', hex: '#252730', use: '구분선, 카드 테두리.' },
    { name: 'Border Strong', token: '--border-strong', hex: '#3A3D4A', use: '하이퍼엣지 라인, 강조 보더.' },
  ];
  const fg = [
    { name: 'Text', token: '--text', hex: '#E8E4D9', use: '본문 (warm cream)' },
    { name: 'Text-2', token: '--text-2', hex: '#B8B4A9', use: '보조 본문' },
    { name: 'Text-3', token: '--text-3', hex: '#7A7B82', use: '메타, 캡션' },
    { name: 'Text-4', token: '--text-4', hex: '#555761', use: '비활성, 힌트' },
  ];
  const semantic = [
    { name: 'Accent', token: '--accent', hex: '#C8A96E', use: '브랜드 골드. 통찰 노드, 핵심 액션.' },
    { name: 'Success', token: '--success', hex: '#5DAB8A', use: '저장 완료, 정리됨' },
    { name: 'Danger', token: '--danger', hex: '#C85D5D', use: '삭제, 경고' },
    { name: 'Hyperedge', token: '--hyperedge', hex: '#3A3D4A', use: '바구니 시각화' },
  ];

  const Swatch = ({ p, big }) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ background: p.hex, height: big ? 64 : 48, borderRadius: 'var(--r-md)', border: '1px solid rgba(255,255,255,0.06)' }} />
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <span style={{ fontSize: 12, color: 'var(--text)', fontWeight: 500 }}>{p.name}</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-3)' }}>{p.hex}</span>
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)' }}>{p.token}</div>
      <div style={{ fontSize: 11, color: 'var(--text-3)', lineHeight: 1.4 }}>{p.use}</div>
    </div>
  );

  return (
    <div style={{ width: '100%', height: '100%', padding: 40, background: 'var(--bg)', display: 'flex', flexDirection: 'column', gap: 24, overflow: 'auto' }}>
      <SectionLabel num="02" title="COLOR PALETTE" subtitle="딥 네이비블랙 위에 웜 크림과 앰버골드. 차갑지 않은 어둠." />

      <div>
        <SubLabel>Surface</SubLabel>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)', gap: 14 }}>
          {palette.map(p => <Swatch key={p.name} p={p} />)}
        </div>
      </div>
      <div>
        <SubLabel>Foreground</SubLabel>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
          {fg.map(p => <Swatch key={p.name} p={p} />)}
        </div>
      </div>
      <div>
        <SubLabel>Brand & Semantic</SubLabel>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
          {semantic.map(p => <Swatch key={p.name} p={p} big />)}
        </div>
      </div>

      <div style={{ marginTop: 'auto', padding: 16, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 24 }}>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>Node states</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <Node label="기본" size={9} />
            <Node label="허브" size={9} hub />
            <Node label="통찰" size={9} insight />
            <Node label="흐림" size={9} dim />
          </div>
        </div>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>Glow</div>
          <div style={{ fontSize: 11, color: 'var(--text-3)' }}>앰버 글로우는 <strong style={{ color: 'var(--accent)' }}>발화·점화 순간</strong>에만. 정적 강조에는 사용 금지.</div>
        </div>
        <div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 6 }}>Saturation rule</div>
          <div style={{ fontSize: 11, color: 'var(--text-3)' }}>모든 surface 톤은 chroma &lt; 0.02. 채도는 액센트와 노드에만 살린다.</div>
        </div>
      </div>
    </div>
  );
}

// ─── TYPE CARD ──────────────────────────────────────────────────────────
function TypeCard() {
  const TypeRow = ({ family, role, sample, sub, fontFamily }) => (
    <div style={{ borderTop: '1px solid var(--border)', padding: '20px 0', display: 'grid', gridTemplateColumns: '180px 1fr', gap: 24, alignItems: 'baseline' }}>
      <div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', textTransform: 'uppercase' }}>{role}</div>
        <div style={{ fontSize: 13, color: 'var(--text-2)', marginTop: 4 }}>{family}</div>
        <div style={{ fontSize: 11, color: 'var(--text-3)', marginTop: 2 }}>{sub}</div>
      </div>
      <div style={{ fontFamily, color: 'var(--text)' }}>{sample}</div>
    </div>
  );

  return (
    <div style={{ width: '100%', height: '100%', padding: 40, background: 'var(--bg)', display: 'flex', flexDirection: 'column', gap: 16, overflow: 'auto' }}>
      <SectionLabel num="03" title="TYPOGRAPHY" subtitle="세 폰트로 직조하는 위계 — 서구 세리프의 격조, 한글 산세리프의 가독성, 모노의 정밀성." />

      <div>
        <TypeRow
          role="Display / Brand"
          family="Playfair Display"
          sub="600 weight. -0.02em tracking."
          fontFamily="var(--font-display)"
          sample={<div style={{ fontSize: 64, fontWeight: 600, lineHeight: 1, letterSpacing: '-0.02em' }}>Synapse</div>}
        />
        <TypeRow
          role="Display Italic"
          family="Playfair Display Italic"
          sub="인용, 슬로건, 빈 상태 메시지"
          fontFamily="var(--font-display)"
          sample={<div style={{ fontSize: 28, fontStyle: 'italic', color: 'var(--text-2)' }}>나의 맥락을 매번 설명하지 않아도 되는 세상.</div>}
        />
        <TypeRow
          role="Body — KR"
          family="Noto Sans KR"
          sub="400/500/600. 본문 14px, line-height 1.55"
          fontFamily="var(--font-body)"
          sample={
            <div>
              <div style={{ fontSize: 17, fontWeight: 500, marginBottom: 8 }}>오늘 회의가 세 개 연속이었다.</div>
              <div style={{ fontSize: 14, color: 'var(--text-2)' }}>김민수가 새 컴포넌트 시안 잡아왔다. 박지수 팀장이 다음 주까지 검토 부탁.</div>
            </div>
          }
        />
        <TypeRow
          role="Mono"
          family="JetBrains Mono"
          sub="노드 이름, 카테고리 코드, 키바인딩, 메타 라벨"
          fontFamily="var(--font-mono)"
          sample={
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 13 }}>
              <div><span style={{ color: 'var(--accent)' }}>node</span> · 박지수 → 더나은.개발팀</div>
              <div><span style={{ color: 'var(--text-3)' }}>category</span> · BOD/WRK/FOD · 자모-거리 1</div>
              <div><span style={{ color: 'var(--text-3)' }}>kbd</span> · ⌘S · ⌘K · ESC</div>
            </div>
          }
        />
      </div>

      {/* Scale */}
      <div style={{ borderTop: '1px solid var(--border)', paddingTop: 20 }}>
        <SubLabel>Scale</SubLabel>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 12 }}>
          {[
            { label: 'xs', size: 11 },
            { label: 'sm', size: 12 },
            { label: 'base', size: 14 },
            { label: 'md', size: 15 },
            { label: 'lg', size: 17 },
            { label: 'xl', size: 20 },
            { label: '2xl', size: 24 },
          ].map(s => (
            <div key={s.label} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: 12 }}>
              <div style={{ fontSize: s.size, color: 'var(--text)', marginBottom: 6 }}>가</div>
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.05em' }}>{s.label} · {s.size}px</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── COMPONENT GALLERY ──────────────────────────────────────────────────
function ComponentGallery() {
  return (
    <div style={{ width: '100%', height: '100%', padding: 40, background: 'var(--bg)', display: 'flex', flexDirection: 'column', gap: 24, overflow: 'auto' }}>
      <SectionLabel num="04" title="CORE COMPONENTS" subtitle="앱 전체에서 일관되게 재사용되는 베이스 컴포넌트." />

      {/* Buttons */}
      <Section title="Buttons">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10 }}>
          <Button variant="primary" icon={<Icon.Sparkle />}>정리하기</Button>
          <Button variant="primary" kbd="⌘S">정리</Button>
          <Button variant="secondary">취소</Button>
          <Button variant="outline" icon={<Icon.Promote />}>통찰로 승격</Button>
          <Button variant="ghost" icon={<Icon.Plus />}>새 노트</Button>
          <Button variant="danger" icon={<Icon.Trash />}>삭제</Button>
          <Button variant="ghost" size="sm">작게</Button>
          <Button variant="primary" size="lg" icon={<Icon.Send />}>보내기</Button>
        </div>
      </Section>

      {/* Badges */}
      <Section title="Badges & Status">
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center' }}>
          <Badge tone="insight" icon={<Icon.Sparkle />}>통찰</Badge>
          <Badge tone="success" icon={<Icon.Check />}>저장됨 · 방금</Badge>
          <Badge tone="neutral">변경됨</Badge>
          <Badge tone="neutral" icon={<Icon.Spinner />}>저장 중…</Badge>
          <Badge tone="neutral" icon={<Icon.Cog />}>정리 중…</Badge>
          <Badge tone="mono">BOD</Badge>
          <Badge tone="mono">WRK</Badge>
          <Badge tone="mono">FOD</Badge>
          <Badge tone="danger">탐색 실패</Badge>
        </div>
      </Section>

      {/* Inputs */}
      <Section title="Inputs">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
          <TextInput placeholder="질문을 입력하세요…" />
          <TextInput placeholder="노드 이름 검색" mono />
        </div>
        {/* Composer */}
        <div style={{ marginTop: 12, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-lg)', padding: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
          <input style={{ flex: 1, background: 'transparent', border: 0, color: 'var(--text)', fontSize: 14, outline: 'none', fontFamily: 'var(--font-body)' }} placeholder="허리 어떻게 진행되고 있지?" />
          <Button variant="primary" size="sm" icon={<Icon.Send />}>보내기</Button>
        </div>
      </Section>

      {/* Nodes */}
      <Section title="Hypergraph nodes & edges">
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-lg)', padding: 24, display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <Node label="박지수 (default)" size={9} />
            <Node label="개발팀 (hub)" size={10} hub />
            <Node label="허리 치료 진행 (insight)" size={10} insight />
            <Node label="비활성 (dim)" size={9} dim />
          </div>
          <div style={{ position: 'relative', minHeight: 140 }}>
            <MiniGraph />
          </div>
        </div>
      </Section>

      {/* Correction card preview */}
      <Section title="LLM correction card (제안만, 자동 적용 금지)">
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <CorrectionCard from="스ㅏ타벅스" to="스타벅스" reason="자모 거리 1, 별칭 미등록" />
          <CorrectionCard from="김민수" to="김민슈" reason="자모 거리 1" />
        </div>
      </Section>
    </div>
  );
}

function CorrectionCard({ from, to, reason }) {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: 14 }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', textTransform: 'uppercase', marginBottom: 8 }}>
        ─── LLM 정정 후보 ───
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 4 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 15, color: 'var(--text-3)', textDecoration: 'line-through' }}>{from}</span>
        <span style={{ color: 'var(--text-4)' }}>→</span>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 15, color: 'var(--accent)', fontWeight: 500 }}>{to}</span>
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12 }}>근거: {reason}</div>
      <div style={{ display: 'flex', gap: 8 }}>
        <Button variant="primary" size="sm">적용</Button>
        <Button variant="secondary" size="sm">무시</Button>
      </div>
    </div>
  );
}

function MiniGraph() {
  // tiny hypergraph viz
  const nodes = [
    { x: 50, y: 30, label: '박지수' },
    { x: 180, y: 40, label: '개발팀', hub: true },
    { x: 280, y: 80, label: '김민수' },
    { x: 130, y: 100, label: '회의' },
    { x: 220, y: 130, label: '시안' },
  ];
  const edges = [[0,1],[1,2],[1,3],[3,4],[2,4]];
  return (
    <svg viewBox="0 0 320 160" style={{ width: '100%', height: '100%' }}>
      {/* hyperedge basket */}
      <path d="M 110 90 Q 100 60, 170 30 Q 240 30, 250 70 Q 240 130, 150 130 Q 90 120, 110 90 Z"
        fill="none" stroke="var(--hyperedge)" strokeWidth="1" strokeDasharray="3 3" opacity="0.5" />
      {edges.map(([a,b], i) => (
        <line key={i} x1={nodes[a].x} y1={nodes[a].y} x2={nodes[b].x} y2={nodes[b].y}
          stroke="var(--border-strong)" strokeWidth="1" />
      ))}
      {nodes.map((n,i) => (
        <g key={i}>
          <circle cx={n.x} cy={n.y} r={n.hub ? 6 : 4.5} fill={n.hub ? 'var(--accent)' : 'var(--node)'}
            style={{ filter: n.hub ? 'drop-shadow(0 0 6px rgba(200,169,110,0.5))' : 'none' }} />
          <text x={n.x + 10} y={n.y + 4} fill="var(--text-2)" fontSize="10" fontFamily="var(--font-mono)">{n.label}</text>
        </g>
      ))}
    </svg>
  );
}

// ─── SECTION HELPERS ────────────────────────────────────────────────────
function SectionLabel({ num, title, subtitle }) {
  return (
    <div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-4)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 6 }}>
        [ Section {num} ]
      </div>
      <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 32, fontWeight: 600, margin: 0, color: 'var(--text)', letterSpacing: '-0.01em' }}>{title}</h2>
      {subtitle && <p style={{ fontSize: 13, color: 'var(--text-3)', margin: '8px 0 0', maxWidth: 640 }}>{subtitle}</p>}
    </div>
  );
}
function SubLabel({ children }) {
  return <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.15em', textTransform: 'uppercase', marginBottom: 12 }}>─── {children} ───</div>;
}
function Section({ title, children }) {
  return (
    <div>
      <SubLabel>{title}</SubLabel>
      {children}
    </div>
  );
}

Object.assign(window, {
  BrandCover, BrandMarkCard, ColorCard, TypeCard, ComponentGallery,
  SectionLabel, SubLabel, Section,
});
