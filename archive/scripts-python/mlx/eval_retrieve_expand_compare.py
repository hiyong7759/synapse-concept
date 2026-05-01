"""retrieve-expand 베이스 vs 어댑터 출력 비교 CSV 생성.

목적:
- 기계 채점(부분 문자열 매칭)으론 0% 였지만 의미상 동등한 답이 많다는 가설.
- LLM 기반 채점(사람 또는 별도 LLM)을 위해 (질문, 기대, 베이스 출력, 어댑터 출력)
  튜플을 CSV 로 저장.

사용: python scripts/mlx/eval_retrieve_expand_compare.py
산출물: /tmp/retrieve_expand_compare.csv
"""
from __future__ import annotations
import csv
import gc
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_MODEL = "unsloth/gemma-4-E2B-it-UD-MLX-4bit"
VALID = ROOT / "data/finetune/tasks/retrieve-expand/valid.jsonl"
PROMPT_FILE = ROOT / "docs/RETRIEVE_EXPAND_SYSTEMPROMPT.md"
ADAPTER_DIR = ROOT / "data/finetune/models/tasks/retrieve-expand"
OUT_CSV = Path("/tmp/retrieve_expand_compare.csv")


def strip_thinking(out: str) -> str:
    if "<channel|>" in out:
        out = out.rsplit("<channel|>", 1)[-1]
    return out.strip()


def parse_list(out: str) -> list[str]:
    """출력에서 마지막 JSON 배열 파싱."""
    out = strip_thinking(out)
    matches = list(re.finditer(r"\[[\s\S]*?\]", out))
    if not matches:
        return []
    try:
        data = json.loads(matches[-1].group())
        return [str(x).strip() for x in data if isinstance(x, (str, int))]
    except json.JSONDecodeError:
        return []


def load_samples() -> list[dict]:
    samples = []
    for line in VALID.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        msgs = d["messages"]
        samples.append({
            "system_train": msgs[0]["content"],
            "user": msgs[1]["content"],
            "expected": json.loads(msgs[2]["content"]),
        })
    return samples


def run_inference(model, tokenizer, messages: list[dict], sampler) -> str:
    from mlx_lm import generate
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True,
        enable_thinking=False,
    )
    kwargs = {"max_tokens": 512, "verbose": False}
    if sampler is not None:
        kwargs["sampler"] = sampler
    return generate(model, tokenizer, prompt=prompt, **kwargs)


def main() -> None:
    from mlx_lm import load
    try:
        from mlx_lm.sample_utils import make_sampler
        sampler = make_sampler(temp=0.0)
    except Exception:
        sampler = None

    samples = load_samples()
    prompt_system = PROMPT_FILE.read_text(encoding="utf-8").strip()
    print(f"샘플 {len(samples)}건")

    results = [{"idx": i + 1, "question": s["user"], "expected": s["expected"]}
               for i, s in enumerate(samples)]

    # ── 1) 베이스 모델 + 시스템 프롬프트
    print(f"\n[1/2] 베이스 모델 로드: {BASE_MODEL}")
    t0 = time.time()
    model, tokenizer = load(BASE_MODEL)
    print(f"  ({time.time() - t0:.1f}s)")
    for i, s in enumerate(samples):
        msgs = [
            {"role": "system", "content": prompt_system},
            {"role": "user", "content": s["user"]},
        ]
        raw = run_inference(model, tokenizer, msgs, sampler)
        results[i]["base_raw"] = strip_thinking(raw)
        results[i]["base_list"] = parse_list(raw)
        print(f"  base [{i+1:2d}/{len(samples)}] {results[i]['base_list']}")
    del model, tokenizer
    gc.collect()

    # ── 2) 어댑터 + 학습 데이터 system
    print(f"\n[2/2] 어댑터 로드: {ADAPTER_DIR}")
    t0 = time.time()
    model, tokenizer = load(BASE_MODEL, adapter_path=str(ADAPTER_DIR))
    print(f"  ({time.time() - t0:.1f}s)")
    for i, s in enumerate(samples):
        msgs = [
            {"role": "system", "content": s["system_train"]},
            {"role": "user", "content": s["user"]},
        ]
        raw = run_inference(model, tokenizer, msgs, sampler)
        results[i]["adapter_raw"] = strip_thinking(raw)
        results[i]["adapter_list"] = parse_list(raw)
        print(f"  adap [{i+1:2d}/{len(samples)}] {results[i]['adapter_list']}")

    # ── CSV 저장
    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["idx", "question", "expected", "base_list", "adapter_list"])
        for r in results:
            writer.writerow([
                r["idx"],
                r["question"].replace("\n", " "),
                json.dumps(r["expected"], ensure_ascii=False),
                json.dumps(r["base_list"], ensure_ascii=False),
                json.dumps(r["adapter_list"], ensure_ascii=False),
            ])
    print(f"\n✅ CSV 저장: {OUT_CSV} ({len(results)} rows)")


if __name__ == "__main__":
    main()
