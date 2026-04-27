/* global React */

// ─── /NOTE SCREEN ─────────────────────────────────────────────────────
function NoteScreen() {
  return (
    <div style={{ width: '100%', height: '100%', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      <TopBar active="note" />
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '220px 1fr 320px', minHeight: 0 }}>
        <PostSidebar />
        <NoteEditorPane />
        <NoteGraphPanel />
      </div>
    </div>
  );
}

function TopBar({ active }) {
  const RouteTab = ({ id, label }) => (
    <span style={{
      fontFamily: 'var(--font-mono)', fontSize: 12, padding: '4px 10px',
      color: active === id ? 'var(--accent)' : 'var(--text-3)',
      borderBottom: active === id ? '1px solid var(--accent)' : '1px solid transparent',
      cursor: 'pointer', letterSpacing: '0.05em',
    }}>/{label}</span>
  );
  return (
    <div style={{ height: 48, padding: '0 20px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg-2)' }}>
      <SynapseLogoLockup size={20} />
      <div style={{ display: 'flex', gap: 4 }}>
        <RouteTab id="note" label="note" />
        <RouteTab id="synapse" label="synapse" />
        <RouteTab id="hypergraph" label="hypergraph" />
      </div>
    </div>
  );
}

function PostSidebar({ activeId = 12 }) {
  const notes = [
    { id: 12, title: '허리 치료', time: '4분 전' },
    { id: 11, title: '팀 회의록', time: '2시간 전' },
    { id: 10, title: '모바일 우선 결정', time: '어제', insight: true },
  ];
  const synapses = [
    { id: 9, title: '허리 치료', time: '3시간 전' },
    { id: 7, title: '주말 일정', time: '그저께' },
  ];
  return (
    <div style={{ borderRight: '1px solid var(--border)', background: 'var(--bg-2)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)' }}>
        <Button variant="ghost" size="sm" icon={<Icon.Plus />}>새 노트</Button>
      </div>
      <div style={{ overflow: 'auto', flex: 1 }}>
        <SidebarGroup label="── 노트 ──">
          {notes.map(n => <PostRow key={n.id} {...n} active={activeId === n.id} />)}
        </SidebarGroup>
        <SidebarGroup label="── 시냅스 ──">
          {synapses.map(n => <PostRow key={n.id} {...n} synapse />)}
        </SidebarGroup>
      </div>
    </div>
  );
}

