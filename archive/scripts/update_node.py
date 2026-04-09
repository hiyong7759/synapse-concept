#!/usr/bin/env python3
"""노드 수정/비활성화/삭제 + 교정 흐름."""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from init_db import get_connection, DB_PATH
from add_nodes import find_node as find_node_by_name


def update_node(name: str, updates: dict, db_path: str = DB_PATH) -> dict:
    """노드 속성 수정."""
    conn = get_connection(db_path)
    node = find_node_by_name(conn, name)

    if not node:
        conn.close()
        return {"status": "error", "message": f"노드 '{name}'을 찾을 수 없습니다."}

    allowed = {"name", "domain", "status", "safety", "safety_rule"}
    sets = []
    params = []

    for key, value in updates.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            params.append(value)

    if not sets:
        conn.close()
        return {"status": "error", "message": "수정할 필드가 없습니다."}

    sets.append("updated_at = datetime('now')")
    params.append(node["id"])

    conn.execute(
        f"UPDATE nodes SET {', '.join(sets)} WHERE id = ?",
        params
    )
    conn.commit()

    updated = conn.execute("SELECT * FROM nodes WHERE id = ?", (node["id"],)).fetchone()
    conn.close()

    return {"status": "ok", "node": dict(updated)}


def deactivate_node(name: str, db_path: str = DB_PATH) -> dict:
    """노드 비활성화 + 연결된 고아 노드 알림.

    V4 교정 흐름:
    - status: active → inactive
    - 연결된 엣지의 반대쪽 노드가 고아(다른 연결 없음)면 알림
    """
    conn = get_connection(db_path)
    node = find_node_by_name(conn, name)

    if not node:
        conn.close()
        return {"status": "error", "message": f"노드 '{name}'을 찾을 수 없습니다."}

    # 비활성화
    conn.execute(
        "UPDATE nodes SET status = 'inactive', updated_at = datetime('now') WHERE id = ?",
        (node["id"],)
    )

    # 연결된 노드 중 고아가 되는 것 찾기
    connected = conn.execute(
        """SELECT DISTINCT n.id, n.name FROM edges e
           JOIN nodes n ON (
               (e.target_node_id = n.id AND e.source_node_id = ?)
               OR (e.source_node_id = n.id AND e.target_node_id = ?)
           )
           WHERE n.status = 'active'""",
        (node["id"], node["id"])
    ).fetchall()

    orphans = []
    for cn in connected:
        # 이 노드 외에 다른 active 연결이 있는지
        other_edges = conn.execute(
            """SELECT COUNT(*) as cnt FROM edges e
               JOIN nodes n1 ON e.source_node_id = n1.id
               JOIN nodes n2 ON e.target_node_id = n2.id
               WHERE (e.source_node_id = ? OR e.target_node_id = ?)
                 AND e.source_node_id != ? AND e.target_node_id != ?
                 AND n1.status = 'active' AND n2.status = 'active'""",
            (cn["id"], cn["id"], node["id"], node["id"])
        ).fetchone()

        if other_edges["cnt"] == 0:
            orphans.append(cn["name"])

    conn.commit()
    conn.close()

    result = {
        "status": "ok",
        "node": name,
        "new_status": "inactive",
    }
    if orphans:
        result["orphans"] = orphans
        result["message"] = f"다음 노드가 고아가 됩니다: {', '.join(orphans)}"

    return result


def restore_node(name: str, db_path: str = DB_PATH) -> dict:
    """비활성화된 노드 복원 (inactive → active)."""
    conn = get_connection(db_path)

    node = conn.execute(
        "SELECT * FROM nodes WHERE LOWER(name) = LOWER(?) AND status = 'inactive'",
        (name,)
    ).fetchone()

    if not node:
        conn.close()
        return {"status": "error", "message": f"복원할 노드 '{name}'을 찾을 수 없습니다."}

    conn.execute(
        "UPDATE nodes SET status = 'active', updated_at = datetime('now') WHERE id = ?",
        (node["id"],)
    )
    conn.commit()
    conn.close()

    return {"status": "ok", "node": name, "new_status": "active"}


