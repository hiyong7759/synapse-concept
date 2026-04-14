"""task6 데이터 재생성 — claude -p 루프 방식.

문장 하나씩 claude -p 호출 → JSONL 저장. 중단 시 재개 가능.

실행:
  python3 scripts/gen_task6_loop.py [--batch 0-4] [--workers 5]
"""

import argparse
import json
import pathlib
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE / "data/finetune"

SYSTEM = (
    "한국어 문장에서 지식 그래프의 노드와 엣지를 추출하라.\n"
    "JSON만 출력. 다른 텍스트 금지.\n\n"
    "출력 형식:\n"
    '{"nodes":[{"name":"노드명","category":"대분류.소분류"}],'
    '"edges":[{"source":"노드명","label":"조사","target":"노드명"}]}\n\n'
    "규칙:\n"
    "- 노드는 원자. 하나의 개념 = 하나의 노드.\n"
    '- 1인칭(나/내/저/제) → 항상 "나"(PER.individual)\n'
    "- 3인칭 주어는 나로 치환하지 말 것. 원문 그대로 노드로 추출.\n"
    '- 저장 불필요한 일상 대화 → {"nodes":[],"edges":[]}\n'
    "- 엣지 label은 원문의 조사 그대로 (에서, 으로, 의, 에, 를/을, 와/과 등). 조사 없으면 null.\n\n"
    "카테고리 대분류(17개): PER BOD MND FOD LIV MON WRK TEC EDU LAW TRV NAT CUL HOB SOC REL REG\n\n"
    "예시:\n"
    '입력: "강남세브란스 정형외과 다니고 있어"\n'
    '출력: {"nodes":[{"name":"나","category":"PER.individual"},{"name":"강남세브란스","category":"BOD.medical"},{"name":"정형외과","category":"BOD.medical"}],'
    '"edges":[{"source":"나","label":"에서","target":"강남세브란스"},{"source":"강남세브란스","label":"의","target":"정형외과"}]}\n\n'
    '입력: "박지수가 개발팀장으로 승진했어"\n'
    '출력: {"nodes":[{"name":"박지수","category":"PER.colleague"},{"name":"개발팀장","category":"WRK.role"}],'
    '"edges":[{"source":"박지수","label":"으로","target":"개발팀장"}]}\n\n'
    '입력: "허리디스크 L4-L5 진단받았어"\n'
    '출력: {"nodes":[{"name":"나","category":"PER.individual"},{"name":"허리디스크","category":"BOD.disease"},{"name":"L4-L5","category":"BOD.part"}],'
    '"edges":[{"source":"나","label":null,"target":"허리디스크"},{"source":"허리디스크","label":null,"target":"L4-L5"}]}\n\n'
    '입력: "안녕 잘 지내?"\n'
    '출력: {"nodes":[],"edges":[]}'
)


def load_all_sentences() -> list[str]:
    sentences = []
    for f in sorted(DATA_DIR.glob("task6*.jsonl")):
        if "postposition" in f.name:
            continue
        for line in f.read_text().splitlines():
            line = line.strip()
            if line:
                sentences.append(json.loads(line)["messages"][1]["content"])
    return sentences


def load_done(out_file: pathlib.Path) -> set[str]:
    done = set()
    if out_file.exists():
        for line in out_file.read_text().splitlines():
            if line.strip():
                try:
                    rec = json.loads(line)
                    done.add(rec["messages"][1]["content"])
                except Exception:
                    pass
    return done


def call_claude(sentence: str) -> str:
    result = subprocess.run(
        ["claude", "-p", f"입력: {sentence}"],
        input=SYSTEM,
        capture_output=True, text=True, timeout=60,
        env={**__import__("os").environ, "CLAUDE_CODE_MAX_OUTPUT_TOKENS": "1024"},
    )
    out = result.stdout.strip()
    # JSON 블록만 추출
    m = re.search(r"\{.*\}", out, re.DOTALL)
    if m:
        try:
            json.loads(m.group())
            return m.group()
        except Exception:
            pass
    return '{"nodes":[],"edges":[]}'


def make_record(sentence: str, output: str) -> str:
    return json.dumps({
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": sentence},
            {"role": "assistant", "content": output},
        ]
    }, ensure_ascii=False)


def process_sentence(sentence: str) -> tuple[str, str]:
    output = call_claude(sentence)
    return sentence, output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=5, help="병렬 워커 수")
    args = parser.parse_args()

    out_file = DATA_DIR / "task6_postposition.jsonl"
    sentences = load_all_sentences()
    done = load_done(out_file)

    todo = [s for s in sentences if s not in done]
    total = len(sentences)
    completed = len(done)

    print(f"전체: {total}건 / 완료: {completed}건 / 남은: {len(todo)}건")
    print(f"출력: {out_file}")
    print(f"워커: {args.workers}개 병렬")
    print()

    with open(out_file, "a", encoding="utf-8") as fp:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_sentence, s): s for s in todo}
            for i, future in enumerate(as_completed(futures), 1):
                sentence, output = future.result()
                fp.write(make_record(sentence, output) + "\n")
                fp.flush()
                completed += 1
                if i % 20 == 0 or i <= 3:
                    print(f"  [{completed}/{total}] {sentence[:50]}")

    print(f"\n완료. 총 {completed}건 → {out_file}")


if __name__ == "__main__":
    main()
