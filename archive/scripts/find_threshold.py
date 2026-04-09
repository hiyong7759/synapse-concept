#!/usr/bin/env python3
"""온보딩 임계점 탐색 — 노드를 점진적으로 추가하며 개별화율 변화를 측정.

단계별로 노드를 추가하고, 각 단계에서 전체 테스트 질문의 개별화율을 측정한다.
어느 시점에서 의미 있는 개별화가 시작되는지 찾는다.
"""

import json
import sys
import os
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(__file__))
from init_db import init_db, get_connection
from add_nodes import add_from_json
from get_context import get_context

# 단계별 추가 데이터 — 현실적 온보딩 순서
# 사용자가 정보를 하나씩 알려주는 시나리오
STAGES = [
    {
        "label": "1단계: 장비만",
        "nodes": [
            {"name": "맥미니", "domain": "장비"},
            {"name": "M4", "domain": "장비"},
        ],
        "edges": [
            {"source": "맥미니", "target": "M4", "type": "link", "label": "스펙"},
        ]
    },
    {
        "label": "2단계: +개발환경",
        "nodes": [
            {"name": "macOS", "domain": "기술"},
            {"name": "Docker", "domain": "기술"},
            {"name": "개발", "domain": "용도"},
        ],
        "edges": [
            {"source": "맥미니", "target": "macOS", "type": "link", "label": "OS"},
            {"source": "맥미니", "target": "Docker", "type": "link", "label": "설치됨"},
            {"source": "맥미니", "target": "개발", "type": "link", "label": "용도"},
        ]
    },
    {
        "label": "3단계: +프로젝트",
        "nodes": [
            {"name": "React Native", "domain": "기술"},
            {"name": "Expo", "domain": "기술"},
            {"name": "Poomacy", "domain": "프로젝트"},
            {"name": "EAS Build", "domain": "기술"},
        ],
        "edges": [
            {"source": "React Native", "target": "Poomacy", "type": "link", "label": "프레임워크"},
            {"source": "Expo", "target": "React Native", "type": "link", "label": "빌드도구"},
            {"source": "EAS Build", "target": "Expo", "type": "link", "label": "배포"},
        ]
    },
    {
        "label": "4단계: +건강",
        "nodes": [
            {"name": "허리디스크", "domain": "건강", "safety": True, "safety_rule": "운동 관련 질문 시 반드시 고려"},
            {"name": "L4-L5", "domain": "건강"},
            {"name": "데드리프트", "domain": "운동"},
            {"name": "트랩바", "domain": "운동"},
            {"name": "재발", "domain": "건강"},
            {"name": "허리부담적음", "domain": "운동"},
        ],
        "edges": [
            {"source": "허리디스크", "target": "L4-L5", "type": "link", "label": "부위"},
            {"source": "허리디스크", "target": "데드리프트", "type": "link", "label": "주의운동"},
            {"source": "데드리프트", "target": "재발", "type": "link", "label": "위험"},
            {"source": "데드리프트", "target": "트랩바", "type": "link", "label": "대안"},
            {"source": "트랩바", "target": "허리부담적음", "type": "link", "label": "장점"},
        ]
    },
    {
        "label": "5단계: +장비2(GPU)",
        "nodes": [
            {"name": "RTX3080", "domain": "장비"},
            {"name": "llama.cpp", "domain": "기술"},
            {"name": "13B", "domain": "기술"},
            {"name": "윈도우", "domain": "기술"},
        ],
        "edges": [
            {"source": "RTX3080", "target": "llama.cpp", "type": "link", "label": "GPU"},
            {"source": "llama.cpp", "target": "13B", "type": "link", "label": "모델크기"},
            {"source": "13B", "target": "RTX3080", "type": "link", "label": "가능"},
            {"source": "RTX3080", "target": "윈도우", "type": "link", "label": "OS"},
        ]
    },
    {
        "label": "6단계: +기타(음식safety, FCM, 회사)",
        "nodes": [
            {"name": "땅콩알레르기", "domain": "건강", "safety": True, "safety_rule": "음식 관련 질문 시 반드시 고려"},
            {"name": "FCM", "domain": "기술"},
            {"name": "Spring Boot", "domain": "기술"},
            {"name": "firebase-admin", "domain": "기술"},
            {"name": "Homebrew", "domain": "기술"},
            {"name": "Synapse", "domain": "프로젝트"},
            {"name": "SQLite", "domain": "기술"},
            {"name": "Python", "domain": "기술"},
        ],
        "edges": [
            {"source": "FCM", "target": "Spring Boot", "type": "link", "label": "패키지분리방식연동"},
            {"source": "FCM", "target": "firebase-admin", "type": "link", "label": "의존성충돌경험"},
            {"source": "Homebrew", "target": "macOS", "type": "link", "label": "패키지매니저"},
            {"source": "Synapse", "target": "SQLite", "type": "link", "label": "저장소"},
            {"source": "Synapse", "target": "Python", "type": "link", "label": "구현언어"},
            {"source": "맥미니", "target": "Synapse", "type": "link", "label": "개발환경"},
        ]
    },
    {
        "label": "7단계: +이력/동의어/음식선호",
        "nodes": [
            {"name": "이력", "domain": "프로필"},
            {"name": "프로필", "domain": "프로필"},
            {"name": "식사", "domain": "음식"},
            {"name": "점심", "domain": "음식"},
            {"name": "한식", "domain": "음식"},
            {"name": "매운거", "domain": "음식"},
        ],
        "edges": [
            {"source": "이력", "target": "프로필", "type": "same", "label": "동의어"},
            {"source": "이력", "target": "React Native", "type": "link", "label": "기술스택"},
            {"source": "이력", "target": "Python", "type": "link", "label": "기술스택"},
            {"source": "이력", "target": "Poomacy", "type": "link", "label": "프로젝트"},
            {"source": "이력", "target": "Synapse", "type": "link", "label": "프로젝트"},
            {"source": "이력", "target": "A기관", "type": "link", "label": "경력"},
            {"source": "점심", "target": "식사", "type": "same", "label": "동의어"},
            {"source": "식사", "target": "한식", "type": "link", "label": "선호"},
            {"source": "식사", "target": "매운거", "type": "link", "label": "선호"},
        ]
    },
]

