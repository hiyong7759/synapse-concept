#!/usr/bin/env python3
"""Synapse 지식 그래프 시각화 — DB에서 읽어 인터랙티브 HTML 생성."""

import json
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(__file__))
from init_db import get_connection, DB_PATH

# 도메인별 색상
# 도메인별 배경색 — 글자색은 휘도 기반으로 자동 결정
DOMAIN_COLORS = {
    "프로필": "#e74c3c", "회사": "#3498db", "학력": "#2ecc71",
    "프로젝트": "#f39c12", "자격": "#9b59b6", "기술": "#1abc9c",
    "고객사": "#e67e22", "역할": "#5d6d7e", "조직": "#7fb3d8",
    "직급": "#aed6f1", "업무": "#d35400", "위치": "#27ae60",
    "경력": "#c0392b", "병역": "#8e44ad", "음식": "#f7dc6f",
    "건강": "#e84393", "운동": "#00b894", "장비": "#0984e3",
    "용도": "#a29bfe", "판단": "#fd79a8",
}
DEFAULT_COLOR = "#636e72"


def _luminance(hex_color: str) -> float:
    """sRGB 상대 휘도 계산 (W3C WCAG 2.0)."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    def linearize(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)


def _text_color(hex_color: str) -> str:
    """배경색 휘도에 따라 글자색 자동 결정."""
    return "#1a1a2e" if _luminance(hex_color) > 0.4 else "#fff"


DOMAIN_TEXT_COLORS = {k: _text_color(v) for k, v in DOMAIN_COLORS.items()}


def export_graph(db_path: str = DB_PATH) -> dict:
    """DB에서 노드/엣지를 읽어 vis.js 형식으로 변환."""
    conn = get_connection(db_path)

    nodes_raw = conn.execute(
        "SELECT id, name, domain FROM nodes WHERE status = 'active'"
    ).fetchall()

    edges_raw = conn.execute(
        """SELECT e.source_node_id, e.target_node_id, e.type, e.label
           FROM edges e
           JOIN nodes s ON e.source_node_id = s.id AND s.status = 'active'
           JOIN nodes t ON e.target_node_id = t.id AND t.status = 'active'"""
    ).fetchall()

    conn.close()

    nodes = []
    for r in nodes_raw:
        color = DOMAIN_COLORS.get(r["domain"], DEFAULT_COLOR)
        nodes.append({
            "id": r["id"],
            "label": r["name"],
            "group": r["domain"],
            "color": {
                "background": color,
                "border": color,
                "highlight": {"background": "#fff", "border": color},
            },
            "font": {"color": "#dfe6e9"},
        })

    edges = []
    for r in edges_raw:
        edge_label = r["type"]
        if r["label"]:
            edge_label += f": {r['label']}"
        edges.append({
            "from": r["source_node_id"],
            "to": r["target_node_id"],
            "label": edge_label,
            "arrows": "to",
            "font": {"color": "#b2bec3", "strokeWidth": 0},
            "color": {"color": "#636e72", "highlight": "#dfe6e9"},
        })

    return {"nodes": nodes, "edges": edges}


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Synapse Knowledge Graph</title>
<script src="https://unpkg.com/vis-network@10.0.2/standalone/umd/vis-network.min.js" integrity="sha384-m/pqkSdIs50f1nWlv062s9HmCAygFne+xY7uot2M8ZVijdcC+c/n97dFCfAZnKwO" crossorigin="anonymous"></script>
<style>
/* 테마 토큰 */
:root {
    --bg: #0a0a0a;
    --text: #dfe6e9;
    --text-sub: #b2bec3;
    --text-muted: #636e72;
    --panel-bg: rgba(20, 20, 20, 0.9);
    --input-bg: #1a1a2e;
    --border: #2d3436;
    --border-active: #3d3d5c;
    --accent: #6c5ce7;
    --edge-color: #636e72;
    --edge-text: #b2bec3;
    --node-font: #dfe6e9;
    --node-font-dim: rgba(223, 230, 233, 0.15);
    --edge-dim: rgba(99, 110, 114, 0.1);
    --shadow: rgba(0, 0, 0, 0.3);
}
body.light {
    --bg: #f5f6fa;
    --text: #2d3436;
    --text-sub: #636e72;
    --text-muted: #b2bec3;
    --panel-bg: rgba(255, 255, 255, 0.92);
    --input-bg: #fff;
    --border: #dfe6e9;
    --border-active: #b2bec3;
    --accent: #6c5ce7;
    --edge-color: #b2bec3;
    --edge-text: #636e72;
    --node-font: #2d3436;
    --node-font-dim: rgba(45, 52, 54, 0.15);
    --edge-dim: rgba(178, 190, 195, 0.15);
    --shadow: rgba(0, 0, 0, 0.08);
}

* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg); font-family: -apple-system, 'Pretendard', sans-serif; color: var(--text); overflow: hidden; transition: background 0.3s, color 0.3s; }
#graph { width: 100vw; height: 100vh; }

/* 타이틀 — 좌상단 고정 */
#title {
    position: fixed; top: 16px; left: 16px; z-index: 10;
    font-size: 13px; color: var(--text); letter-spacing: 1px; font-weight: 700;
    background: var(--panel-bg); backdrop-filter: blur(12px);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 6px 14px;
}

/* 통계 — 우상단 */
#stats {
    position: fixed; top: 16px; right: 16px; z-index: 10;
    background: var(--panel-bg); backdrop-filter: blur(12px);
    border: 1px solid var(--border); border-radius: 8px;
    padding: 6px 14px; font-size: 12px; color: var(--text-sub); white-space: nowrap;
}
#stats span { color: var(--text); font-weight: 600; }

/* 컨트롤 패널 */
#controls {
    position: fixed; top: 50px; left: 16px; z-index: 10;
    background: var(--panel-bg); backdrop-filter: blur(12px);
    border: 1px solid var(--border); border-radius: 12px;
    padding: 12px 16px; min-width: 260px; max-width: 320px;
    max-height: calc(100vh - 70px); overflow-y: auto;
}
#controls::-webkit-scrollbar { width: 4px; }
#controls::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }
#search {
    width: 100%; padding: 8px 12px; background: var(--input-bg); border: 1px solid var(--border);
    border-radius: 8px; color: var(--text); font-size: 14px; outline: none; margin-bottom: 8px;
}
#search:focus { border-color: var(--accent); }
#search::placeholder { color: var(--text-muted); }

/* 툴바 행 */
.toolbar {
    display: flex; align-items: center; justify-content: flex-end;
    margin-bottom: 8px; gap: 4px;
}
.toolbar button {
    padding: 3px 8px; border-radius: 6px;
    border: 1px solid var(--border); background: transparent; color: var(--text-sub);
    font-size: 10px; cursor: pointer; transition: all 0.2s; white-space: nowrap;
}
.toolbar button:hover { border-color: var(--accent); color: var(--accent); }

/* 도메인 그룹 */
.domain-group { margin-top: 4px; }
.domain-group-box {
    border-radius: 8px; background: var(--input-bg);
    padding: 8px 10px; margin-bottom: 4px; transition: all 0.2s;
}
.domain-group-header {
    display: flex; align-items: center; gap: 8px;
    cursor: pointer; user-select: none; margin-bottom: 6px;
}
.domain-group-header .group-label { font-size: 12px; color: var(--text); font-weight: 600; }
.domain-group-header .group-count { font-size: 10px; color: var(--text-sub); margin-left: auto; }
.domain-group-body { display: flex; flex-wrap: wrap; gap: 5px; }

/* 도메인 필터 */
.filter-btn {
    padding: 3px 9px; border-radius: 14px; border: 1px solid transparent;
    background: transparent; color: var(--text-sub); font-size: 11px; cursor: pointer;
    transition: all 0.2s;
}
.filter-btn .node-count { font-size: 9px; opacity: 0.6; margin-left: 2px; }
.filter-btn:hover { opacity: 1; }

/* 노드 정보 패널 */
#info {
    position: fixed; bottom: 16px; left: 16px; z-index: 10;
    background: var(--panel-bg); backdrop-filter: blur(12px);
    border: 1px solid var(--border); border-radius: 12px;
    padding: 16px; min-width: 280px; max-width: 360px;
    display: none;
}
#info h4 { font-size: 16px; margin-bottom: 8px; }
#info .domain-tag {
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 11px; margin-bottom: 8px;
}
#info .edge-list { list-style: none; max-height: 200px; overflow-y: auto; }
#info .edge-list li {
    padding: 4px 0; font-size: 13px; color: var(--text-sub);
    border-bottom: 1px solid var(--border);
}
#info .edge-list li span.type { color: var(--accent); margin: 0 6px; }

/* 바텀시트 핸들 (모바일) */
#sheet-handle {
    display: none; width: 36px; height: 4px; border-radius: 2px;
    background: var(--text-muted); margin: 0 auto 10px; cursor: grab;
}
/* 플로팅 버튼 (모바일) */
#mobile-fab {
    display: none; position: fixed; bottom: 20px; right: 20px; z-index: 11;
    width: 48px; height: 48px; border-radius: 50%;
    border: none; background: var(--accent); color: #fff;
    font-size: 20px; cursor: pointer;
    box-shadow: 0 4px 12px rgba(108, 92, 231, 0.4);
    transition: transform 0.2s;
}
#mobile-fab:active { transform: scale(0.9); }
/* 백드롭 */
#backdrop {
    display: none; position: fixed; inset: 0; z-index: 9;
    background: rgba(0,0,0,0.4); opacity: 0; transition: opacity 0.3s;
}
#backdrop.show { display: block; opacity: 1; }

/* 모바일 */
@media (max-width: 768px) {
    #title { top: 10px; left: 10px; font-size: 11px; padding: 5px 10px; }
    #stats { top: 10px; right: 10px; padding: 5px 10px; font-size: 11px; }
    #sheet-handle { display: block; }
    #mobile-fab { display: flex; align-items: center; justify-content: center; }
    #controls {
        top: auto; bottom: 0; left: 0; right: 0; z-index: 10;
        max-width: 100%; min-width: 0;
        border-radius: 16px 16px 0 0; padding: 10px 16px 20px;
        max-height: 80vh; overflow-y: auto;
        transform: translateY(100%);
        transition: transform 0.3s ease;
    }
    #controls.open { transform: translateY(0); }
    #search { font-size: 16px; }
    #info {
        bottom: 0; top: auto; left: 0; right: 0;
        min-width: 0; max-width: none; max-height: 50vh;
        border-radius: 16px 16px 0 0; padding: 20px 16px;
        overflow-y: auto;
    }
    #info .edge-list { max-height: none; }
    .domain-group-box { padding: 6px 8px; }
    .filter-btn { font-size: 12px; padding: 4px 10px; }
}
</style>
</head>
<body>

<div id="title">SYNAPSE</div>
<div id="stats"></div>
<button id="mobile-fab">☰</button>
<div id="backdrop"></div>
<div id="controls">
    <div id="sheet-handle"></div>
    <input id="search" type="text" placeholder="노드 검색..." autocomplete="off">
    <div class="toolbar">
        <button id="toggle-theme">라이트</button>
        <button id="all-on">전체 켜기</button>
        <button id="all-off">전체 끄기</button>
    </div>
    <div id="filters"></div>
</div>

<div id="info">
    <h4 id="info-name"></h4>
    <div id="info-domain" class="domain-tag"></div>
    <ul id="info-edges" class="edge-list"></ul>
</div>

<div id="graph"></div>

<script>
const DATA = __DATA__;

const DOMAIN_COLORS = __COLORS__;
const DOMAIN_TEXT_COLORS = __TEXT_COLORS__;

// 도메인 → 상위 그룹 매핑
const DOMAIN_GROUPS = {
    '인물': ['프로필', '역할', '직급', '경력', '병역'],
    '조직': ['회사', '고객사', '조직', '업무'],
    '교육/기술': ['학력', '기술', '자격'],
    '프로젝트': ['프로젝트'],
    '환경': ['장비', '용도', '위치'],
    '생활': ['음식', '건강', '운동', '판단'],
};

// 반응형 크기
function getScale() {
    const m = window.matchMedia('(max-width: 768px)').matches;
    return m
        ? { nodeSize: 48, fontSize: 32, edgeFontSize: 22, edgeWidth: 4, hoverWidth: 5, springLen: 160, hover: false, zoom: 0.5 }
        : { nodeSize: 16, fontSize: 14, edgeFontSize: 10, edgeWidth: 1, hoverWidth: 2, springLen: 120, hover: true, zoom: 1 };
}
let S = getScale();

// vis.js 네트워크 초기화
const container = document.getElementById('graph');
const nodes = new vis.DataSet(DATA.nodes);
const edges = new vis.DataSet(DATA.edges);
const allNodes = DATA.nodes.slice();
const allEdges = DATA.edges.slice();

function buildNetworkOptions() {
    return {
        physics: {
            solver: 'forceAtlas2Based',
            forceAtlas2Based: {
                gravitationalConstant: S.hover ? -40 : -60,
                centralGravity: 0.005,
                springLength: S.springLen,
                springConstant: 0.02,
                damping: 0.85,
            },
            stabilization: { iterations: 200 },
        },
        interaction: {
            hover: S.hover,
            tooltipDelay: 100,
            hideEdgesOnDrag: true,
            multiselect: false,
            zoomSpeed: S.zoom,
        },
        edges: {
            smooth: { type: 'continuous', roundness: 0.3 },
            width: S.edgeWidth,
            hoverWidth: S.hoverWidth,
            font: { size: S.edgeFontSize },
        },
        nodes: {
            shape: 'dot',
            size: S.nodeSize,
            borderWidth: 2,
            font: { size: S.fontSize },
            shadow: { enabled: true, color: 'rgba(0,0,0,0.3)', size: 8 },
        },
    };
}

const network = new vis.Network(container, { nodes, edges }, buildNetworkOptions());

// 모바일: stabilization 끝나면 줌 레벨 보정
network.once('stabilizationIterationsDone', () => {
    if (!S.hover) { // 모바일
        network.moveTo({ scale: 0.6, animation: false });
    }
});

// 리사이즈 시 크기 재적용
window.addEventListener('resize', () => {
    const newS = getScale();
    if (newS.nodeSize !== S.nodeSize) {
        S = newS;
        network.setOptions(buildNetworkOptions());
    }
});

// 통계
document.getElementById('stats').innerHTML =
    `노드 <span>${DATA.nodes.length}</span> · 엣지 <span>${DATA.edges.length}</span>`;

// 도메인 필터 — 그룹별 구성
const existingDomains = new Set(DATA.nodes.map(n => n.group));
let activeDomains = new Set(existingDomains);
const filtersEl = document.getElementById('filters');
const domainButtons = {};  // domain → button element

Object.entries(DOMAIN_GROUPS).forEach(([groupName, groupDomains]) => {
    const domainsInGroup = groupDomains.filter(d => existingDomains.has(d));
    if (domainsInGroup.length === 0) return;

    const box = document.createElement('div');
    box.className = 'domain-group-box';

    // 그룹 헤더
    const header = document.createElement('div');
    header.className = 'domain-group-header';

    const label = document.createElement('span');
    label.className = 'group-label';
    label.textContent = groupName;

    const count = document.createElement('span');
    count.className = 'group-count';
    const nodeCount = allNodes.filter(n => domainsInGroup.includes(n.group)).length;
    count.textContent = nodeCount;

    header.append(label, count);

    // 그룹 바디 (뱃지들)
    const body = document.createElement('div');
    body.className = 'domain-group-body';

    domainsInGroup.forEach(d => {
        const btn = document.createElement('button');
        btn.className = 'filter-btn active';
        const domainNodeCount = allNodes.filter(n => n.group === d).length;
        btn.innerHTML = `${d} <span class="node-count">${domainNodeCount}</span>`;
        btn.style.backgroundColor = DOMAIN_COLORS[d] || '#636e72';
        btn.style.color = DOMAIN_TEXT_COLORS[d] || '#fff';
        btn.dataset.domain = d;
        btn.addEventListener('click', (e) => { e.stopPropagation(); toggleDomain(btn, d); });
        body.appendChild(btn);
        domainButtons[d] = btn;
    });

    // 그룹 헤더 클릭 → 그룹 전체 토글
    header.addEventListener('click', () => {
        const allActive = domainsInGroup.every(d => activeDomains.has(d));
        domainsInGroup.forEach(d => {
            if (allActive) {
                activeDomains.delete(d);
                setButtonOff(domainButtons[d], d);
            } else {
                activeDomains.add(d);
                setButtonOn(domainButtons[d], d);
            }
        });
        applyFilter();
    });

    box.append(header, body);
    filtersEl.appendChild(box);
});

function setButtonOn(btn, domain) {
    btn.classList.add('active');
    btn.style.backgroundColor = DOMAIN_COLORS[domain] || '#636e72';
    btn.style.color = DOMAIN_TEXT_COLORS[domain] || '#fff';
    btn.style.borderColor = 'transparent';
}

function setButtonOff(btn, domain) {
    btn.classList.remove('active');
    const c = DOMAIN_COLORS[domain] || '#636e72';
    btn.style.backgroundColor = 'transparent';
    btn.style.color = c;
    btn.style.borderColor = c;
}

function toggleDomain(btn, domain) {
    if (activeDomains.has(domain)) {
        activeDomains.delete(domain);
        setButtonOff(btn, domain);
    } else {
        activeDomains.add(domain);
        setButtonOn(btn, domain);
    }
    applyFilter();
}

// 모바일 바텀시트
const controlsEl = document.getElementById('controls');
const handle = document.getElementById('sheet-handle');
const backdrop = document.getElementById('backdrop');
const fab = document.getElementById('mobile-fab');
let sheetOpen = false;

function openSheet() {
    sheetOpen = true;
    controlsEl.classList.add('open');
    backdrop.classList.add('show');
    fab.style.display = 'none';
}
function closeSheet() {
    sheetOpen = false;
    controlsEl.classList.remove('open');
    backdrop.classList.remove('show');
    fab.style.display = '';
}

fab.addEventListener('click', openSheet);
backdrop.addEventListener('click', closeSheet);

// 핸들 드래그로 닫기
let dragStartY = 0, dragging = false, dragDist = 0;
handle.addEventListener('touchstart', e => {
    dragging = true;
    dragStartY = e.touches[0].clientY;
    dragDist = 0;
    controlsEl.style.transition = 'none';
}, { passive: true });
document.addEventListener('touchmove', e => {
    if (!dragging) return;
    const dy = e.touches[0].clientY - dragStartY;
    dragDist = dy;
    if (dy > 0) { // 아래로만
        controlsEl.style.transform = `translateY(${dy}px)`;
    }
}, { passive: true });
document.addEventListener('touchend', () => {
    if (!dragging) return;
    dragging = false;
    controlsEl.style.transition = '';
    controlsEl.style.transform = '';
    // 빠르게 많이 내렸으면 닫기 (150px 이상)
    if (dragDist > 150) closeSheet();
});

// 테마 전환
let isDark = true;
const themeBtn = document.getElementById('toggle-theme');
function getThemeVars() {
    const s = getComputedStyle(document.body);
    return {
        nodeFont: s.getPropertyValue('--node-font').trim(),
        nodeFontDim: s.getPropertyValue('--node-font-dim').trim(),
        edgeColor: s.getPropertyValue('--edge-color').trim(),
        edgeText: s.getPropertyValue('--edge-text').trim(),
        edgeDim: s.getPropertyValue('--edge-dim').trim(),
        shadow: s.getPropertyValue('--shadow').trim(),
    };
}
function applyThemeToGraph() {
    const t = getThemeVars();
    const nodeUpdates = allNodes.map(n => ({
        id: n.id,
        font: { color: t.nodeFont },
        shadow: { enabled: true, color: t.shadow, size: 8 },
    }));
    nodes.update(nodeUpdates);
    const edgeUpdates = allEdges.map(e => ({
        id: e.id,
        font: { color: t.edgeText, strokeWidth: 0 },
        color: { color: t.edgeColor, highlight: t.nodeFont },
    }));
    edges.update(edgeUpdates);
    allNodes.forEach(n => { n.font = { color: t.nodeFont }; });
    allEdges.forEach(e => {
        e.font = { color: t.edgeText, strokeWidth: 0 };
        e.color = { color: t.edgeColor, highlight: t.nodeFont };
    });
}
themeBtn.addEventListener('click', () => {
    isDark = !isDark;
    document.body.classList.toggle('light', !isDark);
    themeBtn.textContent = isDark ? '라이트' : '다크';
    applyThemeToGraph();
});

// 전체 켜기/끄기
function setAll(on) {
    existingDomains.forEach(d => {
        if (on) {
            activeDomains.add(d);
            if (domainButtons[d]) setButtonOn(domainButtons[d], d);
        } else {
            activeDomains.delete(d);
            if (domainButtons[d]) setButtonOff(domainButtons[d], d);
        }
    });
    applyFilter();
}
document.getElementById('all-on').addEventListener('click', () => setAll(true));
document.getElementById('all-off').addEventListener('click', () => setAll(false));

function applyFilter(searchText) {
    searchText = searchText || document.getElementById('search').value.toLowerCase();
    const visibleNodeIds = new Set();

    const filteredNodes = allNodes.filter(n => {
        const domainOk = activeDomains.has(n.group);
        const searchOk = !searchText || n.label.toLowerCase().includes(searchText);
        if (domainOk && searchOk) { visibleNodeIds.add(n.id); return true; }
        return false;
    });

    const filteredEdges = allEdges.filter(e =>
        visibleNodeIds.has(e.from) && visibleNodeIds.has(e.to)
    );

    nodes.clear(); nodes.add(filteredNodes);
    edges.clear(); edges.add(filteredEdges);
}

// 검색
document.getElementById('search').addEventListener('input', e => {
    applyFilter(e.target.value.toLowerCase());
});

// 노드 클릭 → 정보 패널
network.on('click', params => {
    const infoEl = document.getElementById('info');
    if (params.nodes.length === 0) { infoEl.style.display = 'none'; return; }

    const nodeId = params.nodes[0];
    const node = allNodes.find(n => n.id === nodeId);
    if (!node) return;

    document.getElementById('info-name').textContent = node.label;
    const domainEl = document.getElementById('info-domain');
    domainEl.textContent = node.group;
    domainEl.style.backgroundColor = DOMAIN_COLORS[node.group] || '#636e72';

    // 연결된 엣지 찾기
    const connected = allEdges.filter(e => e.from === nodeId || e.to === nodeId);
    const listEl = document.getElementById('info-edges');
    listEl.innerHTML = '';

    connected.forEach(e => {
        const other = e.from === nodeId
            ? allNodes.find(n => n.id === e.to)
            : allNodes.find(n => n.id === e.from);
        if (!other) return;
        const li = document.createElement('li');
        const dir = e.from === nodeId ? '→' : '←';
        li.appendChild(document.createTextNode(dir + ' '));
        const typeSpan = document.createElement('span');
        typeSpan.className = 'type';
        typeSpan.textContent = e.label;
        li.appendChild(typeSpan);
        li.appendChild(document.createTextNode(' ' + other.label));
        listEl.appendChild(li);
    });

    infoEl.style.display = 'block';
});

// 호버 시 연결 노드만 하이라이트 (변경 대상만 추적)
let _dimmedNodeIds = [];
let _dimmedEdgeIds = [];

network.on('hoverNode', params => {
    const t = getThemeVars();
    const nodeId = params.node;
    const connectedIds = new Set([nodeId]);
    const connectedEdgeIds = [];

    allEdges.forEach(e => {
        if (e.from === nodeId || e.to === nodeId) {
            connectedIds.add(e.from);
            connectedIds.add(e.to);
            connectedEdgeIds.push(e.id);
        }
    });

    // 연결 안 된 노드만 dim 처리
    const dimNodes = [];
    allNodes.forEach(n => {
        if (!connectedIds.has(n.id) && nodes.get(n.id)) {
            dimNodes.push({ id: n.id, opacity: 0.15, font: { color: t.nodeFontDim } });
        }
    });
    nodes.update(dimNodes);
    _dimmedNodeIds = dimNodes.map(n => n.id);

    // 연결 안 된 엣지만 dim, 연결된 엣지는 강조
    const edgeUp = [];
    allEdges.forEach(e => {
        if (!edges.get(e.id)) return;
        if (e.from === nodeId || e.to === nodeId) {
            edgeUp.push({ id: e.id, color: { color: t.nodeFont, highlight: t.nodeFont }, width: 2 });
        } else {
            edgeUp.push({ id: e.id, color: { color: t.edgeDim, highlight: t.nodeFont }, width: 0.5 });
        }
    });
    edges.update(edgeUp);
    _dimmedEdgeIds = edgeUp.map(e => e.id);
});

network.on('blurNode', () => {
    const t = getThemeVars();
    if (_dimmedNodeIds.length) {
        nodes.update(_dimmedNodeIds.map(id => ({ id, opacity: 1.0, font: { color: t.nodeFont } })));
        _dimmedNodeIds = [];
    }
    if (_dimmedEdgeIds.length) {
        edges.update(_dimmedEdgeIds.map(id => ({ id, color: { color: t.edgeColor, highlight: t.nodeFont }, width: S.edgeWidth })));
        _dimmedEdgeIds = [];
    }
});
</script>
</body>
</html>"""


