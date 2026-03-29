#!/usr/bin/env python3
"""맥락 기반 그래프 탐색 → 프롬프트 조립.

탐색 전략:
1. 질문 키워드로 시작 노드 매칭 (노드명, 도메인, 엣지 type 모두 검색)
2. 시작 노드에서 BFS로 연결된 전체 노드 탐색
3. safety 노드는 별도 섹션으로 전달 (LLM이 관련성 판단)
4. 전체 서브그래프를 프롬프트로 조립하여 LLM에 전달
5. LLM이 질문 맥락에서 유효한 노드만 판단하여 답변에 반영
"""

import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from init_db import get_connection, DB_PATH

# 한국어 조사 패턴 (키워드 끝에서 제거)
_PARTICLES = re.compile(
    r'(이|가|은|는|을|를|에|에서|으로|로|와|과|의|도|만|부터|까지|에게|한테|처럼|같이|보다|라도|이라도)$'
)

# 너무 짧거나 흔한 단어는 검색에서 제외
_STOP_WORDS = {
    # 대명사/관형사
    '이', '그', '저', '뭐', '뭘', '어떤', '어디', '언제', '누구', '무슨', '어떻게',
    # 동사/형용사 어간
    '해', '돼', '했어', '했는데', '할까', '할지', '하는', '하고', '싶', '좋', '있', '없',
    '알려', '알아', '보여', '봐', '써', '쓸', '쓰는', '됐', '되는', '된',
    '줘', '줄', '주는', '가르쳐', '찾아',
    # 보조용언/부사
    '안', '못', '좀', '잘', '더', '왜', '다', '또', '꼭', '너무', '많이', '조금',
    # 조사 잔여 (normalize에서 못 잡는 것)
    '를', '을', '수', '때', '걸', '건', '거', '게', '데',
    # 범용 서술어 (노드명이 될 수 없는 것)
    '관리', '시스템', '서비스', '프로그램', '작성', '만들기', '사용', '활용',
    '경험', '추천', '정리', '설명', '비교', '차이', '방법', '설정', '구축',
    '뭐야', '뭐지', '있어', '없어', '했지', '했나', '할래', '할게',
    '살아', '사는', '갈까', '올까', '보자', '하자',
}


def normalize_keywords(raw_keywords: list[str]) -> list[str]:
    """키워드 정규화: 조사 제거 + 불용어 필터 + 최소 길이."""
    result = []
    for kw in raw_keywords:
        # 조사 제거
        stripped = _PARTICLES.sub('', kw)
        if not stripped:
            stripped = kw
        # 불용어 및 1글자 한글 제거 (영문/숫자는 유지: M4, 13B 등)
        if stripped.lower() in _STOP_WORDS:
            continue
        if len(stripped) == 1 and ord(stripped) >= 0xAC00:
            continue
        result.append(stripped)
    return result


