#!/usr/bin/env python3
"""그래프 조회 — 노드/엣지 목록, 도메인별 필터, 검색."""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from init_db import get_connection, DB_PATH


def list_nodes(domain: str = None, status: str = "active",
               search: str = None, limit: int = 100,
               db_path: str = DB_PATH) -> dict:
    """노드 목록 조회."""
    conn = get_connection(db_path)

    conditions = []
    params = []

    if status:
        conditions.append("status = ?")
        params.append(status)

    if domain:
        conditions.append("LOWER(domain) = LOWER(?)")
        params.append(domain)

    if search:
        conditions.append("LOWER(name) LIKE LOWER(?)")
        params.append(f"%{search}%")

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    rows = conn.execute(
        f"SELECT * FROM nodes {where} ORDER BY weight DESC, updated_at DESC LIMIT ?",
        params + [limit]
    ).fetchall()

    nodes = [dict(r) for r in rows]
    conn.close()

    return {
        "status": "ok",
        "count": len(nodes),
        "nodes": nodes,
    }


def list_edges(node_name: str = None, limit: int = 100,
               db_path: str = DB_PATH) -> dict:
    """엣지 목록 조회. node_name 지정 시 해당 노드의 연결만."""
    conn = get_connection(db_path)

    if node_name:
        rows = conn.execute(
            """SELECT e.*, src.name as source_name, tgt.name as target_name
               FROM edges e
               JOIN nodes src ON e.source_node_id = src.id
               JOIN nodes tgt ON e.target_node_id = tgt.id
               WHERE LOWER(src.name) = LOWER(?) OR LOWER(tgt.name) = LOWER(?)
               ORDER BY e.created_at DESC LIMIT ?""",
            (node_name, node_name, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT e.*, src.name as source_name, tgt.name as target_name
               FROM edges e
               JOIN nodes src ON e.source_node_id = src.id
               JOIN nodes tgt ON e.target_node_id = tgt.id
               ORDER BY e.created_at DESC LIMIT ?""",
            (limit,)
        ).fetchall()

    edges = [dict(r) for r in rows]
    conn.close()

    return {
        "status": "ok",
        "count": len(edges),
        "edges": edges,
    }


def list_domains(db_path: str = DB_PATH) -> dict:
    """도메인별 노드 수 요약."""
    conn = get_connection(db_path)

    rows = conn.execute(
        """SELECT domain, COUNT(*) as count
           FROM nodes WHERE status = 'active'
           GROUP BY domain ORDER BY count DESC"""
    ).fetchall()

    domains = [{"domain": r["domain"] or "(없음)", "count": r["count"]} for r in rows]
    conn.close()

    return {
        "status": "ok",
        "domains": domains,
    }


def show_node(name: str, db_path: str = DB_PATH) -> dict:
    """특정 노드의 상세 정보 + 연결."""
    conn = get_connection(db_path)

    # 정확 매칭 우선 → 없으면 substring 매칭
    node = conn.execute(
        "SELECT * FROM nodes WHERE LOWER(name) = LOWER(?)",
        (name,)
    ).fetchone()

    if not node:
        node = conn.execute(
            "SELECT * FROM nodes WHERE LOWER(name) LIKE LOWER(?) ORDER BY weight DESC LIMIT 1",
            (f"%{name}%",)
        ).fetchone()

    if not node:
        conn.close()
        return {"status": "error", "message": f"노드 '{name}'을 찾을 수 없습니다."}

    node_dict = dict(node)

    # 연결된 엣지
    edges = conn.execute(
        """SELECT e.*, src.name as source_name, tgt.name as target_name
           FROM edges e
           JOIN nodes src ON e.source_node_id = src.id
           JOIN nodes tgt ON e.target_node_id = tgt.id
           WHERE e.source_node_id = ? OR e.target_node_id = ?""",
        (node["id"], node["id"])
    ).fetchall()

    conn.close()

    return {
        "status": "ok",
        "node": node_dict,
        "edges": [dict(e) for e in edges],
    }


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "nodes"
    arg = sys.argv[2] if len(sys.argv) > 2 else None

    if cmd == "nodes":
        result = list_nodes(domain=arg)
    elif cmd == "edges":
        result = list_edges(node_name=arg)
    elif cmd == "domains":
        result = list_domains()
    elif cmd == "show":
        if not arg:
            print("Usage: list_nodes.py show <name>")
            sys.exit(1)
        result = show_node(arg)
    else:
        result = {"error": f"Unknown command: {cmd}. Use: nodes, edges, domains, show"}

    print(json.dumps(result, ensure_ascii=False, indent=2))
