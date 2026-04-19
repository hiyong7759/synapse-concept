#!/usr/bin/env python3
"""extract-core 학습 데이터 타겟팅 보강 — Claude CLI(opus) 기반.

실측 결과 (scripts/mlx/eval_extract_core.py):
- 부정부사 정답률 0% (학습 0건)
- 개인 일상 (FOD/HOB) 25%
- MND 감정 0%

카테고리별 타겟 프롬프트로 부족 도메인 보강. 자동 검증으로 품질 체크.

사용:
  python3 scripts/mlx/build_extract_core_aug.py --category neg_an --count 25   # 샘플
  python3 scripts/mlx/build_extract_core_aug.py --all                            # 전체 타겟 실행
  python3 scripts/mlx/build_extract_core_aug.py --merge                          # task dir에 병합
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUG_DIR = ROOT / "data/finetune/aug/extract-core"
TASK_DIR = ROOT / "data/finetune/tasks/extract-core"

CLAUDE_CMD = "/Users/hiyong/.local/bin/claude"
MODEL = "opus"
BATCH_SIZE = 25

VALID_MAJOR = {'PER','BOD','MND','FOD','LIV','MON','WRK','TEC','EDU','LAW','TRV','NAT','CUL','HOB','SOC','REL','REG'}

SYSTEM = """한국어 문장에서 지식 그래프의 노드, 카테고리, 보관 유형을 추출하라.
JSON만 출력. 다른 텍스트 금지.

출력 형식:
{"nodes":[{"name":"노드명","category":"대분류.소분류"}]}

규칙:
- 노드는 원자. 하나의 개념 = 하나의 노드.
- 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드로 추출. 문장에 없는 1인칭 추가 금지.
- 3인칭 주어는 원문 그대로 노드 추출.
- 부정부사(안, 못)는 독립 노드다. 예: "스타벅스 안 좋아" → 스타벅스, 안, 좋아 (3개 독립 노드).
- 추출할 노드가 없는 대화 → {"nodes":[]}

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


COMMON_RULES = """## 필수 규칙
- 노드는 원자 개념. 복합명사는 분리 ("물류 기획 담당자" → 물류/기획/담당, "허리디스크 L4-L5" → 허리디스크/L4-L5)
- 1인칭(나/내/저/제)이 문장에 있으면 "나" 노드 포함. 없으면 넣지 않음
- 카테고리는 대분류.소분류 형식 (위 목록 중 하나)
- 자연스러운 구어체 한국어, 한 문장당 10~40자
- 각 예시의 노드 개수 2~5개 (단문은 1~2개도 허용)"""


