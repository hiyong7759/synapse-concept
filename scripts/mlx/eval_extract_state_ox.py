"""extract-state O/X 방식 실험.

기존 방식:
  user: <발화>\n알려진 사실:\n- [434] ...\n- [435] ...
  assistant: {"deactivate": [434, 435]}  ← 번호 배열

O/X 방식:
  user: 입력 발화: <발화>\n\n사실:\n- [434] ...\n- [435] ...
  assistant: - [434] ... X\n- [435] ... O  ← 사실 원문 + O/X

목적:
- 번호 환각 감소 (모델이 사실 원문을 그대로 다시 씀)
- 사실별 판단 근거 명시
- 파싱 단순화 (줄 끝 O/X)
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

SYSTEM_OX = """입력 발화가 다음 각 사실을 무효화하는지 판단하라.

각 사실 원문을 그대로 다시 쓰고 줄 끝에 O(여전히 유효) 또는 X(무효화됨) 만 표시한다.
다른 설명·텍스트·JSON 금지.

판단 기준: 동일 주체의 상태·소속·위치·습관이 바뀐 경우만 X.

출력 예시:
- [434] 친구 민지가 심리상담 받고 있대 X
- [435] 민지가 항우울제 먹고 있어 X
- [436] 민지 우울증 진단받았대 X
"""


def extract_facts(user_msg: str) -> list[tuple[int, str]]:
    """user 메시지에서 [(sid, text), ...] 추출."""
    facts = []
    for line in user_msg.split("\n"):
        m = re.match(r"\s*-\s*\[(\d+)\]\s*(.*)", line)
        if m:
            facts.append((int(m.group(1)), m.group(2).strip()))
    return facts


def extract_utterance(user_msg: str) -> str:
    """알려진 사실 섹션 이전 = 입력 발화."""
    if "알려진 사실:" in user_msg:
        return user_msg.split("알려진 사실:", 1)[0].strip()
    return user_msg.strip()


def strip_thinking(out: str) -> str:
    if "<channel|>" in out:
        out = out.rsplit("<channel|>", 1)[-1]
    return out.strip()


def parse_ox(out: str) -> set[int]:
    """각 줄 '[sid] ... O|X' 파싱해 X 로 표시된 sid 집합 반환.

    모델이 'X(부가설명...)' 같은 형태로도 출력해서, 줄 끝이 아니라
    사실 원문 '뒤'에 처음 나오는 단일 O/X 토큰을 찾는다.
    """
    out = strip_thinking(out)
    invalid: set[int] = set()
    for line in out.split("\n"):
        line = line.strip()
        bracket = re.match(r"\s*-?\s*\[(\d+)\]\s*(.*)", line)
        if not bracket:
            continue
        sid = int(bracket.group(1))
        tail = bracket.group(2)
        # 사실 본문 뒤에 공백/괄호/줄끝으로 구분된 O 또는 X 단일 토큰
        m = re.search(r"(?:^|\s)([OXox])(?:$|\s|\()", tail)
        if m and m.group(1).upper() == "X":
            invalid.add(sid)
    return invalid


def run(verbose: bool) -> None:
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

    samples = [json.loads(l) for l in VALID.open(encoding="utf-8")]
    total = len(samples)
    print(f"샘플 {total}건 로드\n")

    n_full = 0
    sum_p = sum_r = sum_f1 = 0.0
    fails = []

    for i, d in enumerate(samples, 1):
        msgs = d["messages"]
        user_orig = msgs[1]["content"]
        expected = json.loads(msgs[2]["content"])
        expected_x = set(expected.get("deactivate", []))

        facts = extract_facts(user_orig)
        utter = extract_utterance(user_orig)
        if not facts:
            continue

        fact_lines = "\n".join(f"- [{sid}] {text}" for sid, text in facts)
        new_user = f"입력 발화: {utter}\n\n사실:\n{fact_lines}"

        messages = [
            {"role": "system", "content": SYSTEM_OX},
            {"role": "user", "content": new_user},
        ]
        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
            enable_thinking=False,
        )
        kwargs = {"max_tokens": 2048, "verbose": False}
        if sampler is not None:
            kwargs["sampler"] = sampler
        out = generate(model, tokenizer, prompt=prompt, **kwargs)

        actual_x = parse_ox(out)
        tp = len(expected_x & actual_x)
        fp = len(actual_x - expected_x)
        fn = len(expected_x - actual_x)
        p = tp / (tp + fp) if (tp + fp) else 1.0
        r = tp / (tp + fn) if (tp + fn) else 1.0
        f1 = 2 * p * r / (p + r) if (p + r) else 0.0
        full = (actual_x == expected_x)

        if full:
            n_full += 1
        else:
            fails.append((i, expected_x, actual_x, strip_thinking(out)[:200]))
        sum_p += p
        sum_r += r
        sum_f1 += f1

        mark = "✓" if full else ("△" if tp else "✗")
        print(f"[{i:2d}/{total}] {mark} exp={sorted(expected_x)} act={sorted(actual_x)} P={p:.2f} R={r:.2f}")
        if verbose:
            print(f"       out: {strip_thinking(out)[:300].replace(chr(10),' | ')}")

    print("\n" + "=" * 70)
    print(f"n={total}, full match={n_full} ({n_full/total:.1%})")
    print(f"평균 precision = {sum_p/total:.3f}  (낮을수록 잘못된 무효화 많음)")
    print(f"평균 recall    = {sum_r/total:.3f}  (낮을수록 놓친 무효화 많음)")
    print(f"평균 F1        = {sum_f1/total:.3f}")
    if fails and not verbose:
        print("\n실패 사례 상위 5건:")
        for idx, exp, act, snippet in fails[:5]:
            print(f"  [{idx}] exp={sorted(exp)} act={sorted(act)}")
            print(f"      out: {snippet[:200]}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    run(verbose=args.verbose)


if __name__ == "__main__":
    main()
