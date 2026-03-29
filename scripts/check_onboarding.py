#!/usr/bin/env python3
"""온보딩 상태 확인 — 그래프가 개별화 가능한 수준인지 판단.

단계별 시뮬레이션으로 검증된 기준:
- 노드 수보다 도메인 커버리지가 개별화율을 결정
- 새 도메인 추가 시 개별화율 점프 (2→5노드: +34%p, 9→15노드: +17%p)
- 같은 도메인에 노드 추가는 개별화율 변화 없음 (19노드 75% = 15노드 75%)
- 15노드/4도메인 시점에서 75% 개별화 달성 (실질적 임계점)

온보딩 완료 기준:
1. 최소 4개 이상의 도메인 (개별화율 점프의 핵심 요인)
2. 총 노드 15개 이상 (75% 개별화 달성 시점)
3. 최소 3개 도메인에 각 2개 이상 노드 (단일 노드 도메인은 맥락 불충분)
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from init_db import get_connection, DB_PATH

# 온보딩 완료 기준
MIN_DOMAINS = 4          # 최소 도메인 수
MIN_TOTAL_NODES = 15     # 최소 총 노드 수 (75% 개별화 달성 시점)
MIN_COVERED_DOMAINS = 3  # 최소 N개 도메인에 각 2개 이상 노드


def check_onboarding(db_path: str = DB_PATH) -> dict:
    """온보딩 상태 확인."""
    conn = get_connection(db_path)

    # 전체 통계
    total_nodes = conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE status = 'active'"
    ).fetchone()[0]

    # 도메인별 노드 수
    domain_rows = conn.execute(
        """SELECT domain, COUNT(*) as count
           FROM nodes WHERE status = 'active' AND domain != ''
           GROUP BY domain ORDER BY count DESC"""
    ).fetchall()
    domains = {r["domain"]: r["count"] for r in domain_rows}

    # safety 노드 수
    safety_count = conn.execute(
        "SELECT COUNT(*) FROM nodes WHERE safety = 1 AND status = 'active'"
    ).fetchone()[0]

    conn.close()

    # 판정
    num_domains = len(domains)
    covered_domains = sum(1 for count in domains.values() if count >= 2)

    checks = {
        "domains": {
            "current": num_domains,
            "required": MIN_DOMAINS,
            "passed": num_domains >= MIN_DOMAINS,
        },
        "total_nodes": {
            "current": total_nodes,
            "required": MIN_TOTAL_NODES,
            "passed": total_nodes >= MIN_TOTAL_NODES,
        },
        "covered_domains": {
            "current": covered_domains,
            "required": MIN_COVERED_DOMAINS,
            "passed": covered_domains >= MIN_COVERED_DOMAINS,
        },
    }

    all_passed = all(c["passed"] for c in checks.values())

    # 부족한 부분 안내
    suggestions = []
    if not checks["total_nodes"]["passed"]:
        gap = MIN_TOTAL_NODES - total_nodes
        suggestions.append(f"노드가 {gap}개 더 필요합니다")
    if not checks["domains"]["passed"]:
        gap = MIN_DOMAINS - num_domains
        suggestions.append(f"도메인이 {gap}개 더 필요합니다")

    # 빈 도메인 카테고리 제안
    common_domains = {"기술", "장비", "건강", "프로젝트", "위치", "용도", "취미", "음식", "운동"}
    missing = common_domains - set(domains.keys())
    if missing and not all_passed:
        suggestions.append(f"아직 없는 분야: {', '.join(sorted(missing))}")

    return {
        "status": "complete" if all_passed else "onboarding",
        "checks": checks,
        "domains": domains,
        "safety_nodes": safety_count,
        "suggestions": suggestions,
    }


if __name__ == "__main__":
    result = check_onboarding()
    print(json.dumps(result, ensure_ascii=False, indent=2))
