"""Generate domain-specific episode texts using claude CLI.

Usage:
    python3 finetune/generate_episodes.py [--dry-run] [--domain 기술]
"""

import argparse
import json
import subprocess
import sys

from config import (
    BOUNDARY_EPISODES,
    CLAUDE_CMD,
    CLAUDE_MODEL,
    DIFFICULTY_DIST,
    EPISODE_DISTRIBUTION,
    EPISODE_TYPES,
    EPISODES_DIR,
    EPISODES_FILE,
)

DIFFICULTY_DESCRIPTIONS = {
    "easy": "단일 도메인, 단문 1문장. 노드 1~2개.",
    "medium": "2~3개 노드, 관계가 명시적. 1~2문장.",
    "hard": "복합문 2~3문장, 도메인 혼합 가능, 암시적 관계 포함. 노드 4개 이상.",
}

EPISODE_TYPE_DESCRIPTIONS = {
    "direct": '1인칭 서술. "나는 ~해", "~을 쓰고 있어" 형태.',
    "dialogue": 'Q&A 대화. "Q: 어떤 장비 써? A: 맥미니M4에 Docker 깔아서..." 형태.',
    "document": '이력서/문서 형식. "2018.02~현재 ㈜더나은 근무. BA/기획 담당." 형태.',
    "mixed": "일상 대화 속에 정보가 섞인 형태. 또는 모호한 표현.",
}

BOUNDARY_CATEGORIES = [
    ("greeting", 10, "순수 인사/감탄. '안녕', '뭐해?', '오늘 날씨 좋다'. 저장할 사실 없음."),
    ("greeting_with_info", 10, "인사 + 정보. '안녕! 요즘 React Native로 앱 만들고 있어'. 정보 부분만 추출 대상."),
    ("multi_domain", 15, "3개 이상 도메인이 혼합된 복합문. '진천 집에서 맥미니로 개발하는데 허리 때문에 의자 바꿨어'."),
    ("negation", 10, "부정형. '~는 안 써', '~는 안 해'. 노드 미생성 대상."),
    ("ambiguous", 10, "도메인이 모호하거나 은유적 표현. '요즘 Python 좀 배우고 있어' (기술 vs 학력)."),
]

GENERATION_PROMPT = """\
한국어로 된 개인 정보 에피소드를 생성하세요.
한국인 IT 개발자/직장인이 자신에 대해 말하는 자연스러운 문장입니다.

도메인: {domain}
난이도: {difficulty} — {difficulty_desc}
형식: {episode_type} — {episode_type_desc}

도메인 참고:
- 프로필: 이름, 나이, 성별
- 학력: 대학, 전공, 졸업년도
- 회사: 회사명, 입사, 재직기간
- 프로젝트: 프로젝트명, 기술스택
- 자격: 자격증, 취득년도
- 기술: 프로그래밍 언어, 프레임워크, 도구
- 고객사: 발주사, 외주 관계
- 역할: PM, BA, 개발자 등
- 조직: 부서, 팀
- 직급: 대리, 과장, 부장 등
- 업무: 유지보수, 개발, 기획
- 위치: 거주지, 근무지
- 경력: 연차, 경력 기간
- 병역: 군복무 유형, 기간
- 음식: 좋아하는 음식, 식습관
- 건강: 질병, 알레르기, 운동
- 장비: PC, 모니터, 키보드
- 용도: 장비/기술의 사용 목적
- 스펙: 하드웨어 사양

조건:
- 다양한 인물, 상황, 구체적 고유명사를 사용
- 실제 대화나 이력서에서 나올 법한 자연스러운 표현
- 각 에피소드는 독립적 (서로 다른 인물/상황)
- 너무 뻔하지 않은 다양한 조합

{count}개를 생성하세요. 각 줄에 하나씩, 번호 없이 텍스트만 출력."""

BOUNDARY_PROMPT = """\
한국어로 된 경계 케이스 에피소드를 생성하세요.

카테고리: {category}
설명: {description}

한국인 IT 개발자/직장인의 자연스러운 발화입니다.

조건:
- 다양한 상황과 표현
- 실제 대화에서 나올 법한 자연스러운 문장
- 각 에피소드는 독립적

{count}개를 생성하세요. 각 줄에 하나씩, 번호 없이 텍스트만 출력."""


