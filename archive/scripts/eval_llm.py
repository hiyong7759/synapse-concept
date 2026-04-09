#!/usr/bin/env python3
"""
qwen3:4b (또는 gemma4:e2b) 시냅스 태스크 검증
- 저장: 텍스트 → 노드/엣지 JSON
- 인출: 질문 → 쿼리 확장 (앙상블 3모드)
- 대화: BFS 컨텍스트 + 질문 → 자연어 답변
"""

import json
import sqlite3
import time
import urllib.request

DB_PATH = "/Users/hiyong/.synapse/synapse.db"
MODEL = "qwen3:4b"

# ── 실제 그래프에서 뽑은 테스트 케이스 ──────────────────────────────────────

SAVE_CASES = [
    {
        "input": "나 오늘 충북 진천으로 이사했어",
        "expected_nodes": ["충북진천"],
        "expected_labels": ["위치", "거주"],
    },
    {
        "input": "워크넷 프로젝트 고용정보망이랑 연관있어",
        "expected_nodes": ["워크넷", "고용정보망"],
        "expected_labels": ["관련", "포함"],
    },
    {
        "input": "맥미니 M4 프로 샀어 램은 48기가",
        "expected_nodes": ["맥미니", "M4", "48GB"],
        "expected_labels": ["모델", "RAM", "스펙"],
    },
]

RETRIEVE_CASES = [
    {
        "query": "조용희가 어디 살아?",
        "expected_nodes": ["조용희", "충북진천", "집"],
        "expected_labels": ["거주", "위치"],
    },
    {
        "query": "워크넷 관련 프로젝트 뭐야?",
        "expected_nodes": ["워크넷", "고용정보망", "고용정보망통합유지관리"],
        "expected_labels": ["관련", "포함"],
    },
    {
        "query": "더나은 회사에서 어떤 일 했어?",
        "expected_nodes": ["㈜더나은", "워크넷", "고용정보망"],
        "expected_labels": ["소속", "담당"],
    },
]

CHAT_CASES = [
    {
        "query": "조용희 어디 살아?",
        "context": "조용희 --(거주)--> 집, 집 --(위치)--> 충북진천",
        "expected_keywords": ["충북", "진천"],
    },
    {
        "query": "더나은 회사 어떤 프로젝트 했어?",
        "context": "조용희 --(소속)--> ㈜더나은, ㈜더나은 --(담당)--> 워크넷, ㈜더나은 --(담당)--> 고용정보망",
        "expected_keywords": ["워크넷", "고용정보망"],
    },
]

# ── BFS (실제 DB) ─────────────────────────────────────────────────────────────

