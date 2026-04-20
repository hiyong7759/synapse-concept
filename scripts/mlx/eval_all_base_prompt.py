"""베이스 모델 + 시스템 프롬프트(어댑터 없음)로 7개 태스크를 일괄 평가.

목적: routing, retrieve-filter, retrieve-expand, security-context,
      security-access, save-pronoun, save-subject-org 가 파인튜닝 없이
      베이스 모델 + 프롬프트만으로 실용 수준 정확도에 도달하는지 검증.

사용: python scripts/mlx/eval_all_base_prompt.py [--n 30]
"""
from __future__ import annotations
import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASE_MODEL = "unsloth/gemma-4-E2B-it-UD-MLX-4bit"
TASKS_DIR = ROOT / "data/finetune/tasks"

TASKS = [
    "routing",
    "retrieve-filter",
    "retrieve-expand",
    "security-context",
    "security-access",
    "save-pronoun",
    "save-subject-org",
]


def strip_thinking(out: str) -> str:
    """Gemma 4 thinking 블록 제거 — 마지막 채널 구분자 뒤 텍스트만 남긴다.

    Gemma 4 출력 형태:
      <|channel>thought ... <channel|>{실제 응답}
      <|channel>thought ... <|channel>final<|message|>{실제 응답}
    두 패턴 모두 처리한다.
    """
    # 패턴 1: <channel|> 뒤 (가장 일반적)
    if "<channel|>" in out:
        out = out.rsplit("<channel|>", 1)[-1]
    # 패턴 2: <|channel>final ... <|message|> 뒤
    elif "<|channel>final" in out:
        out = out.split("<|channel>final", 1)[-1]
        if "<|message|>" in out:
            out = out.split("<|message|>", 1)[-1]
    return out.strip()


def find_last_json(text: str) -> Any:
    """텍스트에서 마지막 JSON 객체 또는 배열 추출. 실패 시 None."""
    for pat in (r"\{[\s\S]*\}", r"\[[\s\S]*\]"):
        matches = list(re.finditer(pat, text))
        if matches:
            try:
                return json.loads(matches[-1].group())
            except json.JSONDecodeError:
                continue
    return None


def score_oneword(out: str, expected: str) -> float:
    """첫 ~80자 안에 기대 단어가 등장하면 정답."""
    tail = strip_thinking(out).lower()
    return 1.0 if expected.lower() in tail[:80] else 0.0


def score_list_recall(out: str, expected: list[str]) -> float:
    """기대 리스트 대비 교집합 비율(recall). 베이스가 더 많이 뽑는 건 허용."""
    data = find_last_json(strip_thinking(out))
    if not isinstance(data, list):
        return 0.0
    actual = {str(x).strip().lower() for x in data if isinstance(x, (str, int))}
    exp = {str(x).strip().lower() for x in expected}
    if not exp:
        return 1.0 if not actual else 0.0
    return len(actual & exp) / len(exp)


def score_keys_match(out: str, expected: dict) -> float:
    """반환 JSON 의 핵심 키 세트가 기대와 일치하는지."""
    data = find_last_json(strip_thinking(out))
    if not isinstance(data, dict):
        return 0.0
    return 1.0 if set(expected.keys()) == set(data.keys()) else 0.0


def score_result_field(out: str, expected: dict) -> float:
    """{"result": "safe|confirm|reject", ...} 의 result 값 일치."""
    data = find_last_json(strip_thinking(out))
    if not isinstance(data, dict):
        return 0.0
    return 1.0 if data.get("result") == expected.get("result") else 0.0


def score_pronoun(out: str, expected: dict) -> float:
    """save-pronoun: text 공백 정규화 후 일치."""
    data = find_last_json(strip_thinking(out))
    if not isinstance(data, dict):
        return 0.0
    def norm(s: str) -> str:
        return " ".join(str(s).split())
    return 1.0 if norm(data.get("text", "")) == norm(expected.get("text", "")) else 0.0