def match_start_nodes(conn, keywords: list[str], identity_id: int | None = None) -> tuple[list[dict], set[str], list[str]]:
    """키워드로 시작 노드 매칭 + 도메인 필터 추출.

    검색 대상:
    - 노드명 (name) → 시작 노드
    - 연결된 엣지의 type → 시작 노드
    - 도메인 (domain) → 도메인 필터 (시작 노드가 아님)

    Returns:
        (시작 노드 목록, 도메인 필터 set, 매칭 실패 콘텐츠 키워드)
    """
    if not keywords:
        return [], set(), []

    # 알려진 도메인 목록 (DB에 노드가 없어도 인식)
    KNOWN_DOMAINS = {
        '프로필', '회사', '학력', '프로젝트', '자격', '기술', '고객사',
        '역할', '조직', '직급', '업무', '위치', '경력', '병역',
        '음식', '건강', '운동', '장비', '용도', '판단', '취미',
    }
    # DB에 있는 도메인 + 알려진 도메인
    db_domains = {r["domain"] for r in conn.execute(
        "SELECT DISTINCT domain FROM nodes WHERE status = 'active' AND domain != ''"
    ).fetchall()}
    all_domains = KNOWN_DOMAINS | db_domains

    domain_filters = set()
    content_keywords = []
    for kw in keywords:
        matched_domain = False
        for d in all_domains:
            if kw.lower() in d.lower() or d.lower() in kw.lower():
                domain_filters.add(d)
                matched_domain = True
        if not matched_domain:
            content_keywords.append(kw)

    # 별칭(aliases) 매칭 → 노드명 매칭 순서로 검색
    name_rows = []
    if content_keywords:
        # 1) aliases 테이블에서 먼저 매칭
        alias_conditions = " OR ".join(["LOWER(a.alias) = LOWER(?)" for _ in content_keywords])
        alias_rows = conn.execute(
            f"""SELECT DISTINCT n.* FROM aliases a
                JOIN nodes n ON a.node_id = n.id
                WHERE n.status = 'active' AND ({alias_conditions})
                ORDER BY n.weight DESC""",
            content_keywords
        ).fetchall()

        # 2) 노드명 substring 매칭 (기존 로직)
        name_conditions = " OR ".join([
            "(LOWER(name) LIKE LOWER(?) OR LOWER(?) LIKE '%' || LOWER(name) || '%')"
            for _ in content_keywords
        ])
        name_params = []
        for kw in content_keywords:
            name_params.append(f"%{kw}%")
            name_params.append(kw)

        name_only_rows = conn.execute(
            f"""SELECT * FROM nodes
                WHERE status = 'active' AND ({name_conditions})
                ORDER BY weight DESC""",
            name_params
        ).fetchall()

        # aliases 결과 우선, 중복 제거
        seen_ids = set()
        for row in list(alias_rows) + list(name_only_rows):
            d = dict(row)
            if d["id"] not in seen_ids:
                seen_ids.add(d["id"])
                name_rows.append(row)

    # 엣지 type 매칭 (본인 노드 제외)
    label_rows = []
    if content_keywords:
        type_conditions = " OR ".join([
            "LOWER(e.type) LIKE LOWER(?)"
            for _ in content_keywords
        ])
        type_params = [f"%{kw}%" for kw in content_keywords]

        label_rows = conn.execute(
            f"""SELECT DISTINCT n.* FROM edges e
                JOIN nodes n ON (n.id = e.source_node_id OR n.id = e.target_node_id)
                WHERE n.status = 'active' AND ({type_conditions})
                ORDER BY n.weight DESC""",
            type_params
        ).fetchall()

    # 중복 제거 (엣지 타입 매칭에서 본인 노드 제외)
    seen = set()
    results = []
    for row in list(name_rows):
        d = dict(row)
        if d["id"] not in seen:
            seen.add(d["id"])
            results.append(d)
    for row in list(label_rows):
        d = dict(row)
        if d["id"] not in seen and d["id"] != identity_id:
            seen.add(d["id"])
            results.append(d)

    # 매칭 실패한 콘텐츠 키워드 추적
    matched_names = {r["name"].lower() for r in results}
    unmatched = [kw for kw in content_keywords
                 if not any(kw.lower() in name for name in matched_names)]

    # 시작 노드가 없고 도메인 매칭이 있으면 도메인 전체 반환
    if not results and domain_filters:
        placeholders = ",".join(["?" for _ in domain_filters])
        rows = conn.execute(
            f"SELECT * FROM nodes WHERE status = 'active' AND domain IN ({placeholders})",
            list(domain_filters)
        ).fetchall()
        results = [dict(r) for r in rows]

    return results, domain_filters, unmatched


def get_neighbors(conn, node_ids: list[int], forward_only: bool = False) -> list[dict]:
    """노드 ID 목록의 1홉 이웃 반환.

    forward_only=True: 정방향(source→target)만 탐색.
    """
    if not node_ids:
        return []

    placeholders = ",".join(["?" for _ in node_ids])

    if forward_only:
        # 정방향만: 현재 노드가 source인 엣지의 target만
        rows = conn.execute(
            f"""SELECT DISTINCT n.*, e.type as edge_type,
                       e.source_node_id, e.target_node_id
                FROM edges e
                JOIN nodes n ON e.target_node_id = n.id
                WHERE e.source_node_id IN ({placeholders})
                  AND n.status = 'active' AND n.id NOT IN ({placeholders})""",
            node_ids + node_ids
        ).fetchall()
    else:
        # 양방향
        rows = conn.execute(
            f"""SELECT DISTINCT n.*, e.type as edge_type,
                       e.source_node_id, e.target_node_id
                FROM edges e
                JOIN nodes n ON (
                    (e.target_node_id = n.id AND e.source_node_id IN ({placeholders}))
                    OR
                    (e.source_node_id = n.id AND e.target_node_id IN ({placeholders}))
                )
                WHERE n.status = 'active' AND n.id NOT IN ({placeholders})""",
            node_ids + node_ids + node_ids
        ).fetchall()

    return [dict(r) for r in rows]


