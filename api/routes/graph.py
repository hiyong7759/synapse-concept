"""Synapse API 라우터.

설계서 기준 통합 파이프라인: 모든 입력 → retrieve → save → respond.
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.save import (
    save, rollback, save_response,
    search_sentences, get_sentence_impact, update_sentence, delete_sentence,
)
from engine.retrieve import retrieve
from engine.db import get_connection, get_stats, DB_PATH
from engine.llm import chat as llm_chat, SYSTEM_IMAGE_EXTRACT, OllamaError

router = APIRouter()

USE_LLM = os.environ.get("USE_LLM", "true").lower() == "true"


# ─── 요청/응답 모델 ───────────────────────────────────────────

class HistoryItem(BaseModel):
    role: str    # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    text: str
    images: list[str] = []          # base64 인코딩 이미지 목록 (멀티모달)
    history: list[HistoryItem] = [] # 이전 대화 (최근 N턴)


class SaveResponseModel(BaseModel):
    triples_added: list[tuple[str, Optional[str], str]]
    edge_ids_added: list[int]
    nodes_added: list[str]
    node_ids_added: list[int]
    edges_deactivated: list[tuple[str, Optional[str], str]]
    aliases_added: list[tuple[str, str]]


class RetrieveResponseModel(BaseModel):
    start_nodes: list[str]
    context_triples: list[tuple[str, Optional[str], str]]


class ChatResponse(BaseModel):
    save: Optional[SaveResponseModel] = None
    retrieve: Optional[RetrieveResponseModel] = None
    answer: Optional[str] = None
    question: Optional[str] = None  # 모호성 되물음


class RollbackRequest(BaseModel):
    edge_ids: list[int] = []
    node_ids: list[int] = []


class RollbackResponse(BaseModel):
    edges_deleted: int
    nodes_deleted: int


class AliasRequest(BaseModel):
    alias: str
    node_name: str


class NodeItem(BaseModel):
    id: int
    name: str
    status: str
    degree: int


class EdgeItem(BaseModel):
    id: int
    source_id: int
    source_name: str
    target_id: int
    target_name: str
    label: Optional[str]


# ─── 엔드포인트 ──────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """통합 파이프라인: retrieve → save → respond.

    CLI cmd_interactive() 로직과 동일한 순서.
    """
    images = req.images if req.images else None
    history = [{"role": h.role, "content": h.content} for h in req.history] or None

    # 이미지 텍스트 추출
    text = req.text
    if images and USE_LLM:
        try:
            prompt = text if text.strip() else "이 이미지에서 정보를 추출해주세요."
            text = llm_chat(SYSTEM_IMAGE_EXTRACT, prompt, images=images, temperature=0, max_tokens=512)
            print(f"[IMAGE EXTRACT]\n{text}\n{'─'*40}")
        except OllamaError:
            pass

    if not text.strip():
        return ChatResponse()

    # ── 1단계: 인출 (retrieve) ──
    r_retrieve = retrieve(text, use_llm=USE_LLM, images=images, history=history)

    # context_sentences: 인출된 트리플에서 원본 문장 추출 (문장 단위 dedup)
    seen_sentences: set[str] = set()
    context_sentences: list[str] = []
    for t in r_retrieve.context_triples:
        if t.sentence_text and t.sentence_text not in seen_sentences:
            seen_sentences.add(t.sentence_text)
            context_sentences.append(t.sentence_text)

    # ── 2단계: 저장 (save) ──
    r_save = save(text, use_llm=USE_LLM, context_sentences=context_sentences or None)

    # 모호성 되물음 → 저장/응답 중단, 질문만 반환
    if r_save.question:
        return ChatResponse(question=r_save.question)

    # ── 3단계: 응답 구성 ──
    save_model = SaveResponseModel(
        triples_added=r_save.triples_added,
        edge_ids_added=r_save.edge_ids_added,
        nodes_added=r_save.nodes_added,
        node_ids_added=r_save.node_ids_added,
        edges_deactivated=r_save.edges_deactivated,
        aliases_added=r_save.aliases_added,
    )

    retrieve_model = RetrieveResponseModel(
        start_nodes=r_retrieve.start_nodes,
        context_triples=[(t.src, t.label, t.tgt) for t in r_retrieve.context_triples],
    )

    answer = r_retrieve.answer

    # assistant 응답을 sentences에 저장
    if answer:
        save_response(answer)

    return ChatResponse(
        save=save_model,
        retrieve=retrieve_model,
        answer=answer,
    )


@router.post("/rollback", response_model=RollbackResponse)
def rollback_route(req: RollbackRequest):
    result = rollback(req.edge_ids, req.node_ids)
    return RollbackResponse(
        edges_deleted=result["edges_deleted"],
        nodes_deleted=result["nodes_deleted"],
    )


@router.get("/stats")
def stats():
    return get_stats()


@router.get("/nodes", response_model=list[NodeItem])
def nodes():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                n.id,
                n.name,
                n.status,
                COUNT(e.id) AS degree
            FROM nodes n
            LEFT JOIN edges e
                ON e.source_node_id = n.id OR e.target_node_id = n.id
            WHERE n.status = 'active'
            GROUP BY n.id
            ORDER BY degree DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return [NodeItem(id=r["id"], name=r["name"], status=r["status"], degree=r["degree"]) for r in rows]


@router.get("/edges", response_model=list[EdgeItem])
def edges():
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                e.id,
                e.source_node_id AS source_id,
                n1.name          AS source_name,
                e.target_node_id AS target_id,
                n2.name          AS target_name,
                e.label
            FROM edges e
            JOIN nodes n1 ON n1.id = e.source_node_id
            JOIN nodes n2 ON n2.id = e.target_node_id
            WHERE n1.status = 'active' AND n2.status = 'active'
            """
        ).fetchall()
    finally:
        conn.close()
    return [
        EdgeItem(
            id=r["id"],
            source_id=r["source_id"],
            source_name=r["source_name"],
            target_id=r["target_id"],
            target_name=r["target_name"],
            label=r["label"],
        )
        for r in rows
    ]


@router.post("/aliases")
def add_alias(req: AliasRequest):
    conn = get_connection()
    try:
        node = conn.execute(
            "SELECT id FROM nodes WHERE name = ?", (req.node_name,)
        ).fetchone()
        if not node:
            raise HTTPException(status_code=404, detail=f"노드 '{req.node_name}' 없음")
        conn.execute(
            "INSERT OR IGNORE INTO aliases (alias, node_id) VALUES (?, ?)",
            (req.alias, node["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True}


# ─── 대화 탐색 (sentences) ───────────────────────────────────


class SentenceItem(BaseModel):
    id: int
    text: str
    role: str
    retention: str
    created_at: str


class SentenceUpdateRequest(BaseModel):
    text: str


@router.get("/sentences")
def list_sentences(
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    role: str = "",
    offset: int = 0,
    limit: int = 20,
):
    return search_sentences(q=q, date_from=date_from, date_to=date_to, role=role, offset=offset, limit=limit)


@router.get("/sentences/{sentence_id}/impact")
def sentence_impact(sentence_id: int):
    return get_sentence_impact(sentence_id)


@router.put("/sentences/{sentence_id}")
def edit_sentence(sentence_id: int, req: SentenceUpdateRequest):
    result = update_sentence(sentence_id, req.text, use_llm=USE_LLM)
    return {
        "triples_added": result.triples_added,
        "edges_deactivated": result.edges_deactivated,
    }


@router.delete("/sentences/{sentence_id}")
def remove_sentence(sentence_id: int):
    return delete_sentence(sentence_id)