def _find_edge(conn, source_name: str, target_name: str):
    """소스-타겟 이름으로 엣지 검색 (양방향)."""
    return conn.execute(
        """SELECT e.*, src.name as source_name, tgt.name as target_name
           FROM edges e
           JOIN nodes src ON e.source_node_id = src.id
           JOIN nodes tgt ON e.target_node_id = tgt.id
           WHERE (LOWER(src.name) = LOWER(?) AND LOWER(tgt.name) = LOWER(?))
              OR (LOWER(src.name) = LOWER(?) AND LOWER(tgt.name) = LOWER(?))""",
        (source_name, target_name, target_name, source_name)
    ).fetchone()


def delete_edge(source_name: str, target_name: str, db_path: str = DB_PATH) -> dict:
    """엣지 삭제."""
    conn = get_connection(db_path)
    edge = _find_edge(conn, source_name, target_name)

    if not edge:
        conn.close()
        return {"status": "error", "message": f"'{source_name}' ── '{target_name}' 엣지를 찾을 수 없습니다."}

    conn.execute("DELETE FROM edges WHERE id = ?", (edge["id"],))
    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "deleted": f"{edge['source_name']} --({edge['type']})--> {edge['target_name']}",
    }


def update_edge(source_name: str, target_name: str, updates: dict,
                db_path: str = DB_PATH) -> dict:
    """엣지 속성 수정 (type)."""
    conn = get_connection(db_path)
    edge = _find_edge(conn, source_name, target_name)

    if not edge:
        conn.close()
        return {"status": "error", "message": f"'{source_name}' ── '{target_name}' 엣지를 찾을 수 없습니다."}

    allowed = {"type"}
    sets = []
    params = []
    for key, value in updates.items():
        if key in allowed:
            sets.append(f"{key} = ?")
            params.append(value)

    if not sets:
        conn.close()
        return {"status": "error", "message": "수정할 필드가 없습니다. (type)"}

    params.append(edge["id"])
    conn.execute(f"UPDATE edges SET {', '.join(sets)} WHERE id = ?", params)
    conn.commit()

    updated = conn.execute(
        """SELECT e.*, src.name as source_name, tgt.name as target_name
           FROM edges e
           JOIN nodes src ON e.source_node_id = src.id
           JOIN nodes tgt ON e.target_node_id = tgt.id
           WHERE e.id = ?""",
        (edge["id"],)
    ).fetchone()
    conn.close()

    return {"status": "ok", "edge": dict(updated)}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: update_node.py <command> <name> [args...]")
        print("Commands: update, deactivate, delete, restore, delete-edge, update-edge")
        sys.exit(1)

    cmd = sys.argv[1]
    name = sys.argv[2]

    if cmd == "update":
        if len(sys.argv) < 4:
            print("Usage: update_node.py update <name> '<json>'")
            sys.exit(1)
        updates = json.loads(sys.argv[3])
        result = update_node(name, updates)
    elif cmd in ("deactivate", "delete"):
        result = deactivate_node(name)
    elif cmd == "restore":
        result = restore_node(name)
    elif cmd == "delete-edge":
        if len(sys.argv) < 4:
            print("Usage: update_node.py delete-edge <source> <target>")
            sys.exit(1)
        result = delete_edge(name, sys.argv[3])
    elif cmd == "update-edge":
        if len(sys.argv) < 5:
            print("Usage: update_node.py update-edge <source> <target> '<json>'")
            sys.exit(1)
        result = update_edge(name, sys.argv[3], json.loads(sys.argv[4]))
    else:
        result = {"error": f"Unknown command: {cmd}"}

    print(json.dumps(result, ensure_ascii=False, indent=2))
