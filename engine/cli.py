"""Synapse CLI — 그래프 엔진 테스트 인터페이스.

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
from engine.save import save
from engine.retrieve import retrieve
from engine.llm import llm_extract


def _fmt_triple(src, label, tgt) -> str:
    return f"{src} —({label})→ {tgt}" if label else f"{src} → {tgt}"


def cmd_stats() -> None:
    stats = get_stats()
    print(f"DB: {DB_PATH}")
    print(f"  노드 {stats['nodes_active']}/{stats['nodes_total']} (활성/전체)")
    print(f"  엣지 {stats['edges_total']}")
    print(f"  별칭 {stats['aliases_total']}")


def cmd_reset() -> None:
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"[reset] {DB_PATH} 삭제됨")
    init_db(DB_PATH)
    print("[reset] 빈 DB 생성 완료")


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
                print(f"  [노드] {n['name']} ({n.get('category', '?')})")
            for e in result.get("edges", []):
                print(f"  [엣지] {_fmt_triple(e['source'], e.get('label'), e['target'])}")
            continue
        if text.startswith("/reset"):
            confirm = input("  DB를 초기화합니다. 계속? (y/N) ").strip().lower()
            if confirm == "y":
                cmd_reset()
            continue

        # 저장인지 질문인지 판단: "?" 또는 의문사가 있으면 질문, 아니면 저장
        is_question = "?" in text or any(
            kw in text for kw in ["언제", "어디", "뭐", "무슨", "누가", "어떻", "얼마", "몇"]
        )

        if is_question:
            r = retrieve(text, use_llm=use_llm)
            if r.start_nodes:
                print(f"  [탐색] {' / '.join(r.start_nodes)} → {len(r.context_triples)}개 트리플")
            if r.answer:
                print(f"  {r.answer}")
        else:
            r = save(text, use_llm=use_llm)

            if r.question:
                print(f"  비서: {r.question}")
                # 되물음 — 사용자 답변 받아서 재저장
                answer = input("synapse> ").strip()
                if answer:
                    r2 = save(answer, use_llm=use_llm)
                    _print_save_result(r2)
                continue

            _print_save_result(r)


def _print_save_result(r) -> None:
    for src, label, tgt in r.triples_added:
        print(f"  [저장] {_fmt_triple(src, label, tgt)}")
    for src, label, tgt in r.edges_deactivated:
        print(f"  [비활성] {_fmt_triple(src, label, tgt)}")
    for alias, node in r.aliases_added:
        print(f"  [별칭] {alias} → {node}")
    if not r.triples_added and not r.edges_deactivated:
        print("  (변경 없음)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Synapse CLI")
    parser.add_argument("--no-llm", action="store_true", help="LLM 없이 실행")
    parser.add_argument("--stats",  action="store_true", help="DB 통계 출력")
    parser.add_argument("--reset",  action="store_true", help="DB 초기화")
    args = parser.parse_args()

    if args.stats:
        cmd_stats()
    elif args.reset:
        confirm = input(f"DB를 초기화합니다 ({DB_PATH}). 계속? (y/N) ").strip().lower()
        if confirm == "y":
            cmd_reset()
    else:
        cmd_interactive(use_llm=not args.no_llm)


if __name__ == "__main__":
    main()
