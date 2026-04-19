#!/usr/bin/env python3
"""extract-core 정량 평가 — 80건 골드셋으로 실패 패턴 분석.

각 입력에 예상 노드 집합을 두고, 실제 어댑터 출력과 비교해 정답률·실패 패턴 측정.
"스스로 학습한 데이터 분포 가설"을 실측으로 검증하기 위한 도구.

사용:
  python3 scripts/mlx/eval_extract_core.py
  python3 scripts/mlx/eval_extract_core.py --adapter extract-core_M3_dirty  # 다른 어댑터 비교
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_MODEL = "unsloth/gemma-4-E2B-it-UD-MLX-4bit"

SYSTEM = """한국어 문장에서 지식 하이퍼그래프의 노드를 추출하라.
JSON만 출력. 다른 텍스트 금지.

출력 형식:
{"nodes":["노드명", ...]}

규칙:
- 노드는 원자. 하나의 개념 = 하나의 노드.
- 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드로 추출. 문장에 없는 1인칭 추가 금지.
- 3인칭 주어는 원문 그대로 노드 추출.
- 부정부사(안, 못)는 독립 노드다. 예: "스타벅스 안 좋아" → ["스타벅스", "안", "좋아"].
- 추출할 노드가 없는 대화 → {"nodes":[]}"""


# (카테고리, 입력, 필수 포함 노드 집합)
CASES: list[tuple[str, str, set[str]]] = [
    # === 개인 일상 - 음식 (8) ===
    ("FOD", "어제 김치찌개 먹었어", {"김치찌개"}),
    ("FOD", "점심에 파스타 먹었어", {"파스타"}),
    ("FOD", "저녁엔 삼겹살 구워 먹었어", {"삼겹살"}),
    ("FOD", "아침마다 그릭요거트 먹고 있어", {"그릭요거트"}),
    ("FOD", "커피 두 잔 마셨어", {"커피"}),
    ("FOD", "스타벅스 신메뉴 맛있어", {"스타벅스"}),
    ("FOD", "마라탕 먹으러 갔어", {"마라탕"}),
    ("FOD", "평양냉면 좋아해", {"평양냉면"}),

    # === 개인 일상 - 사람/관계 (8) ===
    ("PER", "민지랑 어제 놀이공원 갔어", {"민지", "놀이공원"}),
    ("PER", "어제 엄마랑 저녁 먹었어", {"엄마"}),
    ("PER", "팀장님이랑 회의했어", {"팀장님"}),
    ("PER", "동생이랑 영화 봤어", {"동생"}),
    ("PER", "박지수 승진했대", {"박지수"}),
    ("PER", "김대리 개발팀으로 이동했어", {"김대리", "개발팀"}),
    ("PER", "아빠 생신이 다음 주야", {"아빠", "생신"}),
    ("PER", "누나가 한 명 있어", {"누나"}),

    # === 개인 건강 (8) ===
    ("BOD", "나 허리디스크 L4-L5 진단받았어", {"나", "허리디스크", "L4-L5"}),
    ("BOD", "어제 정형외과 다녀왔어", {"정형외과"}),
    ("BOD", "세레콕시브 처방받았어", {"세레콕시브"}),
    ("BOD", "물리치료 3회차야", {"물리치료"}),
    ("BOD", "MRI 찍었어", {"MRI"}),
    ("BOD", "허리 다 나았어", {"허리"}),
    ("BOD", "요즘 불면증 심해", {"불면증"}),
    ("BOD", "감기 걸렸어", {"감기"}),

    # === 개인 취미/여행 (8) ===
    ("HOB", "주말에 등산 갔다 왔어", {"등산"}),
    ("HOB", "나 기타 배우고 있어", {"나", "기타"}),
    ("HOB", "헬스장 등록했어", {"헬스장"}),
    ("HOB", "러닝 시작했어", {"러닝"}),
    ("TRV", "작년 여름 제주도 갔어", {"제주도"}),
    ("TRV", "성수동으로 이사 왔어", {"성수동"}),
    ("CUL", "넷플릭스에서 드라마 봤어", {"넷플릭스"}),
    ("CUL", "데미안 읽고 있어", {"데미안"}),

    # === 1인칭 명시 (6) ===
    ("1인칭", "나 오늘 병원 갔어", {"나", "병원"}),
    ("1인칭", "나 Kubernetes 공부 시작했어", {"나", "Kubernetes"}),
    ("1인칭", "내 맥북 고장났어", {"나", "맥북"}),
    ("1인칭", "저 새로 이사 왔어요", {"나"}),
    ("1인칭", "제가 맡은 프로젝트예요", {"나"}),
    ("1인칭", "나 더나은에서 일해", {"나", "더나은"}),

    # === 부정 표현 (6) ===
    ("부정", "스타벅스 안 좋아", {"스타벅스", "안"}),
    ("부정", "운동 못 해", {"운동", "못"}),
    ("부정", "커피 안 마셔", {"커피", "안"}),
    ("부정", "그 영화 안 재밌어", {"안"}),
    ("부정", "수영 못 해", {"수영", "못"}),
    ("부정", "엑셀 못해", {"엑셀", "못"}),

    # === 감정/의견 (6) ===
    ("MND", "요즘 힘들어", set()),  # 힘들어가 노드여야 하는지는 애매 — 빈 집합 허용 테스트
    ("MND", "너무 피곤해", set()),
    ("MND", "스트레스 심해", {"스트레스"}),
    ("MND", "기분 좋아", set()),
    ("MND", "불안해", set()),
    ("MND", "우울한 것 같아", set()),

    # === 조직 문서 (10) ===
    ("LAW", "제35조 연차는 1년 80% 이상 출근 시 15일", {"제35조", "연차", "15일"}),
    ("LAW", "제42조 퇴직금은 1년 이상 근무자에게 지급", {"제42조", "퇴직금"}),
    ("LAW", "제15조 근무시간은 주 40시간이야", {"제15조", "근무시간", "40시간"}),
    ("LAW", "제42조 육아휴직은 만 8세 이하 자녀에 한해 1년 이내 허용", {"제42조", "육아휴직"}),
    ("WRK", "㈜한솔이랑 B프로젝트 계약 체결했어", {"㈜한솔", "B프로젝트"}),
    ("WRK", "㈜삼진전자랑 3년째 거래 중이야", {"㈜삼진전자"}),
    ("WRK", "A프로젝트 마감 6월 30일이야", {"A프로젝트"}),
    ("WRK", "나 더나은에서 웹기획자로 일하고 있어", {"나", "더나은", "웹기획자"}),
    ("WRK", "박지수가 개발팀장으로 승진했어", {"박지수", "개발팀장"}),
    ("MON", "연봉 협상 잘 됐어", {"연봉"}),

    # === 날짜 관련 (6) ===
    ("날짜", "2026-04-15 맥미니 샀어", {"맥미니"}),
    ("날짜", "2026년 4월 민지랑 밥 먹었어", {"민지"}),
    ("날짜", "어제 회의했어", {"회의"}),
    ("날짜", "내일 약속 있어", {"약속"}),
    ("날짜", "3월에 이직했어", {"이직"}),
    ("날짜", "작년 12월 퇴사했어", {"퇴사"}),

    # === 장비/기술 (6) ===
    ("TEC", "맥미니 M4 샀어", {"맥미니"}),
    ("TEC", "Kubernetes 공부 시작했어", {"Kubernetes"}),
    ("TEC", "React Native 배우고 있어", {"React Native"}),
    ("TEC", "Python으로 개발해", {"Python"}),
    ("TEC", "VSCode 쓰고 있어", {"VSCode"}),
    ("TEC", "아이폰 15 Pro 사용 중이야", {"아이폰 15 Pro"}),
]


def run(adapter_dir: Path) -> None:
    from mlx_lm import load, generate
    try:
        from mlx_lm.sample_utils import make_sampler
        sampler = make_sampler(temp=0.0)
    except Exception:
        sampler = None

    print(f"어댑터 로딩: {adapter_dir}")
    t0 = time.time()
    model, tokenizer = load(BASE_MODEL, adapter_path=str(adapter_dir))
    print(f"  ({time.time() - t0:.1f}s)\n")

    # 결과 집계
    per_cat = {}  # {cat: {"total":, "full_match":, "partial":, "empty":, "miss_required":}}
    fails = []  # 실패 상세

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

        # 파싱 (v15: nodes는 문자열 배열. dict 형태도 하위 호환)
        try:
            import re
            m = re.search(r"\{.*\}", out, re.DOTALL)
            if m:
                parsed = json.loads(m.group())
                nodes = parsed.get("nodes", [])
                actual_names = set()
                for n in nodes:
                    if isinstance(n, str):
                        actual_names.add(n.strip())
                    elif isinstance(n, dict) and n.get("name"):
                        actual_names.add(n["name"].strip())
            else:
                actual_names = set()
        except Exception:
            actual_names = set()

        per_cat.setdefault(cat, {"total": 0, "full": 0, "partial": 0, "empty": 0, "miss": 0})
        per_cat[cat]["total"] += 1
        missing = required - actual_names
        if not actual_names:
            per_cat[cat]["empty"] += 1
            fails.append((cat, user_in, required, actual_names, "empty"))
        elif not missing:
            per_cat[cat]["full"] += 1
        elif len(missing) < len(required):
            per_cat[cat]["partial"] += 1
            fails.append((cat, user_in, required, actual_names, "partial"))
        else:
            per_cat[cat]["miss"] += 1
            fails.append((cat, user_in, required, actual_names, "miss"))

        status = "✓" if not missing and actual_names else ("-" if not actual_names else "△")
        print(f"[{idx:2d}] {status} [{cat:5s}] {user_in[:50]:50s} | 필요 {required} | 실제 {actual_names}")

    # 카테고리별 요약
    print("\n\n" + "=" * 70)
    print("카테고리별 정답률")
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

    print("\n실패 케이스 처음 15건:")
    for cat, u, req, act, kind in fails[:15]:
        print(f"  [{kind}][{cat}] {u}")
        print(f"    need: {req}")
        print(f"    got : {act}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", default="extract-core")
    args = ap.parse_args()
    adapter_dir = ROOT / "runpod_output" / "mlx_adapters" / args.adapter
    if not (adapter_dir / "adapters.safetensors").exists():
        print(f"어댑터 없음: {adapter_dir}", file=sys.stderr)
        sys.exit(1)
    run(adapter_dir)


if __name__ == "__main__":
    main()