function SidebarGroup({ label, children }) {
  return (
    <div style={{ padding: '12px 0' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.15em', padding: '0 14px 8px' }}>{label}</div>
      <div>{children}</div>
    </div>
  );
}

function PostRow({ id, title, time, insight, active, synapse }) {
  return (
    <div style={{
      padding: '10px 14px',
      background: active ? 'var(--surface)' : 'transparent',
      borderLeft: active ? '2px solid var(--accent)' : '2px solid transparent',
      borderTop: insight ? '1px solid transparent' : 'none',
      cursor: 'pointer',
      display: 'flex', flexDirection: 'column', gap: 3,
      ...(insight ? { background: 'rgba(200,169,110,0.05)', borderTop: '1px solid var(--accent-line)', borderBottom: '1px solid var(--accent-line)' } : {})
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-4)', minWidth: 18 }}>{id}</span>
        {insight && <span style={{ color: 'var(--accent)', fontSize: 11 }}>✦</span>}
        {synapse && <span style={{ color: 'var(--text-3)', fontSize: 11 }}>◯</span>}
        <span style={{ fontSize: 13, color: active ? 'var(--text)' : 'var(--text-2)', fontWeight: active ? 500 : 400 }}>{title}</span>
      </div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', paddingLeft: 24 }}>{time}</div>
    </div>
  );
}

function NoteEditorPane() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      {/* Status bar */}
      <div style={{ padding: '10px 24px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Badge tone="success" icon={<Icon.Check />}>저장됨 · 방금</Badge>
        <Button variant="primary" size="sm" icon={<Icon.Sparkle />} kbd="⌘S">정리</Button>
      </div>
      {/* Editor */}
      <div style={{ flex: 1, padding: '32px 48px', overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 16, fontSize: 15, lineHeight: 1.7 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 36, fontWeight: 600, margin: 0, color: 'var(--text)', letterSpacing: '-0.01em' }}># 더나은</h1>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 500, margin: 0, color: 'var(--text-2)' }}>## 개발팀</h2>
        <ul style={{ margin: 0, paddingLeft: 20, color: 'var(--text)', display: 'flex', flexDirection: 'column', gap: 4 }}>
          <li>팀장:: <span style={{ color: 'var(--accent)' }}>박지수</span></li>
          <li>프론트엔드 김민수</li>
        </ul>
        <p style={{ margin: 0, color: 'var(--text)' }}>오늘 회의가 세 개 연속이었다.</p>
        <p style={{ margin: 0, color: 'var(--text)' }}>김민수가 새 컴포넌트 시안 잡아왔다.</p>

        {/* Correction card inline */}
        <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <CorrectionCard from="스ㅏ타벅스" to="스타벅스" reason="자모 거리 1, 별칭 미등록" />
        </div>
      </div>
    </div>
  );
}

function NoteGraphPanel() {
  return (
    <div style={{ borderLeft: '1px solid var(--border)', background: 'var(--bg-2)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Icon.Graph style={{ color: 'var(--text-2)' }} />
          <span style={{ fontSize: 12, color: 'var(--text-2)', fontWeight: 500 }}>이 노트 그래프</span>
        </div>
        <Icon.Collapse style={{ color: 'var(--text-3)', cursor: 'pointer' }} />
      </div>
      <div style={{ flex: 1, position: 'relative', padding: 16, minHeight: 280 }}>
        <NoteGraphSVG />
      </div>
      <div style={{ borderTop: '1px solid var(--border)', padding: '10px 16px', display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em' }}>CATEGORY</div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)' }}>더나은.개발팀</div>
        <div style={{ display: 'flex', gap: 12, marginTop: 6, fontSize: 11, color: 'var(--text-3)' }}>
          <span>노드 <span style={{ color: 'var(--text-2)' }}>7</span></span>
          <span>바구니 <span style={{ color: 'var(--text-2)' }}>4</span></span>
        </div>
      </div>
    </div>
  );
}

function NoteGraphSVG() {
  return (
    <svg viewBox="0 0 280 320" style={{ width: '100%', height: '100%' }}>
      {/* hyperedge basket 1 - 회의 */}
      <ellipse cx="140" cy="180" rx="105" ry="45" fill="rgba(200,169,110,0.04)" stroke="var(--hyperedge)" strokeDasharray="3 3" strokeWidth="1" />
      {/* hyperedge basket 2 - team */}
      <ellipse cx="140" cy="80" rx="115" ry="40" fill="rgba(110,157,200,0.03)" stroke="var(--hyperedge)" strokeDasharray="3 3" strokeWidth="1" />

      {/* edges */}
      <g stroke="var(--border-strong)" strokeWidth="1">
        <line x1="60" y1="80" x2="140" y2="60" />
        <line x1="140" y1="60" x2="220" y2="80" />
        <line x1="60" y1="80" x2="100" y2="170" />
        <line x1="220" y1="80" x2="180" y2="170" />
        <line x1="100" y1="170" x2="180" y2="170" />
        <line x1="140" y1="200" x2="140" y2="250" />
        <line x1="140" y1="250" x2="140" y2="300" />
      </g>

      {/* nodes */}
      {[
        { x: 60, y: 80, label: '박지수' },
        { x: 140, y: 60, label: '개발팀', hub: true },
        { x: 220, y: 80, label: '김민수' },
        { x: 100, y: 170, label: '더나은' },
        { x: 180, y: 170, label: '회의', hub: true },
        { x: 140, y: 250, label: '컴포넌트' },
        { x: 140, y: 300, label: '시안' },
      ].map((n, i) => (
        <g key={i}>
          <circle cx={n.x} cy={n.y} r={n.hub ? 6 : 4.5}
            fill={n.hub ? 'var(--accent)' : 'var(--node)'}
            style={{ filter: n.hub ? 'drop-shadow(0 0 6px rgba(200,169,110,0.5))' : 'none' }} />
          <text x={n.x} y={n.y - 10} textAnchor="middle" fill="var(--text-2)" fontSize="10" fontFamily="var(--font-mono)">{n.label}</text>
        </g>
      ))}
    </svg>
  );
}

// ─── /SYNAPSE SCREEN ──────────────────────────────────────────────────
function SynapseScreen() {
  return (
    <div style={{ width: '100%', height: '100%', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      <TopBar active="synapse" />
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '220px 1fr 320px', minHeight: 0 }}>
        <PostSidebar activeId={9} />
        <SynapseThread />
        <SynapseGraphPanel />
      </div>
    </div>
  );
}

function SynapseThread() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: 0, background: 'var(--bg)' }}>
      <div style={{ flex: 1, overflow: 'auto', padding: '32px 48px', display: 'flex', flexDirection: 'column', gap: 20 }}>
        {/* Q */}
        <div style={{
          alignSelf: 'flex-end', maxWidth: '78%',
          background: 'var(--surface)', border: '1px solid var(--border)',
          borderRadius: '14px 14px 4px 14px',
          padding: '12px 16px', fontSize: 14,
        }}>
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', marginRight: 8 }}>Q</span>
          허리 어떻게 진행되고 있지?
        </div>

        {/* Exploring trace */}
        <div style={{ alignSelf: 'flex-start', maxWidth: '78%', display: 'flex', flexDirection: 'column', gap: 10, fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-3)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <Icon.Spinner style={{ color: 'var(--accent)' }} />
            <span>탐색 중…</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, paddingLeft: 22 }}>
            <Node size={7} hub /> <span style={{ color: 'var(--text-2)' }}>허리</span>
            <span style={{ color: 'var(--text-4)' }}>──</span>
            <Node size={7} /> <span>디스크</span>
            <span style={{ color: 'var(--text-4)' }}>──</span>
            <Node size={7} dim /> <span style={{ opacity: 0.5 }}>L4-L5</span>
          </div>
        </div>

        {/* Answer card */}
        <div style={{
          alignSelf: 'flex-start', maxWidth: '85%',
          background: 'var(--surface)', border: '1px solid var(--accent-line)',
          borderRadius: '4px 14px 14px 14px',
          padding: 18,
          boxShadow: '0 0 24px rgba(200,169,110,0.08)',
          position: 'relative',
        }}>
          <div style={{ position: 'absolute', top: -8, right: 16 }}>
            <Badge tone="insight" icon={<Icon.Sparkle />}>답변</Badge>
          </div>
          <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', marginBottom: 8 }}>A</div>
          <div style={{ fontSize: 14, color: 'var(--text)', lineHeight: 1.65 }}>
            <strong style={{ color: 'var(--accent)' }}>2026-04-06</strong> L4-L5 진단,&nbsp;
            <strong style={{ color: 'var(--accent)' }}>4-08</strong>부터 강남세브란스 정형외과에서 물리치료 3회차 받았고,&nbsp;
            <strong style={{ color: 'var(--accent)' }}>4-10</strong>에 <em style={{ color: 'var(--text-2)' }}>"다 나았다"</em> 기록.
          </div>
          <div style={{ marginTop: 16, display: 'flex', gap: 8 }}>
            <Button variant="outline" size="sm" icon={<Icon.Promote />}>통찰로 승격</Button>
            <Button variant="ghost" size="sm">재질문</Button>
            <Button variant="ghost" size="sm">복사</Button>
          </div>
        </div>
      </div>

      {/* Composer */}
      <div style={{ padding: 20, borderTop: '1px solid var(--border)' }}>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border-2)', borderRadius: 'var(--r-lg)', padding: '10px 12px', display: 'flex', alignItems: 'center', gap: 8 }}>
          <input style={{ flex: 1, background: 'transparent', border: 0, color: 'var(--text)', fontSize: 14, outline: 'none', fontFamily: 'var(--font-body)' }} placeholder="질문 입력…" />
          <Button variant="primary" size="sm" icon={<Icon.Send />}>보내기</Button>
        </div>
      </div>
    </div>
  );
}

