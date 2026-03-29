#!/usr/bin/env python3
"""노드/엣지 추가 — 대화에서 추출된 개념을 그래프에 저장."""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from init_db import get_connection, DB_PATH


def find_node(conn, name: str):
    """이름으로 기존 노드 검색 (대소문자 무시)."""
    return conn.execute(
        "SELECT * FROM nodes WHERE LOWER(name) = LOWER(?) AND status != 'deleted'",
        (name,)
    ).fetchone()


SID_PREFIX = {
    '프로필': 'PRF', '회사': 'COM', '학력': 'EDU', '프로젝트': 'PRJ',
    '자격': 'CRT', '기술': 'TEC', '고객사': 'CLI', '역할': 'ROL',
    '조직': 'ORG', '직급': 'RNK', '업무': 'BIZ', '위치': 'LOC',
    '경력': 'CAR', '병역': 'MIL', '음식': 'FOD', '건강': 'HLT',
    '운동': 'SPT', '장비': 'DEV', '용도': 'USE', '판단': 'JDG',
}


def generate_sid(conn, domain: str) -> str:
    """도메인 기반 sid 자동 생성."""
    prefix = SID_PREFIX.get(domain, 'ETC')
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(sid, ?) AS INTEGER)) FROM nodes WHERE sid LIKE ?",
        (len(prefix) + 2, f"{prefix}_%")
    ).fetchone()
    seq = (row[0] or 0) + 1
    return f"{prefix}_{seq:03d}"


def add_node(conn, name: str, domain: str = "", source: str = "user",
             safety: bool = False, safety_rule: str = None,
             confidence: float = None) -> tuple[int, bool]:
    """노드 추가. 이미 존재하면 기존 ID 반환.

    Returns:
        (node_id, is_new)
    """
    existing = find_node(conn, name)
    if existing:
        return existing["id"], False

    sid = generate_sid(conn, domain)
    cursor = conn.execute(
        """INSERT INTO nodes (sid, name, domain, source, safety, safety_rule, confidence)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (sid, name, domain, source, 1 if safety else 0, safety_rule, confidence)
    )
    return cursor.lastrowid, True


def add_edge(conn, source_id: int, target_id: int, edge_type: str = "link",
             label: str = None):
    """엣지 추가. 이미 존재하면 무시."""
    conn.execute(
        """INSERT OR IGNORE INTO edges (source_node_id, target_node_id, type, label)
           VALUES (?, ?, ?, ?)""",
        (source_id, target_id, edge_type, label)
    )


def add_from_json(data: dict, db_path: str = DB_PATH) -> dict:
    """
    JSON 데이터로 노드/엣지 일괄 추가.

    입력 형식:
    {
      "nodes": [
        {"name": "맥미니", "domain": "장비", "safety": false},
        {"name": "M4", "domain": "장비"}
      ],
      "edges": [
        {"source": "맥미니", "target": "M4", "type": "spec"}
      ]
    }
    """
    conn = get_connection(db_path)
    added_nodes = []
    added_edges = []

    try:
        # 노드 추가
        name_to_id = {}
        for node_data in data.get("nodes", []):
            name = node_data["name"]
            node_id, is_new = add_node(
                conn,
                name=name,
                domain=node_data.get("domain", ""),
                source=node_data.get("source", "user"),
                safety=node_data.get("safety", False),
                safety_rule=node_data.get("safety_rule"),
                confidence=node_data.get("confidence"),
            )
            name_to_id[name] = node_id
            added_nodes.append({
                "id": node_id,
                "name": name,
                "is_new": is_new,
            })

        # 엣지 추가 — 이름으로 참조
        for edge_data in data.get("edges", []):
            source_name = edge_data["source"]
            target_name = edge_data["target"]

            # name_to_id에 없으면 DB에서 검색
            source_id = name_to_id.get(source_name)
            if source_id is None:
                src_node = find_node(conn, source_name)
                source_id = src_node["id"] if src_node else None

            target_id = name_to_id.get(target_name)
            if target_id is None:
                tgt_node = find_node(conn, target_name)
                target_id = tgt_node["id"] if tgt_node else None

            if source_id and target_id:
                edge_label = edge_data.get("label")
                add_edge(
                    conn,
                    source_id=source_id,
                    target_id=target_id,
                    edge_type=edge_data.get("type", "link"),
                    label=edge_label,
                )
                added_edges.append({
                    "source": source_name,
                    "target": target_name,
                    "type": edge_data.get("type", "link"),
                    "label": edge_label,
                })

        conn.commit()
    finally:
        conn.close()

    return {
        "status": "ok",
        "nodes_added": len(added_nodes),
        "edges_added": len(added_edges),
        "nodes": added_nodes,
        "edges": added_edges,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: add_nodes.py '<json>'")
        sys.exit(1)

    data = json.loads(sys.argv[1])
    result = add_from_json(data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
