#!/usr/bin/env python3
"""retrieve-filter v12 부족분 Claude CLI 증강.

노이즈 필터링(조사 엣지/형태소 단편)으로 드랍된 부분을 Claude CLI(opus)로 재생성.
기존 generate_task_data.py의 CLI 호출 패턴 재사용.

사용:
  python3 scripts/mlx/build_retrieve_filter_aug.py --train 284 --valid 27
  python3 scripts/mlx/build_retrieve_filter_aug.py --train 284 --valid 27 --dry-run
  python3 scripts/mlx/build_retrieve_filter_aug.py --merge
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK_DIR = ROOT / "data/finetune/tasks/retrieve-filter"
AUG_DIR = ROOT / "data/finetune/aug/retrieve-filter"

CLAUDE_CMD = "/Users/hiyong/.local/bin/claude"
MODEL = "opus"
BATCH_SIZE = 25
PASS_RATIO = 0.56  # 현재 kept 분포 기준 (pass 558 / kept 985 ≈ 0.566)

SYSTEM = """당신은 지식 그래프 인출 필터입니다.
질문과 문장을 보고, 이 문장이 질문과 관련 있는지 판단하세요.
불확실하면 pass로 판단하세요 (제외보다 포함이 안전).
출력: pass 또는 reject (한 단어만)"""

GEN_PROMPT = """\
Synapse 지식 그래프의 "인출 필터" 파인튜닝 데이터를 {count}개 생성하세요.

## 배경
사용자 질문과 후보 문장이 주어지면, 이 문장이 질문의 답변에 도움되는지 판단.
- 판단 단위: 개별 문장 (원자적 사실)
- 원칙: 불확실하면 pass (제외보다 포함이 안전)
- 시간 관련 질문 + 과거 시제 문장 → 대부분 pass

## 문장 스타일 (v12)
v12에서는 "원자 개념 노드 + 실제 한국어 문장" 구조.
문장은 형태소 단편 X. 자연스러운 한국어 완결형 문장.

올바른 문장 예시:
- "허리디스크 L4-L5 진단받았어"
- "어제 팀장님이랑 회의했어"
- "나 Kubernetes 공부 시작했어"
- "맥미니 2026-04-15 샀어"
- "2026년 4월 민지랑 밥 먹었어"
- "제35조 연차는 1년 80% 이상 출근 시 15일"
- "㈜한솔이랑 B프로젝트 계약 체결했어"

잘못된 문장 예시(금지):
- "살 었" (형태소 단편)
- "하 었" (형태소 단편)
- "X —[으로]→ Y" (조사 엣지 문법 표기)

## 질문 도메인 (골고루 혼합)
- 개인: 건강/신체, 음식/취향, 거주지, 가족/관계, 학습/취미, 기기/장비, 일정/시간
- 조직: 회사 규정, 프로젝트, 고객사, 인사이동, 취업규칙 조항

## 출력 형식 (JSON 배열, 다른 텍스트 없이)
[
  {{"user": "질문: <질문>\\n문장: <문장>", "assistant": "pass"}},
  {{"user": "질문: <질문>\\n문장: <문장>", "assistant": "reject"}},
  ...
]

## 생성 규칙
- 비율: pass {pass_count}개 / reject {reject_count}개 (정확히 맞추기)
- 질문과 문장은 매번 다르게. 도메인 골고루.
- pass 유형:
  * 직접 관련: 같은 도메인/대상 ("허리 어때?" + "허리디스크 L4-L5 진단받았어")
  * 간접 관련: 관련 도메인 ("요즘 몸 상태?" + "어제 병원 갔어")
  * 시간 범위: 시간 질문 + 해당 시기 문장 ("올해 뭐 샀어?" + "2026-04-15 맥미니 샀어")
  * 조직 조항: ("연차 며칠?" + "제35조 연차는 1년 80% 이상 출근 시 15일")
  * 경계(불확실): 관련될 수 있으면 pass
- reject 유형:
  * 완전 다른 도메인 ("허리 괜찮아?" + "나 Kubernetes 공부 시작했어")
  * 개인 질문 + 조직 문장, 그 반대도 reject
  * 시간은 맞지만 주제 다름