def score_task(task: str, out: str, expected: Any) -> float:
    if task in ("routing", "retrieve-filter"):
        return score_oneword(out, str(expected))
    if task == "retrieve-expand":
        return score_list_recall(out, expected if isinstance(expected, list) else [])
    if task in ("security-context", "security-access"):
        return score_result_field(out, expected if isinstance(expected, dict) else {})
    if task == "save-pronoun":
        return score_pronoun(out, expected if isinstance(expected, dict) else {})
    if task == "save-subject-org":
        return score_keys_match(out, expected if isinstance(expected, dict) else {})
    return 0.0


def load_samples(task: str, n: int) -> list[tuple[str, str, Any]]:
    """(system, user, expected) 리스트. expected 는 JSON parse 가능하면 dict/list, 아니면 str."""
    path = TASKS_DIR / task / "valid.jsonl"
    samples: list[tuple[str, str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            msgs = d.get("messages", [])
            if len(msgs) < 3:
                continue
            system = msgs[0]["content"]
            user = msgs[1]["content"]
            assistant = msgs[2]["content"].strip()
            try:
                expected: Any = json.loads(assistant)
            except json.JSONDecodeError:
                expected = assistant
            samples.append((system, user, expected))
            if len(samples) >= n:
                break
    return samples


def run(n_per_task: int, verbose: bool) -> None:
    from mlx_lm import load, generate
    try:
        from mlx_lm.sample_utils import make_sampler
        sampler = make_sampler(temp=0.0)
    except Exception:
        sampler = None

    print(f"베이스 모델 로딩: {BASE_MODEL}")
    t0 = time.time()
    model, tokenizer = load(BASE_MODEL)
    print(f"  로드 완료 ({time.time() - t0:.1f}s)\n")

    results: dict[str, dict[str, float]] = {}
    for task in TASKS:
        print(f"\n=== {task} ===")
        samples = load_samples(task, n_per_task)
        total = len(samples)
        full_correct = 0
        score_sum = 0.0
        t_task = time.time()
        for i, (sys_msg, user, expected) in enumerate(samples, 1):
            messages = [
                {"role": "system", "content": sys_msg},
                {"role": "user", "content": user},
            ]
            prompt = tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            kwargs: dict[str, Any] = {"max_tokens": 2048, "verbose": False}
            if sampler is not None:
                kwargs["sampler"] = sampler
            out = generate(model, tokenizer, prompt=prompt, **kwargs)
            s = score_task(task, out, expected)
            score_sum += s
            if s >= 0.999:
                full_correct += 1
            mark = "✓" if s >= 0.999 else ("△" if s > 0 else "✗")
            if verbose:
                snippet = strip_thinking(out)[:80].replace("\n", " ")
                print(f"  [{i:2d}/{total}] {mark} s={s:.2f} | exp={str(expected)[:40]} | got={snippet}")
            else:
                print(f"  [{i:2d}/{total}] {mark} s={s:.2f}")
        elapsed = time.time() - t_task
        results[task] = {
            "n": float(total),
            "full": float(full_correct),
            "avg": score_sum / total if total else 0.0,
            "full_rate": full_correct / total if total else 0.0,
            "elapsed": elapsed,
        }

    print("\n\n" + "=" * 70)
    print("태스크별 베이스 모델 + 시스템 프롬프트 정답률")
    print("=" * 70)
    print(f"{'task':22s} {'n':>4s} {'full':>5s} {'정답률':>8s} {'평균점수':>10s} {'소요(s)':>8s}")
    print("-" * 70)
    for task, s in results.items():
        print(
            f"{task:22s} {int(s['n']):4d} {int(s['full']):5d} "
            f"{s['full_rate']:8.1%} {s['avg']:10.3f} {s['elapsed']:8.1f}"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="태스크별 샘플 수 (기본 30)")
    ap.add_argument("--verbose", action="store_true", help="각 샘플의 기대·실제 출력 표시")
    args = ap.parse_args()
    run(n_per_task=args.n, verbose=args.verbose)


if __name__ == "__main__":
    main()
