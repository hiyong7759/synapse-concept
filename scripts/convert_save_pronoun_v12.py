#!/usr/bin/env python3
"""save-pronoun 학습 데이터 v12 전환.

변경:
- 직전 대화/맥락 라인 제거 (세션리스)
- 시간부사(오늘/어제/내일/그저께/모레/X요일)는 "날짜:" 기준으로 ISO 치환 → tokens
- 맥락 의존 치환(인물·사물 등)은 폐기 → 원문 유지
- 치환 불가 지시어는 LLM이 감지하지 않음 (save.py가 저장 시 정규식 매칭 → unresolved_tokens INSERT)
- LLM 출력: {text, tokens} 또는 {question}. unresolved 필드 없음.
- 시스템 프롬프트를 v12로 교체

사용:
  python3 scripts/convert_save_pronoun_v12.py           # tmp 파일만 생성 (*.v12)
  python3 scripts/convert_save_pronoun_v12.py --apply   # 원본 덮어쓰기
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "finetune" / "tasks" / "save-pronoun"

NEW_SYSTEM_PROMPT = """당신은 지식 그래프 저장 엔진입니다.
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

# 지시어·시간 모호 부사·지시부사·장소부사 사전. save.py가 저장 시 정규식 매칭해 unresolved_tokens에 INSERT.
# 빈도/정도 부사(자주/많이 등)는 지시적 의미가 없어 제외.
AMBIGUOUS_TOKENS = [
    # 2단어 지시
    "그 양반", "이 양반", "저 양반",
    "그 사람", "이 사람", "저 사람",
    "그 친구", "이 친구", "저 친구",
    "그 분", "이 분", "저 분",
    # 1단어 지시대명사 (조사 포함 변형)
    "이거", "그거", "저거", "이것", "그것", "저것",
    "이게", "그게", "저게",
    "이놈", "그놈", "저놈",
    "이분", "그분", "저분",
    "이쪽", "그쪽", "저쪽",
    # 지시부사
    "이렇게", "그렇게", "저렇게",
    # 인물 지시
    "걔", "얘", "쟤",
    # 장소부사
    "여기", "거기", "저기", "이곳", "그곳", "저곳",
    # 시간 모호 부사 (ISO 환산 불가)
    "이때", "그때", "저때",
    "요즘", "최근", "예전", "옛날", "나중", "조만간", "방금", "얼마전", "언젠가",
]
AMBIGUOUS_SORTED = sorted(AMBIGUOUS_TOKENS, key=len, reverse=True)

# 시간부사 치환표
SIMPLE_TIME_DELTAS = {
    "그저께": -2, "어제": -1, "오늘": 0, "내일": 1, "모레": 2,
}
WEEKDAYS_KO = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}

ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
WEEK_PATTERN = re.compile(r"(이번\s?주|지난\s?주|다음\s?주)\s?(월|화|수|목|금|토|일)요일")


def has_ambiguous_token(text: str) -> bool:
    """입력 본문에 모호 토큰(지시어·지시부사·시간모호·장소부사)이 있는지."""
    for tok in AMBIGUOUS_SORTED:
        if tok in text:
            return True
    return False


def compute_time_subs(text: str, base: date) -> list[tuple[int, int, str]]:
    """시간부사 → (start, end, ISO 날짜) 목록."""
    subs: list[tuple[int, int, str]] = []
    for word in sorted(SIMPLE_TIME_DELTAS.keys(), key=len, reverse=True):
        delta = SIMPLE_TIME_DELTAS[word]
        for m in re.finditer(re.escape(word), text):
            new_d = base + timedelta(days=delta)
            subs.append((m.start(), m.end(), new_d.isoformat()))
    for m in WEEK_PATTERN.finditer(text):
        week_word = m.group(1).replace(" ", "")
        weekday_char = m.group(2)
        target_weekday = WEEKDAYS_KO[weekday_char]
        base_monday = base - timedelta(days=base.weekday())
        if week_word == "지난주":
            base_monday -= timedelta(days=7)
        elif week_word == "다음주":
            base_monday += timedelta(days=7)
        new_d = base_monday + timedelta(days=target_weekday)
        subs.append((m.start(), m.end(), new_d.isoformat()))
    return subs


