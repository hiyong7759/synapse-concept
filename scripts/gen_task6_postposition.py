"""task6 파인튜닝 데이터 재생성 — 조사 기반 엣지 라벨.

기존 1,661개 입력 문장을 그대로 쓰고,
Claude Opus로 새 라벨링 규칙(조사 라벨) 적용해 출력 재생성.

실행:
  python3 scripts/gen_task6_postposition.py

출력:
  archive/finetune/data/task6_postposition.jsonl  (완성본)
  archive/finetune/data/task6_postposition.progress  (중단 시 재개용)
"""

import json
import os
import pathlib
import time

import anthropic

# ── 경로 ──────────────────────────────────────────────────────
BASE = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE / "archive/finetune/data"
OUT_FILE = DATA_DIR / "task6_postposition.jsonl"
PROGRESS_FILE = DATA_DIR / "task6_postposition.progress"

# ── 새 시스템 프롬프트 ─────────────────────────────────────────
SYSTEM = (
    "한국어 문장에서 지식 그래프의 노드와 엣지를 추출하라.\n"
    "JSON만 출력. 다른 텍스트 금지.\n\n"
    "출력 형식:\n"
    '{"nodes":[{"name":"노드명","category":"대분류.소분류"}],'
    '"edges":[{"source":"노드명","label":"조사","target":"노드명"}]}\n\n'
    "규칙:\n"
    "- 노드는 원자. 하나의 개념 = 하나의 노드.\n"
    "- 1인칭(나/내/저/제) → 항상 \"나\"(PER.individual)\n"
    "- 3인칭 주어는 나로 치환하지 말 것. 원문 그대로 노드로 추출.\n"
    "- 저장 불필요한 일상 대화 → {\"nodes\":[],\"edges\":[]}\n"
    "- 엣지 label은 원문의 조사 그대로 (에서, 으로, 의, 에, 를/을, 와/과, 한테, 에게 등). 조사 없으면 null.\n\n"
    "카테고리 대분류 (17개):\n"
    "PER(사람/조직) BOD(신체/건강) MND(심리/감정) FOD(음식) LIV(생활/주거)\n"
    "MON(돈/소비) WRK(일/직업) TEC(기술/기기) EDU(교육) LAW(법/행정)\n"
    "TRV(여행/장소) NAT(자연/동물) CUL(문화/예술) HOB(취미/스포츠)\n"
    "SOC(사회/뉴스) REL(종교/철학) REG(지역/날씨)\n\n"
    "예시:\n"
    '입력: "강남세브란스 정형외과 다니고 있어"\n'
    '출력: {"nodes":[{"name":"나","category":"PER.individual"},{"name":"강남세브란스","category":"BOD.medical"},{"name":"정형외과","category":"BOD.medical"}],'
    '"edges":[{"source":"나","label":"에서","target":"강남세브란스"},{"source":"강남세브란스","label":"의","target":"정형외과"}]}\n\n'
    '입력: "박지수가 이번에 개발팀장으로 승진했어"\n'
    '출력: {"nodes":[{"name":"박지수","category":"PER.colleague"},{"name":"개발팀장","category":"WRK.role"}],'
    '"edges":[{"source":"박지수","label":"으로","target":"개발팀장"}]}\n\n'
    '입력: "허리디스크 L4-L5 진단받았어"\n'
    '출력: {"nodes":[{"name":"나","category":"PER.individual"},{"name":"허리디스크","category":"BOD.disease"},{"name":"L4-L5","category":"BOD.part"}],'
    '"edges":[{"source":"나","label":null,"target":"허리디스크"},{"source":"허리디스크","label":null,"target":"L4-L5"}]}\n\n'
    '입력: "안녕 잘 지내?"\n'
    '출력: {"nodes":[],"edges":[]}'
)

MODEL = "claude-opus-4-6"


def load_sentences() -> list[str]:
    files = sorted(DATA_DIR.glob("task6*.jsonl"))
    sentences = []
    for f in files:
        for line in f.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            sentences.append(rec["messages"][1]["content"])
    return sentences


def load_progress() -> int:
    if PROGRESS_FILE.exists():
        return int(PROGRESS_FILE.read_text().strip())
    return 0


def save_progress(idx: int) -> None:
    PROGRESS_FILE.write_text(str(idx))


def call_opus(client: anthropic.Anthropic, sentence: str, retries: int = 3) -> str:
    for attempt in range(retries):
        try:
            msg = client.messages.create(
                model=MODEL,
                max_tokens=512,
                system=SYSTEM,
                messages=[{"role": "user", "content": sentence}],
            )
            return msg.content[0].text.strip()
        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            print(f"  rate limit — {wait}초 대기")
            time.sleep(wait)
        except Exception as e:
            print(f"  오류 (시도 {attempt+1}): {e}")
            time.sleep(5)
    return '{"nodes":[],"edges":[]}'


def make_record(sentence: str, output: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": sentence},
            {"role": "assistant", "content": output},
        ]
    }


def main():
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise SystemExit("ANTHROPIC_API_KEY 환경변수 필요")

    client = anthropic.Anthropic(api_key=api_key)
    sentences = load_sentences()
    total = len(sentences)
    start = load_progress()

    print(f"총 {total}건 / 시작 인덱스: {start}")
    print(f"출력 파일: {OUT_FILE}")

    with open(OUT_FILE, "a", encoding="utf-8") as out_fp:
        for i, sentence in enumerate(sentences[start:], start=start):
            output = call_opus(client, sentence)

            # JSON 유효성 검사
            try:
                json.loads(output)
            except json.JSONDecodeError:
                # JSON 블록만 추출 시도
                import re
                m = re.search(r"\{.*\}", output, re.DOTALL)
                output = m.group() if m else '{"nodes":[],"edges":[]}'

            record = make_record(sentence, output)
            out_fp.write(json.dumps(record, ensure_ascii=False) + "\n")
            out_fp.flush()

            save_progress(i + 1)

            if (i + 1) % 50 == 0 or i == start:
                print(f"  [{i+1}/{total}] {sentence[:40]}")

    PROGRESS_FILE.unlink(missing_ok=True)
    print(f"\n완료. {OUT_FILE}")


if __name__ == "__main__":
    main()