# 테스트 질문 (무관/일반지식 제외 — 개별화 대상만)
TEST_QUERIES = [
    ("빌드가 안 돼", "개발"),
    ("React Native에서 useEffect 무한루프", "개발"),
    ("Docker 컨테이너가 안 올라가", "개발"),
    ("FCM 푸시 알림 구현하려는데", "개발"),
    ("개발 환경 정리하고 싶은데", "개발"),
    ("이력서 써줘", "개발"),
    ("새 프로젝트 기술 스택 추천해줘", "개발"),
    ("허리 때문에 할 수 있는 운동 추천해줘", "건강"),
    ("헬스장에서 하체 운동 루틴", "건강"),
    ("점심 뭐 먹을까", "일상"),
    ("로컬 LLM 돌리려는데 어떤 장비가 좋아?", "장비"),
    ("맥북에서 Homebrew 설치가 안 돼", "장비"),
]


def run_stage(db_path):
    """현재 DB 상태에서 모든 질문 테스트."""
    results = []
    for query, category in TEST_QUERIES:
        ctx = get_context(query, db_path=db_path)
        # safety만 있고 맥락 노드 없으면 매칭 실패로 처리
        has_context = ctx["node_count"] > 0
        results.append({
            "query": query,
            "category": category,
            "nodes": ctx["node_count"],
            "hit": has_context,
        })
    return results


def main():
    # 임시 DB
    tmp_dir = tempfile.mkdtemp()
    db_path = os.path.join(tmp_dir, "test.db")
    init_db(db_path)

    print("=" * 70)
    print("온보딩 임계점 탐색 — 단계별 노드 추가 시 개별화율 변화")
    print("=" * 70)

    cumulative_nodes = 0
    cumulative_edges = 0

    for stage in STAGES:
        # 노드/엣지 추가
        add_from_json(stage, db_path=db_path)

        conn = get_connection(db_path)
        cumulative_nodes = conn.execute("SELECT COUNT(*) FROM nodes WHERE status='active'").fetchone()[0]
        cumulative_edges = conn.execute("SELECT COUNT(*) FROM edges").fetchone()[0]
        domains = conn.execute(
            "SELECT domain, COUNT(*) as c FROM nodes WHERE status='active' AND domain!='' GROUP BY domain"
        ).fetchall()
        conn.close()

        # 테스트
        results = run_stage(db_path)
        hits = sum(1 for r in results if r["hit"])
        total = len(results)
        rate = round(hits / total * 100)

        # 카테고리별
        cat_stats = {}
        for r in results:
            cat = r["category"]
            if cat not in cat_stats:
                cat_stats[cat] = {"total": 0, "hit": 0}
            cat_stats[cat]["total"] += 1
            if r["hit"]:
                cat_stats[cat]["hit"] += 1

        print(f"\n{stage['label']}")
        print(f"  노드: {cumulative_nodes}개, 엣지: {cumulative_edges}개, 도메인: {len(domains)}개")
        print(f"  개별화율: {hits}/{total} ({rate}%)")
        for cat, s in cat_stats.items():
            marker = "✅" if s["hit"] == s["total"] else f"⬜ {s['hit']}/{s['total']}"
            print(f"    {cat}: {marker}")

        # 매칭 실패 목록
        misses = [r["query"] for r in results if not r["hit"]]
        if misses:
            print(f"  미스: {', '.join(misses)}")

    # 정리
    shutil.rmtree(tmp_dir)

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
