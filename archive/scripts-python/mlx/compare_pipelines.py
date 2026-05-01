"""Pipeline A (현재 BFS+filter) vs Pipeline B (sentence 직접) 비교.

DB: /tmp/synapse_verify_db/synapse.db (build_verify_db.py로 구축한 검증 DB)
질문: retrieve-expand valid.jsonl 중 DB와 맥락 맞는 것 선별

측정:
- LLM 호출 수 (approximate; A는 retrieve_expand 1회 + filter N회 + chat 1회)
- 총 소요 시간
- 답변 내용 (정성 비교)
- 컨텍스트로 사용된 증거 (A=triples, B=sentences)

사용:
  python scripts/mlx/compare_pipelines.py               # 기본 10건
  python scripts/mlx/compare_pipelines.py --questions "허리 어때?,요즘 뭐 해?"
"""
from __future__ import annotations
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.environ.setdefault("SYNAPSE_DATA_DIR", "/tmp/synapse_verify_db")
sys.path.insert(0, str(ROOT))

from engine.retrieve import retrieve as retrieve_a
from scripts.mlx.retrieve_b_sentence import retrieve_b


def select_test_questions(conn, n: int = 10) -> list[str]:
    """valid.jsonl에서 DB에 있는 노드 이름을 포함하는 질문 우선 선별."""
    valid_file = ROOT / "data/finetune/tasks/retrieve-expand/valid.jsonl"
    active_names = {r["name"] for r in conn.execute("SELECT name FROM nodes WHERE status='active'")}
    alias_map = {r["alias"]: r["node_id"] for r in conn.execute("SELECT alias, node_id FROM aliases")}

    scored = []
    with valid_file.open() as f:
        for line in f:
            d = json.loads(line)
            u = next(m["content"] for m in d["messages"] if m["role"] == "user")
            q = u.replace("질문:", "").strip()
            # 매칭 점수: 노드 이름 직접 포함 + 별칭 포함
            hit = sum(1 for n in active_names if n and n in q)
            hit += sum(1 for a in alias_map if a and a in q)
            scored.append((hit, q))

    scored.sort(key=lambda x: -x[0])
    # 매칭 있는 것만 top-n; 부족하면 나머지 무작위 보충
    hits = [q for h, q in scored if h > 0]
    if len(hits) >= n:
        return hits[:n]
    extra = [q for h, q in scored if h == 0][: n - len(hits)]
    return hits + extra


def summarize_a(result) -> dict:
    return {
        "pipeline": "A (BFS+filter)",
        "start_nodes": result.start_nodes,
        "context_triples": [str(t) for t in result.context_triples],
        "answer": result.answer,
        "evidence_count": len(result.context_triples),
    }


def summarize_b(result) -> dict:
    return {
        "pipeline": "B (sentence)",
        "start_nodes": result.start_nodes,
        "context_sentences": result.sentences,
        "answer": result.answer,
        "evidence_count": len(result.sentences),
        "llm_calls": result.llm_calls,
        "elapsed_sec": result.elapsed_sec,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", type=int, default=10)
    ap.add_argument("--questions", help="쉼표 구분 직접 지정")
    ap.add_argument("--out", default="/tmp/pipeline_compare.json")
    args = ap.parse_args()

    from engine.db import get_connection
    conn = get_connection()

    if args.questions:
        questions = [q.strip() for q in args.questions.split(",") if q.strip()]
    else:
        questions = select_test_questions(conn, n=args.n)

    print(f"테스트 질문 {len(questions)}건\n")

    results = []
    for i, q in enumerate(questions):
        print(f"\n{'='*70}\n[{i+1}/{len(questions)}] {q}\n{'='*70}")

        # A
        print("  [A 실행 중...]")
        t0 = time.time()
        a = retrieve_a(q)
        a_time = time.time() - t0
        # retrieve_a는 내부적으로 LLM 여러 번 호출; 정확한 수는 로그/측정 필요
        a_summary = summarize_a(a)
        a_summary["elapsed_sec"] = a_time
        print(f"    시간 {a_time:.1f}s  증거 {a_summary['evidence_count']}개  노드 {len(a_summary['start_nodes'])}")

        # B
        print("  [B 실행 중...]")
        b = retrieve_b(q)
        b_summary = summarize_b(b)
        print(f"    시간 {b.elapsed_sec:.1f}s  증거 {b_summary['evidence_count']}개  노드 {len(b_summary['start_nodes'])}")

        print(f"\n  A 답변: {a_summary['answer']}\n")
        print(f"  B 답변: {b_summary['answer']}\n")

        results.append({"question": q, "A": a_summary, "B": b_summary})

    # 저장
    with open(args.out, "w") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 총합
    print(f"\n{'='*70}\n요약\n{'='*70}")
    a_total = sum(r["A"]["elapsed_sec"] for r in results)
    b_total = sum(r["B"]["elapsed_sec"] for r in results)
    a_evid = sum(r["A"]["evidence_count"] for r in results)
    b_evid = sum(r["B"]["evidence_count"] for r in results)
    print(f"총 {len(results)}건")
    print(f"  A 누적 {a_total:.1f}s  (평균 {a_total/len(results):.1f}s/건)  증거 {a_evid}개")
    print(f"  B 누적 {b_total:.1f}s  (평균 {b_total/len(results):.1f}s/건)  증거 {b_evid}개")
    print(f"  속도 비: A/B = {a_total/max(b_total, 0.01):.1f}x")
    print(f"\n결과 저장: {args.out}")


if __name__ == "__main__":
    main()
