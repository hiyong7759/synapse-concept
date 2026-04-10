"""Synapse 저장 파이프라인.

흐름:
  입력 텍스트
  → sentences 테이블에 문장 저장
  → LLM 전처리: 대명사/날짜 치환, 모호성 감지
  → LLM 추출 (task6): retention + 노드 + 엣지 + 카테고리 + deactivate 한 번에
  → extract deactivate 필드로 기존 엣지 비활성화
  → sentences.retention 업데이트
  → DB 저장 (nodes with category + edges with sentence_id)
  → LLM 별칭 제안 (새 노드 시에만)
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from .db import get_connection, DB_PATH
from .llm import chat, LLMError, save_pronoun, llm_extract


@dataclass
class SaveResult:
    sentence_ids: list[int] = field(default_factory=list)
    triples_added: list[tuple[str, Optional[str], str]] = field(default_factory=list)
    edge_ids_added: list[int] = field(default_factory=list)
    nodes_added: list[str] = field(default_factory=list)
    node_ids_added: list[int] = field(default_factory=list)
    edges_deactivated: list[tuple[str, Optional[str], str]] = field(default_factory=list)
    aliases_added: list[tuple[str, str]] = field(default_factory=list)
    question: Optional[str] = None
    is_question: bool = False


# ─── DB 헬퍼 ──────────────────────────────────────────────

def _insert_sentence(
    conn, text: str, role: str = "user", retention: str = "memory"
) -> int:
    cur = conn.execute(
        "INSERT INTO sentences (text, role, retention) VALUES (?,?,?)",
        (text, role, retention),
    )
    return cur.lastrowid


def _upsert_node(conn, name: str, category: Optional[str] = None) -> tuple[int, bool]:
    """노드 삽입 또는 기존 ID 반환. category는 NULL일 때만 업데이트. (id, is_new) 반환."""
    row = conn.execute("SELECT id, category FROM nodes WHERE name=?", (name,)).fetchone()
    if row:
        if category and not row["category"]:
            conn.execute(
                "UPDATE nodes SET category=?, updated_at=datetime('now') WHERE id=?",
                (category, row["id"]),
            )
        return row["id"], False
    cur = conn.execute(
        "INSERT INTO nodes (name, category) VALUES (?,?)", (name, category)
    )
    return cur.lastrowid, True


def _insert_edge(
    conn, src_id: int, tgt_id: int, label: Optional[str], sentence_id: Optional[int]
) -> int:
    cur = conn.execute(
        "INSERT INTO edges (source_node_id, target_node_id, label, sentence_id) VALUES (?,?,?,?)",
        (src_id, tgt_id, label, sentence_id),
    )
    return cur.lastrowid


def _get_existing_triples(conn, node_names: list[str]) -> list[dict]:
    if not node_names:
        return []
    placeholders = ",".join("?" * len(node_names))
    rows = conn.execute(
        f"""
        SELECT n1.name AS src, e.label, n2.name AS tgt, e.id AS edge_id
        FROM edges e
        JOIN nodes n1 ON n1.id = e.source_node_id
        JOIN nodes n2 ON n2.id = e.target_node_id
        WHERE n1.name IN ({placeholders}) OR n2.name IN ({placeholders})
        """,
        node_names + node_names,
    ).fetchall()
    return [dict(r) for r in rows]


def _deactivate_edge(conn, edge_id: int) -> None:
    conn.execute("UPDATE edges SET last_used=datetime('now') WHERE id=?", (edge_id,))
    conn.execute(
        """
        UPDATE nodes SET status='inactive', updated_at=datetime('now')
        WHERE id = (SELECT target_node_id FROM edges WHERE id=?)
        """,
        (edge_id,),
    )


# ─── LLM 전처리 ───────────────────────────────────────────

_DATE_WORDS = (
    # 일 — 과거
    '어제', '그저께', '그제', '엊그제', '그끄제',
    # 일 — 현재/미래
    '오늘', '내일', '모레', '글피', '그글피',
    # 주
    '이번주', '이번 주', '지난주', '저번주', '다음주', '다음 주',
    # 월
    '이번달', '지난달', '다음달',
    # 연
    '올해', '작년', '내년', '재작년', '내후년',
)
_PRONOUN_WORDS = (
    # 사물
    '이거', '그거', '저거', '이것', '그것', '저것',
    # 장소
    '거기', '여기', '저기', '이곳', '그곳', '저곳',
    # 방향
    '이쪽', '그쪽', '저쪽', '이리', '저리',
    # 인물 — 존대
    '이분', '그분', '저분',
    # 인물 — 비존대
    '걔', '쟤', '얘', '그사람', '그 사람', '그애', '그 애', '그녀',
    # 지시형용사/부사
    '이런', '그런', '저런', '이러한', '그러한', '저러한',
    '이렇게', '그렇게', '저렇게',
    # 모호 시간 (LLM 판단)
    '방금', '아까', '지금', '요즘', '최근', '이번에',
    '그날', '그때', '당시', '주말',
    # 요일 (맥락 판단 — "다음 목요일" vs "목요일마다")
    '월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일',
)
_AGE_PATTERN = re.compile(r'\d{1,3}(살|세)|[0-9]0대')
_NEG_WORDS = ('안', '못')
_NEG_PATTERN = re.compile(r'(?:^|\s)(안|못)\s')

_NEG_2PASS_PROMPT = (
    '이 문장에서 부정부사(안/못)의 대상을 찾아라.\n'
    'JSON만 출력: {"negation": "안|못", "subject": "주어노드", "object": "대상노드"}\n'
    '대상을 특정할 수 없으면: {"negation": null}'
)


def _postprocess_negation(
    text: str, nodes: list[dict], edges: list[dict], use_llm: bool = True
) -> tuple[list[dict], list[dict]]:
    """부정부사(안/못) 후처리.

    1차: 엣지 label에 안/못이 있으면 노드+엣지로 변환.
    2차: 문장에 안/못이 있는데 1차에서도 감지 안 되면 LLM 2-pass 호출.
    """
    neg_match = _NEG_PATTERN.search(f' {text} ')
    if not neg_match:
        return nodes, edges

    neg_word = neg_match.group(1)  # "안" or "못"
    node_names = {n['name'] for n in nodes}

    # 이미 노드에 있으면 패스
    if neg_word in node_names:
        return nodes, edges

    # 1차: label에 안/못이 있으면 → 노드+엣지 변환
    new_edges = []
    converted = False
    for e in edges:
        if e.get('label') in _NEG_WORDS:
            neg = e['label']
            src = e.get('source', '')
            tgt = e.get('target', '')
            # 노드 추가
            if neg not in node_names:
                nodes.append({'name': neg, 'category': None})
                node_names.add(neg)
            # 엣지 변환: src→neg(null), neg→tgt(null)
            new_edges.append({'source': src, 'label': None, 'target': neg})
            new_edges.append({'source': neg, 'label': None, 'target': tgt})
            converted = True
        else:
            new_edges.append(e)

    if converted:
        return nodes, new_edges

    # 2차: 완전 누락 → LLM 2-pass
    if use_llm:
        try:
            from .llm import mlx_chat
            raw = mlx_chat('extract', f'{_NEG_2PASS_PROMPT}\n\n문장: {text}', max_tokens=128)
            match = re.search(r'\{.*\}', raw, re.DOTALL)
            if match:
                d2 = json.loads(match.group())
                if d2.get('negation'):
                    neg = d2['negation']
                    subj = d2.get('subject', '')
                    obj = d2.get('object', '')
                    if neg not in node_names:
                        nodes.append({'name': neg, 'category': None})
                    if subj and subj in node_names:
                        edges.append({'source': subj, 'label': None, 'target': neg})
                    if obj and obj in node_names and obj != neg:
                        edges.append({'source': neg, 'label': None, 'target': obj})
        except Exception:
            pass

    return nodes, edges


def _preprocess(text: str) -> dict:
    """대명사/날짜 치환. 모호하면 {"question": ...}, 정상이면 {"text": ...} 반환."""
    needs_today = any(w in text for w in _DATE_WORDS)
    needs_pronoun = any(w in text for w in _PRONOUN_WORDS)
    needs_age = bool(_AGE_PATTERN.search(text))
    if not needs_today and not needs_pronoun and not needs_age:
        return {"text": text}
    today = date.today().isoformat()
    return save_pronoun(text, today=today if (needs_today or needs_age) else "")



# ─── 별칭 ─────────────────────────────────────────────────

_ALIAS_SYSTEM = """당신은 한국어 지식 그래프 별칭 추출기입니다.
주어진 노드 이름의 별칭(줄임말, 영어 원문, 다국어 표기, 흔한 오타)을 JSON 배열로만 출력하세요. 다른 텍스트 금지.

