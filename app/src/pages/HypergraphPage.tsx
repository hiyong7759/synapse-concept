import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Network, DataSet } from 'vis-network/standalone';
import type { NodeItem, Hyperedge } from '../types';
import { api } from '../api';
import styles from './HypergraphPage.module.css';
import { NodeCategoryEditor } from '../components/Graph/NodeCategoryEditor';

// ── 타입 ──────────────────────────────────────────────────────
interface VNode {
  id: number;
  label: string;
  size: number;
  color: { background: string; border: string; highlight: { background: string; border: string } };
  font: { color: string; size: number; face: string; vadjust: number };
  shadow: { enabled: boolean; color: string; size: number; x: number; y: number };
}

interface VEdge {
  id: string;  // 'h-<sentenceId>-<srcId>-<tgtId>' 같은 합성 ID
  from: number;
  to: number;
  title?: string;  // hover tooltip에 문장 원문
  arrows: { to: { enabled: boolean } };
  color: { color: string; highlight: string };
  width: number;
  smooth: { enabled: boolean; type: string; roundness: number };
}

/** 노드 상세 패널의 "같은 바구니 멤버" 정보 */
type BasketMember = {
  otherId: number;
  otherName: string;
  kind: 'sentence' | 'category';
  label: string;  // sentence text 또는 category path
};

// ── 헬퍼 ─────────────────────────────────────────────────────
function isMobile() { return window.matchMedia('(max-width:768px)').matches; }

function buildVNode(node: NodeItem, maxDeg: number, mobile: boolean): VNode {
  const d = node.degree;
  const hub = d > maxDeg * 0.35;
  const base = mobile ? 7 : 4;
  const range = mobile ? 22 : 18;
  const size = base + (d / Math.max(maxDeg, 1)) * range;
  const glow = 6 + (d / Math.max(maxDeg, 1)) * 20;

  const bg = hub ? '#C8A96E' : '#2A2D3E';
  const border = hub ? 'rgba(200,169,110,0.6)' : '#3A3D4A';
  const shadowColor = hub
    ? 'rgba(200,169,110,0.55)'
    : 'rgba(50,53,70,0.5)';

  return {
    id: node.id,
    label: node.name,
    size,
    color: { background: bg, border, highlight: { background: '#fff', border: bg } },
    font: { color: '#E8E4D9', size: hub ? 13 : 11, face: 'JetBrains Mono', vadjust: size + 4 },
    shadow: { enabled: true, color: shadowColor, size: glow, x: 0, y: 0 },
  };
}

/**
 * 하이퍼엣지를 vis-network 페어 엣지로 펼친다.
 * 문장 바구니(같은 sentence에 공출현)의 모든 노드 페어를 연결.
 * 카테고리 바구니는 별칭용으로 detail 패널에만 활용 (시각화는 문장 기반만).
 */
function expandHyperedgesToVEdges(baskets: Hyperedge[]): VEdge[] {
  const out: VEdge[] = [];
  for (const b of baskets) {
    const ids = b.node_ids;
    for (let i = 0; i < ids.length; i++) {
      for (let j = i + 1; j < ids.length; j++) {
        out.push({
          id: `s${b.sentence_id ?? 0}-${ids[i]}-${ids[j]}`,
          from: ids[i],
          to: ids[j],
          title: b.label,
          arrows: { to: { enabled: false } },
          color: { color: 'rgba(58,61,74,0.5)', highlight: 'rgba(200,169,110,0.8)' },
          width: 0.8,
          smooth: { enabled: true, type: 'continuous', roundness: 0.2 },
        });
      }
    }
  }
  return out;
}

function networkOptions(mobile: boolean) {
  return {
    physics: {
      solver: 'forceAtlas2Based',
      forceAtlas2Based: {
        gravitationalConstant: -55,
        centralGravity: 0.004,
        springLength: mobile ? 110 : 130,
        springConstant: 0.015,
        damping: 0.88,
        avoidOverlap: 0.5,
      },
      stabilization: { iterations: 250, fit: true },
    },
    interaction: {
      hover: !mobile,
      tooltipDelay: 200,
      hideEdgesOnDrag: true,
      multiselect: false,
      zoomSpeed: 0.6,
    },
    edges: {
      smooth: { enabled: true, type: 'continuous', roundness: 0.2 },
      width: 0.8,
      hoverWidth: 2,
      selectionWidth: 2.5,
    },
    nodes: {
      shape: 'dot',
      borderWidth: 0,
      borderWidthSelected: 2,
    },
    layout: { improvedLayout: true },
  };
}

