#!/usr/bin/env python3
"""retrieve-expand 데이터 증강 스크립트 (준비만, 실행 시 LLM 호출).

단계:
  classify  - 기존 train.jsonl 질문을 유형별로 분류 → seeds_classified.jsonl
  generate  - 유형별 균등 생성 → aug_raw.jsonl (수동 검증 필요)
  merge     - 검증 통과본 → tasks/retrieve-expand/train.jsonl에 병합

질문 유형 (고정):
  - fact         단순 사실 질문 ("내 팀장 누구야?")
  - compare      비교 질문 ("A랑 B 중 뭐가 더 좋아?")
  - time_range   시간 범위 ("작년에 뭐 했지?")
  - conditional  조건부 ("만약 ~라면")
  - reason       이유/원인 ("왜 ~했어?")
  - recent       근황 ("요즘 ~ 어때?")
  - list         목록 ("~ 뭐 있어?")

사용 예:
  python scripts/mlx/augment_retrieve_expand.py classify
  python scripts/mlx/augment_retrieve_expand.py generate --per-type 100
  # 수동 검증: data/finetune/aug/retrieve-expand/aug_raw.jsonl → aug_verified.jsonl
  python scripts/mlx/augment_retrieve_expand.py merge
"""
import argparse
import json
import sys
from pathlib import Path
from collections import Counter

ROOT = Path(__file__).resolve().parents[2]
TASK_DIR = ROOT / "data/finetune/tasks/retrieve-expand"
AUG_DIR = ROOT / "data/finetune/aug/retrieve-expand"
MLX_URL = "http://localhost:8765/v1/chat/completions"

TYPES = ["fact", "compare", "time_range", "conditional", "reason", "recent", "list"]

CLASSIFY_SYSTEM = """다음 한국어 질문을 7가지 유형 중 하나로 분류하라.
한 단어만 출력: fact | compare | time_range | conditional | reason | recent | list

정의:
- fact: 단순 사실 확인 ("내 팀장 누구야?")
- compare: 두 대상 비교 ("A랑 B 중 뭐가 나아?")
- time_range: 특정 기간 관련 ("작년 여름에 뭐 했지?")
- conditional: 가정/조건부 ("만약 ~라면")
- reason: 이유/원인 ("왜 ~했어?")
- recent: 근황/최근 상태 ("요즘 어때?")
- list: 목록 열거 ("~에 뭐 있어?")"""

GENERATE_SYSTEM = """당신은 개인 지식 그래프 검색 엔진의 학습 데이터 생성기다.
아래 유형의 한국어 질문을 만들고, 그래프에서 검색할 형태소 단위 노드 키워드 배열을 생성하라.

출력 형식 (JSON 1줄):
{"question": "...", "keywords": ["노드1", "노드2", ...]}

규칙:
- keywords는 5~8개, 형태소 쪼개기 일관 ("CI/CD" → ["CI","CD"], "깃허브액션" → ["깃허브","액션"] 또는 그대로)
- 개인 질문만 (조직/회사 주제 제외)
- 질문은 자연스러운 구어체"""


