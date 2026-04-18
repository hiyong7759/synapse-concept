"""Pipeline B: sentence-based 인출.

질문 → 주체 노드 매칭(규칙 기반) → 해당 노드들과 연결된 sentences → chat
- retrieve-expand LLM 호출 없음
- retrieve-filter LLM 호출 없음
- BFS 없음
- LLM 호출: chat 1회만

A 파이프라인 대비 대조군.

사용:
  from scripts.mlx.retrieve_b_sentence import retrieve_b
  result = retrieve_b("허리 어때?")
"""
from __future__ import annotations
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine.db import get_connection
from engine.llm import chat, SYSTEM_CHAT
from engine.retrieve import _match_start_nodes


@dataclass
class SentenceBasedResult:
    start_nodes: list[str] = field(default_factory=list)
    sentences: list[str] = field(default_factory=list)
    answer: Optional[str] = None
    llm_calls: int = 0
    elapsed_sec: float = 0.0


def _simple_keyword_split(question: str) -> list[str]:
    """규칙 기반 간단 키워드 추출: 공백·구두점 분리 + 어미 제거.
    LLM 없이 처리하므로 매우 단순. 노드 매칭은 matched_start_nodes가 aliases/substring으로 보완."""
    import re
    # 한글/영문/숫자 연속만 추출
    tokens = re.findall(r"[가-힣A-Za-z0-9]+", question)
    # 너무 짧은 건 제외
    return [t for t in tokens if len(t) >= 2]


def _fetch_linked_sentences(conn, node_ids: set[int], top_k: int = 10) -> list[tuple[int, str]]:
    """해당 노드들에 연결된(source 또는 target) 엣지의 sentence_id 수집 → sentences 조회.
    최신순 top_k. (sentence_id, text) 반환."""
    if not node_ids:
        return []
    placeholders = ",".join("?" * len(node_ids))
    rows = conn.execute(
        f"""
        SELECT DISTINCT s.id, s.text, s.created_at
        FROM sentences s
        JOIN edges e ON e.sentence_id = s.id
        WHERE (e.source_node_id IN ({placeholders})
            OR e.target_node_id IN ({placeholders}))
          AND s.role = 'user'
        ORDER BY s.created_at DESC
        LIMIT ?
        """,
        (*node_ids, *node_ids, top_k),
    ).fetchall()
    return [(r["id"], r["text"]) for r in rows]


def retrieve_b(question: str, db_path: str | None = None, top_k: int = 10) -> SentenceBasedResult:
    t0 = time.time()
    result = SentenceBasedResult()

    conn = get_connection() if db_path is None else get_connection(db_path)
    try:
        # 1) 질문 → 키워드 (규칙 기반)
        keywords = _simple_keyword_split(question)

        # 2) 키워드 → 노드 매칭 (A 파이프라인 로직 재사용)
        matched = _match_start_nodes(conn, keywords, question=question)
        result.start_nodes = list(matched.keys())

        if not matched:
            # 매칭 없으면 빈 컨텍스트로 chat
            result.answer = chat(SYSTEM_CHAT, question, max_tokens=512)
            result.llm_calls = 1
            result.elapsed_sec = time.time() - t0
            return result

        # 3) 노드 → 연결 sentences
        node_ids = set(matched.values())
        sentence_pairs = _fetch_linked_sentences(conn, node_ids, top_k=top_k)
        result.sentences = [text for _, text in sentence_pairs]

        if not sentence_pairs:
            result.answer = chat(SYSTEM_CHAT, question, max_tokens=512)
            result.llm_calls = 1
            result.elapsed_sec = time.time() - t0
            return result

        # 4) sentences를 컨텍스트로 chat
        context = "\n".join(f"- {text}" for text in result.sentences)
        user_content = f"아래는 관련된 사실 문장들입니다:\n{context}\n\n질문: {question}"
        result.answer = chat(SYSTEM_CHAT, user_content, max_tokens=512)
        result.llm_calls = 1
    finally:
        conn.close()

    result.elapsed_sec = time.time() - t0
    return result


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("question")
    ap.add_argument("--top-k", type=int, default=10)
    args = ap.parse_args()

    r = retrieve_b(args.question, top_k=args.top_k)
    print(f"start_nodes: {r.start_nodes}")
    print(f"sentences ({len(r.sentences)}):")
    for s in r.sentences:
        print(f"  - {s}")
    print(f"\nllm_calls: {r.llm_calls}")
    print(f"elapsed: {r.elapsed_sec:.2f}s")
    print(f"\nanswer:\n{r.answer}")
