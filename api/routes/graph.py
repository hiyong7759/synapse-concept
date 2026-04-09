"""Synapse API 라우터."""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from engine.save import save, rollback
from engine.retrieve import retrieve
from engine.db import get_connection, get_stats, DB_PATH
from engine.llm import chat as llm_chat, SYSTEM_IMAGE_EXTRACT, OllamaError

router = APIRouter()

USE_LLM = os.environ.get("USE_LLM", "false").lower() == "true"


# ─── 요청/응답 모델 ───────────────────────────────────────────

class HistoryItem(BaseModel):
    role: str    # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    text: str
    images: list[str] = []          # base64 인코딩 이미지 목록 (멀티모달)
    history: list[HistoryItem] = [] # 이전 대화 (최근 N턴)


class SaveResponse(BaseModel):
    triples_added: list[tuple[str, Optional[str], str]]
    edge_ids_added: list[int]
    nodes_added: list[str]
    node_ids_added: list[int]
    edges_deactivated: list[tuple[str, Optional[str], str]]
    aliases_added: list[tuple[str, str]]
    question: Optional[str]


class RetrieveResponse(BaseModel):
    start_nodes: list[str]
    context_triples: list[tuple[str, Optional[str], str]]
    answer: Optional[str]


class ChatResponse(BaseModel):
    mode: str  # "save" | "retrieve" | "clarify"
    save: Optional[SaveResponse] = None
    retrieve: Optional[RetrieveResponse] = None
    question: Optional[str] = None  # clarify 모드


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
    images = req.images if req.images else None
    history = [{"role": h.role, "content": h.content} for h in req.history] or None

    # 이미지가 있을 때: LLM으로 이미지에서 텍스트 추출 → save
    text = req.text
    if images and USE_LLM:
        try:
            prompt = text if text.strip() else "이 이미지에서 정보를 추출해주세요."
            text = llm_chat(SYSTEM_IMAGE_EXTRACT, prompt, images=images, temperature=0, max_tokens=512)
            print(f"[IMAGE EXTRACT]\n{text}\n{'─'*40}")
        except OllamaError:
            pass  # 추출 실패 시 원본 텍스트로 진행

    # 이미지 있거나 텍스트 있으면 save 시도
    if text.strip():
        result = save(text, use_llm=USE_LLM)

        if result.question:
            return ChatResponse(mode="clarify", question=result.question)

        # 이미지 있었으면 트리플 0개여도 save 응답 (retrieve로 빠지지 않도록)
        if result.triples_added or images:
            return ChatResponse(
                mode="save",
                save=SaveResponse(
                    triples_added=result.triples_added,
                    edge_ids_added=result.edge_ids_added,
                    nodes_added=result.nodes_added,
                    node_ids_added=result.node_ids_added,
                    edges_deactivated=result.edges_deactivated,
                    aliases_added=result.aliases_added,
                    question=None,
                ),
            )

    # 이미지 있었지만 텍스트 추출 실패 → save 빈 응답
    if images:
        return ChatResponse(
            mode="save",
            save=SaveResponse(
                triples_added=[], edge_ids_added=[], nodes_added=[],
                node_ids_added=[], edges_deactivated=[], aliases_added=[], question=None,
            ),
        )

    # 저장된 것 없음 → retrieve
    ret = retrieve(req.text, use_llm=USE_LLM, images=images, history=history)
    return ChatResponse(
        mode="retrieve",
        retrieve=RetrieveResponse(
            start_nodes=ret.start_nodes,
            context_triples=[(t.src, t.label, t.tgt) for t in ret.context_triples],
            answer=ret.answer,
        ),
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
