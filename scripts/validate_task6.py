"""Task 6 v2 파인튜닝 데이터 전수검사 스크립트.

검사 항목:
  1. retention 필드 누락/비정상값
  2. 비공식 카테고리 (공식 목록 외)
  3. 엣지 source/target이 nodes에 없는 것
  4. "나" 노드가 문장에 1인칭(나/내/저/제) 없는데 생성된 것
  5. deactivate source/target이 current_graph에 없는 것

실행:
  python3 scripts/validate_task6.py                     # 전체 파일
  python3 scripts/validate_task6.py --group b           # 특정 그룹
  python3 scripts/validate_task6.py --file path/to.jsonl  # 특정 파일
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(__file__).parent.parent
DATA_DIR = BASE / "archive/finetune/data"

GROUPS = {
    "a": "task6_v2_a.jsonl",
    "b": "task6_v2_b.jsonl",
    "c": "task6_v2_c.jsonl",
    "d": "task6_v2_d.jsonl",
    "e": "task6_v2_e.jsonl",
}

OFFICIAL: dict[str, set[str]] = {
    "PER": {"individual", "family", "friend", "colleague", "public", "org"},
    "BOD": {"part", "disease", "medical", "exercise", "nutrition", "sleep"},
    "MND": {"emotion", "personality", "mental", "motivation", "coping"},
    "FOD": {"ingredient", "recipe", "restaurant", "drink", "product"},
    "LIV": {"housing", "appliance", "interior", "supply", "maintenance", "moving"},
    "MON": {"income", "spending", "invest", "payment", "loan", "insurance"},
    "WRK": {"workplace", "role", "jobchange", "business", "cert", "tool"},
    "TEC": {"sw", "hw", "ai", "infra", "data", "security"},
    "EDU": {"school", "online", "language", "academic", "reading", "exam"},
    "LAW": {"statute", "contract", "admin", "rights", "tax"},
    "TRV": {"domestic", "abroad", "transport", "stay", "flight", "place"},
    "NAT": {"animal", "plant", "weather", "terrain", "ecology", "space"},
    "CUL": {"film", "music", "book", "art", "show", "media"},
    "HOB": {"sport", "outdoor", "game", "craft", "sing", "collect", "social"},
    "SOC": {"politics", "international", "incident", "economy", "issue", "news"},
    "REL": {"romance", "conflict", "comm", "manner", "online"},
    "REG": {"christianity", "buddhism", "catholic", "islam", "other", "practice"},
}

FIRST_PERSON_RE = re.compile(r"(나는|나를|나의|나한테|나도|나만|나도|내가|내 |내가|저는|저를|저의|저한테|저도|제가|제 |나[가은이]?[ ,]|저[는을의]?[ ,])")


def is_official_category(cat: str) -> bool:
    if not cat:
        return True  # NULL 허용
    parts = cat.split(".")
    if len(parts) != 2:
        return False
    major, minor = parts
    return major in OFFICIAL and minor in OFFICIAL[major]


def validate_record(rec: dict, line_no: int) -> list[str]:
    errors = []

    try:
        messages = rec["messages"]
        system_msg = messages[0]["content"]
        user_content = messages[1]["content"]
        answer_str = messages[2]["content"]
    except (KeyError, IndexError):
        return [f"L{line_no}: messages 구조 오류"]

    # 문장과 current_graph 파싱
    lines = user_content.split("\n")
    sentence = lines[0].strip() if lines else ""

    current_graph_nodes: set[str] = set()
    for line in lines[1:]:
        m = re.match(r"-\s*(.+?)\s*→\s*(.+)", line)
        if m:
            current_graph_nodes.add(m.group(1).strip())
            current_graph_nodes.add(m.group(2).strip())

    # answer 파싱
    try:
        answer = json.loads(answer_str)
    except json.JSONDecodeError:
        return [f"L{line_no}: answer JSON 파싱 실패"]

    # 1. retention 검사
    retention = answer.get("retention")
    if retention not in ("memory", "daily"):
        errors.append(f"L{line_no}: retention 비정상 ({retention!r}) — '{sentence[:30]}'")

    nodes = answer.get("nodes", [])
    edges = answer.get("edges", [])
    deactivate = answer.get("deactivate", [])

    node_names: set[str] = {n["name"] for n in nodes if isinstance(n, dict) and "name" in n}
    node_names |= current_graph_nodes  # current_graph의 기존 노드도 유효한 참조 대상

    # 2. 비공식 카테고리 검사
    for n in nodes:
        if not isinstance(n, dict):
            continue
        cat = n.get("category")
        if cat and not is_official_category(cat):
            errors.append(f"L{line_no}: 비공식 카테고리 {cat!r} (노드: {n.get('name')!r}) — '{sentence[:30]}'")

    # 3. 엣지 source/target이 nodes에 없는 것
    for e in edges:
        if not isinstance(e, dict):
            continue
        src = e.get("source")
        tgt = e.get("target")
        if src and src not in node_names:
            errors.append(f"L{line_no}: 엣지 source {src!r}가 nodes에 없음 — '{sentence[:30]}'")
        if tgt and tgt not in node_names:
            errors.append(f"L{line_no}: 엣지 target {tgt!r}가 nodes에 없음 — '{sentence[:30]}'")

    # 4. "나" 노드가 문장에 1인칭 없는데 생성된 것 (answer.nodes만 검사, current_graph 제외)
    answer_node_names: set[str] = {n["name"] for n in nodes if isinstance(n, dict) and "name" in n}
    if "나" in answer_node_names:
        if not FIRST_PERSON_RE.search(sentence):
            errors.append(f"L{line_no}: '나' 노드가 있으나 문장에 1인칭 없음 — '{sentence[:50]}'")

    # 5. deactivate source/target이 current_graph에 없는 것
    if deactivate and current_graph_nodes:
        for d in deactivate:
            if not isinstance(d, dict):
                continue
            src = d.get("source")
            tgt = d.get("target")
            if src and src not in current_graph_nodes:
                errors.append(f"L{line_no}: deactivate source {src!r}가 current_graph에 없음 — '{sentence[:30]}'")
            if tgt and tgt not in current_graph_nodes:
                errors.append(f"L{line_no}: deactivate target {tgt!r}가 current_graph에 없음 — '{sentence[:30]}'")

    return errors


def validate_file(path: Path) -> dict:
    if not path.exists():
        print(f"  파일 없음: {path}")
        return {"total": 0, "errors": 0, "error_list": []}

    all_errors = []
    total = 0

    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            all_errors.append(f"L{line_no}: JSON 파싱 실패")
            continue
        total += 1
        all_errors.extend(validate_record(rec, line_no))

    return {"total": total, "errors": len(all_errors), "error_list": all_errors}


def main():
    parser = argparse.ArgumentParser(description="Task 6 v2 전수검사")
    parser.add_argument("--group", choices=list(GROUPS.keys()), help="특정 그룹만 검사")
    parser.add_argument("--file", type=Path, help="특정 파일 직접 지정")
    parser.add_argument("--show-all", action="store_true", help="오류 전체 출력 (기본: 최대 20개)")
    args = parser.parse_args()

    if args.file:
        files = [(args.file.stem, args.file)]
    elif args.group:
        files = [(args.group, DATA_DIR / GROUPS[args.group])]
    else:
        files = [(k, DATA_DIR / v) for k, v in GROUPS.items()]

    total_records = 0
    total_errors = 0

    for name, path in files:
        print(f"\n[{name.upper()}] {path.name}")
        result = validate_file(path)
        total_records += result["total"]
        total_errors += result["errors"]

        if result["total"] == 0:
            continue

        error_rate = result["errors"] / result["total"] * 100
        print(f"  총 {result['total']}건 — 오류 {result['errors']}건 ({error_rate:.1f}%)")

        if result["error_list"]:
            limit = None if args.show_all else 20
            for err in result["error_list"][:limit]:
                print(f"  ❌ {err}")
            if not args.show_all and len(result["error_list"]) > 20:
                print(f"  ... 외 {len(result['error_list']) - 20}건 (--show-all로 전체 확인)")
        else:
            print("  ✅ 오류 없음")

    if len(files) > 1:
        print(f"\n{'='*50}")
        print(f"전체: {total_records}건 — 오류 {total_errors}건")
        if total_records > 0:
            print(f"오류율: {total_errors / total_records * 100:.1f}%")


if __name__ == "__main__":
    main()