PROMPTS = {
    "neg_an": """synapse extract-core 학습 데이터 {count}개 생성. **"안" 부정부사 포함 문장**.

{common}

## 이 배치 특화 규칙
- 각 문장에 "안"이 부정부사로 반드시 포함 (예: "안 좋아", "안 먹어", "안 해")
- **"안"은 반드시 독립 노드**로 추출 (category: MND.emotion 또는 해당 동사의 대분류)
- 도메인 다양: 음식/취미/사람/건강/업무/기술 골고루
- 짧고 자연스러운 일상 문장

## 출력 형식 (JSON 배열)
[{{"user":"문장","assistant":"{{\\"nodes\\":[{{\\"name\\":\\"...\\",\\"category\\":\\"...\\"}}]}}"}}]

예시:
[{{"user":"스타벅스 안 좋아","assistant":"{{\\"nodes\\":[{{\\"name\\":\\"스타벅스\\",\\"category\\":\\"FOD.restaurant\\"}},{{\\"name\\":\\"안\\",\\"category\\":\\"MND.emotion\\"}},{{\\"name\\":\\"좋아\\",\\"category\\":\\"MND.emotion\\"}}]}}"}}]

JSON 배열만 출력. 설명/마크다운 금지.""",

    "neg_mot": """synapse extract-core 학습 데이터 {count}개 생성. **"못" 부정부사 포함 문장**.

{common}

## 이 배치 특화 규칙
- 각 문장에 "못"이 부정부사로 반드시 포함 (예: "운동 못 해", "수영 못 해", "엑셀 못해")
- **"못"은 반드시 독립 노드**로 추출 (category: MND.coping)
- 도메인: 운동/업무/기술/일상 능력
- 짧고 자연스러운 구어체

## 출력 형식 (JSON 배열)
[{{"user":"문장","assistant":"{{\\"nodes\\":[{{\\"name\\":\\"...\\",\\"category\\":\\"...\\"}}]}}"}}]

JSON 배열만 출력.""",

    "food": """synapse extract-core 학습 데이터 {count}개 생성. **개인 일상 음식 문장**.

{common}

## 이 배치 특화 규칙
- 음식/식당/음료/재료 관련 일상 단문 ("어제 김치찌개 먹었어", "점심 파스타", "커피 마셨어")
- 음식명은 단일 노드 (예: "김치찌개", "삼겹살", "평양냉면")
- 식당/카페명도 노드 (예: "스타벅스", "투썸")
- 1인칭 명시 문장도 일부 포함
- 카테고리: FOD.ingredient/recipe/restaurant/drink/product 중 하나

JSON 배열만 출력. [{{"user":"...","assistant":"..."}}]""",

    "hobby": """synapse extract-core 학습 데이터 {count}개 생성. **개인 취미/여가 문장**.

{common}

## 이 배치 특화 규칙
- 운동/취미/야외/게임/크래프트/모임 ("등산 갔다 왔어", "기타 배우고 있어", "러닝 시작")
- 취미명은 단일 노드 (예: "등산", "기타", "러닝", "요가")
- 장소명 포함 시 별도 노드 (예: "헬스장", "공원")
- 카테고리: HOB.sport/outdoor/game/craft/social/sing

JSON 배열만 출력.""",

    "relation": """synapse extract-core 학습 데이터 {count}개 생성. **개인 사람/관계 문장**.

{common}

## 이 배치 특화 규칙
- 가족/친구/동료/연인 관련 일상 ("민지랑 영화 봤어", "엄마랑 통화했어", "누나가 취업했어")
- 사람 이름/관계어는 별도 노드 (예: "민지", "엄마", "팀장님", "남자친구")
- 활동 노드 포함 (예: "영화", "통화", "저녁")
- 카테고리: PER.family/friend/colleague 또는 REL.romance/comm/conflict

JSON 배열만 출력.""",

    "health_short": """synapse extract-core 학습 데이터 {count}개 생성. **개인 건강/신체 단문**.

{common}

## 이 배치 특화 규칙
- 증상/병원/약/치료 짧은 일상 문장 ("감기 걸렸어", "두통 심해", "정형외과 갔어")
- 병명/증상/약명은 단일 노드 (예: "감기", "두통", "허리디스크", "세레콕시브")
- 구체 진단명은 별도 (예: "L4-L5")
- 카테고리: BOD.disease/medical/part/sleep/exercise/nutrition

JSON 배열만 출력.""",

    "emotion": """synapse extract-core 학습 데이터 {count}개 생성. **감정/심리 문장**.

{common}

## 이 배치 특화 규칙
- 감정 상태/스트레스/동기 ("요즘 힘들어", "스트레스 심해", "우울한 것 같아")
- 추상 감정어는 노드로 추출 (예: "스트레스", "불안", "힘들어", "피곤")
- 시간부사(요즘/최근)는 노드 아님
- 노드가 없어도 되는 경우는 제외 (반드시 1개 이상 노드)
- 카테고리: MND.mental/emotion/coping/motivation

JSON 배열만 출력.""",
}

TARGETS = {
    "neg_an":       40,
    "neg_mot":      40,
    "food":         80,
    "hobby":        60,
    "relation":     60,
    "health_short": 40,
    "emotion":      50,
}


def call_claude(prompt: str) -> str:
    try:
        r = subprocess.run(
            [CLAUDE_CMD, "-p", "--model", MODEL, prompt],
            capture_output=True, text=True, timeout=600,
        )
    except subprocess.TimeoutExpired:
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


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
    start = raw.find("[")
    if start == -1:
        return []
    raw = raw[start:]
    try:
        data = json.JSONDecoder().raw_decode(raw)[0]
        return [it for it in data if "user" in it and "assistant" in it]
    except json.JSONDecodeError:
        pass
    last = raw.rfind("},")
    if last > 0:
        try:
            data = json.loads(raw[:last + 1] + "]")
            return [it for it in data if "user" in it and "assistant" in it]
        except json.JSONDecodeError:
            return []
    return []


# ─── 자동 검증 ───────────────────────────────────────────────

NEG_WORDS = {"안", "못"}
FIRST_PERSON_WORDS = {"나", "내", "저", "제"}


def _has_first_person(text: str) -> bool:
    """입력에 1인칭 단어가 독립 토큰으로 있는지 (어절 경계)."""
    # 공백 분리 토큰에서 1인칭 prefix 체크
    for tok in re.split(r"\s+", text):
        stripped = re.sub(r"[은는이가을를에와과,\.\?!]+$", "", tok)
        if stripped in FIRST_PERSON_WORDS:
            return True
        # "저는" "제가" "나는" "내가" 등
        if any(tok.startswith(p) for p in ["나는", "내가", "저는", "제가", "나도", "내", "제"]):
            if tok[0] in "나내저제" and len(tok) <= 3:
                return True
    return False


