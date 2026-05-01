"""하이브리드 retrieve PoC.

기존 /tmp/synapse_verify_db 사용.
임베딩 컬럼 추가 → 기존 노드/문장 embed 계산 → 하이브리드 retrieve 구현 → A/B 비교.

임베딩 모델: intfloat/multilingual-e5-small (384dim)
  - query 입력 시 "query: ..." prefix
  - passage 입력 시 "passage: ..." prefix
  - 이 모델의 학습 규약
"""
from __future__ import annotations
import argparse
import json
import os
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np
from sentence_transformers import SentenceTransformer

os.environ.setdefault("SYNAPSE_DATA_DIR", "/tmp/synapse_verify_db")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine.db import get_connection
from engine.llm import chat, SYSTEM_CHAT, mlx_chat
from engine.retrieve import retrieve as retrieve_a, _match_start_nodes, _get_triples

# ── 임베딩 모델 ──────────────────────────────────────────
_EMB_MODEL: Optional[SentenceTransformer] = None


def get_embedder() -> SentenceTransformer:
    global _EMB_MODEL
    if _EMB_MODEL is None:
        _EMB_MODEL = SentenceTransformer("intfloat/multilingual-e5-small")
    return _EMB_MODEL


def embed_query(text: str) -> np.ndarray:
    return get_embedder().encode(f"query: {text}", normalize_embeddings=True)


def embed_passage(text: str) -> np.ndarray:
    return get_embedder().encode(f"passage: {text}", normalize_embeddings=True)


def embed_batch_passages(texts: list[str]) -> np.ndarray:
    return get_embedder().encode(
        [f"passage: {t}" for t in texts],
        normalize_embeddings=True,
        batch_size=32,
    )


# ── 스키마 마이그레이션 + 임베딩 계산 ─────────────────────
def ensure_embedding_columns(conn: sqlite3.Connection):
    """nodes, sentences에 embedding BLOB 컬럼 추가 (없으면)."""
    cols_nodes = {r[1] for r in conn.execute("PRAGMA table_info(nodes)")}
    if "embedding" not in cols_nodes:
        conn.execute("ALTER TABLE nodes ADD COLUMN embedding BLOB")
    cols_sent = {r[1] for r in conn.execute("PRAGMA table_info(sentences)")}
    if "embedding" not in cols_sent:
        conn.execute("ALTER TABLE sentences ADD COLUMN embedding BLOB")
    conn.commit()


def compute_missing_embeddings(conn: sqlite3.Connection):
    """embedding 없는 노드/문장 batch 계산."""
    # 노드
    rows = list(conn.execute("SELECT id, name FROM nodes WHERE embedding IS NULL AND status = 'active'"))
    if rows:
        print(f"  노드 임베딩 계산 {len(rows)}건...")
        ids = [r[0] for r in rows]
        names = [r[1] for r in rows]
        vecs = embed_batch_passages(names)
        for i, vec in zip(ids, vecs):
            conn.execute("UPDATE nodes SET embedding = ? WHERE id = ?",
                         (vec.astype(np.float16).tobytes(), i))
        conn.commit()

    # 문장
    rows = list(conn.execute("SELECT id, text FROM sentences WHERE embedding IS NULL AND role = 'user'"))
    if rows:
        print(f"  문장 임베딩 계산 {len(rows)}건...")
        ids = [r[0] for r in rows]
        texts = [r[1] for r in rows]
        vecs = embed_batch_passages(texts)
        for i, vec in zip(ids, vecs):
            conn.execute("UPDATE sentences SET embedding = ? WHERE id = ?",
                         (vec.astype(np.float16).tobytes(), i))
        conn.commit()


def load_node_embeddings(conn: sqlite3.Connection) -> tuple[np.ndarray, list[tuple[int, str]]]:
    """(vectors, [(id, name)...]) 반환."""
    rows = list(conn.execute(
        "SELECT id, name, embedding FROM nodes WHERE embedding IS NOT NULL AND status='active'"))
    if not rows:
        return np.zeros((0, 384), dtype=np.float16), []
    vectors = np.stack([np.frombuffer(r[2], dtype=np.float16) for r in rows])
    meta = [(r[0], r[1]) for r in rows]
    return vectors, meta


# ── 하이브리드 retrieve (Pipeline B) ────────────────────
@dataclass
class HybridResult:
    start_nodes: list[str] = field(default_factory=list)
    triples_all: list = field(default_factory=list)
    triples_kept: list = field(default_factory=list)
    llm_filter_calls: int = 0
    embedding_calls: int = 0
    answer: Optional[str] = None
    elapsed_sec: float = 0.0


