#!/usr/bin/env python3
"""
Gemma4 E2B/E4B Ollama vs MLX 순차 벤치마크
- 한 모델씩 로드 → 테스트 → 언로드
- 저장/인출/대화 정확도 + 응답시간 측정
"""

import gc
import json
import re
import sqlite3
import sys
import time
import urllib.request

DB_PATH = "/Users/hiyong/.synapse/synapse.db"
UNSLOTH_PYTHON = "/Users/hiyong/.unsloth/unsloth_gemma4_mlx/bin/python"

MODELS = [
    {"name": "unsloth/gemma-4-E2B-it-UD-MLX-4bit",     "backend": "mlx"},
    {"name": "unsloth/gemma-4-E4B-it-UD-MLX-4bit",     "backend": "mlx"},
]

# ── 테스트 케이스 ─────────────────────────────────────────────────────────────

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

# ── BFS ───────────────────────────────────────────────────────────────────────

def get_bfs_context(start_names):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    ph = ",".join("?" * len(start_names))
    rows = conn.execute(
        f"SELECT id, name FROM nodes WHERE name IN ({ph}) AND status='active'",
        start_names
    ).fetchall()
    visited = {r["id"]: r["name"] for r in rows}
    queue = list(visited.keys())
    for _ in range(2):
        if not queue:
            break
        ph2 = ",".join("?" * len(queue))
        edges = conn.execute(
            f"""SELECT e.source_node_id, e.target_node_id, s.name as sname, t.name as tname
                FROM edges e
                JOIN nodes s ON s.id = e.source_node_id
                JOIN nodes t ON t.id = e.target_node_id
                WHERE (e.source_node_id IN ({ph2}) OR e.target_node_id IN ({ph2}))
                  AND s.status='active' AND t.status='active'""",
            queue + queue
        ).fetchall()
        next_q = []
        for e in edges:
            for nid, nname in [(e["source_node_id"], e["sname"]), (e["target_node_id"], e["tname"])]:
                if nid not in visited:
                    visited[nid] = nname
                    next_q.append(nid)
        queue = next_q
    result = set()
    if visited:
        ph3 = ",".join("?" * len(visited))
        edges2 = conn.execute(
            f"""SELECT s.name as sname, t.name as tname
                FROM edges e
                JOIN nodes s ON s.id = e.source_node_id
                JOIN nodes t ON t.id = e.target_node_id
                WHERE e.source_node_id IN ({ph3}) OR e.target_node_id IN ({ph3})""",
            list(visited.keys()) + list(visited.keys())
        ).fetchall()
        for e in edges2:
            result.add(e["sname"])
            result.add(e["tname"])
    conn.close()
    return result

# ── 백엔드별 호출 ─────────────────────────────────────────────────────────────

