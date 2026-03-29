#!/usr/bin/env python3
"""개별화 임계점 시뮬레이션.

다양한 질문에 대해 그래프 크기별 맥락 품질을 측정한다.
- 매칭되는 시작 노드 수
- 탐색되는 전체 노드 수
- 질문 유형별 커버리지
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from get_context import get_context
from init_db import get_connection, DB_PATH

# 다양한 페르소나 질문 (일상 ~ 전문)
TEST_QUERIES = [
    # 개발 (구체적)
    ("빌드가 안 돼", "개발-구체"),
    ("React Native에서 useEffect 무한루프", "개발-구체"),
    ("Docker 컨테이너가 안 올라가", "개발-구체"),
    ("FCM 푸시 알림 구현하려는데", "개발-구체"),
    # 개발 (넓은)
    ("개발 환경 정리하고 싶은데", "개발-넓음"),
    ("이력서 써줘", "개발-넓음"),
    ("새 프로젝트 기술 스택 추천해줘", "개발-넓음"),
    # 건강/운동
    ("허리 때문에 할 수 있는 운동 추천해줘", "건강"),
    ("헬스장에서 하체 운동 루틴", "건강"),
    ("점심 뭐 먹을까", "일상-음식"),
    # 장비
    ("로컬 LLM 돌리려는데 어떤 장비가 좋아?", "장비"),
    ("맥북에서 Homebrew 설치가 안 돼", "장비"),
    # 무관한 질문 (매칭 안 되어야 함)
    ("오늘 날씨 어때?", "무관"),
    ("영화 추천해줘", "무관"),
    ("파이썬 리스트 컴프리헨션 문법", "일반지식"),
]


def evaluate_graph():
    """현재 그래프 상태에서 모든 질문의 맥락 품질 측정."""
    conn = get_connection(DB_PATH)
    total_nodes = conn.execute("SELECT COUNT(*) FROM nodes WHERE status='active'").fetchone()[0]
    total_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
    conn.close()

    results = {
        "graph_size": {"nodes": total_nodes, "edges": total_edges},
        "queries": [],
        "summary": {}
    }

    category_hits = {}

    for query, category in TEST_QUERIES:
        ctx = get_context(query)
        node_count = ctx["node_count"]
        edge_count = ctx["edge_count"]
        nodes_used = ctx["nodes_used"]

        safety = ctx.get("safety_nodes", [])
        hit = node_count > 0
        results["queries"].append({
            "query": query,
            "category": category,
            "nodes_found": node_count,
            "edges_found": edge_count,
            "nodes": nodes_used[:10],
            "safety": safety,
            "has_context": hit,
        })

        if category not in category_hits:
            category_hits[category] = {"total": 0, "hit": 0, "avg_nodes": 0}
        category_hits[category]["total"] += 1
        if hit:
            category_hits[category]["hit"] += 1
        category_hits[category]["avg_nodes"] += node_count

    # 카테고리별 요약
    for cat, stats in category_hits.items():
        stats["avg_nodes"] = round(stats["avg_nodes"] / stats["total"], 1)
        stats["hit_rate"] = f"{stats['hit']}/{stats['total']}"

    results["summary"] = category_hits

    # 전체 개별화 점수 (무관 제외)
    relevant = [q for q in results["queries"] if q["category"] not in ("무관", "일반지식")]
    hit_count = sum(1 for q in relevant if q["has_context"])
    results["personalization_score"] = {
        "relevant_queries": len(relevant),
        "contextualized": hit_count,
        "rate": f"{hit_count}/{len(relevant)} ({round(hit_count/len(relevant)*100)}%)" if relevant else "N/A",
    }

    return results


if __name__ == "__main__":
    results = evaluate_graph()
    print(json.dumps(results, ensure_ascii=False, indent=2))
