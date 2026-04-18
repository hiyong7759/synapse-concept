#!/usr/bin/env python3
"""retrieve-filter 학습 데이터 v12 전환.

기존 입력 단위: 트리플 ("질문: X\n트리플: A → B")
신규 입력 단위: 문장  ("질문: X\n문장: A B")

트리플 엣지가 v12에서 폐기되면서(조사 엣지 제거) 판단 단위를 문장으로 통일.
기존 데이터의 트리플을 단어 연결된 의사 문장으로 기계 변환.

사용:
  python3 scripts/convert_retrieve_filter_v12.py           # tmp 파일만 (*.v12)
  python3 scripts/convert_retrieve_filter_v12.py --apply   # 덮어쓰기
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "finetune" / "tasks" / "retrieve-filter"

NEW_SYSTEM_PROMPT = """당신은 지식 그래프 인출 필터입니다.
질문과 문장을 보고, 이 문장이 질문과 관련 있는지 판단하세요.
불확실하면 pass로 판단하세요 (제외보다 포함이 안전).
출력: pass 또는 reject (한 단어만)"""

# "A —[label, seq=N]→ B" 또는 "A —[label]→ B" 또는 "A → B"
LABELED_EDGE_RE = re.compile(r"^(.+?)\s*—\[[^\]]+\]→\s*(.+)$")
SIMPLE_EDGE_RE = re.compile(r"^(.+?)\s*→\s*(.+)$")


def triple_line_to_sentence(triple_line: str) -> str:
    """'트리플: X → Y' 또는 '트리플: X —[label]→ Y' → '문장: X Y'."""
    body = triple_line
    if body.startswith("트리플:"):
        body = body[len("트리플:"):].strip()
    m = LABELED_EDGE_RE.match(body) or SIMPLE_EDGE_RE.match(body)
    if m:
        return f"문장: {m.group(1).strip()} {m.group(2).strip()}"
    return f"문장: {body}"


def transform_record(record: dict) -> dict:
    messages = record["messages"]
    user = messages[1]["content"]

    lines = user.split("\n")
    question_line = next((l for l in lines if l.startswith("질문:")), "")
    triple_line = next((l for l in lines if l.startswith("트리플:")), "")
    sentence_line = triple_line_to_sentence(triple_line) if triple_line else ""

    new_user_parts = [question_line]
    if sentence_line:
        new_user_parts.append(sentence_line)
    new_user = "\n".join(new_user_parts)

    return {
        "messages": [
            {"role": "system", "content": NEW_SYSTEM_PROMPT},
            {"role": "user", "content": new_user},
            messages[2],  # assistant(pass/reject) 유지
        ]
    }


def transform_file(src: Path, dst: Path) -> dict:
    stats = {"total": 0, "pass": 0, "reject": 0, "other": 0}
    with src.open() as fin, dst.open("w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            new_record = transform_record(record)
            label = new_record["messages"][-1]["content"].strip()
            stats["total"] += 1
            if label == "pass":
                stats["pass"] += 1
            elif label == "reject":
                stats["reject"] += 1
            else:
                stats["other"] += 1
            fout.write(json.dumps(new_record, ensure_ascii=False) + "\n")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    for name in ("train.jsonl", "valid.jsonl"):
        src = DATA_DIR / name
        tmp = DATA_DIR / f"{name}.v12"
        stats = transform_file(src, tmp)
        print(f"{name}: {stats}")
        if args.apply:
            tmp.replace(src)
            print(f"  -> applied")
        else:
            print(f"  -> tmp: {tmp}")


if __name__ == "__main__":
    main()