def call_ollama(model_name, system, user):
    prompt = f"{system}\n\n{user}"
    payload = json.dumps({
        "model": model_name,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 2048}
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
            out = r.get("response", "").strip()
            out = re.sub(r"<think>.*?</think>", "", out, flags=re.DOTALL).strip()
            out = re.sub(r"^```(?:json)?\s*", "", out).rstrip("` \n")
            return out
    except Exception as e:
        return f"ERROR: {e}"

def ollama_unload(model_name):
    """Ollama 모델 메모리에서 언로드 (keep_alive=0)"""
    payload = json.dumps({
        "model": model_name,
        "keep_alive": 0,
        "prompt": "",
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            pass
    except Exception:
        pass

_mlx_model = None
_mlx_tokenizer = None
_mlx_model_name = None

def _load_mlx(model_name):
    global _mlx_model, _mlx_tokenizer, _mlx_model_name
    if _mlx_model_name != model_name:
        from mlx_lm import load
        print(f"  (MLX 모델 로드 중: {model_name.split('/')[-1]}...)", flush=True)
        _mlx_model, _mlx_tokenizer = load(model_name)
        _mlx_model_name = model_name

def _unload_mlx():
    global _mlx_model, _mlx_tokenizer, _mlx_model_name
    _mlx_model = None
    _mlx_tokenizer = None
    _mlx_model_name = None
    import gc
    gc.collect()

def call_mlx(model_name, system, user):
    from mlx_lm import generate
    import re
    _load_mlx(model_name)
    messages = [{"role": "user", "content": system + "\n\n" + user}]
    prompt = _mlx_tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    t0 = time.time()
    out = generate(_mlx_model, _mlx_tokenizer, prompt=prompt, max_tokens=2048, verbose=False)
    elapsed = time.time() - t0
    # <think>...</think> 및 ```json 코드블록 제거
    out = re.sub(r"<think>.*?</think>", "", out, flags=re.DOTALL).strip()
    out = re.sub(r"^```(?:json)?\s*", "", out).rstrip("` \n")
    return out, elapsed

# ── 태스크 평가 ───────────────────────────────────────────────────────────────

def run_inference(model_info, system, user):
    t0 = time.time()
    if model_info["backend"] == "ollama":
        response = call_ollama(model_info["name"], system, user)
        elapsed = time.time() - t0
    else:
        response, elapsed = call_mlx(model_info["name"], system, user)
    return response, elapsed

def eval_save(model_info):
    scores, times = [], []
    for case in SAVE_CASES:
        raw, elapsed = run_inference(model_info, SAVE_SYSTEM, f"입력: {case['input']}\n출력:")
        times.append(elapsed)
        try:
            result = json.loads(raw)
            nodes = result.get("nodes", [])
            labels = [e.get("label", "") for e in result.get("edges", [])]
            node_hits = sum(1 for n in case["expected_nodes"] if any(n in r for r in nodes))
            label_hits = sum(1 for l in case["expected_labels"] if l in labels)
            score = (node_hits / len(case["expected_nodes"]) + label_hits / max(len(case["expected_labels"]), 1)) / 2
            scores.append(score)
        except json.JSONDecodeError:
            scores.append(0)
    return scores, times

def eval_retrieve(model_info):
    scores, times = [], []
    for case in RETRIEVE_CASES:
        raw, elapsed = run_inference(model_info, RETRIEVE_SYSTEM, f"질문: {case['query']}\n출력:")
        times.append(elapsed)
        try:
            result = json.loads(raw)
            all_nodes = set()
            for mode in ["mode1", "mode2", "mode3"]:
                all_nodes.update(result.get(mode, {}).get("start_nodes", []))
            bfs_nodes = get_bfs_context(list(all_nodes))
            node_hits = sum(1 for n in case["expected_nodes"] if n in bfs_nodes)
            scores.append(node_hits / len(case["expected_nodes"]))
        except json.JSONDecodeError:
            scores.append(0)
    return scores, times

def eval_chat(model_info):
    scores, times = [], []
    for case in CHAT_CASES:
        system = CHAT_SYSTEM.format(context=case["context"])
        raw, elapsed = run_inference(model_info, system, case["query"])
        times.append(elapsed)
        hits = sum(1 for k in case["expected_keywords"] if k in raw)
        scores.append(hits / len(case["expected_keywords"]))
    return scores, times

# ── 메인 ─────────────────────────────────────────────────────────────────────

def bench_model(model_info):
    label = f"{model_info['backend'].upper()} {model_info['name'].split('/')[-1]}"
    print(f"\n{'='*60}")
    print(f"모델: {label}")
    print(f"{'='*60}")

    print("  저장 평가 중...", flush=True)
    save_scores, save_times = eval_save(model_info)
    print("  인출 평가 중...", flush=True)
    retr_scores, retr_times = eval_retrieve(model_info)
    print("  대화 평가 중...", flush=True)
    chat_scores, chat_times = eval_chat(model_info)

    avg = lambda s: sum(s)/len(s) if s else 0
    all_scores = save_scores + retr_scores + chat_scores
    all_times  = save_times  + retr_times  + chat_times

    result = {
        "model": label,
        "save":  avg(save_scores),
        "retr":  avg(retr_scores),
        "chat":  avg(chat_scores),
        "total": avg(all_scores),
        "avg_time": avg(all_times),
        "max_time": max(all_times) if all_times else 0,
    }

    print(f"  저장: {result['save']:.0%}  인출: {result['retr']:.0%}  대화: {result['chat']:.0%}")
    print(f"  전체: {result['total']:.0%}  평균응답: {result['avg_time']:.1f}s  최대: {result['max_time']:.1f}s")

    if model_info["backend"] == "ollama":
        print("  (Ollama 모델 언로드 중...)", flush=True)
        ollama_unload(model_info["name"])
        time.sleep(3)
    else:
        print("  (MLX 모델 언로드 중...)", flush=True)
        _unload_mlx()
        time.sleep(2)

    return result

if __name__ == "__main__":
    results = []
    for m in MODELS:
        r = bench_model(m)
        results.append(r)

    print(f"\n{'='*60}")
    print("최종 비교")
    print(f"{'='*60}")
    print(f"{'모델':<40} {'전체':>6} {'저장':>6} {'인출':>6} {'대화':>6} {'avg(s)':>7} {'max(s)':>7}")
    print("-"*80)
    for r in sorted(results, key=lambda x: -x["total"]):
        print(f"{r['model']:<40} {r['total']:>6.0%} {r['save']:>6.0%} {r['retr']:>6.0%} {r['chat']:>6.0%} {r['avg_time']:>7.1f} {r['max_time']:>7.1f}")
