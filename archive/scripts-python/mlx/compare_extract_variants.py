"""extract 파이프라인 4가지 변형 비교 (A/B/C/D).

샘플: extract-core 데이터에서 10건 다양하게.
각 샘플마다 gold answer 있음 → precision/recall 측정 가능.

A: LLM 단독 (현재 기준)
B: LLM → MeCab 후처리 (조사 제거 + self-loop 제거)
C: MeCab → LLM 힌트 제공
D: MeCab 명사 추출 + LLM은 엣지 추론만

사용:
  python scripts/mlx/compare_extract_variants.py
"""
from __future__ import annotations
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import MeCab

os.environ.setdefault("MECABRC", "/opt/homebrew/etc/mecabrc")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

# sentence_id가 반드시 필요하지 않으므로 llm_extract와 mlx_chat만 사용
from engine.llm import mlx_chat

TAGGER = MeCab.Tagger("-d /opt/homebrew/lib/mecab/dic/mecab-ko-dic")

# 안전 조사 (거의 항상 조사)
SAFE_PARTICLES = ["이", "가", "은", "는", "을", "를", "에서", "부터", "까지", "에게", "한테", "께서", "께"]
# 애매한 조사 (맥락 필요)
AMBIG_PARTICLES = ["도", "만", "의", "에", "로", "으로", "와", "과", "랑"]


# ─── 샘플 ─────────────────────────────────────────────
# (입력문, gold_nodes set)
SAMPLES = [
    ("민지 상담 끝내고 약도 졸업했대", set()),  # gold 빈 답 (무의미 문장 or 파싱 불가)
    ("할머니 치매 많이 진행돼서 요양원에 가셨어", {"할머니", "치매", "요양원"}),
    ("교회 탈퇴하고 불교로 개종했어", {"교회", "불교", "탈퇴", "개종"}),
    ("민수 우울증 다 나았다고 했지?", {"민수", "우울증"}),
    ("동생 공황장애 다 나았대 약도 끊었어", {"동생", "공황장애", "약"}),
    ("허리 디스크로 병원 갔어", {"허리", "디스크", "병원"}),
    ("꿈도 못 꿔", {"꿈"}),
    ("저녁에 운동하러 가", {"저녁", "운동"}),
    ("나 적금 만기 언제였지?", {"나", "적금", "만기"}),
    ("교회 탈퇴하고 불교로 개종했어", {"교회", "불교", "탈퇴", "개종"}),
]


# ─── MeCab 헬퍼 ──────────────────────────────────────────
def mecab_parse(text: str) -> list[tuple[str, str]]:
    """(형태소, 품사) 리스트."""
    out = []
    for line in TAGGER.parse(text).splitlines():
        if line == "EOS" or not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        morph = parts[0]
        pos = parts[1].split(",")[0]
        out.append((morph, pos))
    return out


def mecab_nouns(text: str) -> list[str]:
    """NNG / NNP만 (일반명사·고유명사)."""
    nouns = [m for m, p in mecab_parse(text) if p in ("NNG", "NNP")]
    # 너무 짧은 것은 제거 (1글자는 대체로 무의미)
    return [n for n in nouns if len(n) >= 2]


def mecab_strip_particle(node: str) -> str:
    """노드 이름 끝에서 조사만 제거. 애매한 조사는 제거 안 함."""
    if not node:
        return node
    # MeCab으로 분석해서 끝이 조사인지 확인
    parsed = mecab_parse(node)
    if not parsed:
        return node
    # 마지막 요소가 조사(JX/JKB/JKS/JKO/JKC/JKG/JKV/JC)면 제거
    last_morph, last_pos = parsed[-1]
    if last_pos in ("JX", "JKB", "JKS", "JKO", "JKC", "JKG", "JKV", "JC"):
        stripped = node[: -len(last_morph)] if node.endswith(last_morph) else node
        if len(stripped) >= 1:
            return stripped
    return node


# ─── 4가지 추출 변형 ─────────────────────────────────────
def extract_A(text: str) -> dict:
    """LLM 단독."""
    t0 = time.time()
    try:
        raw = mlx_chat("extract", text, max_tokens=512)
        parsed = _parse_llm_json(raw)
    except Exception as e:
        parsed = {"nodes": [], "edges": [], "error": str(e)}
    parsed["elapsed"] = time.time() - t0
    parsed["llm_calls"] = 1
    return parsed


def extract_B(text: str) -> dict:
    """LLM → MeCab 후처리."""
    t0 = time.time()
    base = extract_A(text)
    # 조사 제거 + self-loop 제거
    new_nodes = []
    name_map = {}
    for n in base.get("nodes", []):
        orig = n["name"] if isinstance(n, dict) else n
        cleaned = mecab_strip_particle(orig)
        name_map[orig] = cleaned
        if isinstance(n, dict):
            n2 = {**n, "name": cleaned}
        else:
            n2 = cleaned
        new_nodes.append(n2)
    new_edges = []
    for e in base.get("edges", []):
        s = name_map.get(e.get("source", ""), e.get("source", ""))
        t = name_map.get(e.get("target", ""), e.get("target", ""))
        if s != t:
            new_edges.append({**e, "source": s, "target": t})
    return {
        "nodes": new_nodes,
        "edges": new_edges,
        "elapsed": time.time() - t0,
        "llm_calls": 1,
    }