def validate_record(item: dict, category_hint: str) -> tuple[bool, str]:
    """검증. (valid, reason) 반환."""
    user = item.get("user", "")
    asst_raw = item.get("assistant", "")
    try:
        asst = json.loads(asst_raw) if isinstance(asst_raw, str) else asst_raw
    except json.JSONDecodeError:
        return False, "JSON_parse_fail"

    nodes = asst.get("nodes", [])
    if not isinstance(nodes, list) or len(nodes) == 0:
        return False, "empty_nodes"

    names = []
    for n in nodes:
        if not isinstance(n, dict):
            return False, "node_not_dict"
        nm = n.get("name", "").strip()
        cat = n.get("category", "")
        if not nm:
            return False, "empty_name"
        # 원자성: 공백 2개 이상 OR 길이 10자 초과 → 의심
        if nm.count(" ") >= 2 or len(nm) > 12:
            return False, f"non_atomic:{nm}"
        # 카테고리 형식
        if "." not in cat or cat.split(".")[0] not in VALID_MAJOR:
            return False, f"bad_cat:{cat}"
        names.append(nm)

    # 중복 이름
    if len(names) != len(set(names)):
        return False, "duplicate_names"

    # 1인칭 규칙
    if _has_first_person(user):
        if "나" not in names:
            return False, "missing_self_node"

    # 부정부사 규칙 (neg_ 카테고리만)
    if category_hint.startswith("neg_"):
        target = "안" if category_hint == "neg_an" else "못"
        if target not in user:
            return False, f"missing_{target}_in_input"
        if target not in names:
            return False, f"missing_{target}_in_nodes"

    return True, "ok"


def normalize_record(item: dict) -> dict:
    """학습 포맷으로 변환 — messages 구조."""
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": item["user"]},
            {"role": "assistant", "content": item["assistant"]},
        ]
    }


# ─── 생성 ─────────────────────────────────────────────────

def generate_category(category: str, target: int) -> tuple[list[dict], dict]:
    """해당 카테고리 목표 수 생성. (records, stats) 반환."""
    AUG_DIR.mkdir(parents=True, exist_ok=True)
    out_path = AUG_DIR / f"{category}.jsonl"
    existing = 0
    if out_path.exists():
        with out_path.open() as f:
            existing = sum(1 for _ in f)
    remaining = max(0, target - existing)
    stats = {"target": target, "existing": existing, "generated": 0, "rejected": 0, "reasons": {}}
    if remaining == 0:
        return [], stats

    records = []
    seen_user = set()
    if out_path.exists():
        with out_path.open() as f:
            for line in f:
                r = json.loads(line)
                seen_user.add(r["messages"][1]["content"])
                records.append(r)

    with out_path.open("a") as out:
        while stats["generated"] + existing < target:
            need = min(BATCH_SIZE, target - stats["generated"] - existing)
            prompt = PROMPTS[category].format(count=need, common=COMMON_RULES)
            raw = call_claude(prompt)
            items = parse_examples(raw)
            if not items:
                print(f"  [{category}] 배치 파싱 실패, 재시도")
                continue

            batch_ok = 0
            for it in items:
                if stats["generated"] + existing >= target:
                    break
                valid, reason = validate_record(it, category)
                if not valid:
                    stats["rejected"] += 1
                    stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1
                    continue
                if it["user"] in seen_user:
                    stats["rejected"] += 1
                    stats["reasons"]["duplicate"] = stats["reasons"].get("duplicate", 0) + 1
                    continue
                seen_user.add(it["user"])
                rec = normalize_record(it)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                records.append(rec)
                stats["generated"] += 1
                batch_ok += 1
            out.flush()
            print(f"  [{category}] 배치 +{batch_ok}/{len(items)} (누적 gen {stats['generated']}, rej {stats['rejected']})")
            if batch_ok == 0:
                # 전체 배치 실패: 프롬프트 문제일 수 있으니 중단
                print(f"  [{category}] 전체 배치 실패, 중단")
                break

    return records, stats


# ─── 병합 ─────────────────────────────────────────────────

def merge_to_task():
    """aug/*.jsonl → task/extract-core/train.jsonl 에 append."""
    dst = TASK_DIR / "train.jsonl"
    before = sum(1 for _ in dst.open()) if dst.exists() else 0
    total_added = 0
    with dst.open("a") as out:
        for aug_file in sorted(AUG_DIR.glob("*.jsonl")):
            count = 0
            with aug_file.open() as f:
                for line in f:
                    out.write(line)
                    count += 1
            print(f"  {aug_file.name}: +{count}")
            total_added += count
    after = sum(1 for _ in dst.open())
    print(f"train.jsonl: {before} → {after} (+{total_added})")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", choices=list(TARGETS.keys()))
    ap.add_argument("--count", type=int)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args()

    if args.merge:
        merge_to_task()
        return

    if args.all:
        total_stats = {}
        for cat, target in TARGETS.items():
            print(f"\n▶ {cat} (목표 {target})")
            _, stats = generate_category(cat, target)
            total_stats[cat] = stats
        print("\n=== 전체 결과 ===")
        for cat, s in total_stats.items():
            print(f"  {cat}: gen {s['generated']}, rej {s['rejected']}, reasons {s['reasons']}")
        return

    if args.category:
        target = args.count or TARGETS[args.category]
        print(f"▶ {args.category} (목표 {target})")
        _, stats = generate_category(args.category, target)
        print(f"결과: gen {stats['generated']}, rej {stats['rejected']}")
        print(f"reasons: {stats['reasons']}")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
