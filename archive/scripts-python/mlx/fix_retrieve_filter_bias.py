#!/usr/bin/env python3
"""retrieve-filter 편향 케이스 수정.

기준: 한 질문에 특정 라벨이 85% 이상 + 10회 이상 등장 → 편향.
조치:
  1. 치우친 라벨 과잉 케이스 일부 삭제 (목표 비율 70%까지)
  2. 같은 질문 × 반대 라벨 케이스를 Claude CLI로 생성
  3. 기존 train.jsonl 대체

사용:
  python3 scripts/mlx/fix_retrieve_filter_bias.py --detect   # 편향 감지만
  python3 scripts/mlx/fix_retrieve_filter_bias.py --fix      # 생성 + 교체
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAIN_PATH = ROOT / "data/finetune/tasks/retrieve-filter/train.jsonl"
CLAUDE_CMD = "/Users/hiyong/.local/bin/claude"
MODEL = "opus"

SYSTEM = """당신은 지식 그래프 인출 필터입니다.
질문과 문장을 보고, 이 문장이 질문과 관련 있는지 판단하세요.
불확실하면 pass로 판단하세요 (제외보다 포함이 안전).
출력: pass 또는 reject (한 단어만)"""

FIX_PROMPT = """\
retrieve-filter 학습 데이터 편향 수정을 위해 아래 각 (질문, 목표 라벨, 개수)에 맞춰 정확히 생성하세요.

요청:
{requests}

각 묶음에 대해:
- 목표 라벨이 reject인 경우: 질문과 완전 무관한 도메인의 실제 한국어 문장과 페어링
- 목표 라벨이 pass인 경우: 질문의 핵심 키워드와 직결되는 다양한 문장 페어링
  (예: "맥미니 언제 샀어?" + pass → 맥미니 구매 시기가 드러나는 서로 다른 문장 5개)

## 문장 스타일
- v12 완결형 한국어 (형태소 단편 금지: "살 었", "하 어" 등 금지)
- 실제 자연스러운 개인 일상 또는 조직 규정 문장
- 같은 페어 중복 금지

## 출력 형식 (JSON 배열만, 마크다운 없이)
[
  {{"user": "질문: <질문>\\n문장: <문장>", "assistant": "<pass 또는 reject>"}},
  ...
]
"""


def load_records(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(l) for l in f if l.strip()]


def detect_bias(records: list[dict], min_count: int = 10, threshold: float = 0.85):
    q_label: dict[str, Counter] = defaultdict(Counter)
    for r in records:
        u = r["messages"][1]["content"]
        q = next(l[4:].strip() for l in u.split("\n") if l.startswith("질문:"))
        label = r["messages"][2]["content"].strip()
        q_label[q][label] += 1

    biased = []
    for q, dist in q_label.items():
        tot = sum(dist.values())
        if tot < min_count:
            continue
        max_label, max_count = dist.most_common(1)[0]
        ratio = max_count / tot
        if ratio >= threshold:
            opp_label = "reject" if max_label == "pass" else "pass"
            target_max = int(tot * 0.7)
            drop_count = max_count - target_max
            biased.append({
                "question": q,
                "total": tot,
                "majority_label": max_label,
                "majority_count": max_count,
                "opposite_label": opp_label,
                "drop_count": drop_count,
                "add_count": drop_count,
            })
    return biased


def make_request_block(biased: list[dict]) -> str:
    lines = []
    for i, b in enumerate(biased, 1):
        lines.append(
            f"{i}. 질문 \"{b['question']}\" × {b['opposite_label']} {b['add_count']}건"
        )
    return "\n".join(lines)


def call_claude(prompt: str) -> str:
    try:
        r = subprocess.run(
            [CLAUDE_CMD, "-p", "--model", MODEL, prompt],
            capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def parse_examples(raw: str) -> list[dict]:
    raw = strip_code_fence(raw)
    start = raw.find("[")
    if start == -1:
        return []
    raw = raw[start:]
    try:
        data = json.JSONDecoder().raw_decode(raw)[0]
        return [it for it in data if "user" in it and "assistant" in it]
    except json.JSONDecodeError:
        pass
    last = raw.rfind("},")
    if last > 0:
        try:
            data = json.loads(raw[:last + 1] + "]")
            return [it for it in data if "user" in it and "assistant" in it]
        except json.JSONDecodeError:
            return []
    return []


def fix(records: list[dict], biased: list[dict], seed: int = 42) -> list[dict]:
    random.seed(seed)
    prompt = FIX_PROMPT.format(requests=make_request_block(biased))
    raw = call_claude(prompt)
    new_items = parse_examples(raw)
    print(f"Claude 생성: {len(new_items)}건")

    # 생성 내용을 (question, label)별로 정리
    by_qlabel: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for it in new_items:
        u = it["user"]
        q = next((l[4:].strip() for l in u.split("\n") if l.startswith("질문:")), None)
        if q is None:
            continue
        by_qlabel[(q, it["assistant"].strip())].append(it)

    # 각 편향 질문에 대해 치우친 라벨 케이스 중 drop_count만큼 삭제하고 새 케이스 추가
    drop_idx: set[int] = set()
    q_records: dict[str, list[int]] = defaultdict(list)
    for idx, r in enumerate(records):
        u = r["messages"][1]["content"]
        q = next(l[4:].strip() for l in u.split("\n") if l.startswith("질문:"))
        label = r["messages"][2]["content"].strip()
        q_records[(q, label)].append(idx)

    new_records: list[dict] = []
    for b in biased:
        key = (b["question"], b["majority_label"])
        idxs = q_records.get(key, [])
        to_drop = random.sample(idxs, min(b["drop_count"], len(idxs)))
        drop_idx.update(to_drop)
        generated = by_qlabel.get((b["question"], b["opposite_label"]), [])
        take = generated[:b["add_count"]]
        for it in take:
            new_records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": it["user"]},
                    {"role": "assistant", "content": it["assistant"].strip()},
                ]
            })
        print(f"  '{b['question']}': -{len(to_drop)} {b['majority_label']}, +{len(take)} {b['opposite_label']}")

    kept = [r for i, r in enumerate(records) if i not in drop_idx]
    return kept + new_records


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--detect", action="store_true")
    ap.add_argument("--fix", action="store_true")
    args = ap.parse_args()

    records = load_records(TRAIN_PATH)
    biased = detect_bias(records)
    print(f"편향 질문 {len(biased)}개:")
    for b in biased:
        print(f"  '{b['question']}' ({b['total']}회, {b['majority_label']} {b['majority_count']}) → 제거 {b['drop_count']}, {b['opposite_label']} 추가 {b['add_count']}")

    if args.detect:
        return
    if not args.fix:
        return

    fixed = fix(records, biased)
    print(f"\n결과: {len(records)} → {len(fixed)}")

    out = TRAIN_PATH.with_suffix(".jsonl.fixed")
    with out.open("w") as f:
        for r in fixed:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"저장: {out}")
    print("검증 후 덮어쓰기: mv " + str(out) + " " + str(TRAIN_PATH))


if __name__ == "__main__":
    main()
