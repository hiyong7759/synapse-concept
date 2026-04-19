"""Synapse API 라우터 (v15 — 하이퍼그래프 기반).

설계서 기준 통합 파이프라인: 모든 입력 → retrieve → save → respond.
v15: edges 테이블 폐기로 관련 엔드포인트·필드 제거. 연결은 node_mentions +
node_categories + aliases 세 하이퍼엣지로 표현.
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from engine.save import (
    save, rollback, save_response,
    search_sentences, get_sentence_impact, update_sentence, delete_sentence,
    merge_nodes,
)
from engine.retrieve import retrieve
from engine.db import get_connection, get_stats, DB_PATH
from engine.llm import chat as llm_chat, SYSTEM_IMAGE_EXTRACT, OllamaError
from engine import suggestions as sug

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
    # v15: 게시물 단위 저장. edges 테이블 폐기로 관련 필드 제거.
    post_id: Optional[int] = None
    nodes_added: list[str]
    node_ids_added: list[int]
    mentions_added: int = 0
    nodes_deactivated: list[str] = []  # v15: 상태변경된 노드 이름 (현재는 sentence#N 식별자)


class RetrieveResponseModel(BaseModel):
    start_nodes: list[str]
    context_triples: list[tuple[str, Optional[str], str]]


class ChatResponse(BaseModel):
    save: Optional[SaveResponseModel] = None
    retrieve: Optional[RetrieveResponseModel] = None
    answer: Optional[str] = None
    question: Optional[str] = None  # 모호성 되물음
    markdown_draft: Optional[str] = None  # v12: structure-suggest 초안 (저장 보류 시)


class RollbackRequest(BaseModel):
    sentence_ids: list[int] = []
    node_ids: list[int] = []


class RollbackResponse(BaseModel):
    sentences_deleted: int
    nodes_deleted: int


class AliasRequest(BaseModel):
    alias: str
    node_name: str


class NodeItem(BaseModel):
    id: int
    name: str
    status: str
    degree: int   # v15: 같은 문장 바구니에 함께 등장한 고유 노드 수


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

    # 인출 결과·답변은 항상 구성 (저장 보류 시에도 전달)
    retrieve_model = RetrieveResponseModel(
        start_nodes=r_retrieve.start_nodes,
        context_triples=[(t.src, t.label, t.tgt) for t in r_retrieve.context_triples],
    )
    answer = r_retrieve.answer

    # 모호성 되물음 → 저장 중단. 인출 결과·답변은 그대로 반환
    if r_save.question:
        return ChatResponse(question=r_save.question, retrieve=retrieve_model, answer=answer)

    # v12: structure-suggest 초안 반환 (저장 보류). 사용자가 검색 의도였다면 answer로,
    # 저장 의도였다면 markdown_draft 카드로 분기
    if r_save.markdown_draft:
        if answer:
            save_response(answer)
        return ChatResponse(
            markdown_draft=r_save.markdown_draft,
            retrieve=retrieve_model,
            answer=answer,
        )

    # ── 3단계: 정상 저장 응답 ──
    save_model = SaveResponseModel(
        post_id=r_save.post_id,
        nodes_added=r_save.nodes_added,
        node_ids_added=r_save.node_ids_added,
        mentions_added=r_save.mentions_added,
        nodes_deactivated=r_save.nodes_deactivated,
    )

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
    result = rollback(req.sentence_ids, req.node_ids)
    return RollbackResponse(
        sentences_deleted=result["sentences_deleted"],
        nodes_deleted=result["nodes_deleted"],
    )


@router.get("/stats")
def stats():
    return get_stats()


@router.get("/nodes", response_model=list[NodeItem])
def nodes():
    """노드 목록. degree = 같은 문장 바구니에 함께 등장한 고유 노드 수."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT
                n.id,
                n.name,
                n.status,
                COUNT(DISTINCT co.node_id) AS degree
            FROM nodes n
            LEFT JOIN node_mentions m  ON m.node_id = n.id
            LEFT JOIN node_mentions co ON co.sentence_id = m.sentence_id AND co.node_id != n.id
            WHERE n.status = 'active'
            GROUP BY n.id
            ORDER BY degree DESC
            """
        ).fetchall()
    finally:
        conn.close()
    return [NodeItem(id=r["id"], name=r["name"], status=r["status"], degree=r["degree"]) for r in rows]


@router.get("/hyperedges")
def hyperedges():
    """하이퍼그래프 시각화용: 문장 바구니 + 카테고리 바구니 + 별칭 바구니.

    각 바구니는 여러 노드를 동시에 묶는다 (엣지가 아니라 하이퍼엣지).
    """
    conn = get_connection()
    try:
        # 문장 바구니: 같은 sentence에 2개 이상의 노드가 공출현하는 케이스만 반환
        sentence_rows = conn.execute(
            """
            SELECT s.id AS sentence_id, s.text,
                   GROUP_CONCAT(m.node_id)   AS node_ids,
                   GROUP_CONCAT(n.name, '|') AS node_names
            FROM sentences s
            JOIN node_mentions m ON m.sentence_id = s.id
            JOIN nodes n ON n.id = m.node_id AND n.status='active'
            GROUP BY s.id
            HAVING COUNT(m.node_id) >= 2
            """
        ).fetchall()

        # 카테고리 바구니: 카테고리 공유 노드들
        category_rows = conn.execute(
            """
            SELECT nc.category,
                   GROUP_CONCAT(n.id)        AS node_ids,
                   GROUP_CONCAT(n.name, '|') AS node_names
            FROM node_categories nc
            JOIN nodes n ON n.id = nc.node_id AND n.status='active'
            GROUP BY nc.category
            HAVING COUNT(n.id) >= 2
            """
        ).fetchall()
    finally:
        conn.close()

    return {
        "sentence_baskets": [
            {
                "kind": "sentence",
                "sentence_id": r["sentence_id"],
                "label": r["text"],
                "node_ids": [int(x) for x in (r["node_ids"] or "").split(",") if x],
                "node_names": (r["node_names"] or "").split("|"),
            }
            for r in sentence_rows
        ],
        "category_baskets": [
            {
                "kind": "category",
                "category": r["category"],
                "label": r["category"],
                "node_ids": [int(x) for x in (r["node_ids"] or "").split(",") if x],
                "node_names": (r["node_names"] or "").split("|"),
            }
            for r in category_rows
        ],
    }


# ─── 노드 카테고리 편집 (Phase 4) ──────────────────────────

class CategoryAddRequest(BaseModel):
    category: str


class CategoryRenameRequest(BaseModel):
    # 'from'은 파이썬 예약어 → alias로 외부 키 매핑
    from_: str = Field(alias="from")
    to: str

    model_config = ConfigDict(populate_by_name=True)


@router.get("/nodes/{node_id}/categories")
def list_node_categories(node_id: int):
    """노드의 카테고리 목록 반환."""
    conn = get_connection()
    try:
        node = conn.execute("SELECT id, name FROM nodes WHERE id=?", (node_id,)).fetchone()
        if not node:
            raise HTTPException(status_code=404, detail=f"node {node_id} 없음")
        rows = conn.execute(
            "SELECT category, created_at FROM node_categories WHERE node_id=? ORDER BY created_at",
            (node_id,),
        ).fetchall()
    finally:
        conn.close()
    return {
        "node_id": node["id"],
        "node_name": node["name"],
        "categories": [{"category": r["category"], "created_at": r["created_at"]} for r in rows],
    }


@router.post("/nodes/{node_id}/categories")
def add_node_category(node_id: int, req: CategoryAddRequest):
    """노드에 카테고리 추가. 사용자 명시 — 즉시 승인된 것으로 간주."""
    cat = req.category.strip()
    if not cat:
        raise HTTPException(status_code=400, detail="category 비어있음")
    conn = get_connection()
    try:
        node = conn.execute("SELECT id FROM nodes WHERE id=?", (node_id,)).fetchone()
        if not node:
            raise HTTPException(status_code=404, detail=f"node {node_id} 없음")
        conn.execute(
            "INSERT OR IGNORE INTO node_categories (node_id, category) VALUES (?,?)",
            (node_id, cat),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "node_id": node_id, "category": cat}


@router.delete("/nodes/{node_id}/categories/{category}")
def remove_node_category(node_id: int, category: str):
    """노드에서 카테고리 제거 (복수 카테고리 중 일부만)."""
    conn = get_connection()
    try:
        cur = conn.execute(
            "DELETE FROM node_categories WHERE node_id=? AND category=?",
            (node_id, category),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "deleted": cur.rowcount}


@router.put("/nodes/{node_id}/categories")
def rename_node_category(node_id: int, req: CategoryRenameRequest):
    """노드 카테고리 이름 변경 (from → to)."""
    src = req.from_.strip()
    dst = req.to.strip()
    if not src or not dst:
        raise HTTPException(status_code=400, detail="from/to 비어있음")
    if src == dst:
        return {"ok": True, "changed": 0}
    conn = get_connection()
    try:
        # 새 카테고리가 이미 있으면 from만 삭제
        existing = conn.execute(
            "SELECT 1 FROM node_categories WHERE node_id=? AND category=?",
            (node_id, dst),
        ).fetchone()
        if existing:
            cur = conn.execute(
                "DELETE FROM node_categories WHERE node_id=? AND category=?",
                (node_id, src),
            )
        else:
            cur = conn.execute(
                "UPDATE node_categories SET category=? WHERE node_id=? AND category=?",
                (dst, node_id, src),
            )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "changed": cur.rowcount}


@router.get("/categories")
def list_all_categories():
    """모든 카테고리 경로 목록 (편집 UI 자동완성용)."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT category, COUNT(*) AS node_count
               FROM node_categories
               GROUP BY category
               ORDER BY node_count DESC, category"""
        ).fetchall()
    finally:
        conn.close()
    return [{"category": r["category"], "node_count": r["node_count"]} for r in rows]


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
        "sentence_id": sentence_id,
        "nodes_deactivated": result.nodes_deactivated,
    }


@router.delete("/sentences/{sentence_id}")
def remove_sentence(sentence_id: int):
    return delete_sentence(sentence_id)


# ─── /review (Phase 5) ─────────────────────────────────────

class ReviewApplyRequest(BaseModel):
    # category | alias | category_delete | alias_delete | merge | archive
    # | token | token_dismiss | basic_info
    type: str
    params: dict


@router.get("/review")
def review_all(sections: Optional[str] = None):
    """현재 시점의 모든 섹션 제안을 반환. 저장 없음."""
    keys = [s.strip() for s in sections.split(",")] if sections else None
    return sug.all_sections(use_llm=USE_LLM, sections=keys)


@router.get("/review/count")
def review_count():
    """배지용 집계 — 빠른 쿼리만."""
    return sug.counts()


@router.post("/review/apply")
def review_apply(req: ReviewApplyRequest):
    """제안 수락 → 최종 테이블 INSERT/UPDATE."""
    p = req.params or {}
    t = req.type

    conn = get_connection()
    try:
        if t == "category":
            nid = p.get("node_id")
            cat = (p.get("category") or "").strip()
            if nid is None or not cat:
                raise HTTPException(status_code=400, detail="node_id/category 필요")
            conn.execute(
                "INSERT OR IGNORE INTO node_categories (node_id, category) VALUES (?,?)",
                (nid, cat),
            )
            conn.commit()
            return {"ok": True}

        if t == "alias":
            nid = p.get("node_id")
            alias = (p.get("alias") or "").strip()
            if nid is None or not alias:
                raise HTTPException(status_code=400, detail="node_id/alias 필요")
            conn.execute(
                "INSERT OR IGNORE INTO aliases (alias, node_id) VALUES (?,?)",
                (alias, nid),
            )
            conn.commit()
            return {"ok": True}

        if t == "merge":
            keep = p.get("keep_id")
            remove = p.get("remove_id")
            if keep is None or remove is None:
                raise HTTPException(status_code=400, detail="keep_id/remove_id 필요")
            conn.close()
            return merge_nodes(keep, remove)

        if t == "archive":
            nid = p.get("node_id")
            if nid is None:
                raise HTTPException(status_code=400, detail="node_id 필요")
            conn.execute(
                "UPDATE nodes SET status='inactive', updated_at=datetime('now') WHERE id=?",
                (nid,),
            )
            conn.commit()
            return {"ok": True}

        if t == "token":
            sentence_id = p.get("sentence_id")
            token = (p.get("token") or "").strip()
            value = (p.get("value") or "").strip()
            if not (sentence_id and token and value):
                raise HTTPException(status_code=400, detail="sentence_id/token/value 필요")
            # 노드 upsert
            row = conn.execute(
                "SELECT id FROM nodes WHERE name=? COLLATE NOCASE AND status='active' "
                "ORDER BY updated_at DESC LIMIT 1",
                (value,),
            ).fetchone()
            if row:
                nid = row["id"]
            else:
                nid = conn.execute(
                    "INSERT INTO nodes (name) VALUES (?)", (value,)
                ).lastrowid
            conn.execute(
                "INSERT OR IGNORE INTO node_mentions (node_id, sentence_id) VALUES (?,?)",
                (nid, sentence_id),
            )
            conn.execute(
                "DELETE FROM unresolved_tokens WHERE sentence_id=? AND token=?",
                (sentence_id, token),
            )
            conn.commit()
            return {"ok": True, "node_id": nid}

        if t == "basic_info":
            answer = (p.get("answer") or "").strip()
            if not answer:
                raise HTTPException(status_code=400, detail="answer 비어있음")
            conn.close()
            # 일반 저장 파이프라인으로 위임 (게시물 1건 생성, 노드 추출)
            r = save(answer, use_llm=USE_LLM)
            return {
                "ok": True,
                "post_id": r.post_id,
                "nodes_added": r.nodes_added,
                "mentions_added": r.mentions_added,
                "markdown_draft": r.markdown_draft,
            }

        if t == "category_delete":
            # ai_generated 섹션 "삭제" 버튼. origin 필수 — 사용자 수동 등록(user)은
            # 노드 상세 화면에서 삭제하도록 분리 (실수 방지).
            nid = p.get("node_id")
            cat = (p.get("category") or "").strip()
            origin = (p.get("origin") or "").strip()
            if nid is None or not cat or origin not in ("ai", "rule", "external"):
                raise HTTPException(
                    status_code=400,
                    detail="node_id/category/origin(ai|rule|external) 필요",
                )
            cur = conn.execute(
                "DELETE FROM node_categories WHERE node_id=? AND category=? AND origin=?",
                (nid, cat, origin),
            )
            conn.commit()
            return {"ok": True, "deleted": cur.rowcount}

        if t == "alias_delete":
            # external_generated 섹션 "삭제" 버튼. origin 필수 — 사용자/규칙 별칭은
            # 노드 상세 화면에서 삭제.
            alias = (p.get("alias") or "").strip()
            origin = (p.get("origin") or "").strip()
            if not alias or origin not in ("ai", "rule", "external"):
                raise HTTPException(
                    status_code=400,
                    detail="alias/origin(ai|rule|external) 필요",
                )
            cur = conn.execute(
                "DELETE FROM aliases WHERE alias=? AND origin=?",
                (alias, origin),
            )
            conn.commit()
            return {"ok": True, "deleted": cur.rowcount}

        if t == "token_dismiss":
            sentence_id = p.get("sentence_id")
            token = (p.get("token") or "").strip()
            if not (sentence_id and token):
                raise HTTPException(status_code=400, detail="sentence_id/token 필요")
            conn.execute(
                "DELETE FROM unresolved_tokens WHERE sentence_id=? AND token=?",
                (sentence_id, token),
            )
            conn.commit()
            return {"ok": True}

        raise HTTPException(status_code=400, detail=f"unknown type: {t}")
    finally:
        try:
            conn.close()
        except Exception:
            pass