def hybrid_retrieve(
    question: str,
    conn: sqlite3.Connection,
    top_k_seed: int = 5,
    pre_threshold_pass: float = 0.65,
    pre_threshold_reject: float = 0.35,
    max_triples: int = 20,
) -> HybridResult:
    t0 = time.time()
    result = HybridResult()

    # 1) 질문 embed → 시드 노드 top-K (임베딩 매칭)
    q_vec = embed_query(question)
    result.embedding_calls += 1
    node_vecs, node_meta = load_node_embeddings(conn)
    if len(node_vecs) == 0:
        result.elapsed_sec = time.time() - t0
        return result
    sims = node_vecs @ q_vec
    top_idx = np.argsort(-sims)[:top_k_seed]
    seed_node_ids = []
    for idx in top_idx:
        if sims[idx] > 0.4:  # 너무 낮은 건 노이즈
            seed_node_ids.append(node_meta[idx][0])
            result.start_nodes.append(f"{node_meta[idx][1]} ({sims[idx]:.2f})")

    # fallback: aliases/substring 매칭 (A 파이프라인 로직)
    if not seed_node_ids:
        matched = _match_start_nodes(conn, [question], question=question)
        seed_node_ids = list(matched.values())
        result.start_nodes = list(matched.keys())

    if not seed_node_ids:
        result.answer = chat(SYSTEM_CHAT, question, max_tokens=512)
        result.elapsed_sec = time.time() - t0
        return result

    # 2) BFS (1-hop만, 확장 제어 간소화)
    triples = _get_triples(conn, set(seed_node_ids))
    result.triples_all = triples[:max_triples]

    if not triples:
        result.answer = chat(SYSTEM_CHAT, question, max_tokens=512)
        result.elapsed_sec = time.time() - t0
        return result

    # 3) 임베딩 pre-filter: 트리플을 "src label tgt" 문자열로 embed → 질문과 유사도
    triple_strs = [str(t) for t in result.triples_all]
    triple_vecs = embed_batch_passages(triple_strs)
    result.embedding_calls += 1
    tri_sims = triple_vecs @ q_vec

    # 명백 pass / reject / 애매
    kept = []
    ambiguous = []
    for t, s in zip(result.triples_all, tri_sims):
        if s >= pre_threshold_pass:
            kept.append((t, s, "pass_by_embed"))
        elif s <= pre_threshold_reject:
            pass  # reject
        else:
            ambiguous.append((t, s))

    # 4) 애매한 것만 LLM filter (소수)
    for t, s in ambiguous[:5]:  # 최대 5건만
        user = f"질문: {question}\n트리플: {t}"
        try:
            out = mlx_chat("retrieve-filter", user, max_tokens=8).strip().lower()
            result.llm_filter_calls += 1
            if "pass" in out:
                kept.append((t, s, "pass_by_llm"))
        except Exception:
            pass

    result.triples_kept = [(str(t), round(float(s), 3), tag) for t, s, tag in kept]

    # 5) chat로 최종 답변
    if kept:
        ctx = "\n".join(f"- {t}" for t, _, _ in kept)
        user_content = f"아래는 관련 트리플입니다:\n{ctx}\n\n질문: {question}"
    else:
        user_content = question
    result.answer = chat(SYSTEM_CHAT, user_content, max_tokens=512)

    result.elapsed_sec = time.time() - t0
    return result


# ── 비교 실행 ────────────────────────────────────────────
DEFAULT_QUESTIONS = [
    "요즘 허리 상태 어때?",
    "내 약 뭐 먹고 있더라?",
    "민수는 요즘 어때?",
    "적금 만기 언제였지?",
    "할머니 어디 계셔?",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--questions", help="쉼표 구분 직접 지정")
    ap.add_argument("-n", type=int, default=5)
    args = ap.parse_args()

    print("임베딩 모델 로드...")
    get_embedder()

    conn = get_connection()
    print("스키마 확인 + 임베딩 계산...")
    ensure_embedding_columns(conn)
    compute_missing_embeddings(conn)

    # 통계
    n_nodes = conn.execute("SELECT COUNT(*) FROM nodes WHERE embedding IS NOT NULL").fetchone()[0]
    n_sents = conn.execute("SELECT COUNT(*) FROM sentences WHERE embedding IS NOT NULL").fetchone()[0]
    print(f"  임베딩 있는 노드: {n_nodes}, 문장: {n_sents}")

    questions = [q.strip() for q in (args.questions or "").split(",") if q.strip()] or DEFAULT_QUESTIONS[:args.n]

    print(f"\n테스트 질문 {len(questions)}건\n")
    for i, q in enumerate(questions):
        print("=" * 70)
        print(f"[{i+1}] {q}")
        print("=" * 70)

        # A (현재)
        print("\n  [A 현재 파이프라인]")
        t0 = time.time()
        a = retrieve_a(q)
        a_time = time.time() - t0
        print(f"    시간 {a_time:.1f}s  시작노드 {a.start_nodes}  증거 {len(a.context_triples)}개")
        print(f"    답변: {a.answer}")

        # B (하이브리드)
        print("\n  [B 하이브리드]")
        b = hybrid_retrieve(q, conn)
        print(f"    시간 {b.elapsed_sec:.1f}s  LLM filter {b.llm_filter_calls}회  embed {b.embedding_calls}회")
        print(f"    시작노드 {b.start_nodes}")
        print(f"    증거 {len(b.triples_kept)}개:")
        for s, sim, tag in b.triples_kept:
            print(f"      [{tag} sim={sim}] {s}")
        print(f"    답변: {b.answer}")
        print()


if __name__ == "__main__":
    main()
