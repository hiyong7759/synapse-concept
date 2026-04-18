"""문장 수준 임베딩만 사용하는 retrieve 테스트.

질문 embed → sentences.embedding top-K → chat
다른 것 없음 (필터·BFS·노드매칭·LLM filter 전부 제외).

목적: sentence 수준 임베딩이 단독으로 노이즈 적게 쓸 만한지 확인.
"""
from __future__ import annotations
import os
import sys
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

os.environ.setdefault("SYNAPSE_DATA_DIR", "/tmp/synapse_verify_db")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from engine.db import get_connection
from engine.llm import chat, SYSTEM_CHAT
from engine.retrieve import retrieve as retrieve_a

_EMB = None


def emb():
    global _EMB
    if _EMB is None:
        _EMB = SentenceTransformer("intfloat/multilingual-e5-small")
    return _EMB


def load_sentence_embeddings(conn: sqlite3.Connection):
    rows = list(conn.execute(
        "SELECT id, text, embedding FROM sentences WHERE embedding IS NOT NULL AND role='user'"
    ))
    vecs = np.stack([np.frombuffer(r[2], dtype=np.float16) for r in rows]).astype(np.float32)
    meta = [(r[0], r[1]) for r in rows]
    return vecs, meta


@dataclass
class SentResult:
    top_sentences: list = field(default_factory=list)
    answer: str = ""
    elapsed_sec: float = 0.0


def retrieve_sentence_only(question: str, conn: sqlite3.Connection, top_k: int = 7) -> SentResult:
    t0 = time.time()
    r = SentResult()
    q_vec = emb().encode(f"query: {question}", normalize_embeddings=True)
    vecs, meta = load_sentence_embeddings(conn)
    if len(vecs) == 0:
        r.answer = chat(SYSTEM_CHAT, question, max_tokens=512)
        r.elapsed_sec = time.time() - t0
        return r
    sims = vecs @ q_vec
    idx = np.argsort(-sims)[:top_k]
    r.top_sentences = [(meta[i][1], float(sims[i])) for i in idx]
    ctx = "\n".join(f"- {text}" for text, _ in r.top_sentences)
    user_content = f"아래는 관련된 사실 문장들입니다:\n{ctx}\n\n질문: {question}"
    r.answer = chat(SYSTEM_CHAT, user_content, max_tokens=512)
    r.elapsed_sec = time.time() - t0
    return r


QUESTIONS = [
    "요즘 허리 상태 어때?",
    "내 약 뭐 먹고 있더라?",
    "민수는 요즘 어때?",
    "적금 만기 언제였지?",
    "할머니 어디 계셔?",
]


def main():
    conn = get_connection()
    print("임베딩 모델 로드...")
    emb()

    for i, q in enumerate(QUESTIONS):
        print(f"\n{'='*70}\n[{i+1}] {q}\n{'='*70}")

        print("\n  [A 현재 파이프라인]")
        t0 = time.time()
        a = retrieve_a(q)
        print(f"    시간 {time.time() - t0:.1f}s  증거 {len(a.context_triples)}개")
        print(f"    답변: {a.answer}")

        print("\n  [S 문장 임베딩 전용]")
        s = retrieve_sentence_only(q, conn)
        print(f"    시간 {s.elapsed_sec:.1f}s  top-{len(s.top_sentences)} 문장:")
        for text, sim in s.top_sentences:
            print(f"      [{sim:.3f}] {text}")
        print(f"    답변: {s.answer}")


if __name__ == "__main__":
    main()
