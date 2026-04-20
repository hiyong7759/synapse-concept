"""extract-state 1:1 이진 판정 실험 (베이스 모델만).

현 방식: 발화 + 사실 N개 → {"deactivate": [sid,...]} (한 번에)
실험 방식: 발화 + 사실 1개 → "유효" 또는 "무효" (한 사실씩 이진)

목적: N개 동시 판정의 집중도 분산 문제를 회피. 베이스 모델 + 단순 프롬프트
로도 파인튜닝 어댑터 수준 달성 가능한지 확인. 백그라운드에서 사실별 호출
가능하니 속도는 부차.
"""
from __future__ import annotations
import argparse
import json
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_MODEL = "unsloth/gemma-4-E2B-it-UD-MLX-4bit"
VALID = ROOT / "data/finetune/tasks/extract-state/valid.jsonl"

SYSTEM = """새 발화가 주어진 기존 사실을 무효화하는지 판단하라.

무효화 기준: 동일 주체의 상태·소속·위치·습관이 바뀐 경우만.
그 외(관련 있지만 상태 변화 아님, 별개 주제)는 유효로 판단.

출력: "유효" 또는 "무효" 한 단어만. 다른 설명 금지."""


def extract_facts(user_msg: str) -> list[tuple[int, str]]:
    """user 메시지에서 [(sid, text), ...] 추출."""
    facts = []
    for line in user_msg.split("\n"):
        m = re.match(r"\s*-\s*\[(\d+)\]\s*(.*)", line)
        if m:
            facts.append((int(m.group(1)), m.group(2).strip()))
    return facts


def extract_utterance(user_msg: str) -> str:
    if "알려진 사실:" in user_msg:
        return user_msg.split("알려진 사실:", 1)[0].strip()
    return user_msg.strip()


def strip_thinking(out: str) -> str:
    if "<channel|>" in out:
        out = out.rsplit("<channel|>", 1)[-1]
    return out.strip()


def parse_verdict(out: str) -> str:
    """출력에서 '유효' / '무효' 감지. 기본은 '유효' (보수적)."""
    tail = strip_thinking(out)[:120]
    if "무효" in tail and "무효화할" not in tail:
        return "무효"
    if "유효" in tail:
        return "유효"
    return "유효"  # 모호하면 유효 (기존 사실 보존 우선)


def run(verbose: bool, limit: int) -> None:
    from mlx_lm import load, generate
    try:
        from mlx_lm.sample_utils import make_sampler
        sampler = make_sampler(temp=0.0)
    except Exception:
        sampler = None

    print(f"베이스 모델 로딩: {BASE_MODEL}")
    t0 = time.time()
    model, tokenizer = load(BASE_MODEL)
    print(f"  ({time.time() - t0:.1f}s)")

    samples = [json.loads(l) for l in VALID.read_text(encoding="utf-8").splitlines() if l.strip()]
    if limit:
        samples = samples[:limit]
    total_samples = len(samples)
    print(f"샘플 {total_samples}건\n")

    n_full = 0
    sum_p = sum_r = sum_f1 = 0.0
    fact_count = 0
    t_start = time.time()

    for i, d in enumerate(samples, 1):
        msgs = d["messages"]
        user_orig = msgs[1]["content"]
        expected = json.loads(msgs[2]["content"])
        expected_x = set(expected.get("deactivate", []))

        facts = extract_facts(user_orig)
        utter = extract_utterance(user_orig)
        if not facts:
            continue

        actual_x: set[int] = set()
        for sid, ftext in facts:
            fact_count += 1
            user_msg = f"새 발화: {utter}\n\n기존 사실: {ftext}"
            messages = [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": user_msg},
            ]
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True,
                enable_thinking=False,
            )
            kwargs = {"max_tokens": 16, "verbose": False}
            if sampler is not None:
                kwargs["sampler"] = sampler
            raw = generate(model, tokenizer, prompt=prompt, **kwargs)
            verdict = parse_verdict(raw)
            if verdict == "무효":
                actual_x.add(sid)
            if verbose:
                mark = "✓" if (sid in expected_x) == (sid in actual_x) else "✗"
                exp_lbl = "무효" if sid in expected_x else "유효"
                print(f"    {mark} sid={sid} 기대={exp_lbl} 실제={verdict} | {ftext[:50]}")

        tp = len(expected_x & actual_x)
        fp = len(actual_x - expected_x)
        fn = len(expected_x - actual_x)
        p = tp / (tp + fp) if (tp + fp) else 1.0
        r = tp / (tp + fn) if (tp + fn) else 1.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        full = (actual_x == expected_x)

        if full:
            n_full += 1
        sum_p += p
        sum_r += r
        sum_f1 += f1

        mark = "✓" if full else ("△" if tp else "✗")
        print(f"[{i:2d}/{total_samples}] {mark} facts={len(facts)} exp={sorted(expected_x)} act={sorted(actual_x)} P={p:.2f} R={r:.2f}")

    elapsed = time.time() - t_start
    print("\n" + "=" * 70)
    print(f"샘플 {total_samples}건 / 호출 {fact_count}회 / 소요 {elapsed:.1f}s ({elapsed/max(fact_count,1)*1000:.0f}ms/호출)")
    print(f"Full match     = {n_full}/{total_samples} ({n_full/total_samples:.1%})")
    print(f"평균 precision = {sum_p/total_samples:.3f}")
    print(f"평균 recall    = {sum_r/total_samples:.3f}")
    print(f"평균 F1        = {sum_f1/total_samples:.3f}")
    print("\n참고 — 같은 valid 52건 기준")
    print(f"  어댑터 (N개 한번에): full 53.3%, F1 0.692")
    print(f"  O/X   (N개 한번에): full 28.8%, F1 0.550")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="처음 N개 샘플만 (0=전체)")
    args = ap.parse_args()
    run(verbose=args.verbose, limit=args.limit)


if __name__ == "__main__":
    main()
