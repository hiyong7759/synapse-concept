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
_STOP_WORDS = {'안', '못', '좀', '잘', '더', '왜', '뭐', '어떤', '이', '그', '저', '다', '를', '을',
               '수', '때', '뭘', '걸', '건', '거', '게', '데', '줘', '해', '돼', '싶', '좋'}


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


def match_start_nodes(conn, keywords: list[str], identity_id: int | None = None) -> tuple[list[dict], set[str]]:
    """키워드로 시작 노드 매칭 + 도메인 필터 추출.

    검색 대상:
    - 노드명 (name) → 시작 노드
    - 연결된 엣지의 type → 시작 노드
    - 도메인 (domain) → 도메인 필터 (시작 노드가 아님)

    Returns:
        (시작 노드 목록, 도메인 필터 set)
    """
    if not keywords:
        return [], set()

    # 도메인 매칭 키워드 분리 → 필터로 사용
    all_domains = {r["domain"] for r in conn.execute(
        "SELECT DISTINCT domain FROM nodes WHERE status = 'active' AND domain != ''"
    ).fetchall()}

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

    # 노드명 매칭 (도메인 필터 키워드 제외)
    name_rows = []
    if content_keywords:
        name_conditions = " OR ".join([
            "(LOWER(name) LIKE LOWER(?) OR LOWER(?) LIKE '%' || LOWER(name) || '%')"
            for _ in content_keywords
        ])
        name_params = []
        for kw in content_keywords:
            name_params.append(f"%{kw}%")
            name_params.append(kw)

        name_rows = conn.execute(
            f"""SELECT * FROM nodes
                WHERE status = 'active' AND ({name_conditions})
                ORDER BY weight DESC""",
            name_params
        ).fetchall()

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

    # 도메인 필터만 있고 시작 노드가 없으면, 해당 도메인 전체를 시작 노드로
    if not results and domain_filters:
        placeholders = ",".join(["?" for _ in domain_filters])
        rows = conn.execute(
            f"SELECT * FROM nodes WHERE status = 'active' AND domain IN ({placeholders})",
            list(domain_filters)
        ).fetchall()
        results = [dict(r) for r in rows]

    return results, domain_filters


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


# 도메인 → 클러스터 매핑
DOMAIN_CLUSTERS = {
    '프로필': '인물', '역할': '인물', '직급': '인물', '경력': '인물', '병역': '인물',
    '회사': '조직', '고객사': '조직', '조직': '조직', '업무': '조직',
    '학력': '교육기술', '기술': '교육기술', '자격': '교육기술',
    '프로젝트': '프로젝트',
    '장비': '환경', '용도': '환경', '위치': '환경',
    '음식': '생활', '건강': '생활', '운동': '생활', '판단': '생활',
}


def build_subgraph(conn, keywords: list[str]) -> dict:
    """키워드 → 서브그래프 추출 (도메인 클러스터 기반 BFS).

    1. 키워드로 시작 노드 매칭
    2. 시작 노드가 속한 도메인 클러스터 확인
    3. 해당 클러스터 안에서만 BFS (클러스터 경계를 넘지 않음)
    4. 본인 노드는 경유 차단 (시작 노드인 경우 제외)
    safety 노드는 별도로 전달하여 LLM이 관련성을 판단하게 한다.
    """
    # 본인 노드 찾기 (1회만 조회하여 재사용)
    identity_id = find_identity_node(conn)

    # 1. 시작 노드 매칭 + 도메인 필터
    start_nodes, domain_filters = match_start_nodes(conn, keywords, identity_id=identity_id)
    start_nodes = [n for n in start_nodes if not n.get("safety")]
    start_ids = set(n["id"] for n in start_nodes)

    # 2. 시작 노드들의 클러스터 + 도메인 필터 클러스터 수집
    active_clusters = set()
    for n in start_nodes:
        cluster = DOMAIN_CLUSTERS.get(n.get("domain", ""))
        if cluster:
            active_clusters.add(cluster)
    for d in domain_filters:
        cluster = DOMAIN_CLUSTERS.get(d)
        if cluster:
            active_clusters.add(cluster)

    # 클러스터를 못 찾으면 전체 탐색
    has_clusters = bool(active_clusters)

    # 3. BFS — 시작 노드는 양방향, 이후는 정방향만
    #    본인 노드 경유 차단 + 클러스터 경계 제한
    visited = set(start_ids)
    queue = list(start_ids)
    is_first_hop = True
    all_nodes_map = {n["id"]: n for n in start_nodes}

    while queue:
        # 시작 노드에서 첫 홉은 양방향, 이후는 정방향만
        neighbors = get_neighbors(conn, queue, forward_only=not is_first_hop)
        is_first_hop = False
        next_queue = []
        for n in neighbors:
            if n["id"] not in visited:
                if n.get("safety"):
                    continue
                # 클러스터 경계 체크
                if has_clusters:
                    n_cluster = DOMAIN_CLUSTERS.get(n.get("domain", ""))
                    if n_cluster and n_cluster not in active_clusters:
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

    # 도메인 필터 적용: 필터가 있으면 해당 도메인의 클러스터 + 시작 노드만 유지
    if domain_filters:
        filter_clusters = {DOMAIN_CLUSTERS.get(d, d) for d in domain_filters}
        all_nodes = [n for n in all_nodes
                     if DOMAIN_CLUSTERS.get(n.get("domain", "")) in filter_clusters
                     or n["id"] in start_ids]
        all_ids = [n["id"] for n in all_nodes]

    # 3. safety 노드는 별도 수집 (LLM이 관련성 판단)
    safety_nodes = get_safety_nodes(conn)

    # 4. 내부 엣지 추출 (safety 노드 제외한 서브그래프)
    edges = get_edges_for_nodes(conn, all_ids)

    return {
        "start_nodes": [n["name"] for n in start_nodes],
        "nodes": all_nodes,
        "edges": edges,
        "safety_nodes": safety_nodes,
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


EXPOSURE_LOG_RETENTION_DAYS = 90


def log_exposure(conn, node_ids: list[int], target: str = "lens",
                 provider: str = "anthropic"):
    """노출 원장 기록 + 오래된 로그 정리."""
    conn.executemany(
        "INSERT INTO exposure_log (node_id, direction, target, provider) VALUES (?, 'out', ?, ?)",
        [(nid, target, provider) for nid in node_ids]
    )
    conn.execute(
        "DELETE FROM exposure_log WHERE created_at < datetime('now', ?)",
        (f"-{EXPOSURE_LOG_RETENTION_DAYS} days",)
    )


def increment_weights(conn, node_ids: list[int]):
    """프롬프트에 포함된 노드의 weight 증가."""
    if not node_ids:
        return
    placeholders = ",".join(["?" for _ in node_ids])
    conn.execute(
        f"UPDATE nodes SET weight = weight + 1, updated_at = datetime('now') WHERE id IN ({placeholders})",
        node_ids
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

        # weight 증가 + 노출 기록 (단일 트랜잭션)
        node_ids = [n["id"] for n in subgraph["nodes"]]
        if node_ids:
            increment_weights(conn, node_ids)
            log_exposure(conn, node_ids)
            conn.commit()

        return {
            "status": "ok",
            "prompt": prompt,
            "nodes_used": [n["name"] for n in subgraph["nodes"]],
            "safety_nodes": [n["name"] for n in subgraph["safety_nodes"]],
            "node_count": len(subgraph["nodes"]),
            "edge_count": len(subgraph["edges"]),
        }
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: get_context.py '<query>'")
        sys.exit(1)

    result = get_context(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