def get_safety_nodes(conn) -> list[dict]:
    """safety 태그 노드 전체 반환."""
    rows = conn.execute(
        "SELECT * FROM nodes WHERE safety = 1 AND status = 'active'"
    ).fetchall()
    return [dict(r) for r in rows]


def get_edges_for_nodes(conn, node_ids: list[int]) -> list[dict]:
    """노드 집합 내부의 엣지만 반환."""
    if not node_ids:
        return []

    placeholders = ",".join(["?" for _ in node_ids])
    rows = conn.execute(
        f"""SELECT e.*, src.name as source_name, tgt.name as target_name
            FROM edges e
            JOIN nodes src ON e.source_node_id = src.id
            JOIN nodes tgt ON e.target_node_id = tgt.id
            WHERE e.source_node_id IN ({placeholders})
              AND e.target_node_id IN ({placeholders})""",
        node_ids + node_ids
    ).fetchall()

    return [dict(r) for r in rows]


def find_identity_node(conn) -> int | None:
    """본인 노드 찾기 — 엣지 연결이 가장 많은 노드가 본인."""
    row = conn.execute(
        """SELECT node_id, COUNT(*) as cnt FROM (
               SELECT source_node_id as node_id FROM edges
               UNION ALL
               SELECT target_node_id as node_id FROM edges
           ) GROUP BY node_id ORDER BY cnt DESC LIMIT 1"""
    ).fetchone()
    return row["node_id"] if row else None


def build_subgraph(conn, keywords: list[str]) -> dict:
    """키워드 → 서브그래프 추출.

    1. 키워드로 시작 노드 매칭
    2. 정방향 BFS
    3. 본인 노드 경유 차단 (무한 확산 방지)
    4. 도메인 키워드가 있으면 해당 도메인 결과만 유지
    safety 노드는 별도로 전달하여 LLM이 관련성을 판단하게 한다.
    """
    identity_id = find_identity_node(conn)

    start_nodes, domain_filters, unmatched = match_start_nodes(conn, keywords, identity_id=identity_id)
    start_nodes = [n for n in start_nodes if not n.get("safety")]
    start_ids = set(n["id"] for n in start_nodes)

    # BFS — 정방향만. 본인 노드 경유 차단.
    visited = set(start_ids)
    queue = list(start_ids)
    all_nodes_map = {n["id"]: n for n in start_nodes}

    while queue:
        neighbors = get_neighbors(conn, queue, forward_only=True)
        next_queue = []
        for n in neighbors:
            if n["id"] not in visited:
                if n.get("safety"):
                    continue
                visited.add(n["id"])
                all_nodes_map[n["id"]] = n
                # 본인 노드는 도달만, 경유 차단
                if n["id"] == identity_id:
                    continue
                next_queue.append(n["id"])
        queue = next_queue

    all_ids = list(visited)
    all_nodes = [all_nodes_map[nid] for nid in all_ids if nid in all_nodes_map]

    # 도메인 필터: 도메인 키워드가 있으면 해당 도메인 결과만 유지
    # "건강 관리" → "관리"로 프로젝트가 매칭되더라도, "건강" 도메인 결과만 남김
    if domain_filters and all_nodes:
        filtered = [n for n in all_nodes if n.get("domain") in domain_filters]
        # 도메인 필터 결과가 있으면 그것만, 없으면 원본 유지
        if filtered:
            all_nodes = filtered
            all_ids = [n["id"] for n in all_nodes]

    safety_nodes = get_safety_nodes(conn)
    edges = get_edges_for_nodes(conn, all_ids)

    # 매칭 실패 정보
    missing = []
    for kw in unmatched:
        missing.append(f"\"{kw}\" 노드가 없습니다. 추가하시겠어요?")
    if not all_nodes and domain_filters:
        for d in domain_filters:
            count = conn.execute(
                "SELECT COUNT(*) FROM nodes WHERE status = 'active' AND domain = ?", (d,)
            ).fetchone()[0]
            if count == 0:
                missing.append(f"\"{d}\" 관련 노드가 없습니다. 추가하시겠어요?")

    return {
        "start_nodes": [n["name"] for n in start_nodes],
        "nodes": all_nodes,
        "edges": edges,
        "safety_nodes": safety_nodes,
        "missing": missing,
    }


