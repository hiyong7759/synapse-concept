"""Synapse CLI — 하이퍼그래프 엔진 테스트 인터페이스.

사용법:
  python3 -m engine.cli            # 대화형 모드 (MLX 서버 필요: python api/mlx_server.py)
  python3 -m engine.cli --no-llm  # LLM 없이 BFS 구조만
  python3 -m engine.cli --stats   # DB 통계
  python3 -m engine.cli --reset   # DB 초기화 (기존 데이터 삭제)
"""

from __future__ import annotations
import sys
import os
import argparse

# 패키지 루트를 sys.path에 추가 (직접 실행 시)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from engine.db import get_stats, init_db, DB_PATH
from engine.save import save, find_suspected_typos
from engine.retrieve import retrieve
from engine.llm import llm_extract
from typing import Optional


def cmd_stats() -> None:
    stats = get_stats()
    print(f"DB: {DB_PATH}")
    print(f"  문장 {stats['sentences_total']} (user={stats['sentences_user']}, assistant={stats['sentences_assistant']})")
    print(f"  노드 {stats['nodes_active']}/{stats['nodes_total']} (활성/전체)")
    print(f"  언급 {stats['node_mentions_total']} (문장 바구니 멤버십)")
    print(f"  카테고리 {stats['categories_total']} (카테고리 바구니 멤버십)")
    print(f"  별칭 {stats['aliases_total']}")
    print(f"  미해결 토큰 {stats['unresolved_total']}")


def cmd_reset() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"[reset] {DB_PATH} 삭제됨")
    init_db(DB_PATH)
    print("[reset] 빈 DB 생성 완료")


def cmd_typos() -> None:
    pairs = find_suspected_typos()
    if not pairs:
        print("오타 의심 쌍 없음")
        return
    print(f"오타 의심 쌍 {len(pairs)}개:")
    for p in pairs:
        a, b = p["node_a"], p["node_b"]
        print(f"  {a['name']} (id={a['id']}, mentions={a['mention_count']}) ↔ {b['name']} (id={b['id']}, mentions={b['mention_count']})")


def cmd_interactive(use_llm: bool) -> None:
    mode_tag = "" if use_llm else " [LLM 없음]"
    print(f"Synapse 그래프 엔진{mode_tag}")
    print("  입력: 자유 대화  |  /q 종료  |  /stats 통계  |  /extract <텍스트> 추출 확인")
    print()

    while True:
        try:
            text = input("synapse> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not text:
            continue
        if text == "/q":
            break
        if text == "/stats":
            cmd_stats()
            continue
        if text.startswith("/extract "):
            raw = text[9:]
            result = llm_extract(raw)
            for n in result.get("nodes", []):
                print(f"  [노드] {n['name']}")
            if result.get("deactivate"):
                print(f"  [deactivate] {result['deactivate']}")
            continue
        if text.startswith("/reset"):
            confirm = input("  DB를 초기화합니다. 계속? (y/N) ").strip().lower()
            if confirm == "y":
                cmd_reset()
            continue

        # 1. 인출: 관련 문장 수집 + 잠재적 답변 생성
        r_retrieve = retrieve(text, use_llm=use_llm)
        if r_retrieve.start_nodes:
            print(f"  [탐색] {' / '.join(r_retrieve.start_nodes)} → {len(r_retrieve.context_triples)}개 트리플")

        # 2. context_sentences: 인출된 트리플에서 원본 문장 추출 (문장 단위 dedup)
        seen_sentences: set[str] = set()
        context_sentences = []
        for t in r_retrieve.context_triples:
            if t.sentence_text and t.sentence_text not in seen_sentences:
                seen_sentences.add(t.sentence_text)
                context_sentences.append(t.sentence_text)

        # 3. 저장: context 포함하여 노드/엣지 추출
        r_save = save(text, use_llm=use_llm, context_sentences=context_sentences)

        # 4. 모호성 되물음 처리
        if r_save.question:
            print(f"  비서: {r_save.question}")
            answer = input("synapse> ").strip()
            if answer:
                r2 = save(answer, use_llm=use_llm)
                _print_save_result(r2)
            continue

        # 5. 저장 결과 출력
        _print_save_result(r_save)

        # 6. 인출 답변 출력
        if r_retrieve.answer:
            print(f"  비서: {r_retrieve.answer}")


def _print_save_result(r) -> None:
    if r.nodes_added:
        print(f"  [노드 신규] {', '.join(r.nodes_added)}")
    if r.mentions_added:
        print(f"  [언급 기록] {r.mentions_added}건")
    for marker in r.nodes_deactivated:
        print(f"  [상태변경] {marker}")
    if not r.nodes_added and not r.mentions_added and not r.nodes_deactivated:
        print("  (변경 없음)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Synapse CLI")
    parser.add_argument("--no-llm", action="store_true", help="LLM 없이 실행")
    parser.add_argument("--stats",  action="store_true", help="DB 통계 출력")
    parser.add_argument("--reset",  action="store_true", help="DB 초기화")
    parser.add_argument("--typos", action="store_true", help="오타 의심 노드 쌍 스캔")
    args = parser.parse_args()

    if args.stats:
        cmd_stats()
    elif args.typos:
        cmd_typos()
    elif args.reset:
        confirm = input(f"DB를 초기화합니다 ({DB_PATH}). 계속? (y/N) ").strip().lower()
        if confirm == "y":
            cmd_reset()
    else:
        cmd_interactive(use_llm=not args.no_llm)


if __name__ == "__main__":
    main()