def call_claude(prompt: str, model: str = CLAUDE_MODEL) -> str:
    """Call claude CLI with -p flag."""
    result = subprocess.run(
        [CLAUDE_CMD, "-p", "--model", model, prompt],
        capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr[:200]}", file=sys.stderr)
        return ""
    return result.stdout.strip()


def build_generation_plan() -> list[dict]:
    """Build a list of generation specs. Consolidate small buckets."""
    plan = []

    for domain, total in EPISODE_DISTRIBUTION.items():
        # Consolidate: one call per (domain, difficulty) to reduce call count
        for difficulty, diff_ratio in DIFFICULTY_DIST.items():
            count = max(1, round(total * diff_ratio))
            if count < 1:
                continue
            # Pick dominant episode type description for the prompt
            plan.append({
                "domain": domain,
                "difficulty": difficulty,
                "episode_type": "direct",  # dominant type
                "count": count,
                "category": "domain",
            })

    for category, count, description in BOUNDARY_CATEGORIES:
        plan.append({
            "domain": "mixed",
            "difficulty": "hard",
            "episode_type": "mixed",
            "count": count,
            "category": category,
            "description": description,
        })

    return plan


def make_prompt(spec: dict) -> str:
    """Create the user prompt for a generation spec."""
    if spec["category"] != "domain":
        return BOUNDARY_PROMPT.format(
            category=spec["category"],
            description=spec.get("description", ""),
            count=spec["count"],
        )

    return GENERATION_PROMPT.format(
        domain=spec["domain"],
        difficulty=spec["difficulty"],
        difficulty_desc=DIFFICULTY_DESCRIPTIONS[spec["difficulty"]],
        episode_type=spec["episode_type"],
        episode_type_desc=EPISODE_TYPE_DESCRIPTIONS[spec["episode_type"]],
        count=spec["count"],
    )


def parse_episodes(text: str) -> list[str]:
    """Parse newline-separated episodes from CLI response."""
    lines = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        for prefix in ["- ", "• ", "* "]:
            if line.startswith(prefix):
                line = line[len(prefix):]
        if line and line[0].isdigit() and ". " in line[:5]:
            line = line.split(". ", 1)[1]
        if line:
            lines.append(line.strip('"').strip())
    return lines


def generate(dry_run: bool = False, domain_filter: str | None = None):
    """Run episode generation via claude CLI."""
    plan = build_generation_plan()

    if domain_filter:
        plan = [s for s in plan if s["domain"] == domain_filter]

    total_planned = sum(s["count"] for s in plan)
    print(f"Generation plan: {len(plan)} claude calls, ~{total_planned} episodes")
    print(f"Model: {CLAUDE_MODEL}")

    if dry_run:
        for i, spec in enumerate(plan):
            print(f"  [{i+1}] {spec['domain']}/{spec.get('category','domain')} "
                  f"{spec.get('difficulty','')}"
                  f" x{spec['count']}")
        return

    EPISODES_DIR.mkdir(parents=True, exist_ok=True)

    all_episodes = []
    ep_id = 0

    for i, spec in enumerate(plan):
        prompt = make_prompt(spec)
        print(f"[{i+1}/{len(plan)}] {spec['domain']}/{spec.get('category','domain')} "
              f"x{spec['count']}...", end=" ", flush=True)

        text = call_claude(prompt)
        if not text:
            print("SKIP (empty)")
            continue

        episodes = parse_episodes(text)
        print(f"→ {len(episodes)} episodes")

        for ep_text in episodes:
            ep_id += 1
            entry = {
                "id": f"ep_{ep_id:04d}",
                "text": ep_text,
                "domain": spec["domain"],
                "difficulty": spec.get("difficulty", "hard"),
                "category": spec.get("category", "domain"),
            }
            all_episodes.append(entry)

    # Write JSONL
    with open(EPISODES_FILE, "w", encoding="utf-8") as f:
        for entry in all_episodes:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\nDone. {len(all_episodes)} episodes → {EPISODES_FILE}")

    domain_counts = {}
    for ep in all_episodes:
        domain_counts[ep["domain"]] = domain_counts.get(ep["domain"], 0) + 1
    print("\nDomain distribution:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        print(f"  {domain}: {count}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate episode texts via claude CLI")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--domain", type=str)
    args = parser.parse_args()

    generate(dry_run=args.dry_run, domain_filter=args.domain)
