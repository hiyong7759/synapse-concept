"""extract-core 학습 데이터 v15 포맷 전환.

전: {"retention": "memory|daily", "nodes": [{"name": "X", "category": "Y"}]}
후: {"nodes": ["X", ...]}  (retention·category 드롭)

사용:
    python3 scripts/mlx/convert_extract_core_v15.py
        - 기본: train.jsonl + valid.jsonl 모두 변환
        - 원본은 *.pre-v15-backup으로 보존
"""
from __future__ import annotations
import json
from pathlib import Path

NEW_SYSTEM_PROMPT = """한국어 문장에서 지식 하이퍼그래프의 노드를 추출하라.
JSON만 출력. 다른 텍스트 금지.

출력 형식:
{"nodes":["노드명", ...]}

규칙:
- 노드는 원자. 하나의 개념 = 하나의 노드.
- 1인칭(나/내/저/제)이 문장에 명시된 경우 "나" 노드로 추출. 문장에 없는 1인칭 추가 금지.
- 3인칭 주어는 원문 그대로 노드 추출.
- 부정부사(안, 못)는 독립 노드다. 예: "스타벅스 안 좋아" → ["스타벅스", "안", "좋아"].
- 추출할 노드가 없는 대화 → {"nodes":[]}"""


def convert_sample(sample: dict) -> dict:
    """한 샘플을 v15 포맷으로 변환."""
    msgs = sample["messages"]
    new_msgs = []
    for m in msgs:
        if m["role"] == "system":
            new_msgs.append({"role": "system", "content": NEW_SYSTEM_PROMPT})
        elif m["role"] == "assistant":
            ast = json.loads(m["content"])
            # retention 폐기, nodes는 이름만 추출
            nodes = []
            for nd in ast.get("nodes", []):
                if isinstance(nd, dict):
                    nm = nd.get("name", "").strip()
                    if nm:
                        nodes.append(nm)
                elif isinstance(nd, str):
                    nm = nd.strip()
                    if nm:
                        nodes.append(nm)
            new_content = json.dumps({"nodes": nodes}, ensure_ascii=False)
            new_msgs.append({"role": "assistant", "content": new_content})
        else:
            new_msgs.append(m)
    return {"messages": new_msgs}


def convert_file(src: Path) -> dict:
    """파일 변환. 백업·검증 포함."""
    backup = src.with_suffix(src.suffix + ".pre-v15-backup")
    if not backup.exists():
        backup.write_bytes(src.read_bytes())
        print(f"  백업 생성: {backup.name}")
    else:
        print(f"  백업 이미 존재: {backup.name} (유지)")

    in_lines = src.read_text().splitlines()
    out_lines = []
    errors = []
    for i, line in enumerate(in_lines):
        try:
            d = json.loads(line)
            new_d = convert_sample(d)
            out_lines.append(json.dumps(new_d, ensure_ascii=False))
        except Exception as e:
            errors.append((i, str(e)))

    if errors:
        print(f"  ⚠️  에러 {len(errors)}건: {errors[:3]}")
        return {"src": str(src), "ok": False, "errors": errors}

    src.write_text("\n".join(out_lines) + "\n")
    return {
        "src": str(src),
        "ok": True,
        "in_count": len(in_lines),
        "out_count": len(out_lines),
    }


def verify_file(src: Path) -> dict:
    """변환 결과 검증: JSON 파싱, 필드 제거 확인, 샘플 출력."""
    bad_assist = []
    has_retention = 0
    has_category = 0
    total = 0
    node_counts = []

    for i, line in enumerate(src.read_text().splitlines()):
        total += 1
        try:
            d = json.loads(line)
            ast_c = next(m["content"] for m in d["messages"] if m["role"] == "assistant")
            ast = json.loads(ast_c)
            if "retention" in ast:
                has_retention += 1
            for nd in ast.get("nodes", []):
                if isinstance(nd, dict) and "category" in nd:
                    has_category += 1
            node_counts.append(len(ast.get("nodes", [])))
        except Exception as e:
            bad_assist.append((i, str(e)))

    return {
        "src": str(src),
        "total": total,
        "parse_fail": len(bad_assist),
        "has_retention": has_retention,
        "has_category": has_category,
        "avg_nodes": sum(node_counts) / len(node_counts) if node_counts else 0,
        "max_nodes": max(node_counts) if node_counts else 0,
    }


def main():
    root = Path(__file__).parent.parent.parent
    targets = [
        root / "data/finetune/tasks/extract-core/train.jsonl",
        root / "data/finetune/tasks/extract-core/valid.jsonl",
    ]
    print("=" * 60)
    print("extract-core v15 포맷 변환")
    print("=" * 60)
    for t in targets:
        print(f"\n▶ {t.name}")
        r = convert_file(t)
        if not r["ok"]:
            print("  실패. 중단.")
            return
        print(f"  변환: {r['in_count']} → {r['out_count']} 샘플")
        v = verify_file(t)
        print(f"  검증:")
        print(f"    JSON 파싱 실패: {v['parse_fail']}")
        print(f"    retention 잔존: {v['has_retention']}")
        print(f"    category 잔존: {v['has_category']}")
        print(f"    노드 수 평균/최대: {v['avg_nodes']:.1f} / {v['max_nodes']}")

    print("\n✅ 완료")


if __name__ == "__main__":
    main()