def demo_graph() -> dict:
    """Demo data for screenshots — realistic developer profile."""
    nodes_data = [
        (1, "React Native", "기술"), (2, "TypeScript", "기술"), (3, "Docker", "기술"),
        (4, "Python", "기술"), (5, "PostgreSQL", "기술"), (6, "Expo", "기술"),
        (7, "맥북 프로 16", "장비"), (8, "M3 Max", "장비"), (9, "RTX4080", "장비"),
        (10, "우분투 서버", "장비"), (11, "커밋매니저", "프로젝트"), (12, "푸드로그", "프로젝트"),
        (13, "사내 ERP", "프로젝트"), (14, "허리디스크", "건강"), (15, "L4-L5", "건강"),
        (16, "데드리프트", "운동"), (17, "트랩바", "운동"), (18, "수영", "운동"),
        (19, "카페인 알레르기", "음식"), (20, "집", "위치"), (21, "회사", "위치"),
        (22, "프론트엔드 개발자", "역할"), (23, "3년차", "경력"),
        (24, "Git", "기술"), (25, "Figma", "기술"),
        (26, "김시냅스", "프로필"), (27, "서울", "위치"), (28, "스타트업A", "회사"),
    ]

    edges_data = [
        (1, 6, "link", "빌드도구"), (1, 2, "link", "주 언어"), (1, 11, "link", "프레임워크"),
        (1, 12, "link", "프레임워크"), (3, 10, "link", "실행환경"), (4, 13, "link", "백엔드"),
        (5, 13, "link", "DB"), (7, 8, "link", "스펙"), (7, 20, "link", "위치"),
        (9, 21, "link", "위치"), (14, 15, "link", "부위"), (14, 16, "link", "주의"),
        (16, 17, "link", "대체"), (17, 14, "link", "허리부담적음"),
        (18, 14, "link", "안전"), (22, 1, "link", "주력"), (22, 23, "link", "경력"),
        (3, 4, "link", "함께사용"), (24, 11, "link", "핵심도구"), (25, 12, "link", "디자인"),
        (26, 22, "link", "직업"), (26, 28, "link", "소속"), (28, 27, "link", "위치"),
        (26, 14, "link", "지병"), (26, 19, "link", "알레르기"),
        (26, 1, "link", "주력기술"), (26, 2, "link", "사용언어"), (26, 3, "link", "사용기술"),
        (26, 4, "link", "사용언어"), (26, 7, "link", "장비"), (26, 9, "link", "장비"),
        (26, 11, "link", "프로젝트"), (26, 12, "link", "프로젝트"), (26, 13, "link", "프로젝트"),
        (26, 16, "link", "운동"), (26, 18, "link", "운동"), (26, 20, "link", "거주지"),
    ]

    nodes = []
    for nid, name, domain in nodes_data:
        color = DOMAIN_COLORS.get(domain, DEFAULT_COLOR)
        nodes.append({
            "id": nid, "label": name, "group": domain,
            "color": {"background": color, "border": color,
                      "highlight": {"background": "#fff", "border": color}},
            "font": {"color": "#dfe6e9"},
        })

    edges = []
    for src, tgt, etype, label in edges_data:
        edge_label = label if label else etype
        edges.append({
            "from": src, "to": tgt, "label": edge_label, "arrows": "to",
            "font": {"color": "#b2bec3", "strokeWidth": 0},
            "color": {"color": "#636e72", "highlight": "#dfe6e9"},
        })

    return {"nodes": nodes, "edges": edges}


