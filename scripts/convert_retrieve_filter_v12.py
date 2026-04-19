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
LABELED_EDGE_RE = re.compile(r"^(.+?)\s*—\[([^\]]+)\]→\s*(.+)$")
SIMPLE_EDGE_RE = re.compile(r"^(.+?)\s*→\s*(.+)$")

# v12에서 폐기된 조사 라벨(형태소 분석 시절 엣지)
JOSA_LABELS = {
    "으로", "로", "에서", "에게", "에", "을", "를", "이", "가", "와", "과",
    "의", "은", "는", "도", "만", "부터", "까지", "께서", "한테",
    "하고", "랑", "이랑", "보다", "처럼", "같이", "마다", "조차",
    "고", "며", "지만", "아서", "어서", "니까",
}

# 어미·어간 단편으로 간주할 1~2자 한글 노이즈 목록 (Kiwi 형태소 분석 잔재)
NOISE_FRAGMENTS = {
    "었", "았", "겠", "더", "어", "아", "지", "고", "며", "되", "살", "먹", "가",
    "오", "보", "듣", "쓰", "있", "없", "않", "되",
    "다", "요", "지만", "니까", "아서", "어서", "려고", "려면",
    "니다", "습니다", "어요", "아요",
}


def is_fragment(token: str) -> bool:
    """형태소 단편 판정: 1자 한글 또는 노이즈 어미/어간."""
    token = token.strip()
    if token in NOISE_FRAGMENTS:
        return True
    if len(token) == 1 and "\uAC00" <= token <= "\uD7A3":
        return True
    return False


def is_noise_triple(triple_body: str) -> bool:
    """조사 라벨 엣지 또는 양쪽 토큰이 형태소 단편인 경우 노이즈."""
    m = LABELED_EDGE_RE.match(triple_body)
    if m:
        label = m.group(2).split(",")[0].strip()
        if label in JOSA_LABELS:
            return True
        left, right = m.group(1).strip(), m.group(3).strip()
        if is_fragment(left) or is_fragment(right):
            return True
        return False
    m2 = SIMPLE_EDGE_RE.match(triple_body)
    if m2:
        left, right = m2.group(1).strip(), m2.group(2).strip()
        if is_fragment(left) and is_fragment(right):
            return True
    return False


def triple_line_to_sentence(triple_line: str) -> str:
    """'트리플: X → Y' 또는 '트리플: X —[label]→ Y' → '문장: X Y'."""
    body = triple_line
    if body.startswith("트리플:"):
        body = body[len("트리플:"):].strip()
    m = LABELED_EDGE_RE.match(body) or SIMPLE_EDGE_RE.match(body)
    if m:
        return f"문장: {m.group(1).strip()} {m.group(2).strip()}"
    return f"문장: {body}"


def transform_record(record: dict) -> dict | None:
    """노이즈(조사 라벨/형태소 단편)이면 None 반환해 드랍."""
    messages = record["messages"]
    user = messages[1]["content"]

    lines = user.split("\n")
    question_line = next((l for l in lines if l.startswith("질문:")), "")
    triple_line = next((l for l in lines if l.startswith("트리플:")), "")

    if triple_line:
        triple_body = triple_line[len("트리플:"):].strip()
        if is_noise_triple(triple_body):
            return None

    sentence_line = triple_line_to_sentence(triple_line) if triple_line else ""
    new_user_parts = [question_line]
    if sentence_line:
        new_user_parts.append(sentence_line)
    new_user = "\n".join(new_user_parts)

    return {
        "messages": [
            {"role": "system", "content": NEW_SYSTEM_PROMPT},
            {"role": "user", "content": new_user},
            messages[2],
        ]
    }


def transform_file(src: Path, dst: Path) -> dict:
    stats = {"input": 0, "kept": 0, "dropped_noise": 0, "pass": 0, "reject": 0}
    with src.open() as fin, dst.open("w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            stats["input"] += 1
            record = json.loads(line)
            new_record = transform_record(record)
            if new_record is None:
                stats["dropped_noise"] += 1
                continue
            label = new_record["messages"][-1]["content"].strip()
            stats["kept"] += 1
            if label == "pass":
                stats["pass"] += 1
            elif label == "reject":
                stats["reject"] += 1
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
