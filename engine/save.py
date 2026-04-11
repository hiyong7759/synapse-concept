"""Synapse 저장 파이프라인.

흐름:
  입력 텍스트
  → sentences 테이블에 문장 저장
  → LLM 전처리: 대명사/날짜 치환, 모호성 감지
  → LLM 추출 (task6): retention + 노드 + 엣지 + 카테고리 + deactivate 한 번에
  → 오타 교정: 추출된 노드 이름을 기존 노드+별칭과 자모 거리 비교 (distance 1)
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
    typos_corrected: list[tuple[str, str]] = field(default_factory=list)
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
    """노드 삽입 또는 기존 ID 반환. 동명 노드가 여러 개면 가장 최근 업데이트된 노드 사용.
    category는 NULL일 때만 업데이트. (id, is_new) 반환."""
    row = conn.execute(
        "SELECT id, category FROM nodes WHERE name=? ORDER BY updated_at DESC LIMIT 1",
        (name,),
    ).fetchone()
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



# ─── 오타 교정 ────────────────────────────────────────────

def _correct_typos(
    conn,
    ext_nodes: list[dict],
    ext_edges: list[dict],
    ext_deactivate: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[tuple[str, str]]]:
    """추출된 노드/엣지 이름을 기존 노드+별칭과 대조하여 오타 교정.

    Returns: (ext_nodes, ext_edges, ext_deactivate, corrections)
    corrections: [(typo_name, canonical_name), ...]
    """
    from .jamo import decompose, levenshtein, is_typo_candidate

    # 1. DB에서 활성 노드 이름 + 별칭 로드
    rows = conn.execute(
        "SELECT id, name FROM nodes WHERE status='active'"
    ).fetchall()
    alias_rows = conn.execute(
        """SELECT a.alias, n.name FROM aliases a
           JOIN nodes n ON n.id = a.node_id
           WHERE n.status = 'active'"""
    ).fetchall()

    # canonical 이름 → (이름, 엣지 수) 맵
    canonical: dict[str, str] = {}  # lookup_key → node_name
    for r in rows:
        canonical[r["name"]] = r["name"]
    for r in alias_rows:
        canonical[r["alias"]] = r["name"]

    # 자모 분해 캐시 (기존 노드 이름만, 별칭은 정확매칭용)
    node_names = list({r["name"] for r in rows})
    jamo_cache: dict[str, str] = {n: decompose(n) for n in node_names}

    # 엣지 수 캐시 (tiebreaker용)
    edge_counts: dict[str, int] = {}
    for n in node_names:
        row = conn.execute(
            """SELECT COUNT(*) AS cnt FROM edges e
               JOIN nodes ns ON ns.id = e.source_node_id
               JOIN nodes nt ON nt.id = e.target_node_id
               WHERE (ns.name=? OR nt.name=?) AND ns.status='active' AND nt.status='active'""",
            (n, n),
        ).fetchone()
        edge_counts[n] = row["cnt"] if row else 0

    # 2. 추출된 이름 수집
    extracted_names: set[str] = set()
    for n in ext_nodes:
        extracted_names.add(n["name"])
    for e in ext_edges:
        extracted_names.add(e["source"])
        extracted_names.add(e["target"])
    for d in ext_deactivate:
        if d.get("source"):
            extracted_names.add(d["source"])
        if d.get("target"):
            extracted_names.add(d["target"])

    # 3. 오타 감지
    corrections: dict[str, str] = {}  # typo → canonical
    for name in extracted_names:
        if name in canonical:
            continue  # 정확매칭 → 교정 불필요
        jamo_name = decompose(name)
        if len(jamo_name) < 6:
            continue
        best_match: str | None = None
        best_edges = -1
        for node_name, jamo_node in jamo_cache.items():
            if abs(len(jamo_name) - len(jamo_node)) > 1:
                continue
            if levenshtein(jamo_name, jamo_node) == 1:
                ec = edge_counts.get(node_name, 0)
                if ec > best_edges:
                    best_match = node_name
                    best_edges = ec
        if best_match:
            corrections[name] = best_match

    if not corrections:
        return ext_nodes, ext_edges, ext_deactivate, []

    # 4. 치환 적용
    def fix(name: str) -> str:
        return corrections.get(name, name)

    ext_nodes = [
        {**n, "name": fix(n["name"])} for n in ext_nodes
    ]
    ext_edges = [
        {**e, "source": fix(e["source"]), "target": fix(e["target"])}
        for e in ext_edges
    ]
    ext_deactivate = [
        {**d,
         "source": fix(d["source"]) if d.get("source") else d.get("source"),
         "target": fix(d["target"]) if d.get("target") else d.get("target")}
        for d in ext_deactivate
    ]

    # 5. 오타를 별칭으로 등록 (재발 방지)
    for typo_name, canonical_name in corrections.items():
        node_row = conn.execute(
            "SELECT id FROM nodes WHERE name=? AND status='active' ORDER BY updated_at DESC LIMIT 1",
            (canonical_name,),
        ).fetchone()
        if node_row:
            conn.execute(
                "INSERT OR IGNORE INTO aliases (alias, node_id) VALUES (?,?)",
                (typo_name, node_row["id"]),
            )

    return ext_nodes, ext_edges, ext_deactivate, list(corrections.items())


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

        # 3.5 오타 교정: 추출된 노드/엣지 이름을 기존 노드+별칭과 자모 거리 비교
        if ext_nodes or ext_edges:
            ext_nodes, ext_edges, ext_deactivate, corrections = _correct_typos(
                conn, ext_nodes, ext_edges, ext_deactivate
            )
            result.typos_corrected = corrections

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


def split_node(
    node_id: int,
    alias_for_original: str,
    alias_for_new: str,
    edge_ids_to_move: list[int],
    db_path: str = DB_PATH,
) -> dict:
    """동명 노드 분리. 기존 노드에서 지정된 엣지를 새 노드로 이동.

    - 기존 노드의 name으로 새 노드 생성 (동명, 다른 id)
    - edge_ids_to_move의 엣지를 새 노드로 이동 (source 또는 target)
    - 양쪽 별칭 등록
    """
    conn = get_connection(db_path)
    try:
        orig = conn.execute("SELECT id, name, category FROM nodes WHERE id=?", (node_id,)).fetchone()
        if not orig:
            return {"error": "node not found"}

        # 새 노드 생성 (같은 name)
        cur = conn.execute(
            "INSERT INTO nodes (name, category) VALUES (?,?)",
            (orig["name"], orig["category"]),
        )
        new_id = cur.lastrowid

        # 엣지 이동
        moved = 0
        for eid in edge_ids_to_move:
            edge = conn.execute("SELECT source_node_id, target_node_id FROM edges WHERE id=?", (eid,)).fetchone()
            if not edge:
                continue
            if edge["source_node_id"] == node_id:
                conn.execute("UPDATE edges SET source_node_id=? WHERE id=?", (new_id, eid))
                moved += 1
            elif edge["target_node_id"] == node_id:
                conn.execute("UPDATE edges SET target_node_id=? WHERE id=?", (new_id, eid))
                moved += 1

        # 별칭 등록
        conn.execute("INSERT OR IGNORE INTO aliases (alias, node_id) VALUES (?,?)", (alias_for_original, node_id))
        conn.execute("INSERT OR IGNORE INTO aliases (alias, node_id) VALUES (?,?)", (alias_for_new, new_id))

        conn.commit()
    finally:
        conn.close()

    return {
        "original_node_id": node_id,
        "new_node_id": new_id,
        "edges_moved": moved,
        "aliases": {alias_for_original: node_id, alias_for_new: new_id},
    }


def merge_nodes(
    keep_id: int,
    remove_id: int,
    db_path: str = DB_PATH,
) -> dict:
    """두 노드를 병합. remove_id의 엣지/별칭을 keep_id로 이동, 비활성화.

    split_node()의 반대 동작. 오타 노드 정리용.
    """
    conn = get_connection(db_path)
    try:
        keep = conn.execute("SELECT id, name FROM nodes WHERE id=?", (keep_id,)).fetchone()
        remove = conn.execute("SELECT id, name FROM nodes WHERE id=?", (remove_id,)).fetchone()
        if not keep or not remove:
            return {"error": "node not found"}

        # 엣지 이동: source
        cur1 = conn.execute(
            "UPDATE edges SET source_node_id=? WHERE source_node_id=?",
            (keep_id, remove_id),
        )
        # 엣지 이동: target
        cur2 = conn.execute(
            "UPDATE edges SET target_node_id=? WHERE target_node_id=?",
            (keep_id, remove_id),
        )
        edges_moved = cur1.rowcount + cur2.rowcount

        # 별칭 이동
        aliases_moved = []
        for r in conn.execute("SELECT alias FROM aliases WHERE node_id=?", (remove_id,)).fetchall():
            aliases_moved.append(r["alias"])
        conn.execute("UPDATE aliases SET node_id=? WHERE node_id=?", (keep_id, remove_id))

        # 제거 노드 이름을 별칭으로 등록 (재발 방지)
        conn.execute(
            "INSERT OR IGNORE INTO aliases (alias, node_id) VALUES (?,?)",
            (remove["name"], keep_id),
        )

        # 제거 노드 비활성화
        conn.execute(
            "UPDATE nodes SET status='inactive', updated_at=datetime('now') WHERE id=?",
            (remove_id,),
        )

        conn.commit()
    finally:
        conn.close()

    return {
        "keep_id": keep_id,
        "keep_name": keep["name"],
        "removed_id": remove_id,
        "removed_name": remove["name"],
        "edges_moved": edges_moved,
        "aliases_moved": aliases_moved,
    }


def find_suspected_typos(db_path: str = DB_PATH) -> list[dict]:
    """모든 활성 노드를 스캔하여 오타 의심 쌍 반환."""
    from .jamo import decompose, levenshtein

    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            """SELECT n.id, n.name,
                  (SELECT COUNT(*) FROM edges
                   WHERE source_node_id=n.id OR target_node_id=n.id) AS edge_count
               FROM nodes n WHERE n.status='active'"""
        ).fetchall()
    finally:
        conn.close()

    nodes = [{"id": r["id"], "name": r["name"], "edge_count": r["edge_count"]} for r in rows]
    jamo_cache = {n["name"]: decompose(n["name"]) for n in nodes}

    suspects = []
    for i, a in enumerate(nodes):
        ja = jamo_cache[a["name"]]
        if len(ja) < 6:
            continue
        for b in nodes[i + 1:]:
            jb = jamo_cache[b["name"]]
            if len(jb) < 6:
                continue
            if abs(len(ja) - len(jb)) > 1:
                continue
            dist = levenshtein(ja, jb)
            if dist == 1:
                suspects.append({
                    "node_a": a,
                    "node_b": b,
                    "jamo_distance": dist,
                })

    suspects.sort(key=lambda s: max(s["node_a"]["edge_count"], s["node_b"]["edge_count"]), reverse=True)
    return suspects


def save_response(text: str, db_path: str = DB_PATH) -> int:
    """assistant 응답을 sentences에 저장. 그래프 추출 없음. sentence_id 반환."""
    conn = get_connection(db_path)
    try:
        sid = _insert_sentence(conn, text, role="assistant")
        conn.commit()
    finally:
        conn.close()
    return sid


# ── 문장 검색/수정/삭제 ──────────────────────────────────────


def search_sentences(
    q: str = "",
    date_from: str = "",
    date_to: str = "",
    role: str = "",
    offset: int = 0,
    limit: int = 20,
    db_path: str = DB_PATH,
) -> dict:
    """sentences 검색. 키워드·날짜·role 필터, 페이지네이션."""
    conn = get_connection(db_path)
    try:
        where: list[str] = []
        params: list = []

        if q:
            where.append("s.text LIKE ?")
            params.append(f"%{q}%")
        if date_from:
            where.append("s.created_at >= ?")
            params.append(date_from)
        if date_to:
            where.append("s.created_at <= ?")
            params.append(date_to + " 23:59:59")
        if role:
            where.append("s.role = ?")
            params.append(role)

        where_clause = f"WHERE {' AND '.join(where)}" if where else ""

        total = conn.execute(
            f"SELECT COUNT(*) FROM sentences s {where_clause}", params
        ).fetchone()[0]

        rows = conn.execute(
            f"""SELECT s.id, s.text, s.role, s.retention, s.created_at
                FROM sentences s {where_clause}
                ORDER BY s.created_at DESC
                LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
    finally:
        conn.close()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "items": [
            {
                "id": r["id"],
                "text": r["text"],
                "role": r["role"],
                "retention": r["retention"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
    }


def get_sentence_impact(sentence_id: int, db_path: str = DB_PATH) -> dict:
    """문장 삭제 시 영향 받는 그래프 관계 미리보기."""
    conn = get_connection(db_path)
    try:
        edges = conn.execute(
            """SELECT e.id, n1.name AS src, e.label, n2.name AS tgt
               FROM edges e
               JOIN nodes n1 ON n1.id = e.source_node_id
               JOIN nodes n2 ON n2.id = e.target_node_id
               WHERE e.sentence_id = ?""",
            (sentence_id,),
        ).fetchall()
    finally:
        conn.close()

    return {
        "sentence_id": sentence_id,
        "affected_edges": [
            {"id": e["id"], "source": e["src"], "label": e["label"], "target": e["tgt"]}
            for e in edges
        ],
    }


def update_sentence(
    sentence_id: int,
    new_text: str,
    use_llm: bool = True,
    db_path: str = DB_PATH,
) -> SaveResult:
    """문장 수정: 기존 엣지 삭제 → 새 텍스트 재분석 → 새 엣지 삽입."""
    conn = get_connection(db_path)
    try:
        # 기존 엣지 삭제
        conn.execute("DELETE FROM edges WHERE sentence_id = ?", (sentence_id,))
        # 문장 텍스트 업데이트
        conn.execute(
            "UPDATE sentences SET text = ? WHERE id = ?",
            (new_text, sentence_id),
        )
        conn.commit()
    finally:
        conn.close()

    # 새 텍스트로 재분석 (save 파이프라인 재실행)
    return save(new_text, db_path=db_path, use_llm=use_llm)


def delete_sentence(sentence_id: int, db_path: str = DB_PATH) -> dict:
    """문장 삭제: 연결된 엣지 삭제 → 고아 노드 보존 → 문장 삭제."""
    conn = get_connection(db_path)
    try:
        edges_deleted = conn.execute(
            "DELETE FROM edges WHERE sentence_id = ?", (sentence_id,)
        ).rowcount
        conn.execute("DELETE FROM sentences WHERE id = ?", (sentence_id,))
        conn.commit()
    finally:
        conn.close()

    return {"sentence_id": sentence_id, "edges_deleted": edges_deleted}


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
