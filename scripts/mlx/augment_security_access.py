#!/usr/bin/env python3
"""security-access 데이터 증강 스크립트 (준비만, 실행 시 LLM 호출).

현재 분포 (2026-04-15 기준):
  result:   safe 34% / confirm 34% / reject 32%  (균형)
  권한:     employee 41% / team_lead 31% / hr 20% / executive 8%  (executive 부족)

증강 목표:
  - executive 권한 샘플을 50건 → 150건 수준으로 증강
  - 각 (권한 × result) 조합에 최소 15건 확보
  - 총 269 → 600건 목표

단계:
  audit     - 현재 (권한 × result) 교차표 출력 → aug_target.txt에 필요 증강 수 저장
  generate  - 부족 조합별 샘플 생성 → aug_raw.jsonl (수동 검증 필요)
  merge     - 검증 통과본 → tasks/security-access/train.jsonl

사용 예:
  python scripts/mlx/augment_security_access.py audit
  python scripts/mlx/augment_security_access.py generate --target-per-cell 15
  # 수동 검증: aug_raw.jsonl → aug_verified.jsonl
  python scripts/mlx/augment_security_access.py merge
"""
import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK_DIR = ROOT / "data/finetune/tasks/security-access"
AUG_DIR = ROOT / "data/finetune/aug/security-access"
MLX_URL = "http://localhost:8765/v1/chat/completions"

PERMS = ["employee", "team_lead", "hr", "executive"]
RESULTS = ["safe", "confirm", "reject"]

GENERATE_SYSTEM = """당신은 조직 지식 그래프 보안 학습 데이터 생성기다.
주어진 (질의자 권한, 기대 결과) 조합에 맞는 현실적인 질문·컨텍스트를 만들어라.

출력 형식 (JSON 1줄):
{
  "question": "질문 문장",
  "permission": "employee|team_lead|hr|executive",
  "context": [
    {"marking": "safe|sensitive:performance|sensitive:personal_info|sensitive:trade_secret|sensitive:internal_decision|sensitive:client_confidential|sensitive:legal_risk", "triple": "주체 →(관계)→ 대상"},
    ...
  ],
  "answer": {"result": "safe|confirm|reject", "message": "..." }
}

규칙:
- context는 4~8개 트리플, 5A 마킹 포함
- result가 safe면 message 필드 생략
- result가 confirm이면 message는 어떤 민감정보가 섞였는지 간결하게 안내
- result가 reject면 왜 거절하는지 권한 기준으로 설명
- 트리플 주체는 가상 인물명 (김민수·박지현 등) 또는 가상 프로젝트명"""


def parse_record(d: dict) -> dict:
    user = next(m["content"] for m in d["messages"] if m["role"] == "user")
    ast = next(m["content"] for m in d["messages"] if m["role"] == "assistant")
    m = re.search(r"질의자 권한:\s*(\S+)", user)
    perm = m.group(1) if m else "?"
    try:
        ans = json.loads(ast)
        result = ans.get("result", "?")
    except Exception:
        result = "?"
    return {"perm": perm, "result": result, "user": user, "ast": ast, "raw": d}


def load_records() -> list[dict]:
    items = []
    with (TASK_DIR / "train.jsonl").open() as f:
        for line in f:
            items.append(parse_record(json.loads(line)))
    return items


def cmd_audit(_args) -> None:
    AUG_DIR.mkdir(parents=True, exist_ok=True)
    recs = load_records()
    table: dict[tuple, int] = Counter((r["perm"], r["result"]) for r in recs)
    print(f"{'권한':12s}" + "".join(f"{r:>10s}" for r in RESULTS) + "  total")
    print("-" * 56)
    for p in PERMS:
        row = [table[(p, r)] for r in RESULTS]
        total = sum(row)
        print(f"{p:12s}" + "".join(f"{v:>10d}" for v in row) + f"  {total:5d}")
    totals = [sum(table[(p, r)] for p in PERMS) for r in RESULTS]
    print("-" * 56)
    print(f"{'total':12s}" + "".join(f"{v:>10d}" for v in totals) + f"  {sum(totals):5d}")