function SynapseGraphPanel() {
  return (
    <div style={{ borderLeft: '1px solid var(--border)', background: 'var(--bg-2)', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <Icon.Graph style={{ color: 'var(--text-2)' }} />
          <span style={{ fontSize: 12, color: 'var(--text-2)', fontWeight: 500 }}>이 세션 그래프</span>
        </div>
        <Icon.Collapse style={{ color: 'var(--text-3)', cursor: 'pointer' }} />
      </div>
      <div style={{ flex: 1, padding: 16, minHeight: 280 }}>
        <svg viewBox="0 0 280 340" style={{ width: '100%', height: '100%' }}>
          <ellipse cx="140" cy="170" rx="120" ry="120" fill="rgba(200,169,110,0.04)" stroke="var(--hyperedge)" strokeDasharray="3 3" strokeWidth="1" />
          <g stroke="var(--border-strong)" strokeWidth="1">
            <line x1="80" y1="50" x2="140" y2="100" />
            <line x1="200" y1="60" x2="140" y2="100" />
            <line x1="140" y1="100" x2="140" y2="160" />
            <line x1="140" y1="160" x2="140" y2="220" />
            <line x1="140" y1="220" x2="140" y2="280" />
          </g>
          {[
            { x: 80, y: 50, label: '허리', hub: true },
            { x: 200, y: 60, label: 'L4-L5' },
            { x: 140, y: 100, label: '디스크' },
            { x: 140, y: 160, label: '진단' },
            { x: 140, y: 220, label: '강남세브란스' },
            { x: 140, y: 280, label: '물리치료' },
          ].map((n, i) => (
            <g key={i}>
              <circle cx={n.x} cy={n.y} r={n.hub ? 6 : 4.5}
                fill={n.hub ? 'var(--accent)' : 'var(--node)'}
                style={{ filter: n.hub ? 'drop-shadow(0 0 6px rgba(200,169,110,0.5))' : 'none' }} />
              <text x={n.x + 10} y={n.y + 4} fill="var(--text-2)" fontSize="10" fontFamily="var(--font-mono)">{n.label}</text>
            </g>
          ))}
        </svg>
      </div>
      <div style={{ borderTop: '1px solid var(--border)', padding: '10px 16px', fontSize: 11, color: 'var(--text-3)', display: 'flex', flexDirection: 'column', gap: 4 }}>
        <div>retrieve 캐시 <span style={{ color: 'var(--text-2)' }}>6 노드</span></div>
        <div>✦ 통찰 <span style={{ color: 'var(--text-2)' }}>0</span> <span style={{ color: 'var(--text-4)' }}>(승격 전)</span></div>
      </div>
    </div>
  );
}

// ─── /HYPERGRAPH SCREEN (옵션 ε — 노드 중심 + hover 시 바구니 원문) ──────
// 카테고리별 색상 (시드 19 중 일부)
const CAT_COLORS = {
  BOD: '#C85D5D',  // 빨강 (body)
  WRK: '#6E9DC8',  // 파랑 (work)
  FOD: '#D9A55D',  // 주황 (food)
  REL: '#B68AC8',  // 보라 (relationship)
  MED: '#5DAB8A',  // 초록 (media/medical)
  PLC: '#8AC8B6',  // 청록 (place)
  TIM: '#7A7B82',  // 회색 (time)
};

// 더미 노드 데이터 — 시각의 주인공
const HYPERGRAPH_NODES = [
  // 의료/신체 클러스터 (BOD)
  { id: 'yak',     label: '약',           x: 240, y: 80,  degree: 3,  cat: 'BOD' },
  { id: 'byungwn', label: '병원',         x: 340, y: 80,  degree: 5,  cat: 'BOD' },
  { id: 'jindan',  label: '진단',         x: 460, y: 90,  degree: 4,  cat: 'BOD' },
  { id: 'boktong', label: '복통',         x: 180, y: 150, degree: 2,  cat: 'BOD' },
  { id: 'huri',    label: '허리',         x: 280, y: 160, degree: 24, cat: 'BOD', hub: true },
  { id: 'physi',   label: '물리치료',     x: 440, y: 160, degree: 12, cat: 'BOD', hub: true },
  { id: 'hospi',   label: '강남세브란스', x: 580, y: 165, degree: 7,  cat: 'BOD' },
  // 통찰 노드 — 시각의 무게중심
  { id: 'ins1',    label: '허리 치료 진행', x: 380, y: 270, degree: 24, cat: 'BOD', insight: true },
  // 업무 클러스터 (WRK)
  { id: 'park',    label: '박지수',       x: 200, y: 380, degree: 8,  cat: 'WRK' },
  { id: 'team',    label: '개발팀',       x: 340, y: 380, degree: 14, cat: 'WRK', hub: true },
  { id: 'kim',     label: '김민수',       x: 480, y: 380, degree: 9,  cat: 'WRK' },
  { id: 'product', label: '더나은',       x: 200, y: 450, degree: 5,  cat: 'WRK' },
  { id: 'comp',    label: '컴포넌트',     x: 480, y: 450, degree: 6,  cat: 'WRK' },
  { id: 'leader',  label: '팀장',         x: 200, y: 510, degree: 3,  cat: 'WRK' },
  { id: 'design',  label: '시안',         x: 480, y: 510, degree: 4,  cat: 'WRK' },
  // 고립 노드들 (외곽)
  { id: 'iso1', label: '서점',     x: 60,  y: 50,  degree: 1, cat: 'PLC', isolated: true },
  { id: 'iso2', label: '커피',     x: 90,  y: 280, degree: 1, cat: 'FOD', isolated: true },
  { id: 'iso3', label: '여권',     x: 60,  y: 460, degree: 1, cat: 'PLC', isolated: true },
  { id: 'iso4', label: '런닝',     x: 660, y: 50,  degree: 1, cat: 'BOD', isolated: true },
  { id: 'iso5', label: '동호회',   x: 680, y: 280, degree: 1, cat: 'REL', isolated: true },
  { id: 'iso6', label: '이력서',   x: 660, y: 460, degree: 1, cat: 'WRK', isolated: true },
];

// 공출현 가중 엣지 (weight = 같은 바구니 등장 횟수)
const HYPERGRAPH_EDGES = [
  // 허리 클러스터
  ['yak', 'huri', 2],
  ['byungwn', 'huri', 3],
  ['byungwn', 'jindan', 2],
  ['boktong', 'huri', 2],
  ['huri', 'physi', 6],   // 굵은 선 — 자주 함께 등장
  ['physi', 'hospi', 5],
  ['jindan', 'huri', 4],
  // 통찰 허브 연결 (Hebbian — 시냅스 세션 발화 시 묶임)
  ['huri', 'ins1', 8],
  ['physi', 'ins1', 6],
  ['hospi', 'ins1', 4],
  ['jindan', 'ins1', 3],
  // 업무 클러스터
  ['park', 'team', 5],
  ['team', 'kim', 6],
  ['park', 'product', 3],
  ['kim', 'comp', 4],
  ['team', 'comp', 3],
  ['comp', 'design', 4],
  ['park', 'leader', 3],
];

// 호버 시 보여줄 바구니 멤버십 (더미)
const NODE_DETAIL = {
  huri: {
    degree: 24, cat: 'BOD.medical', userHeading: '건강',
    sentences: [
      { id: 's#3', text: 'L4-L5 진단 받았다' },
      { id: 's#28', text: '물리치료 3회차 받았고…' },
      { id: 's#106', text: '허리가 다 나았다' },
      { id: 's#142', text: '병원 예약 4-08' },
      { id: 's#188', text: '약 7일치 처방' },
    ],
    aliases: [],
    extraSentences: 3,
  },
};

function HypergraphScreen() {
  const [hoverId, setHoverId] = React.useState('huri');
  return (
    <div style={{ width: '100%', height: '100%', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      <TopBar active="hypergraph" />
      <div style={{ flex: 1, display: 'grid', gridTemplateColumns: '220px 1fr 280px', minHeight: 0 }}>
        {/* Left: filter sidebar */}
        <HypergraphFilters />
        {/* Center: node-centric canvas */}
        <div style={{ position: 'relative', overflow: 'hidden', background: 'radial-gradient(ellipse at center, #0c0d11 0%, var(--bg) 70%)' }}>
          <NodeCentricGraph hoverId={hoverId} onHover={setHoverId} />
          <GraphLegend />
          <div style={{ position: 'absolute', bottom: 16, right: 16, display: 'flex', gap: 2, background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: 2 }}>
            <Button variant="ghost" size="sm">＋</Button>
            <Button variant="ghost" size="sm">fit</Button>
            <Button variant="ghost" size="sm">−</Button>
          </div>
        </div>
        {/* Right: hover detail panel */}
        <NodeDetailPanel nodeId={hoverId} />
      </div>
    </div>
  );
}

function HypergraphFilters() {
  const cats = [
    ['BOD', true,  'body'],
    ['WRK', true,  'work'],
    ['FOD', false, 'food'],
    ['REL', false, 'relation'],
    ['MED', false, 'medical'],
    ['PLC', false, 'place'],
    ['TIM', false, 'time'],
  ];
  return (
    <div style={{ borderRight: '1px solid var(--border)', background: 'var(--bg-2)', padding: 16, display: 'flex', flexDirection: 'column', gap: 16, overflow: 'auto' }}>
      <TextInput placeholder="🔍 노드·별칭 검색" />
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        <Badge tone="insight">전체</Badge>
        <Badge tone="neutral">허브</Badge>
        <Badge tone="neutral">✦ 통찰</Badge>
        <Badge tone="neutral">고립만</Badge>
      </div>
      <div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', marginBottom: 8 }}>BFS 깊이</div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 11, color: 'var(--text-3)' }}>
          <span>0</span>
          <div style={{ flex: 1, height: 2, background: 'var(--border)', borderRadius: 1, position: 'relative' }}>
            <div style={{ position: 'absolute', left: '40%', top: -4, width: 10, height: 10, borderRadius: 5, background: 'var(--accent)' }} />
          </div>
          <span>5</span>
        </div>
      </div>
      <div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', marginBottom: 8 }}>카테고리 (19 시드)</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontSize: 12, fontFamily: 'var(--font-mono)' }}>
          {cats.map(([k, on, label]) => (
            <label key={k} style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-2)', cursor: 'pointer' }}>
              <span style={{ width: 12, height: 12, borderRadius: 2, border: `1px solid ${on ? CAT_COLORS[k] : 'var(--border-strong)'}`, background: on ? CAT_COLORS[k] : 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                {on && <span style={{ width: 5, height: 5, background: 'var(--bg)' }} />}
              </span>
              <span style={{ width: 8, height: 8, borderRadius: 4, background: CAT_COLORS[k] }} />
              <span style={{ flex: 1 }}>{k}</span>
              <span style={{ color: 'var(--text-4)', fontSize: 10 }}>{label}</span>
            </label>
          ))}
        </div>
      </div>
      <div style={{ padding: '10px 12px', background: 'rgba(200,93,93,0.06)', border: '1px solid rgba(200,93,93,0.25)', borderRadius: 'var(--r-md)', fontSize: 11, color: 'var(--danger)', display: 'flex', alignItems: 'center', gap: 6 }}>
        <span>⚠</span>
        <span>고립 노드 <strong>12</strong> 개</span>
      </div>
      <div style={{ marginTop: 'auto', padding: 12, background: 'var(--surface)', borderRadius: 'var(--r-md)', fontSize: 11, color: 'var(--text-3)', fontFamily: 'var(--font-mono)', display: 'flex', flexDirection: 'column', gap: 3 }}>
        <div>노드 <span style={{ color: 'var(--text)' }}>937</span></div>
        <div>✦ 통찰 <span style={{ color: 'var(--accent)' }}>1</span></div>
        <div>바구니 <span style={{ color: 'var(--text)' }}>393</span></div>
      </div>
    </div>
  );
}

function NodeCentricGraph({ hoverId, onHover }) {
  // 노드 반지름: degree 기반 (4 ~ 18)
  const radius = (n) => {
    if (n.insight) return 16;
    if (n.isolated) return 2.5;
    return Math.min(14, 3 + Math.sqrt(n.degree) * 2.2);
  };
  // 엣지 굵기: weight 기반 (0.5 ~ 3.5)
  const stroke = (w) => Math.min(3.5, 0.5 + w * 0.4);

  const byId = Object.fromEntries(HYPERGRAPH_NODES.map(n => [n.id, n]));
  const hoverNeighbors = new Set();
  if (hoverId) {
    hoverNeighbors.add(hoverId);
    HYPERGRAPH_EDGES.forEach(([a, b]) => {
      if (a === hoverId) hoverNeighbors.add(b);
      if (b === hoverId) hoverNeighbors.add(a);
    });
  }

  return (
    <svg viewBox="0 0 720 560" style={{ width: '100%', height: '100%' }}>
      {/* edges */}
      <g>
        {HYPERGRAPH_EDGES.map(([a, b, w], i) => {
          const na = byId[a], nb = byId[b];
          const dim = hoverId && !(hoverNeighbors.has(a) && hoverNeighbors.has(b));
          const involves = hoverId && (a === hoverId || b === hoverId);
          return (
            <line key={i}
              x1={na.x} y1={na.y} x2={nb.x} y2={nb.y}
              stroke={involves ? 'var(--accent-line)' : 'var(--border-strong)'}
              strokeWidth={stroke(w)}
              opacity={dim ? 0.12 : involves ? 0.85 : 0.55}
              style={{ transition: 'opacity 200ms' }}
            />
          );
        })}
      </g>
      {/* nodes */}
      <g>
        {HYPERGRAPH_NODES.map(n => {
          const r = radius(n);
          const fill = n.insight ? 'var(--accent-2)' : CAT_COLORS[n.cat] || 'var(--node)';
          const dim = hoverId && !hoverNeighbors.has(n.id);
          const isHovered = n.id === hoverId;
          return (
            <g key={n.id} style={{ cursor: 'pointer' }}
               onMouseEnter={() => onHover(n.id)}>
              {n.insight && (
                <circle cx={n.x} cy={n.y} r={r + 6} fill="none" stroke="var(--accent-line)" strokeWidth="1.5" opacity={dim ? 0.2 : 1} />
              )}
              <circle cx={n.x} cy={n.y} r={r}
                fill={fill}
                opacity={dim ? 0.25 : 1}
                style={{
                  filter: n.insight ? 'drop-shadow(0 0 14px rgba(217,188,131,0.7))'
                       : n.hub      ? `drop-shadow(0 0 8px ${fill}88)`
                       : 'none',
                  transition: 'opacity 200ms',
                }} />
              {isHovered && !n.isolated && (
                <circle cx={n.x} cy={n.y} r={r + 4} fill="none" stroke="var(--accent)" strokeWidth="1" />
              )}
              {!n.isolated && (
                <text x={n.x} y={n.y - r - 6}
                  textAnchor="middle"
                  fill={n.insight ? 'var(--accent-2)' : dim ? 'var(--text-4)' : 'var(--text-2)'}
                  fontSize={n.insight ? 12 : n.hub ? 11 : 10}
                  fontFamily="var(--font-mono)"
                  fontWeight={n.insight || n.hub ? 600 : 400}
                  opacity={dim ? 0.4 : 1}
                  style={{ transition: 'opacity 200ms' }}>
                  {n.insight && '✦ '}{n.label}
                  {n.hub && !n.insight && <tspan fill="var(--text-4)" fontSize="9"> · {n.degree}</tspan>}
                </text>
              )}
            </g>
          );
        })}
      </g>
      {/* 주석 — 굵은 선 */}
      <g fontFamily="var(--font-mono)" fontSize="9" fill="var(--text-4)">
        <text x={360} y={150}>━━ 공출현 6회</text>
      </g>
    </svg>
  );
}

function GraphLegend() {
  return (
    <div style={{ position: 'absolute', top: 16, left: 16, background: 'rgba(20,21,25,0.85)', backdropFilter: 'blur(8px)', border: '1px solid var(--border)', borderRadius: 'var(--r-md)', padding: '10px 12px', fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-3)', display: 'flex', flexDirection: 'column', gap: 6, minWidth: 200 }}>
      <div style={{ color: 'var(--text-4)', letterSpacing: '0.15em' }}>─── LEGEND ───</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ display: 'flex', alignItems: 'baseline', gap: 4 }}>
          <span style={{ width: 4, height: 4, borderRadius: 2, background: 'var(--node)' }} />
          <span style={{ width: 7, height: 7, borderRadius: 4, background: 'var(--node)' }} />
          <span style={{ width: 11, height: 11, borderRadius: 6, background: 'var(--node)' }} />
        </span>
        <span>크기 = mention degree</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 24, height: 1, background: 'var(--border-strong)' }} />
        <span style={{ width: 24, height: 3, background: 'var(--border-strong)' }} />
        <span>두께 = 공출현 가중치</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 10, height: 10, borderRadius: 5, background: 'var(--accent-2)', boxShadow: '0 0 8px rgba(217,188,131,0.7)' }} />
        <span>✦ 통찰 (Hebbian 허브)</span>
      </div>
    </div>
  );
}