def format_prompt(subgraph: dict) -> str:
    """서브그래프 → 프롬프트 텍스트 조립."""
    lines = []

    # 맥락 노드가 있을 때
    if subgraph["nodes"]:
        lines.append("[사용자 맥락 정보]")
        lines.append("")

        for node in subgraph["nodes"]:
            parts = [node["name"]]
            if node.get("domain"):
                parts.append(f"({node['domain']})")
            lines.append(f"- {' '.join(parts)}")

        if subgraph["edges"]:
            lines.append("")
            lines.append("관계:")
            for edge in subgraph["edges"]:
                label_part = f": {edge['label']}" if edge.get('label') else ""
                lines.append(f"  {edge['source_name']} --({edge['type']}{label_part})--> {edge['target_name']}")

    # safety 노드는 별도 섹션으로 전달
    if subgraph["safety_nodes"]:
        lines.append("")
        lines.append("[사용자 주의사항 — 질문과 관련될 때만 고려]")
        for node in subgraph["safety_nodes"]:
            rule = node.get("safety_rule") or "관련 질문 시 고려"
            lines.append(f"- {node['name']}: {rule}")

    return "\n".join(lines) if lines else ""


def increment_weights(conn, node_ids: list[int]):
    """프롬프트에 포함된 노드의 weight 증가."""
    if not node_ids:
        return
    placeholders = ",".join(["?" for _ in node_ids])
    conn.execute(
        f"UPDATE nodes SET weight = weight + 1, updated_at = datetime('now') WHERE id IN ({placeholders})",
        node_ids
    )


def update_edges_last_used(conn, node_ids: list[int]):
    """탐색에 사용된 엣지의 last_used 갱신."""
    if not node_ids:
        return
    placeholders = ",".join(["?" for _ in node_ids])
    conn.execute(
        f"""UPDATE edges SET last_used = datetime('now')
            WHERE source_node_id IN ({placeholders})
              AND target_node_id IN ({placeholders})""",
        node_ids + node_ids
    )


def get_context(query: str, db_path: str = DB_PATH) -> dict:
    """질문 → 맥락 프롬프트 생성 (메인 엔트리)."""
    conn = get_connection(db_path)

    try:
        # 키워드 분리 + 정규화 (조사 제거, 불용어 필터)
        raw_keywords = [kw.strip() for kw in query.split() if kw.strip()]
        keywords = normalize_keywords(raw_keywords)

        # 서브그래프 추출
        subgraph = build_subgraph(conn, keywords)

        # 프롬프트 조립
        prompt = format_prompt(subgraph)

        # weight 증가 + 엣지 last_used 갱신 (단일 트랜잭션)
        node_ids = [n["id"] for n in subgraph["nodes"]]
        if node_ids:
            increment_weights(conn, node_ids)
            update_edges_last_used(conn, node_ids)
            conn.commit()

        result = {
            "status": "ok",
            "prompt": prompt,
            "nodes_used": [n["name"] for n in subgraph["nodes"]],
            "safety_nodes": [n["name"] for n in subgraph["safety_nodes"]],
            "node_count": len(subgraph["nodes"]),
            "edge_count": len(subgraph["edges"]),
        }
        if subgraph.get("missing"):
            result["missing"] = subgraph["missing"]
        return result
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: get_context.py '<query>'")
        sys.exit(1)

    result = get_context(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