def get_bfs_context(start_names: list[str], max_depth=2) -> list[dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 노드명 → id
    placeholders = ",".join("?" * len(start_names))
    rows = conn.execute(
        f"SELECT id, name FROM nodes WHERE name IN ({placeholders}) AND status='active'",
        start_names
    ).fetchall()

    visited = {r["id"]: r["name"] for r in rows}
    queue = list(visited.keys())

    for _ in range(max_depth):
        if not queue:
            break
        ph = ",".join("?" * len(queue))
        edges = conn.execute(
            f"""SELECT e.source_node_id, e.target_node_id, e.type, e.label,
                       s.name as sname, t.name as tname
                FROM edges e
                JOIN nodes s ON s.id = e.source_node_id
                JOIN nodes t ON t.id = e.target_node_id
                WHERE (e.source_node_id IN ({ph}) OR e.target_node_id IN ({ph}))
                  AND s.status='active' AND t.status='active'""",
            queue + queue
        ).fetchall()

        next_q = []
        for e in edges:
            for nid, nname in [(e["source_node_id"], e["sname"]),
                               (e["target_node_id"], e["tname"])]:
                if nid not in visited:
                    visited[nid] = nname
                    next_q.append(nid)
        queue = next_q

    # 엣지 텍스트로 조합
    result = []
    if visited:
        ph = ",".join("?" * len(visited))
        edges = conn.execute(
            f"""SELECT s.name as sname, e.type, e.label, t.name as tname
                FROM edges e
                JOIN nodes s ON s.id = e.source_node_id
                JOIN nodes t ON t.id = e.target_node_id
                WHERE e.source_node_id IN ({ph}) OR e.target_node_id IN ({ph})""",
            list(visited.keys()) + list(visited.keys())
        ).fetchall()
        result = [dict(e) for e in edges]

    conn.close()
    return result

def format_context(edges: list[dict]) -> str:
    lines = []
    for e in edges:
        label = e["label"] or e["type"]
        lines.append(f"{e['sname']} --({label})--> {e['tname']}")
    return "\n".join(lines)

# ── Ollama 호출 ───────────────────────────────────────────────────────────────

def ollama(system: str, user: str) -> str:
    """qwen3:4b — think:true + num_predict 충분히 줘야 response가 나옴."""
    prompt = f"{system}\n\n{user}"

    payload = json.dumps({
        "model": MODEL,
        "prompt": prompt,
        "stream": False,
        "think": True,
        "options": {
            "temperature": 0.1,
            "num_predict": 4096,
        }
    }).encode()

    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            r = json.loads(resp.read())
            return r.get("response", "").strip()
    except Exception as e:
        return f"ERROR: {e}"

# ── 태스크별 프롬프트 ─────────────────────────────────────────────────────────

SAVE_SYSTEM = """당신은 지식 그래프 구조화 AI입니다.
입력 텍스트에서 노드(개념)와 엣지(관계)를 추출해 JSON으로 반환하세요.

규칙:
- 노드: 명사, 고유명사, 수치+단위 (예: 48GB, 3년)
- 엣지 라벨: 소속, 담당, 역할, 거주, 위치, 모델, 스펙, RAM, OS, 기간, 관련, 종류, 포함, 사용, 소유 중 하나
- 방향: source --[label]--> target

출력 형식 (JSON만, 설명 없음):
{"nodes": ["노드1", "노드2"], "edges": [{"source": "A", "label": "관계", "target": "B"}]}"""

RETRIEVE_SYSTEM = """당신은 지식 그래프 검색 AI입니다.
사용자 질문을 분석해 그래프 탐색에 필요한 키워드를 확장하세요.

3가지 탐색 전략으로 각각 출력하세요:
- mode1: 넓게 (동의어, 관련 개념 포함)
- mode2: 힌트 포함 (시작 노드 + 엣지 라벨 힌트)
- mode3: 좁게 (핵심 노드만 + 강한 필터)

출력 형식 (JSON만):
{
  "mode1": {"start_nodes": [...], "filter_strength": "none"},
  "mode2": {"start_nodes": [...], "hints": [...], "filter_strength": "weighted"},
  "mode3": {"start_nodes": [...], "hints": [...], "filter_strength": "strict"}
}"""

CHAT_SYSTEM = """당신은 개인 지식 그래프 기반 AI 어시스턴트입니다.
아래 컨텍스트(지식 그래프 탐색 결과)를 바탕으로 질문에 자연스럽게 한국어로 답변하세요.
컨텍스트에 없는 내용은 "모르겠어요"라고 하세요.

컨텍스트:
{context}"""

# ── 평가 함수 ─────────────────────────────────────────────────────────────────

def eval_save():
    print("\n" + "="*60)
    print("📥 저장 태스크 평가")
    print("="*60)

    scores = []
    for i, case in enumerate(SAVE_CASES):
        print(f"\n[{i+1}] 입력: {case['input']}")
        t0 = time.time()
        raw = ollama(SAVE_SYSTEM, f"입력: {case['input']}\n출력:")
        elapsed = time.time() - t0

        try:
            # JSON 파싱
            result = json.loads(raw)
            nodes = result.get("nodes", [])
            labels = [e.get("label", "") for e in result.get("edges", [])]

            node_hits = sum(1 for n in case["expected_nodes"] if any(n in r for r in nodes))
            label_hits = sum(1 for l in case["expected_labels"] if l in labels)

            node_score = node_hits / len(case["expected_nodes"])
            label_score = label_hits / max(len(case["expected_labels"]), 1)

            print(f"    노드: {nodes}")
            print(f"    엣지: {[(e['source'], e['label'], e['target']) for e in result.get('edges', [])]}")
            print(f"    노드 적중: {node_hits}/{len(case['expected_nodes'])} ({node_score:.0%})")
            print(f"    라벨 적중: {label_hits}/{len(case['expected_labels'])} ({label_score:.0%})")
            print(f"    응답 시간: {elapsed:.1f}s")
            scores.append((node_score + label_score) / 2)
        except json.JSONDecodeError:
            print(f"    ❌ JSON 파싱 실패: {raw[:200]}")
            scores.append(0)

    print(f"\n평균 점수: {sum(scores)/len(scores):.0%}")
    return scores

def eval_retrieve():
    print("\n" + "="*60)
    print("🔍 인출 태스크 평가 (쿼리 확장 앙상블)")
    print("="*60)

    scores = []
    for i, case in enumerate(RETRIEVE_CASES):
        print(f"\n[{i+1}] 질문: {case['query']}")
        t0 = time.time()
        raw = ollama(RETRIEVE_SYSTEM, f"질문: {case['query']}\n출력:")
        elapsed = time.time() - t0

        try:
            result = json.loads(raw)

            # 3모드 모두 수집
            all_nodes = set()
            all_labels = set()
            for mode in ["mode1", "mode2", "mode3"]:
                m = result.get(mode, {})
                all_nodes.update(m.get("start_nodes", []))
                all_labels.update(m.get("hints", []))

            # BFS로 실제 탐색
            bfs_edges = get_bfs_context(list(all_nodes))
            bfs_node_names = set()
            for e in bfs_edges:
                bfs_node_names.add(e["sname"])
                bfs_node_names.add(e["tname"])

            node_hits = sum(1 for n in case["expected_nodes"] if n in bfs_node_names)
            node_score = node_hits / len(case["expected_nodes"])

            print(f"    mode1 시작: {result.get('mode1', {}).get('start_nodes', [])}")
            print(f"    mode2 시작: {result.get('mode2', {}).get('start_nodes', [])} | 힌트: {result.get('mode2', {}).get('hints', [])}")
            print(f"    mode3 시작: {result.get('mode3', {}).get('start_nodes', [])} | 힌트: {result.get('mode3', {}).get('hints', [])}")
            print(f"    BFS 도달 노드: {bfs_node_names}")
            print(f"    기대 노드 적중: {node_hits}/{len(case['expected_nodes'])} ({node_score:.0%})")
            print(f"    응답 시간: {elapsed:.1f}s")
            scores.append(node_score)
        except json.JSONDecodeError:
            print(f"    ❌ JSON 파싱 실패: {raw[:200]}")
            scores.append(0)

    print(f"\n평균 점수: {sum(scores)/len(scores):.0%}")
    return scores

def eval_chat():
    print("\n" + "="*60)
    print("💬 대화 태스크 평가")
    print("="*60)

    scores = []
    for i, case in enumerate(CHAT_CASES):
        print(f"\n[{i+1}] 질문: {case['query']}")
        print(f"    컨텍스트: {case['context']}")

        system = CHAT_SYSTEM.format(context=case["context"])
        t0 = time.time()
        raw = ollama(system, case["query"])
        elapsed = time.time() - t0

        hits = sum(1 for k in case["expected_keywords"] if k in raw)
        score = hits / len(case["expected_keywords"])

        print(f"    답변: {raw}")
        print(f"    키워드 적중: {hits}/{len(case['expected_keywords'])} ({score:.0%})")
        print(f"    응답 시간: {elapsed:.1f}s")
        scores.append(score)

    print(f"\n평균 점수: {sum(scores)/len(scores):.0%}")
    return scores

# ── 메인 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"모델: {MODEL}")
    print(f"DB: {DB_PATH}")

    save_scores = eval_save()
    retrieve_scores = eval_retrieve()
    chat_scores = eval_chat()

    print("\n" + "="*60)
    print("📊 종합 결과")
    print("="*60)
    avg = lambda s: sum(s)/len(s) if s else 0
    print(f"저장:  {avg(save_scores):.0%}")
    print(f"인출:  {avg(retrieve_scores):.0%}")
    print(f"대화:  {avg(chat_scores):.0%}")
    print(f"전체:  {avg(save_scores + retrieve_scores + chat_scores):.0%}")