function NodeDetailPanel({ nodeId }) {
  const node = HYPERGRAPH_NODES.find(n => n.id === nodeId);
  const detail = NODE_DETAIL[nodeId];
  const catColor = node ? CAT_COLORS[node.cat] : 'var(--node)';

  return (
    <div style={{ borderLeft: '1px solid var(--border)', background: 'var(--bg-2)', padding: 16, display: 'flex', flexDirection: 'column', gap: 14, overflow: 'auto' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.15em' }}>─── HOVER DETAIL ───</div>

      {!node ? (
        <div style={{ fontSize: 12, color: 'var(--text-4)', fontStyle: 'italic' }}>노드 위에 마우스를 올려보세요.</div>
      ) : (
        <>
          {/* Node header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{
              width: 14, height: 14, borderRadius: 7,
              background: node.insight ? 'var(--accent-2)' : catColor,
              boxShadow: node.insight ? '0 0 12px rgba(217,188,131,0.7)' : `0 0 6px ${catColor}aa`,
            }} />
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 16, color: 'var(--text)', fontWeight: 600 }}>
              {node.insight && '✦ '}{node.label}
            </span>
          </div>

          {/* Meta */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 11, fontFamily: 'var(--font-mono)' }}>
            <div style={{ color: 'var(--text-3)' }}>
              degree <span style={{ color: 'var(--text)' }}>{node.degree}</span>
              {node.hub && <span style={{ color: 'var(--accent)', marginLeft: 8 }}>· hub</span>}
              {node.isolated && <span style={{ color: 'var(--danger)', marginLeft: 8 }}>· isolated</span>}
            </div>
            <div style={{ color: 'var(--text-3)' }}>
              category <span style={{ color: catColor }}>{detail?.cat || `${node.cat}.unclassified`}</span>
            </div>
            {detail?.userHeading && (
              <div style={{ color: 'var(--text-3)' }}>
                heading <span style={{ color: 'var(--text-2)' }}>{detail.userHeading}</span>
              </div>
            )}
          </div>

          {/* Sentence baskets */}
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', marginBottom: 8 }}>
              문장 바구니 {detail ? detail.sentences.length + (detail.extraSentences || 0) : 0}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {detail?.sentences.map(s => (
                <div key={s.id} style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--r-sm)', padding: '6px 8px' }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--accent)', marginRight: 6 }}>{s.id}</span>
                  <span style={{ fontSize: 12, color: 'var(--text-2)' }}>{s.text}</span>
                </div>
              ))}
              {detail?.extraSentences > 0 && (
                <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-4)', paddingLeft: 4 }}>…외 {detail.extraSentences}</div>
              )}
              {!detail && (
                <div style={{ fontSize: 11, color: 'var(--text-4)', fontStyle: 'italic' }}>(이 노드에 대한 상세 데이터 없음)</div>
              )}
            </div>
          </div>

          {/* Aliases */}
          <div>
            <div style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-4)', letterSpacing: '0.1em', marginBottom: 6 }}>별칭</div>
            <div style={{ fontSize: 12, color: detail?.aliases.length ? 'var(--text-2)' : 'var(--text-4)' }}>
              {detail?.aliases.length ? detail.aliases.join(', ') : '(없음)'}
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 10, marginTop: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
            <Button variant="outline" size="sm">이 노드가 들어있는 노트로 →</Button>
            <div style={{ fontSize: 10, color: 'var(--text-4)', fontFamily: 'var(--font-mono)', textAlign: 'center' }}>조회 전용 · 수정은 /note 또는 /review</div>
          </div>
        </>
      )}
    </div>
  );
}