def mlx_chat(system: str, user: str, temperature: float = 0.3, max_tokens: int = 256) -> str:
    import urllib.request
    req = urllib.request.Request(
        MLX_URL,
        data=json.dumps({
            "model": "synapse/retrieve-expand",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        data = json.loads(r.read())
    return data["choices"][0]["message"]["content"].strip()


def load_seeds() -> list[dict]:
    items = []
    with (TASK_DIR / "train.jsonl").open() as f:
        for line in f:
            d = json.loads(line)
            user = next(m["content"] for m in d["messages"] if m["role"] == "user")
            ast = next(m["content"] for m in d["messages"] if m["role"] == "assistant")
            q = user.replace("질문:", "").strip()
            try:
                kws = json.loads(ast)
            except Exception:
                continue
            items.append({"question": q, "keywords": kws})
    return items


def cmd_classify(_args) -> None:
    AUG_DIR.mkdir(parents=True, exist_ok=True)
    seeds = load_seeds()
    out = AUG_DIR / "seeds_classified.jsonl"
    counts = Counter()
    print(f"분류 대상: {len(seeds)}건")
    with out.open("w") as f:
        for i, item in enumerate(seeds):
            try:
                t = mlx_chat(CLASSIFY_SYSTEM, item["question"], temperature=0.0, max_tokens=8).lower()
                t = next((x for x in TYPES if x in t), "fact")
            except Exception as e:
                t = "fact"
                print(f"  [warn] {i}: {e}", file=sys.stderr)
            counts[t] += 1
            f.write(json.dumps({**item, "type": t}, ensure_ascii=False) + "\n")
            if (i + 1) % 20 == 0:
                print(f"  {i+1}/{len(seeds)}", flush=True)
    print(f"\n유형 분포:")
    for t in TYPES:
        print(f"  {t:12s} {counts[t]:4d}")
    print(f"저장: {out}")


def cmd_generate(args) -> None:
    classified = AUG_DIR / "seeds_classified.jsonl"
    if not classified.exists():
        sys.exit(f"먼저 classify 실행 필요: {classified}")
    by_type: dict[str, list[dict]] = {t: [] for t in TYPES}
    with classified.open() as f:
        for line in f:
            d = json.loads(line)
            by_type[d["type"]].append(d)

    out = AUG_DIR / "aug_raw.jsonl"
    per_type = args.per_type
    print(f"유형당 {per_type}건 생성 (총 {per_type * len(TYPES)}건 목표)")
    with out.open("w") as f:
        for t in TYPES:
            seeds = by_type[t]
            if not seeds:
                print(f"  {t}: 시드 없음, 스킵")
                continue
            print(f"  {t}: 시드 {len(seeds)}건 → 목표 {per_type}건")
            # 3개 시드를 예시로 주고 새 질문 + keywords 생성
            for i in range(per_type):
                import random
                exemplars = random.sample(seeds, min(3, len(seeds)))
                examples_str = "\n".join(
                    f"예시: {json.dumps({'question': e['question'], 'keywords': e['keywords']}, ensure_ascii=False)}"
                    for e in exemplars
                )
                prompt = f"유형: {t}\n\n{examples_str}\n\n위 유형과 비슷한 스타일로 새 질문 1건을 JSON으로 생성하라."
                try:
                    raw = mlx_chat(GENERATE_SYSTEM, prompt, temperature=0.7, max_tokens=256)
                    d = json.loads(raw)
                    d["type"] = t
                    d["source"] = "mlx_aug"
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
                except Exception as e:
                    print(f"    [warn] {t} #{i}: {e}", file=sys.stderr)
                if (i + 1) % 20 == 0:
                    print(f"    {t} {i+1}/{per_type}", flush=True)
    print(f"\n저장: {out}")
    print("다음 단계: aug_raw.jsonl을 사람이 검증해 aug_verified.jsonl로 저장 후 merge 실행")


def cmd_merge(_args) -> None:
    verified = AUG_DIR / "aug_verified.jsonl"
    if not verified.exists():
        sys.exit(f"검증 파일 없음: {verified}")
    # retrieve-expand 포맷으로 변환하여 기존 train.jsonl에 append
    target = TASK_DIR / "train.jsonl"
    before = sum(1 for _ in target.open())
    added = 0
    system_prompt = None
    with target.open() as f:
        for line in f:
            d = json.loads(line)
            system_prompt = next(m["content"] for m in d["messages"] if m["role"] == "system")
            break
    with target.open("a") as out, verified.open() as vf:
        for line in vf:
            d = json.loads(line)
            record = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"질문: {d['question']}"},
                    {"role": "assistant", "content": json.dumps(d["keywords"], ensure_ascii=False)},
                ]
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            added += 1
    after = before + added
    print(f"병합 완료: {before} → {after} (+{added})")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("classify")
    g = sub.add_parser("generate")
    g.add_argument("--per-type", type=int, default=100)
    sub.add_parser("merge")
    args = ap.parse_args()
    {"classify": cmd_classify, "generate": cmd_generate, "merge": cmd_merge}[args.cmd](args)


if __name__ == "__main__":
    main()