// ── 컴포넌트 ─────────────────────────────────────────────────
export function HypergraphPage() {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const visNodesRef = useRef<DataSet<VNode> | null>(null);
  const visEdgesRef = useRef<DataSet<VEdge> | null>(null);
  const allNodesRef = useRef<VNode[]>([]);
  const allEdgesRef = useRef<VEdge[]>([]);
  const rawNodesRef = useRef<NodeItem[]>([]);
  const sentenceBasketsRef = useRef<Hyperedge[]>([]);
  const categoryBasketsRef = useRef<Hyperedge[]>([]);
  const adjRef = useRef<Map<number, number[]>>(new Map());

  const [stats, setStats] = useState({ nodes: 0, baskets: 0 });
  const [loading, setLoading] = useState(true);

  // 사이드바
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  // 검색
  const [searchText, setSearchText] = useState('');

  // 허브 필터
  const [filterMode, setFilterMode] = useState<'all' | 'hub'>('all');

  // depth (BFS)
  const [depthLimit, setDepthLimit] = useState(0);
  const [selectedNodeId, setSelectedNodeId] = useState<number | null>(null);

  // 노드 상세 패널
  const [detailNode, setDetailNode] = useState<NodeItem | null>(null);
  const [detailMembers, setDetailMembers] = useState<BasketMember[]>([]);

  // hover 상태
  const dimmedNodesRef = useRef<number[]>([]);
  const dimmedEdgesRef = useRef<string[]>([]);

  // ── 노드가 속한 바구니의 다른 멤버 추출 ───────────────────────
  function getMembersForNode(id: number): BasketMember[] {
    const out: BasketMember[] = [];
    const seen = new Set<string>();  // 중복 방지 (otherId + kind 조합)

    for (const b of sentenceBasketsRef.current) {
      if (!b.node_ids.includes(id)) continue;
      b.node_ids.forEach((otherId, idx) => {
        if (otherId === id) return;
        const key = `s-${otherId}-${b.sentence_id}`;
        if (seen.has(key)) return;
        seen.add(key);
        out.push({
          otherId,
          otherName: b.node_names[idx],
          kind: 'sentence',
          label: b.label,
        });
      });
    }
    for (const b of categoryBasketsRef.current) {
      if (!b.node_ids.includes(id)) continue;
      b.node_ids.forEach((otherId, idx) => {
        if (otherId === id) return;
        const key = `c-${otherId}-${b.category}`;
        if (seen.has(key)) return;
        seen.add(key);
        out.push({
          otherId,
          otherName: b.node_names[idx],
          kind: 'category',
          label: b.category ?? '',
        });
      });
    }
    return out;
  }

  // ── BFS ─────────────────────────────────────────────────────
  function bfsReachable(startId: number, depth: number): Set<number> {
    const adj = adjRef.current;
    const visited = new Set([startId]);
    let frontier = [startId];
    for (let i = 0; i < depth; i++) {
      const next: number[] = [];
      frontier.forEach(nid => {
        (adj.get(nid) ?? []).forEach(neighbor => {
          if (!visited.has(neighbor)) { visited.add(neighbor); next.push(neighbor); }
        });
      });
      frontier = next;
      if (!frontier.length) break;
    }
    return visited;
  }

  // ── 필터 적용 ────────────────────────────────────────────────
  const applyFilter = useCallback((
    search: string,
    mode: 'all' | 'hub',
    depth: number,
    selId: number | null,
  ) => {
    if (!visNodesRef.current || !visEdgesRef.current) return;

    const nodes = rawNodesRef.current;
    const maxDeg = nodes.reduce((m, n) => Math.max(m, n.degree), 1);

    let reachable: Set<number> | null = null;
    if (depth > 0 && selId !== null) reachable = bfsReachable(selId, depth);

    const visibleIds = new Set<number>();
    nodes.forEach(n => {
      const hubOk = mode === 'all' || n.degree > maxDeg * 0.35;
      const searchOk = !search || n.name.toLowerCase().includes(search);
      const depthOk = !reachable || reachable.has(n.id);
      if (hubOk && searchOk && depthOk) visibleIds.add(n.id);
    });

    const nodeUpdates = allNodesRef.current.map(n => {
      if (!visibleIds.has(n.id)) return { id: n.id, hidden: true };
      if (search && n.label.toLowerCase().includes(search)) {
        return { id: n.id, hidden: false, borderWidth: 2, color: { ...n.color, border: '#C8A96E' } };
      }
      return { id: n.id, hidden: false, borderWidth: 0, color: n.color };
    });

    const edgeUpdates = allEdgesRef.current.map(e => ({
      id: e.id,
      hidden: !visibleIds.has(e.from) || !visibleIds.has(e.to),
    }));

    visNodesRef.current.update(nodeUpdates);
    visEdgesRef.current.update(edgeUpdates);

    const visibleBaskets = sentenceBasketsRef.current.length + categoryBasketsRef.current.length;
    setStats({ nodes: visibleIds.size, baskets: visibleBaskets });
  }, []);

  // ── 데이터 로드 + 네트워크 초기화 ───────────────────────────
  useEffect(() => {
    if (!containerRef.current) return;

    let destroyed = false;

    function handleResize() {
      networkRef.current?.setOptions(networkOptions(isMobile()));
    }

    async function init() {
      try {
        const [nodes, h] = await Promise.all([api.nodes(), api.hyperedges()]);
        if (destroyed) return;

        rawNodesRef.current = nodes;
        sentenceBasketsRef.current = h.sentence_baskets;
        categoryBasketsRef.current = h.category_baskets;

        // 문장 바구니만 시각화 엣지로 펼침 (카테고리는 detail 패널에만)
        const vEdges = expandHyperedgesToVEdges(h.sentence_baskets);

        // 인접 맵 구성 (bfsReachable 성능 최적화)
        const adj = new Map<number, number[]>();
        vEdges.forEach(e => {
          if (!adj.has(e.from)) adj.set(e.from, []);
          if (!adj.has(e.to)) adj.set(e.to, []);
          adj.get(e.from)!.push(e.to);
          adj.get(e.to)!.push(e.from);
        });
        adjRef.current = adj;

        const mobile = isMobile();
        const maxDeg = nodes.reduce((m, n) => Math.max(m, n.degree), 1);
        const vNodes = nodes.map(n => buildVNode(n, maxDeg, mobile));

        allNodesRef.current = vNodes;
        allEdgesRef.current = vEdges;

        const visNodes = new DataSet<VNode>(vNodes);
        const visEdges = new DataSet<VEdge>(vEdges);
        visNodesRef.current = visNodes;
        visEdgesRef.current = visEdges;

        setStats({
          nodes: nodes.length,
          baskets: h.sentence_baskets.length + h.category_baskets.length,
        });

        const net = new Network(
          containerRef.current!,
          { nodes: visNodes, edges: visEdges },
          networkOptions(mobile),
        );
        networkRef.current = net;

        net.once('stabilizationIterationsDone', () => {
          if (isMobile()) net.fit({ animation: false });
        });

        // 호버 — Obsidian 스타일 dim
        net.on('hoverNode', ({ node: nodeId }: { node: number }) => {
          const connectedNodeIds = new Set([nodeId]);
          const connectedEdgeIds = new Set<string>();
          allEdgesRef.current.forEach(e => {
            if (e.from === nodeId || e.to === nodeId) {
              connectedNodeIds.add(e.from);
              connectedNodeIds.add(e.to);
              connectedEdgeIds.add(e.id);
            }
          });

          const nUp: object[] = [];
          const eUp: object[] = [];

          allNodesRef.current.forEach(n => {
            if ((visNodes.get(n.id) as { hidden?: boolean } | null)?.hidden) return;
            if (!connectedNodeIds.has(n.id)) {
              nUp.push({ id: n.id, opacity: 0.08, font: { color: 'rgba(232,228,217,0.06)' } });
            }
          });
          allEdgesRef.current.forEach(e => {
            if ((visEdges.get(e.id) as { hidden?: boolean } | null)?.hidden) return;
            if (connectedEdgeIds.has(e.id)) {
              eUp.push({ id: e.id, color: { color: 'rgba(200,169,110,0.75)' }, width: 1.5 });
            } else {
              eUp.push({ id: e.id, color: { color: 'rgba(58,61,74,0.06)' }, width: 0.3 });
            }
          });

          visNodes.update(nUp as VNode[]);
          visEdges.update(eUp as VEdge[]);
          dimmedNodesRef.current = nUp.map((n: { id?: number }) => n.id!);
          dimmedEdgesRef.current = eUp.map((e: { id?: string }) => e.id!);
        });

        net.on('blurNode', () => {
          if (dimmedNodesRef.current.length) {
            visNodes.update(dimmedNodesRef.current.map(id => {
              const n = allNodesRef.current.find(x => x.id === id);
              return { id, opacity: 1, font: n?.font ?? { color: '#E8E4D9' } };
            }));
            dimmedNodesRef.current = [];
          }
          if (dimmedEdgesRef.current.length) {
            visEdges.update(dimmedEdgesRef.current.map(id => ({
              id, color: { color: 'rgba(58,61,74,0.5)' }, width: 0.8,
            })));
            dimmedEdgesRef.current = [];
          }
        });

        // 노드 클릭
        net.on('click', ({ nodes: clickedNodes }: { nodes: number[] }) => {
          if (clickedNodes.length === 0) {
            setDetailNode(null);
            setSelectedNodeId(null);
            return;
          }
          const id = clickedNodes[0];
          const node = rawNodesRef.current.find(n => n.id === id) ?? null;
          setDetailNode(node);
          setSelectedNodeId(id);
          setDetailMembers(getMembersForNode(id));
        });

        window.addEventListener('resize', handleResize);
        setLoading(false);
      } catch {
        setLoading(false);
      }
    }

    init();

    return () => {
      destroyed = true;
      networkRef.current?.destroy();
      networkRef.current = null;
      window.removeEventListener('resize', handleResize);
    };
  }, []);

  // 필터 변경 시 적용
  useEffect(() => {
    applyFilter(searchText.toLowerCase().trim(), filterMode, depthLimit, selectedNodeId);
  }, [searchText, filterMode, depthLimit, selectedNodeId, applyFilter]);

  // 줌 컨트롤
  function zoomIn() { networkRef.current?.moveTo({ scale: (networkRef.current.getScale()) * 1.3, animation: true }); }
  function zoomOut() { networkRef.current?.moveTo({ scale: (networkRef.current.getScale()) * 0.77, animation: true }); }
  function zoomFit() { networkRef.current?.fit({ animation: true }); }

  // 사이드바 토글 (데스크탑)
  function collapseSidebar() {
    setSidebarCollapsed(true);
    setTimeout(() => networkRef.current?.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } }), 300);
  }
  function expandSidebar() {
    setSidebarCollapsed(false);
    setTimeout(() => networkRef.current?.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } }), 300);
  }

  // 모바일 사이드바 닫기
  function closeMobileSidebar() { setMobileOpen(false); }

  // 노드 상세에서 다른 노드로 포커스
  function focusNode(id: number) {
    networkRef.current?.focus(id, { animation: true });
    const node = rawNodesRef.current.find(n => n.id === id) ?? null;
    setDetailNode(node);
    setSelectedNodeId(id);
    setDetailMembers(getMembersForNode(id));
  }

  const maxDeg = rawNodesRef.current.reduce((m, n) => Math.max(m, n.degree), 1);
  const isHub = (n: NodeItem) => n.degree > maxDeg * 0.35;

  // 바구니 멤버 분류
  const sentenceMembers = detailMembers.filter(m => m.kind === 'sentence');
  const categoryMembers = detailMembers.filter(m => m.kind === 'category');

  return (
    <div className={styles.page}>
      {/* ─ 사이드바 ─ */}
      <aside
        className={[
          styles.sidebar,
          sidebarCollapsed ? styles.collapsed : '',
          mobileOpen ? styles.mobileOpen : '',
        ].join(' ')}
      >
        <div className={styles.sidebarHeader}>
          <div className={styles.brandName}>Synapse</div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button className={styles.backBtn} onClick={() => navigate('/chat')}>← 채팅</button>
            <button className={styles.sidebarToggle} onClick={collapseSidebar} title="사이드바 닫기">‹</button>
          </div>
        </div>

        <div className={styles.stats}>
          노드 <span>{stats.nodes}</span> · 바구니 <span>{stats.baskets}</span>
        </div>

        {/* 검색 */}
        <div className={styles.searchWrap}>
          <span className={styles.searchIcon}>⌕</span>
          <input
            className={styles.searchInput}
            type="text"
            placeholder="노드 검색..."
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
          {searchText && (
            <button className={styles.searchClear} onClick={() => setSearchText('')}>✕</button>
          )}
        </div>

        {/* 필터 패널 */}
        <div className={styles.filterPanel}>
          <div className={styles.filterToolbar}>
            <button
              className={[styles.filterToolBtn, filterMode === 'all' ? styles.filterToolBtnActive : ''].join(' ')}
              onClick={() => setFilterMode('all')}
            >전체</button>
            <button
              className={[styles.filterToolBtn, filterMode === 'hub' ? styles.filterToolBtnActive : ''].join(' ')}
              onClick={() => setFilterMode('hub')}
            >허브만</button>
          </div>

          <div className={styles.depthWrap}>
            <label>깊이</label>
            <input
              type="range"
              className={styles.depthSlider}
              min={0} max={5} value={depthLimit} step={1}
              onChange={e => setDepthLimit(parseInt(e.target.value, 10))}
            />
            <span className={styles.depthVal}>{depthLimit === 0 ? '전체' : depthLimit}</span>
          </div>
        </div>
      </aside>

      {/* 사이드바 열기 버튼 (접혔을 때) */}
      <button
        className={[styles.sidebarOpen, sidebarCollapsed ? styles.sidebarOpenVisible : styles.sidebarOpenHidden].join(' ')}
        onClick={expandSidebar}
        title="사이드바 열기"
      >›</button>

      {/* ─ 하이퍼그래프 영역 ─ */}
      <div className={styles.graphArea}>
        <div ref={containerRef} className={styles.graphContainer} />

        {loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>
            하이퍼그래프 로딩 중...
          </div>
        )}

        {/* 줌 컨트롤 */}
        <div className={styles.zoomControls}>
          <button className={styles.zoomBtn} onClick={zoomIn}>+</button>
          <div className={styles.zoomDivider} />
          <button className={styles.zoomBtn} onClick={zoomFit}>⊡</button>
          <div className={styles.zoomDivider} />
          <button className={styles.zoomBtn} onClick={zoomOut}>−</button>
        </div>
      </div>

      {/* ─ 노드 상세 패널 ─ */}
      <div className={[styles.nodeDetail, detailNode ? styles.nodeDetailOpen : ''].join(' ')}>
        {detailNode && (
          <>
            <div className={styles.nodeDetailHeader}>
              <div>
                <div className={styles.nodeName}>{detailNode.name}</div>
                {isHub(detailNode) && (
                  <span style={{ fontSize: 9, color: 'var(--accent)', fontFamily: 'JetBrains Mono, monospace', marginTop: 2, display: 'inline-block' }}>HUB</span>
                )}
              </div>
              <button className={styles.nodeClose} onClick={() => { setDetailNode(null); setSelectedNodeId(null); }}>✕</button>
            </div>

            {sentenceMembers.length > 0 && (
              <>
                <div className={styles.sectionLabel}>같은 문장 바구니</div>
                <ul className={styles.edgeList}>
                  {sentenceMembers.map((m, i) => (
                    <li
                      key={`s-${i}`}
                      className={styles.edgeItem}
                      onClick={() => focusNode(m.otherId)}
                      title={m.label}
                    >
                      <span className={styles.edgeNode}>{m.otherName}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}

            {categoryMembers.length > 0 && (
              <>
                <div className={styles.sectionLabel}>같은 카테고리 바구니</div>
                <ul className={styles.edgeList}>
                  {categoryMembers.map((m, i) => (
                    <li
                      key={`c-${i}`}
                      className={styles.edgeItem}
                      onClick={() => focusNode(m.otherId)}
                      title={m.label}
                    >
                      <span className={styles.edgeNode}>{m.otherName}</span>
                    </li>
                  ))}
                </ul>
              </>
            )}

            <div className={styles.nodeStats}>
              문장 바구니 {sentenceMembers.length} · 카테고리 바구니 {categoryMembers.length}
              {isHub(detailNode) ? '  ·  허브 노드' : ''}
            </div>

            <NodeCategoryEditor nodeId={detailNode.id} />

            <button className={styles.nodeDetailChatBtn} onClick={() => navigate('/chat/new')}>채팅으로 이동</button>
          </>
        )}
      </div>

      {/* 모바일 FAB */}
      <button
        className={styles.fab}
        onClick={() => {
          if (detailNode) { setDetailNode(null); setSelectedNodeId(null); return; }
          setMobileOpen(prev => !prev);
        }}
      >
        {mobileOpen ? '✕' : '☰'}
      </button>

      {/* 모바일 백드롭 */}
      {mobileOpen && (
        <div className={[styles.backdrop, styles.backdropShow].join(' ')} onClick={closeMobileSidebar} />
      )}
    </div>
  );
}
