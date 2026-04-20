"""베이스 모델 + 시스템 프롬프트 (어댑터 없음)로 extract 평가.

비교용: 파인튜닝 vs 베이스+프롬프트
같은 80건 골드셋 사용.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_MODEL = "unsloth/gemma-4-E2B-it-UD-MLX-4bit"

SYSTEM = """너는 형태소 분석기다.
한국어 문장에서 노드를 추출하라.

노드 원칙:
- 노드는 원자. 하나의 개념 = 하나의 노드.
- 품사 무관 (명사·동사·형용사·부정부사 모두 가능)
- 조사·어미 제거 (예: "허리디스크를" → "허리디스크")
- 1인칭(나/내/저/제) 명시된 경우 "나"로 통일
- 부정부사(안, 못)는 독립 노드

출력: {"nodes": ["노드1", "노드2", ...]}
JSON 한 줄만 출력. 설명·주석 금지.

예시:
입력: 어제 김치찌개 먹었어
출력: {"nodes":["김치찌개","먹"]}

입력: 스타벅스 안 좋아
출력: {"nodes":["스타벅스","안","좋"]}

입력: 나 허리디스크 L4-L5 진단받았어
출력: {"nodes":["나","허리디스크","L4-L5","진단받"]}

입력: 안녕 잘 지내?
출력: {"nodes":[]}"""

# eval_extract_core.py의 CASES 재사용
from eval_extract_core import CASES


def run() -> None:
    from mlx_lm import load, generate
    try:
        from mlx_lm.sample_utils import make_sampler
        sampler = make_sampler(temp=0.0)
    except Exception:
        sampler = None

    print(f"베이스 모델 로딩 (어댑터 없음): {BASE_MODEL}")
    t0 = time.time()
    model, tokenizer = load(BASE_MODEL)
    print(f"  ({time.time() - t0:.1f}s)\n")

    per_cat: dict = {}
    fails: list = []

    for idx, (cat, user_in, required) in enumerate(CASES, 1):
        messages = [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_in},
        ]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        kwargs = {"max_tokens": 1024, "verbose": False}
        if sampler is not None:
            kwargs["sampler"] = sampler
        out = generate(model, tokenizer, prompt=prompt, **kwargs)

        # Gemma 4 thinking 블록 후 JSON 추출
        out_clean = out
        if "<|channel>final" in out_clean:
            out_clean = out_clean.split("<|channel>final", 1)[1]
        if "<|message|>" in out_clean:
            out_clean = out_clean.split("<|message|>", 1)[1]
        try:
            matches = list(re.finditer(r'\{[^{}]*"nodes"[^{}]*\}', out_clean))
            if not matches:
                matches = list(re.finditer(r'\{.*?"nodes".*?\}', out_clean, re.DOTALL))
            parsed = json.loads(matches[-1].group()) if matches else {}
            nodes = parsed.get("nodes", [])
            actual = set()
            for n in nodes:
                if isinstance(n, str):
                    actual.add(n.strip())
                elif isinstance(n, dict) and n.get("name"):
                    actual.add(n["name"].strip())
        except Exception:
            actual = set()

        per_cat.setdefault(cat, {"total": 0, "full": 0, "partial": 0, "empty": 0, "miss": 0})
        per_cat[cat]["total"] += 1
        missing = required - actual
        if not actual:
            per_cat[cat]["empty"] += 1
            fails.append((cat, user_in, required, actual, "empty"))
        elif not missing:
            per_cat[cat]["full"] += 1
        elif len(missing) < len(required):
            per_cat[cat]["partial"] += 1
            fails.append((cat, user_in, required, actual, "partial"))
        else:
            per_cat[cat]["miss"] += 1
            fails.append((cat, user_in, required, actual, "miss"))

        status = "✓" if not missing and actual else ("-" if not actual else "△")
        print(f"[{idx:2d}] {status} [{cat:5s}] {user_in[:50]:50s} | 필요 {required} | 실제 {actual}")

    print("\n\n" + "=" * 70)
    print("카테고리별 정답률 — 베이스 모델 + 시스템 프롬프트 (어댑터 없음)")
    print("=" * 70)
    print(f"{'cat':8s} {'total':>5s} {'full':>5s} {'partial':>7s} {'empty':>5s} {'miss':>4s}  {'정답률':>6s}")
    g_total = g_full = 0
    for cat, s in per_cat.items():
        rate = s["full"] / s["total"] if s["total"] else 0
        g_total += s["total"]
        g_full += s["full"]
        print(f"{cat:8s} {s['total']:5d} {s['full']:5d} {s['partial']:7d} {s['empty']:5d} {s['miss']:4d}  {rate:6.1%}")
    print("-" * 70)
    print(f"{'TOTAL':8s} {g_total:5d} {g_full:5d}                         {g_full/g_total:6.1%}")


if __name__ == "__main__":
    run()