JSON 배열만 출력. 마크다운 코드블록, 설명, 번호 없음."""


def call_claude(prompt: str) -> str:
    try:
        r = subprocess.run(
            [CLAUDE_CMD, "-p", "--model", MODEL, prompt],
            capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        print("  ERROR: timeout", file=sys.stderr)
        return ""
    if r.returncode != 0:
        print(f"  ERROR: {r.stderr[:300]}", file=sys.stderr)
        return ""
    return r.stdout.strip()


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
    if not raw:
        return []
    start = raw.find("[")
    if start == -1:
        return []
    raw = raw[start:]
    decoder = json.JSONDecoder()
    try:
        data, _ = decoder.raw_decode(raw)
        if isinstance(data, list):
            return [it for it in data if "user" in it and "assistant" in it]
    except json.JSONDecodeError:
        pass
    last_close = raw.rfind("},")
    if last_close == -1:
        last_close = raw.rfind("}")
    if last_close != -1:
        cand = raw[:last_close + 1] + "]"
        try:
            data = json.loads(cand)
            if isinstance(data, list):
                return [it for it in data if "user" in it and "assistant" in it]
        except json.JSONDecodeError:
            pass
    return []


def make_record(user: str, assistant: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
            {"role": "assistant", "content": assistant},
        ]
    }


def generate(need: int, out_path: Path, dry_run: bool = False) -> int:
    """Claude CLI 배치 호출로 need건 생성."""
    AUG_DIR.mkdir(parents=True, exist_ok=True)
    # 기존 aug 이어쓰기
    existing = 0
    if out_path.exists():
        with out_path.open() as f:
            existing = sum(1 for _ in f)
    remaining = max(0, need - existing)
    print(f"→ {out_path.name}: 기존 {existing} / 필요 {need} / 추가 {remaining}")
    if dry_run:
        batches = (remaining + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"  [DRY] {batches}회 claude 호출 예상")
        return 0
    if remaining == 0:
        return 0

    seen_keys = set()
    if out_path.exists():
        with out_path.open() as f:
            for line in f:
                r = json.loads(line)
                seen_keys.add(r["messages"][1]["content"])

    added = 0
    with out_path.open("a") as out:
        while added < remaining:
            batch = min(BATCH_SIZE, remaining - added)
            pc = round(batch * PASS_RATIO)
            rc = batch - pc
            prompt = GEN_PROMPT.format(count=batch, pass_count=pc, reject_count=rc)
            raw = call_claude(prompt)
            items = parse_examples(raw)
            if not items:
                print(f"  batch 실패 (added={added}), 재시도")
                continue
            new_items = 0
            for it in items:
                u = it["user"]
                if u in seen_keys:
                    continue
                seen_keys.add(u)
                rec = make_record(u, it["assistant"].strip())
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                new_items += 1
                added += 1
                if added >= remaining:
                    break
            out.flush()
            print(f"  batch +{new_items} (누적 {added}/{remaining})")
    return added


def merge_into_task():
    """aug/retrieve-filter/*.jsonl 을 task/retrieve-filter/{train,valid}.jsonl 에 병합."""
    for split in ("train", "valid"):
        aug_path = AUG_DIR / f"{split}_aug.jsonl"
        dst = TASK_DIR / f"{split}.jsonl"
        if not aug_path.exists():
            print(f"skip {split}: aug 없음")
            continue
        before = sum(1 for _ in dst.open()) if dst.exists() else 0
        added = 0
        with dst.open("a") as out, aug_path.open() as f:
            for line in f:
                out.write(line)
                added += 1
        after = sum(1 for _ in dst.open())
        print(f"{split}: {before} → {after} (+{added})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train", type=int, default=0)
    ap.add_argument("--valid", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--merge", action="store_true", help="aug → task 병합만 실행")
    args = ap.parse_args()

    if args.merge:
        merge_into_task()
        return

    if args.train > 0:
        generate(args.train, AUG_DIR / "train_aug.jsonl", args.dry_run)
    if args.valid > 0:
        generate(args.valid, AUG_DIR / "valid_aug.jsonl", args.dry_run)


if __name__ == "__main__":
    main()
