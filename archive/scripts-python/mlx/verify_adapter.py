#!/usr/bin/env python3
"""학습된 어댑터 추론 검증.

각 태스크별 테스트 케이스로 mlx_lm.generate 호출 → 출력 포맷/의미 확인.

사용:
  python3 scripts/mlx/verify_adapter.py --task extract-core
  python3 scripts/mlx/verify_adapter.py --task save-pronoun
  python3 scripts/mlx/verify_adapter.py --task retrieve-filter
  python3 scripts/mlx/verify_adapter.py --task all
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ADAPTER_ROOT = ROOT / "runpod_output/mlx_adapters"
BASE_MODEL = "unsloth/gemma-4-E2B-it-UD-MLX-4bit"

EXTRACT_CORE_SYSTEM = """한국어 문장에서 지식 그래프의 노드, 카테고리, 보관 유형을 추출하라.
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

SAVE_PRONOUN_SYSTEM = """당신은 지식 그래프 저장 엔진입니다.
입력 문장에서 치환 가능한 부분만 치환합니다.

규칙:
- 인칭대명사(나/내/저/제)는 절대 치환하지 않습니다.
- 날짜 관련 부사(오늘/어제/내일/이번 주/지난달 등)는 "날짜:" 값 기준으로 계산하여 치환.
- 치환 성공한 고정 토큰은 tokens[]에 {name, category?}로 담기. category는 규칙 기반 분명할 때만 (시간/장소/인물/사물/부정 등).
- 치환할 수 없는 지시어(이거/그거/걔/그때/거기 등)는 그대로 원문에 남깁니다. LLM이 따로 표기하지 않습니다.
- 저장 자체가 불가능한 완전 모호 케이스만 {"question": "..."} 단독 반환.

출력 형식:
{"text": "...", "tokens": [...]}
또는 {"question": "..."}"""

RETRIEVE_FILTER_SYSTEM = """당신은 지식 그래프 인출 필터입니다.
질문과 문장을 보고, 이 문장이 질문과 관련 있는지 판단하세요.
불확실하면 pass로 판단하세요 (제외보다 포함이 안전).
출력: pass 또는 reject (한 단어만)"""

TEST_CASES = {
    "extract-core": [
        ("나 허리디스크 L4-L5 진단받았어", "memory, '나'+'허리디스크 L4-L5'+'진단'"),
        ("어제 팀장님이랑 회의했어", "daily, '2026-04-17'? 아니, user가 직접 날짜 안 줌. '어제'·'팀장님'·'회의'"),
        ("제35조 연차는 1년 80% 이상 출근 시 15일", "memory, '제35조'(LAW.statute) 등"),
        ("스타벅스 안 좋아", "daily? memory?. 3개 노드: 스타벅스, 안, 좋아"),
        ("민지랑 어제 놀이공원 갔어", "daily"),
    ],
    "save-pronoun": [
        ("입력: 오늘 병원 갔어\n날짜: 2026-04-18", "text: '2026-04-18 병원 갔어', tokens 시간"),
        ("입력: 그거 별로야\n날짜: 2026-04-18", "text: '그거 별로야', tokens []"),
        ("입력: 나 오늘 이거 시작했어\n날짜: 2026-04-18", "text: '나 2026-04-18 이거 시작했어'"),
        ("입력: 그 동네 살기 좋아\n날짜: 2026-04-18", "question 가능"),
        ("입력: 어제 그 사람 만났어\n날짜: 2026-04-18", "text: '2026-04-17 그 사람 만났어'"),
    ],
    "retrieve-filter": [
        ("질문: 허리 언제 아팠지?\n문장: 허리디스크 L4-L5 진단받았어", "pass"),
        ("질문: 허리 언제 아팠지?\n문장: 나 Kubernetes 공부 시작했어", "reject"),
        ("질문: 연차 며칠이야?\n문장: 제35조 연차는 1년 80% 이상 출근 시 15일", "pass"),
        ("질문: 점심 뭐 먹을까?\n문장: ㈜한솔이랑 B프로젝트 계약 체결했어", "reject"),
        ("질문: 요즘 몸 상태?\n문장: 어제 정형외과 다녀왔어", "pass"),
    ],
}

SYSTEMS = {
    "extract-core": EXTRACT_CORE_SYSTEM,
    "save-pronoun": SAVE_PRONOUN_SYSTEM,
    "retrieve-filter": RETRIEVE_FILTER_SYSTEM,
}

MAX_TOKENS = {
    "extract-core": 1024,
    "save-pronoun": 256,
    "retrieve-filter": 8,
}


def run(task: str) -> None:
    try:
        from mlx_lm import load, generate
    except ImportError:
        print("mlx_lm not installed", file=sys.stderr)
        sys.exit(1)

    adapter_dir = ADAPTER_ROOT / task
    if not (adapter_dir / "adapters.safetensors").exists():
        print(f"어댑터 없음: {adapter_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{'='*60}\n▶ {task}  ({adapter_dir})\n{'='*60}")
    t0 = time.time()
    model, tokenizer = load(BASE_MODEL, adapter_path=str(adapter_dir))
    print(f"모델 로딩 {time.time()-t0:.1f}s\n")

    system = SYSTEMS[task]
    for i, (user_in, hint) in enumerate(TEST_CASES[task], 1):
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_in},
        ]
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        t1 = time.time()
        try:
            from mlx_lm.sample_utils import make_sampler
            sampler = make_sampler(temp=0.0)
            out = generate(model, tokenizer, prompt=prompt, max_tokens=MAX_TOKENS[task], sampler=sampler, verbose=False)
        except Exception:
            out = generate(model, tokenizer, prompt=prompt, max_tokens=MAX_TOKENS[task], verbose=False)
        dt = time.time() - t1
        print(f"[{i}] ({dt:.1f}s) IN : {user_in[:80]}")
        print(f"     EXPECT: {hint}")
        print(f"     OUT   : {out.strip()[:400]}")
        print()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, choices=["extract-core", "save-pronoun", "retrieve-filter", "all"])
    args = ap.parse_args()
    tasks = ["extract-core", "save-pronoun", "retrieve-filter"] if args.task == "all" else [args.task]
    for t in tasks:
        run(t)


if __name__ == "__main__":
    main()