def cmd_generate(args) -> None:
    import urllib.request

    recs = load_records()
    by_cell = defaultdict(list)
    for r in recs:
        by_cell[(r["perm"], r["result"])].append(r)

    out = AUG_DIR / "aug_raw.jsonl"
    AUG_DIR.mkdir(parents=True, exist_ok=True)
    need: list[tuple] = []
    for p in PERMS:
        for res in RESULTS:
            have = len(by_cell[(p, res)])
            deficit = max(0, args.target_per_cell - have)
            if deficit:
                need.append((p, res, deficit))
                print(f"  {p}×{res}: {have} → +{deficit}")
    if not need:
        print("모든 셀이 목표 충족. 생성 불필요.")
        return

    def mlx_chat(system: str, user: str) -> str:
        req = urllib.request.Request(
            MLX_URL,
            data=json.dumps({
                "model": "synapse/security-access",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.5,
                "max_tokens": 512,
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"].strip()

    with out.open("w") as f:
        for p, res, count in need:
            seeds = by_cell[(p, res)] or []
            for i in range(count):
                exemplars_str = ""
                if seeds:
                    exemplars = random.sample(seeds, min(2, len(seeds)))
                    exemplars_str = "\n\n참고 예시:\n" + "\n---\n".join(
                        f"{e['user']}\n→ {e['ast']}" for e in exemplars
                    )
                prompt = f"조합: permission={p}, expected_result={res}{exemplars_str}\n\n위 조합에 맞는 새 샘플 1건을 JSON으로 생성."
                try:
                    raw = mlx_chat(GENERATE_SYSTEM, prompt)
                    d = json.loads(raw)
                    d["_target_perm"] = p
                    d["_target_result"] = res
                    f.write(json.dumps(d, ensure_ascii=False) + "\n")
                except Exception as e:
                    print(f"    [warn] {p}×{res} #{i}: {e}", file=sys.stderr)
                if (i + 1) % 10 == 0:
                    print(f"    {p}×{res} {i+1}/{count}", flush=True)
    print(f"\n저장: {out}")
    print("다음 단계: aug_raw.jsonl 수동 검증 → aug_verified.jsonl → merge")


def cmd_merge(_args) -> None:
    verified = AUG_DIR / "aug_verified.jsonl"
    if not verified.exists():
        sys.exit(f"검증 파일 없음: {verified}")
    target = TASK_DIR / "train.jsonl"
    system_prompt = None
    before = 0
    with target.open() as f:
        for line in f:
            before += 1
            if system_prompt is None:
                d = json.loads(line)
                system_prompt = next(m["content"] for m in d["messages"] if m["role"] == "system")
    added = 0
    with target.open("a") as out, verified.open() as vf:
        for line in vf:
            d = json.loads(line)
            ctx_lines = "\n".join(f"- [{t['marking']}] {t['triple']}" for t in d["context"])
            user_content = (
                f"질문: {d['question']}\n"
                f"질의자 권한: {d['permission']}\n"
                f"컨텍스트:\n{ctx_lines}"
            )
            answer = d["answer"]
            if answer.get("result") == "safe":
                answer = {"result": "safe"}
            record = {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": json.dumps(answer, ensure_ascii=False)},
                ]
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            added += 1
    print(f"병합 완료: {before} → {before + added} (+{added})")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("audit")
    g = sub.add_parser("generate")
    g.add_argument("--target-per-cell", type=int, default=15)
    sub.add_parser("merge")
    args = ap.parse_args()
    {"audit": cmd_audit, "generate": cmd_generate, "merge": cmd_merge}[args.cmd](args)


if __name__ == "__main__":
    main()