def apply_subs(text: str, subs: list[tuple[int, int, str]]) -> tuple[str, list[str]]:
    """뒤에서부터 치환. 반환: (치환된 텍스트, 적용된 ISO 날짜 목록 — 출현 순서)."""
    subs_sorted = sorted(subs, key=lambda x: x[0], reverse=True)
    applied: list[tuple[int, int, str]] = []
    result = text
    for start, end, repl in subs_sorted:
        if any(not (end <= s or start >= e) for s, e, _ in applied):
            continue
        result = result[:start] + repl + result[end:]
        applied.append((start, end, repl))
    applied_in_order = sorted(applied, key=lambda x: x[0])
    isos: list[str] = []
    for _, _, iso in applied_in_order:
        if iso not in isos:
            isos.append(iso)
    return result, isos


def parse_user_content(user: str) -> tuple[str, str | None]:
    """user content에서 입력 본문과 날짜 라인만 추출."""
    lines = user.split("\n")
    input_text = None
    date_line = None
    for line in lines:
        if line.startswith("입력:"):
            input_text = line[len("입력:"):].strip()
        elif line.startswith("날짜:"):
            date_line = line.strip()
    return input_text or user, date_line


def parse_base_date(date_line: str | None) -> date | None:
    if not date_line:
        return None
    m = ISO_DATE_RE.search(date_line)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group())
    except ValueError:
        return None


def build_new_user(input_text: str, date_line: str | None) -> str:
    if date_line:
        return f"입력: {input_text}\n{date_line}"
    return f"입력: {input_text}"


def transform_record(record: dict) -> dict:
    messages = record["messages"]
    user = messages[1]["content"]
    asst = json.loads(messages[2]["content"])

    input_text, date_line = parse_user_content(user)
    base_date = parse_base_date(date_line)

    if "question" in asst:
        # 모호 토큰이 있으면 원문 그대로 반환 (save.py가 unresolved_tokens에 기록).
        # 모호 토큰조차 없는 완전 모호 케이스만 question 유지.
        if has_ambiguous_token(input_text):
            new_asst: dict = {"text": input_text, "tokens": []}
        else:
            new_asst = {"question": asst["question"]}
    else:
        if base_date:
            time_subs = compute_time_subs(input_text, base_date)
            new_text, isos = apply_subs(input_text, time_subs)
        else:
            new_text, isos = input_text, []
        tokens = [{"name": iso, "category": "시간"} for iso in isos]
        new_asst = {"text": new_text, "tokens": tokens}

    new_user = build_new_user(input_text, date_line)
    return {
        "messages": [
            {"role": "system", "content": NEW_SYSTEM_PROMPT},
            {"role": "user", "content": new_user},
            {"role": "assistant", "content": json.dumps(new_asst, ensure_ascii=False)},
        ]
    }


def transform_file(src: Path, dst: Path) -> dict:
    stats = {"total": 0, "question_kept": 0, "tokens_only": 0, "text_only": 0}
    with src.open() as fin, dst.open("w") as fout:
        for line in fin:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            new_record = transform_record(record)
            payload = json.loads(new_record["messages"][-1]["content"])
            stats["total"] += 1
            if "question" in payload:
                stats["question_kept"] += 1
            elif payload.get("tokens"):
                stats["tokens_only"] += 1
            else:
                stats["text_only"] += 1
            fout.write(json.dumps(new_record, ensure_ascii=False) + "\n")
    return stats


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="overwrite original files")
    args = ap.parse_args()

    for name in ("train.jsonl", "valid.jsonl"):
        src = DATA_DIR / name
        tmp = DATA_DIR / f"{name}.v12"
        stats = transform_file(src, tmp)
        print(f"{name}: {stats}")
        if args.apply:
            tmp.replace(src)
            print(f"  -> applied to {src}")
        else:
            print(f"  -> tmp only: {tmp}")


if __name__ == "__main__":
    main()
