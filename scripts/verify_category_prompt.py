#!/usr/bin/env python3
"""
프롬프트 기반 카테고리 분류 검증 스크립트.

목적: 파인튜닝 없이 "시스템 프롬프트 + 전체 택소노미"만으로 2B 모델이
      노드 카테고리를 정확히 뽑을 수 있는지 확인.

사전 조건: MLX 서버 실행 중 (python api/mlx_server.py → localhost:8765)

사용법:
    python3 scripts/verify_category_prompt.py --samples 50
    python3 scripts/verify_category_prompt.py --file data/finetune/task6_v2_e.jsonl --samples 100

채점 기준:
    - per-node category 정확도 (대분류.소분류 완전 일치)
    - 대분류만 맞는 비율 (부분 점수)
    - 실패 케이스 저장 → scripts/_verify_failures.jsonl
"""
import argparse
import json
import random
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path


MLX_URL = "http://localhost:8765/v1/chat/completions"
MODEL = "synapse/extract"  # 어댑터 이름 - 파인튜닝 안 된 베이스 모델로 바꿔야 검증 의미 있음
# 베이스만 쓰려면: MODEL = "synapse/chat" 또는 MLX 서버 라우트 확인


def call_llm(messages, temperature=0.0, max_tokens=512):
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        MLX_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def parse_output(text):
    """JSON 파싱 실패 시 None."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`").split("\n", 1)[-1]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def score(sample, predicted):
    """정답(sample["messages"][2])과 비교 → (match_cnt, partial_cnt, total_cnt, failures)."""
    expected = json.loads(sample["messages"][2]["content"])
    exp_nodes = {n["name"]: n.get("category") for n in expected.get("nodes", [])}
    if predicted is None:
        return 0, 0, len(exp_nodes), [{"expected": exp_nodes, "predicted": None}]

    pred_nodes = {n.get("name"): n.get("category") for n in predicted.get("nodes", [])}

    match = 0
    partial = 0
    failures = []
    for name, exp_cat in exp_nodes.items():
        pred_cat = pred_nodes.get(name)
        if pred_cat == exp_cat:
            match += 1
        else:
            if exp_cat and pred_cat and exp_cat.split(".")[0] == pred_cat.split(".")[0]:
                partial += 1
            failures.append({
                "sentence": sample["messages"][1]["content"].split("\n")[0],
                "node": name,
                "expected": exp_cat,
                "predicted": pred_cat,
            })
    return match, partial, len(exp_nodes), failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default="data/finetune/task6_v2_e.jsonl",
                    help="평가 데이터 (held-out 추천)")
    ap.add_argument("--samples", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="scripts/_verify_failures.jsonl")
    args = ap.parse_args()

    lines = Path(args.file).read_text().splitlines()
    random.seed(args.seed)
    sampled = random.sample(lines, min(args.samples, len(lines)))

    total_nodes = 0
    total_match = 0
    total_partial = 0
    all_failures = []
    per_cat_stats = defaultdict(lambda: [0, 0, 0])  # cat -> [match, partial, total]

    for i, line in enumerate(sampled, 1):
        sample = json.loads(line)
        sys_msg = sample["messages"][0]
        user_msg = sample["messages"][1]
        try:
            raw = call_llm([sys_msg, user_msg])
        except Exception as e:
            print(f"[{i}] 호출 실패: {e}", file=sys.stderr)
            continue

        predicted = parse_output(raw)
        m, p, t, fails = score(sample, predicted)
        total_nodes += t
        total_match += m
        total_partial += p
        all_failures.extend(fails)

        # 카테고리별 통계
        expected = json.loads(sample["messages"][2]["content"])
        for n in expected.get("nodes", []):
            cat = n.get("category")
            if not cat:
                continue
            per_cat_stats[cat][2] += 1
            if predicted:
                pred_map = {nn.get("name"): nn.get("category")
                            for nn in predicted.get("nodes", [])}
                pc = pred_map.get(n["name"])
                if pc == cat:
                    per_cat_stats[cat][0] += 1
                elif pc and pc.split(".")[0] == cat.split(".")[0]:
                    per_cat_stats[cat][1] += 1

        if i % 10 == 0:
            print(f"  진행 {i}/{len(sampled)} | acc={total_match}/{total_nodes} "
                  f"({100*total_match/max(total_nodes,1):.1f}%)")

    print(f"\n=== 결과 ({args.samples}샘플) ===")
    print(f"노드 총 {total_nodes}개")
    print(f"완전 일치:  {total_match} ({100*total_match/max(total_nodes,1):.1f}%)")
    print(f"대분류 일치: {total_partial} ({100*total_partial/max(total_nodes,1):.1f}%)")
    print(f"오분류:     {total_nodes - total_match - total_partial} "
          f"({100*(total_nodes - total_match - total_partial)/max(total_nodes,1):.1f}%)")

    print(f"\n카테고리별 (샘플 ≥3):")
    for cat, (m, p, t) in sorted(per_cat_stats.items(), key=lambda x: -x[1][2]):
        if t < 3:
            continue
        print(f"  {cat:25s}  {m}/{t} ({100*m/t:.0f}%)  +부분 {p}")

    Path(args.out).write_text("\n".join(json.dumps(f, ensure_ascii=False) for f in all_failures))
    print(f"\n실패 케이스: {args.out}")


if __name__ == "__main__":
    main()