def extract_C(text: str) -> dict:
    """MeCab 힌트 → LLM."""
    t0 = time.time()
    nouns = mecab_nouns(text)
    hint = f"형태소 분석 힌트 (명사 후보): {', '.join(nouns)}\n문장: {text}"
    try:
        raw = mlx_chat("extract", hint, max_tokens=512)
        parsed = _parse_llm_json(raw)
    except Exception as e:
        parsed = {"nodes": [], "edges": [], "error": str(e)}
    parsed["elapsed"] = time.time() - t0
    parsed["llm_calls"] = 1
    parsed["mecab_hint"] = nouns
    return parsed


def extract_D(text: str) -> dict:
    """MeCab 명사 = 노드, LLM은 엣지만 추론."""
    t0 = time.time()
    nouns = mecab_nouns(text)
    if len(nouns) < 2:
        return {
            "nodes": [{"name": n} for n in nouns],
            "edges": [],
            "elapsed": time.time() - t0,
            "llm_calls": 0,
        }
    # LLM에게 주어진 명사 사이 엣지만 추론 요청
    user = (
        f"문장: {text}\n명사 후보: {', '.join(nouns)}\n"
        f"출력: JSON 배열만. [{{\"source\":\"...\",\"label\":\"조사\",\"target\":\"...\"}}, ...]. "
        f"관계 없으면 []."
    )
    try:
        raw = mlx_chat("extract", user, max_tokens=256)
        edges = _parse_json_array(raw)
    except Exception as e:
        edges = []
    return {
        "nodes": [{"name": n} for n in nouns],
        "edges": edges,
        "elapsed": time.time() - t0,
        "llm_calls": 1,
    }


def _parse_llm_json(raw: str) -> dict:
    # LLM 출력에서 JSON 추출
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return {"nodes": [], "edges": [], "raw": raw[:200]}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {"nodes": [], "edges": [], "raw": raw[:200]}


def _parse_json_array(raw: str) -> list:
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        return json.loads(m.group(0))
    except Exception:
        return []


# ─── 평가 지표 ────────────────────────────────────────────
def metrics(result: dict, gold: set[str]) -> dict:
    pred_names = {n["name"] if isinstance(n, dict) else n for n in result.get("nodes", [])}
    tp = pred_names & gold
    fp = pred_names - gold
    fn = gold - pred_names
    precision = len(tp) / max(len(pred_names), 1) if pred_names else 0.0
    recall = len(tp) / max(len(gold), 1) if gold else 1.0
    # self-loop 검출
    self_loops = sum(
        1 for e in result.get("edges", [])
        if isinstance(e, dict) and e.get("source") == e.get("target") and e.get("source")
    )
    # 조사 포함 의심 (2글자 이상 노드 끝이 조사로 끝남)
    particle_nodes = sum(
        1 for n in pred_names
        if any(n.endswith(p) and len(n) > len(p) for p in (SAFE_PARTICLES + AMBIG_PARTICLES))
    )
    return {
        "pred": sorted(pred_names),
        "gold": sorted(gold),
        "tp": sorted(tp),
        "fp": sorted(fp),
        "fn": sorted(fn),
        "precision": precision,
        "recall": recall,
        "self_loops": self_loops,
        "particle_nodes": particle_nodes,
    }


# ─── 실행 ─────────────────────────────────────────────
def main():
    results = []
    for i, (text, gold) in enumerate(SAMPLES):
        print(f"\n{'='*70}")
        print(f"[{i+1}/{len(SAMPLES)}] {text}")
        print(f"  gold: {sorted(gold) or '(empty)'}")
        print(f"{'='*70}")
        row = {"text": text, "gold": sorted(gold), "variants": {}}
        for name, fn in [("A", extract_A), ("B", extract_B), ("C", extract_C), ("D", extract_D)]:
            res = fn(text)
            m = metrics(res, gold)
            print(f"\n  [{name}] {res['elapsed']:.1f}s  pred={m['pred']}")
            print(f"     P={m['precision']:.2f} R={m['recall']:.2f} "
                  f"self_loop={m['self_loops']} particle_nodes={m['particle_nodes']}")
            row["variants"][name] = {**res, **m}
        results.append(row)

    # 총합
    print(f"\n{'='*70}\n총합 (평균)\n{'='*70}")
    for v in ["A", "B", "C", "D"]:
        precisions = [r["variants"][v]["precision"] for r in results]
        recalls = [r["variants"][v]["recall"] for r in results]
        elapsed = sum(r["variants"][v]["elapsed"] for r in results)
        loops = sum(r["variants"][v]["self_loops"] for r in results)
        particles = sum(r["variants"][v]["particle_nodes"] for r in results)
        llm = sum(r["variants"][v]["llm_calls"] for r in results)
        print(f"  {v}: P={sum(precisions)/len(precisions):.2f} "
              f"R={sum(recalls)/len(recalls):.2f} "
              f"총시간={elapsed:.1f}s LLM호출={llm} self_loop={loops} particle_nodes={particles}")

    out = Path("/tmp/extract_variants_compare.json")
    with out.open("w") as f:
        # MeCab Tagger 객체 포함 안 되게 간단 dump
        import copy
        simple = copy.deepcopy(results)
        for r in simple:
            for v in r["variants"].values():
                v.pop("pred", None); v.pop("gold", None); v.pop("tp", None); v.pop("fp", None); v.pop("fn", None)
        f.write(json.dumps(simple, ensure_ascii=False, indent=2))
    print(f"\n저장: {out}")


if __name__ == "__main__":
    main()
