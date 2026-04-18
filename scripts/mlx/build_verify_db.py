#!/usr/bin/env python3
"""검증용 임시 DB 구축.

extract-core train.jsonl의 user 문장들을 synapse save 파이프라인으로
태워서 노드/엣지/sentences를 실제로 쌓는다.

프로덕션 DB(~/.synapse/synapse.db)는 건드리지 않음.
SYNAPSE_DATA_DIR 환경변수로 /tmp/synapse_verify_db 사용.

사용:
  python scripts/mlx/build_verify_db.py --n 30
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TRAIN_FILE = ROOT / "data/finetune/tasks/extract-core/train.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30, help="쌓을 문장 수")
    ap.add_argument("--data-dir", default="/tmp/synapse_verify_db")
    ap.add_argument("--reset", action="store_true", help="기존 검증 DB 삭제 후 시작")
    ap.add_argument("--markdown", action="store_true", help="입력을 마크다운 모드로 래핑 (save-pronoun 스킵)")
    args = ap.parse_args()

    os.environ["SYNAPSE_DATA_DIR"] = args.data_dir
    Path(args.data_dir).mkdir(parents=True, exist_ok=True)

    if args.reset:
        db_path = Path(args.data_dir) / "synapse.db"
        if db_path.exists():
            db_path.unlink()
            print(f"기존 DB 삭제: {db_path}")

    # 경로 설정 후 engine import
    sys.path.insert(0, str(ROOT))
    from engine.db import init_db, get_stats
    from engine.save import save

    init_db()
    print(f"검증 DB: {args.data_dir}/synapse.db")

    # 샘플 문장 로드
    sentences = []
    with TRAIN_FILE.open() as f:
        for line in f:
            if len(sentences) >= args.n:
                break
            d = json.loads(line)
            user = next(m["content"] for m in d["messages"] if m["role"] == "user")
            sentences.append(user.strip())

    print(f"투입 문장: {len(sentences)}건\n")

    ok = 0
    fail = 0
    t0 = time.time()
    for i, sent in enumerate(sentences):
        elapsed_sent = time.time()
        input_text = f"# 기록\n{sent}" if args.markdown else sent
        try:
            result = save(input_text)
            dt = time.time() - elapsed_sent
            print(f"  [{i+1}/{len(sentences)}] {dt:.1f}s  nodes+{len(result.nodes_added)} edges+{len(result.edge_ids_added)}  {sent[:50]}")
            ok += 1
        except Exception as e:
            print(f"  [{i+1}/{len(sentences)}] FAIL: {e}  {sent[:50]}")
            fail += 1

    total = time.time() - t0
    print(f"\n완료: ok={ok} fail={fail} 총 {total:.0f}초 ({total/max(ok,1):.1f}초/건)")
    print("\nDB 통계:")
    for k, v in get_stats().items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