// ─── MOBILE NOTE ─────────────────────────────────────────────────────
function MobileNote() {
  return (
    <div style={{ width: '100%', height: '100%', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 44, padding: '0 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg-2)' }}>
        <Icon.Menu style={{ color: 'var(--text-2)' }} />
        <SynapseLogoLockup size={18} />
        <div style={{ display: 'flex', gap: 10 }}>
          <Icon.Graph style={{ color: 'var(--text-2)' }} />
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)' }}>/note</span>
        </div>
      </div>
      <div style={{ padding: '8px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Badge tone="success" icon={<Icon.Check />}>저장됨</Badge>
        <Button variant="primary" size="sm" icon={<Icon.Sparkle />}>정리</Button>
      </div>
      <div style={{ flex: 1, padding: '20px 18px', overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 12, fontSize: 14, lineHeight: 1.65 }}>
        <h1 style={{ fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 600, margin: 0, color: 'var(--text)' }}># 더나은</h1>
        <h2 style={{ fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 500, margin: 0, color: 'var(--text-2)' }}>## 개발팀</h2>
        <ul style={{ margin: 0, paddingLeft: 18, color: 'var(--text)' }}>
          <li>팀장:: <span style={{ color: 'var(--accent)' }}>박지수</span></li>
          <li>프론트엔드 김민수</li>
        </ul>
        <p style={{ margin: 0 }}>오늘 회의가 세 개 연속이었다.</p>
        <p style={{ margin: 0 }}>김민수가 새 컴포넌트 시안 잡아왔다.</p>
        <CorrectionCard from="스ㅏ타벅스" to="스타벅스" reason="자모 거리 1" />
      </div>
    </div>
  );
}

// ─── MOBILE SYNAPSE ───────────────────────────────────────────────────
function MobileSynapse() {
  return (
    <div style={{ width: '100%', height: '100%', background: 'var(--bg)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ height: 44, padding: '0 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg-2)' }}>
        <Icon.Menu style={{ color: 'var(--text-2)' }} />
        <SynapseLogoLockup size={18} />
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--accent)' }}>/synapse</span>
      </div>
      <div style={{ flex: 1, padding: '16px 14px', overflow: 'auto', display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ alignSelf: 'flex-end', maxWidth: '85%', background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: '12px 12px 4px 12px', padding: '10px 12px', fontSize: 13 }}>
          허리 어떻게 진행되고 있지?
        </div>
        <div style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-3)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <Icon.Spinner style={{ color: 'var(--accent)' }} /> 탐색 중…
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, paddingLeft: 4 }}>
          <Node size={6} hub /> <span style={{ color: 'var(--text-2)', fontFamily: 'var(--font-mono)' }}>허리</span>
          <span style={{ color: 'var(--text-4)' }}>──</span>
          <Node size={6} /> <span style={{ fontFamily: 'var(--font-mono)' }}>디스크</span>
        </div>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--accent-line)', borderRadius: '4px 12px 12px 12px', padding: 14, fontSize: 13, lineHeight: 1.6, boxShadow: '0 0 16px rgba(200,169,110,0.06)' }}>
          <strong style={{ color: 'var(--accent)' }}>2026-04-06</strong> L4-L5 진단, <strong style={{ color: 'var(--accent)' }}>4-08</strong>부터 강남세브란스에서 물리치료 3회차 받았고 <strong style={{ color: 'var(--accent)' }}>4-10</strong>에 "다 나았다" 기록.
          <div style={{ marginTop: 12 }}>
            <Button variant="outline" size="sm" icon={<Icon.Promote />}>통찰로 승격</Button>
          </div>
        </div>
      </div>
      <div style={{ padding: 12, borderTop: '1px solid var(--border)' }}>
        <div style={{ background: 'var(--surface)', border: '1px solid var(--border-2)', borderRadius: 'var(--r-lg)', padding: '8px 10px', display: 'flex', alignItems: 'center', gap: 8 }}>
          <input style={{ flex: 1, background: 'transparent', border: 0, color: 'var(--text)', fontSize: 13, outline: 'none', fontFamily: 'var(--font-body)' }} placeholder="질문 입력…" />
          <Icon.Send style={{ color: 'var(--accent)', cursor: 'pointer' }} />
        </div>
      </div>
    </div>
  );
}