def generate_html(db_path: str = DB_PATH) -> str:
    """DB에서 그래프 데이터를 읽어 HTML 문자열 생성."""
    data = export_graph(db_path)
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    html = html.replace("__COLORS__", json.dumps(DOMAIN_COLORS, ensure_ascii=False))
    html = html.replace("__TEXT_COLORS__", json.dumps(DOMAIN_TEXT_COLORS, ensure_ascii=False))
    return html


def main():
    data_dir = os.environ.get('SYNAPSE_DATA_DIR', os.path.join(os.path.expanduser('~'), '.synapse'))
    os.makedirs(data_dir, exist_ok=True)
    out_path = os.path.join(data_dir, 'graph.html')

    if "--demo" in sys.argv:
        data = demo_graph()
        html = HTML_TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
        html = html.replace("__COLORS__", json.dumps(DOMAIN_COLORS, ensure_ascii=False))
        html = html.replace("__TEXT_COLORS__", json.dumps(DOMAIN_TEXT_COLORS, ensure_ascii=False))
    else:
        html = generate_html()

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(json.dumps({
        "status": "ok",
        "output": out_path,
    }, ensure_ascii=False, indent=2))

    # 자동으로 브라우저에서 열기
    if "--no-open" not in sys.argv:
        webbrowser.open(f"file://{out_path}")


if __name__ == "__main__":
    main()
