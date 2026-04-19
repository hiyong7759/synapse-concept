#!/usr/bin/env python3
"""extract-core 학습 데이터 v12 전환: edges 필드 드롭.

기존: {"retention":"...", "nodes":[...], "edges":[...]}
신규: {"retention":"...", "nodes":[...]}

시스템 프롬프트도 edges 관련 규칙 제거.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "finetune" / "tasks" / "extract-core"

NEW_SYSTEM_PROMPT = """한국어 문장에서 지식 그래프의 노드, 카테고리, 보관 유형을 추출하라.
JSON만 출력. 다른 텍스트 금지.

출력 형식:
{"retention":"memory|daily","nodes":[{"name":"노드명","category":"대분류.소분류"}]}

규칙:
- 노드는 원자. 하나의 개념 = 하나의 노드.
- 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드로 추출. 문장에 없는 1인칭 추가 금지.
- 3인칭 주어는 원문 그대로 노드 추출.
- 부정부사(안, 못)는 독립 노드다. 예: "스타벅스 안 좋아" → 스타벅스, 안, 좋아 (3개 독립 노드).
- retention: 잘 변하지 않는 사실/상태/이력 → "memory". 순간적 활동/감정/일상 → "daily".
- 추출할 노드가 없는 대화 → {"retention":"daily","nodes":[]}

카테고리는 반드시 '대분류.소분류' 형식. 약어 금지.
PER: individual,family,friend,colleague,org,public
BOD: disease,medical,part,sleep,exercise,nutrition
MND: mental,emotion,coping,motivation,personality
FOD: ingredient,recipe,restaurant,drink,product
LIV: housing,moving,appliance,interior,maintenance,supply
MON: income,spending,saving,invest,loan,insurance,payment
WRK: workplace,role,jobchange,business,cert,tool
TEC: sw,hw,infra,ai,data
EDU: school,academic,exam,online,reading
LAW: statute,contract,rights,admin,tax
TRV: domestic,abroad,flight,place,stay
NAT: weather,animal,plant,ecology,terrain
CUL: music,film,book,art,show,media
HOB: sport,outdoor,game,craft,social,sing
SOC: issue,news,politics,economy,international,incident
REL: romance,comm,conflict
REG: practice,catholic,christianity,buddhism,islam,other"""


def transform_record(record: dict) -> dict:
    messages = record["messages"]
    new_messages = []
    for msg in messages:
        if msg["role"] == "system":
            new_messages.append({"role": "system", "content": NEW_SYSTEM_PROMPT})
        elif msg["role"] == "assistant":
            payload = json.loads(msg["content"])
            payload.pop("edges", None)
            new_messages.append({"role": "assistant", "content": json.dumps(payload, ensure_ascii=False)})
        else:
            new_messages.append(msg)
    return {"messages": new_messages}


def transform_file(src: Path, dst: Path) -> tuple[int, int]:
    kept = 0
    empty = 0
    with src.open() as fin, dst.open("w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            new_record = transform_record(record)
            payload = json.loads(new_record["messages"][-1]["content"])
            if not payload.get("nodes"):
                empty += 1
            kept += 1
            fout.write(json.dumps(new_record, ensure_ascii=False) + "\n")
    return kept, empty


def main() -> None:
    for name in ("train.jsonl", "valid.jsonl"):
        src = DATA_DIR / name
        tmp = DATA_DIR / f"{name}.v12"
        kept, empty = transform_file(src, tmp)
        tmp.replace(src)
        print(f"{name}: {kept} records (empty nodes: {empty})")


if __name__ == "__main__":
    main()