// ─── PROMOTION MODAL ──────────────────────────────────────────────────
function PromoteModalCard() {
  return (
    <div style={{ width: '100%', height: '100%', background: 'rgba(10,11,14,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', backdropFilter: 'blur(8px)' }}>
      <div style={{ background: 'var(--surface)', border: '1px solid var(--accent-line)', borderRadius: 'var(--r-xl)', padding: 28, maxWidth: 420, boxShadow: 'var(--shadow-3), var(--glow-amber)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
          <Icon.Sparkle style={{ color: 'var(--accent)' }} />
          <h3 style={{ fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 600, margin: 0, color: 'var(--text)' }}>통찰로 승격하시겠어요?</h3>
        </div>
        <p style={{ fontSize: 14, color: 'var(--text-2)', lineHeight: 1.65, margin: '0 0 20px' }}>
          새 <span style={{ color: 'var(--accent)' }}>✦ 통찰</span> post 가 생성되며, 이 시냅스 세션에서 함께 발화한 노드 <strong style={{ color: 'var(--text)' }}>12 개</strong>가 자동으로 연결됩니다 <em style={{ color: 'var(--text-3)' }}>(Hebbian)</em>.
        </p>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <Button variant="ghost">취소</Button>
          <Button variant="primary" icon={<Icon.Sparkle />}>승격</Button>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, {
  NoteScreen, SynapseScreen, HypergraphScreen,
  MobileNote, MobileSynapse, PromoteModalCard,
});
