#!/usr/bin/env python3
"""extract-core 학습 데이터 v13 전환 — category 필드 제거 + 빈 nodes 폐기.

배경:
- v13에서 retention 폐기. 이미 M9.1에서 스키마는 제거했으나 학습 데이터엔 잔존 가능
- category 분류는 base 모델 프롬프트로 처리(실측 검증됨). extract-core는 노드 이름만 학습
- 빈 nodes 레코드는 "daily → 빈 nodes" 과적합 원인 → 폐기

처리:
- assistant content의 nodes 각 원소에서 category 키 제거 → {"name": "..."}만
- retention 필드 잔존 시 제거
- nodes 빈 배열 레코드는 폐기
- 시스템 프롬프트 v13 단순화로 교체
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "finetune" / "tasks" / "extract-core"

NEW_SYSTEM_PROMPT = """한국어 문장에서 지식 그래프의 노드를 추출하라.
JSON만 출력. 다른 텍스트 금지.

출력 형식:
{"nodes":[{"name":"노드명"}]}

규칙:
- 노드는 원자. 하나의 개념 = 하나의 노드. 품사 무관 — 인물·장소·수치·상태·행위·부정부사 모두 노드.
- 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드로 추출. 문장에 없는 1인칭 추가 금지.
- 3인칭 주어는 원문 그대로 노드 추출.
- 부정부사(안, 못)는 독립 노드. 예: "스타벅스 안 좋아" → 스타벅스, 안, 좋아 (3개 독립 노드)."""


def transform(record: dict) -> dict | None:
    messages = record["messages"]
    try:
        asst = json.loads(messages[2]["content"])
    except json.JSONDecodeError:
        return None

    # retention 제거
    asst.pop("retention", None)

    # nodes 정리 — category 제거
    nodes = asst.get("nodes", [])
    cleaned = []
    for n in nodes:
        if isinstance(n, dict) and n.get("name"):
            cleaned.append({"name": n["name"]})
        elif isinstance(n, str) and n:
            cleaned.append({"name": n})

    # 빈 nodes 레코드 폐기
    if not cleaned:
        return None

    asst["nodes"] = cleaned

    return {
        "messages": [
            {"role": "system", "content": NEW_SYSTEM_PROMPT},
            messages[1],  # user 유지
            {"role": "assistant", "content": json.dumps(asst, ensure_ascii=False)},
        ]
    }


def process(src: Path, dst: Path) -> dict:
    stats = {"input": 0, "kept": 0, "empty_dropped": 0, "parse_fail": 0}
    with src.open() as fin, dst.open("w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            stats["input"] += 1
            record = json.loads(line)
            new = transform(record)
            if new is None:
                if record["messages"][2]["content"].strip() == "":
                    stats["parse_fail"] += 1
                else:
                    stats["empty_dropped"] += 1
                continue
            stats["kept"] += 1
            fout.write(json.dumps(new, ensure_ascii=False) + "\n")
    return stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    for name in ("train.jsonl", "valid.jsonl"):
        src = DATA_DIR / name
        tmp = DATA_DIR / f"{name}.v13"
        stats = process(src, tmp)
        print(f"{name}: {stats}")
        if args.apply:
            tmp.replace(src)
            print(f"  -> applied")
        else:
            print(f"  -> tmp: {tmp}")


if __name__ == "__main__":
    main()
