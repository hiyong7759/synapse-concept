import { useEffect, useRef, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Network, DataSet } from 'vis-network/standalone';
import type { NodeItem, EdgeItem } from '../types';
import { api } from '../api';
import styles from './GraphPage.module.css';
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
  id: number;
  from: number;
  to: number;
  label?: string;
  arrows: { to: { enabled: boolean } };
  color: { color: string; highlight: string };
  width: number;
  font: { color: string; size: number; face: string; strokeWidth: number };
  smooth: { enabled: boolean; type: string; roundness: number };
}

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
    ? `rgba(200,169,110,${hub ? 0.55 : 0.35})`
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

function buildVEdge(edge: EdgeItem): VEdge {
  return {
    id: edge.id,
    from: edge.source_id,
    to: edge.target_id,
    label: edge.label ?? undefined,
    arrows: { to: { enabled: false } },
    color: { color: 'rgba(58,61,74,0.5)', highlight: 'rgba(200,169,110,0.8)' },
    width: 0.8,
    font: { color: '#8A8B92', size: 9, face: 'JetBrains Mono', strokeWidth: 0 },
    smooth: { enabled: true, type: 'continuous', roundness: 0.2 },
  };
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

type DetailEdge = { dir: '→' | '←'; label: string | null; otherName: string; otherId: number };

// ── 컴포넌트 ─────────────────────────────────────────────────
export function GraphPage() {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const visNodesRef = useRef<DataSet<VNode> | null>(null);
  const visEdgesRef = useRef<DataSet<VEdge> | null>(null);
  const allNodesRef = useRef<VNode[]>([]);
  const allEdgesRef = useRef<VEdge[]>([]);
  const rawNodesRef = useRef<NodeItem[]>([]);
  const rawEdgesRef = useRef<EdgeItem[]>([]);
  const adjRef = useRef<Map<number, number[]>>(new Map());

  const [stats, setStats] = useState({ nodes: 0, edges: 0 });
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
  const [detailEdges, setDetailEdges] = useState<DetailEdge[]>([]);

  // hover 상태
  const dimmedNodesRef = useRef<number[]>([]);
  const dimmedEdgesRef = useRef<number[]>([]);

  // ── 노드의 연결 엣지 목록 추출 ────────────────────────────────
  function getEdgesForNode(id: number): DetailEdge[] {
    return rawEdgesRef.current
      .filter(e => e.source_id === id || e.target_id === id)
      .map(e => {
        const isOut = e.source_id === id;
        const otherId = isOut ? e.target_id : e.source_id;
        const otherNode = rawNodesRef.current.find(n => n.id === otherId);
        return {
          dir: (isOut ? '→' : '←') as '→' | '←',
          label: e.label,
          otherName: otherNode?.name ?? String(otherId),
          otherId,
        };
      });
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

    const visibleEdges = edgeUpdates.filter(e => !e.hidden).length;
    setStats({ nodes: visibleIds.size, edges: visibleEdges });
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
        const [nodes, edges] = await Promise.all([api.nodes(), api.edges()]);
        if (destroyed) return;

        rawNodesRef.current = nodes;
        rawEdgesRef.current = edges;

        // 인접 맵 구성 (bfsReachable 성능 최적화)
        const adj = new Map<number, number[]>();
        edges.forEach(e => {
          if (!adj.has(e.source_id)) adj.set(e.source_id, []);
          if (!adj.has(e.target_id)) adj.set(e.target_id, []);
          adj.get(e.source_id)!.push(e.target_id);
          adj.get(e.target_id)!.push(e.source_id);
        });
        adjRef.current = adj;

        const mobile = isMobile();
        const maxDeg = nodes.reduce((m, n) => Math.max(m, n.degree), 1);
        const vNodes = nodes.map(n => buildVNode(n, maxDeg, mobile));
        const vEdges = edges.map(buildVEdge);

        allNodesRef.current = vNodes;
        allEdgesRef.current = vEdges;

        const visNodes = new DataSet<VNode>(vNodes);
        const visEdges = new DataSet<VEdge>(vEdges);
        visNodesRef.current = visNodes;
        visEdgesRef.current = visEdges;

        setStats({ nodes: nodes.length, edges: edges.length });

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
          const connectedEdgeIds = new Set<number>();
          rawEdgesRef.current.forEach(e => {
            if (e.source_id === nodeId || e.target_id === nodeId) {
              connectedNodeIds.add(e.source_id);
              connectedNodeIds.add(e.target_id);
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
              eUp.push({ id: e.id, color: { color: 'rgba(200,169,110,0.75)' }, width: 1.5, font: { color: '#C8A96E', strokeWidth: 0 } });
            } else {
              eUp.push({ id: e.id, color: { color: 'rgba(58,61,74,0.06)' }, width: 0.3, font: { color: 'transparent' } });
            }
          });

          visNodes.update(nUp as VNode[]);
          visEdges.update(eUp as VEdge[]);
          dimmedNodesRef.current = nUp.map((n: { id?: number }) => n.id!);
          dimmedEdgesRef.current = eUp.map((e: { id?: number }) => e.id!);
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
            visEdges.update(dimmedEdgesRef.current.map(id => {
              const e = allEdgesRef.current.find(x => x.id === id);
              return { id, color: { color: 'rgba(58,61,74,0.5)' }, width: 0.8, font: e?.font ?? { color: '#8A8B92', size: 9, face: 'JetBrains Mono', strokeWidth: 0 } };
            }));
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
          setDetailEdges(getEdgesForNode(id));
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
    setDetailEdges(getEdgesForNode(id));
  }

  const maxDeg = rawNodesRef.current.reduce((m, n) => Math.max(m, n.degree), 1);
  const isHub = (n: NodeItem) => n.degree > maxDeg * 0.35;

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
          노드 <span>{stats.nodes}</span> · 엣지 <span>{stats.edges}</span>
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

      {/* ─ 그래프 영역 ─ */}
      <div className={styles.graphArea}>
        <div ref={containerRef} className={styles.graphContainer} />

        {loading && (
          <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-tertiary)', fontFamily: 'JetBrains Mono, monospace', fontSize: 12 }}>
            그래프 로딩 중...
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

            <ul className={styles.edgeList}>
              {detailEdges.map((e, i) => (
                <li
                  key={i}
                  className={styles.edgeItem}
                  onClick={() => focusNode(e.otherId)}
                >
                  <span className={styles.edgeDir}>{e.dir}</span>
                  {e.label && <span className={styles.edgeLabel}>{e.label}</span>}
                  <span className={styles.edgeNode}>{e.otherName}</span>
                </li>
              ))}
            </ul>

            <div className={styles.nodeStats}>
              연결 {detailEdges.length}개 (→ {detailEdges.filter(e => e.dir === '→').length} ← {detailEdges.filter(e => e.dir === '←').length})
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