규칙:
- 100% 확실한 동의어만 포함 (추측 금지)
- 노드 이름 자체는 제외
- 없으면 반드시 [] 반환

예시:
"스타벅스" → ["Starbucks", "스벅"]
"리액트 네이티브" → ["React Native", "RN"]
"허리디스크" → ["요추디스크", "추간판탈출증"]
"맥북프로" → ["MacBook Pro", "맥프로"]
"김민수" → []"""

_FIRST_PERSON_ALIASES = ("내", "저", "제", "나의", "저의", "제가", "나는", "저는", "내가", "제가", "나한테", "저한테")


def _suggest_aliases(node_name: str) -> list[str]:
    try:
        raw = chat(_ALIAS_SYSTEM, node_name, temperature=0, max_tokens=64)
        match = re.search(r"\[.*?\]", raw, re.DOTALL)
        if not match:
            return []
        candidates = json.loads(match.group())
        return [a for a in candidates if isinstance(a, str) and a != node_name]
    except Exception:
        return []


def _register_first_person_aliases(conn, node_id: int) -> None:
    for alias in _FIRST_PERSON_ALIASES:
        conn.execute(
            "INSERT OR IGNORE INTO aliases (alias, node_id) VALUES (?,?)",
            (alias, node_id),
        )


# ─── 메인 API ─────────────────────────────────────────────

def save(
    text: str,
    db_path: str = DB_PATH,
    use_llm: bool = True,
    images: Optional[list[str]] = None,
    context_sentences: Optional[list[str]] = None,
) -> SaveResult:
    """텍스트를 그래프에 저장. SaveResult 반환.

    use_llm=False이면 LLM 단계를 건너뜀 (서버 없이 구조 테스트 시 사용).
    """
    result = SaveResult()

    conn = get_connection(db_path)
    try:
        # 1. 문단 분리 → sentences 저장 (role='user')
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()] or [text]
        sentence_ids: list[int] = []
        for paragraph in paragraphs:
            sid = _insert_sentence(conn, paragraph)
            sentence_ids.append(sid)
        result.sentence_ids = sentence_ids

        # 2. LLM 전처리: 치환 / 모호성 감지
        effective_text = text
        if use_llm:
            try:
                pre = _preprocess(text)
                if pre.get("question"):
                    result.question = pre["question"]
                    conn.commit()
                    return result
                effective_text = pre.get("text", text)
            except LLMError:
                pass

        # 3. LLM 추출 (task6): 노드+엣지+카테고리
        if use_llm:
            try:
                extracted = llm_extract(effective_text, context_sentences=context_sentences)
            except LLMError:
                extracted = {"nodes": [], "edges": []}
        else:
            extracted = {"nodes": [], "edges": []}

        ext_nodes = extracted.get("nodes", [])  # [{"name": ..., "category": ...}]
        ext_edges = extracted.get("edges", [])  # [{"source": ..., "label": ..., "target": ...}]
        ext_deactivate = extracted.get("deactivate", [])  # [{"source": ..., "target": ...}]
        retention = extracted.get("retention", "memory")

        # 부정부사(안/못) 후처리: label→노드 변환 + 2-pass fallback
        ext_nodes, ext_edges = _postprocess_negation(
            effective_text, ext_nodes, ext_edges, use_llm=use_llm
        )

        # 4. 기존 트리플 조회 (deactivate 매칭용)
        # target 없는 엣지(LLM 오출력) 필터링
        ext_edges = [e for e in ext_edges if e.get("source") and e.get("target")]

        all_names = list(
            {n["name"] for n in ext_nodes}
            | {e["source"] for e in ext_edges}
            | {e["target"] for e in ext_edges}
            | {d["source"] for d in ext_deactivate if d.get("source")}
            | {d["target"] for d in ext_deactivate if d.get("target")}
        )
        existing = _get_existing_triples(conn, all_names)

        # 5. extract deactivate 필드 → 엣지 비활성화
        if ext_deactivate and existing:
            existing_index = {(e["src"], e["tgt"]): e for e in existing}
            for d in ext_deactivate:
                src, tgt = d.get("source", ""), d.get("target", "")
                e = existing_index.get((src, tgt))
                if e:
                    _deactivate_edge(conn, e["edge_id"])
                    result.edges_deactivated.append((e["src"], e["label"], e["tgt"]))

        # 6. sentences.retention 업데이트 (extract 결과 반영)
        if sentence_ids:
            ph = ",".join("?" * len(sentence_ids))
            conn.execute(
                f"UPDATE sentences SET retention=? WHERE id IN ({ph})",
                [retention] + sentence_ids,
            )

        if not ext_nodes and not ext_edges:
            conn.commit()
            return result

        # 7. DB 저장: 노드 upsert → 이름→ID 맵 → 엣지 insert
        sentence_id = sentence_ids[0] if sentence_ids else None
        name_to_id: dict[str, int] = {}

        for node in ext_nodes:
            nid, is_new = _upsert_node(conn, node["name"], node.get("category"))
            name_to_id[node["name"]] = nid
            if is_new:
                result.nodes_added.append(node["name"])
                result.node_ids_added.append(nid)
                if node["name"] == "나":
                    _register_first_person_aliases(conn, nid)

        # 엣지에서 참조하는 노드 중 ext_nodes에 없는 것도 upsert
        for edge in ext_edges:
            for nm in (edge["source"], edge["target"]):
                if nm not in name_to_id:
                    nid, is_new = _upsert_node(conn, nm)
                    name_to_id[nm] = nid
                    if is_new:
                        result.nodes_added.append(nm)
                        result.node_ids_added.append(nid)
                        if nm == "나":
                            _register_first_person_aliases(conn, nid)

        for edge in ext_edges:
            src_id = name_to_id.get(edge["source"])
            tgt_id = name_to_id.get(edge["target"])
            if src_id is None or tgt_id is None:
                continue
            edge_id = _insert_edge(conn, src_id, tgt_id, edge.get("label"), sentence_id)
            result.triples_added.append((edge["source"], edge.get("label"), edge["target"]))
            result.edge_ids_added.append(edge_id)

        conn.commit()

        # 8. 새 노드 별칭 제안
        if use_llm and result.nodes_added:
            name_to_id_map = dict(zip(result.nodes_added, result.node_ids_added))
            for node_name in result.nodes_added:
                aliases = _suggest_aliases(node_name)
                node_id = name_to_id_map.get(node_name)
                if node_id is None:
                    continue
                for alias in aliases:
                    try:
                        conn.execute(
                            "INSERT OR IGNORE INTO aliases (alias, node_id) VALUES (?,?)",
                            (alias, node_id),
                        )
                        result.aliases_added.append((alias, node_name))
                    except Exception:
                        pass
            conn.commit()

    finally:
        conn.close()

    return result


def rollback(edge_ids: list[int], node_ids: list[int], db_path: str = DB_PATH) -> dict:
    """저장된 엣지/노드를 삭제해 롤백. [취소] 버튼용."""
    conn = get_connection(db_path)
    edges_deleted = 0
    nodes_deleted = 0
    try:
        if edge_ids:
            ph = ",".join("?" * len(edge_ids))
            cur = conn.execute(f"DELETE FROM edges WHERE id IN ({ph})", edge_ids)
            edges_deleted = cur.rowcount

        if node_ids:
            ph = ",".join("?" * len(node_ids))
            orphan_ids = [
                r[0] for r in conn.execute(
                    f"""SELECT id FROM nodes WHERE id IN ({ph})
                        AND id NOT IN (SELECT source_node_id FROM edges)
                        AND id NOT IN (SELECT target_node_id FROM edges)""",
                    node_ids,
                ).fetchall()
            ]
            if orphan_ids:
                ph2 = ",".join("?" * len(orphan_ids))
                cur2 = conn.execute(f"DELETE FROM nodes WHERE id IN ({ph2})", orphan_ids)
                nodes_deleted = cur2.rowcount

        conn.commit()
    finally:
        conn.close()

    return {"edges_deleted": edges_deleted, "nodes_deleted": nodes_deleted}


def save_response(text: str, db_path: str = DB_PATH) -> int:
    """assistant 응답을 sentences에 저장. 그래프 추출 없음. sentence_id 반환."""
    conn = get_connection(db_path)
    try:
        sid = _insert_sentence(conn, text, role="assistant")
        conn.commit()
    finally:
        conn.close()
    return sid


if __name__ == "__main__":
    tests = [
        "오늘 병원 다녀왔어",
        "세레콕시브 처방 받았어. 허리디스크 L4-L5 진단이야.",
        "나는 조용희고 웹기획자야.",
    ]
    for text in tests:
        r = save(text, use_llm=False)
        print(f"\n입력: {text!r}")
        print(f"  sentence_ids: {r.sentence_ids}")
        for src, label, tgt in r.triples_added:
            lbl = f" —({label})→ " if label else " → "
            print(f"  [저장] {src}{lbl}{tgt}")
        if r.nodes_added:
            print(f"  [신규 노드] {r.nodes_added}")
