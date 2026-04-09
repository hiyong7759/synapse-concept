"""Extract random 10~20% samples for human review.

Usage:
    python finetune/sample_review.py [--ratio 0.15] [--count 50]
"""

import argparse
import json
import random

from config import TRAINING_FILE


def format_entry(idx: int, entry: dict) -> str:
    """Format a single training entry for human-readable review."""
    user_text = entry["messages"][1]["content"]
    assistant_text = entry["messages"][2]["content"]

    try:
        data = json.loads(assistant_text)
    except json.JSONDecodeError:
        return f"[{idx:04d}] JSON PARSE ERROR\n입력: {user_text}\n응답: {assistant_text[:200]}\n"

    nodes = data.get("nodes", [])
    edges = data.get("edges", [])

    lines = [f"[{idx:04d}]"]
    lines.append(f"입력: {user_text}")

    if not nodes and not edges:
        lines.append("결과: (빈 결과 — 일상대화)")
    else:
        node_strs = []
        for n in nodes:
            s = f"{n['name']}[{n.get('domain', '?')}]"
            if n.get("safety"):
                s += " ⚠SAFETY"
            node_strs.append(s)
        lines.append(f"노드: {', '.join(node_strs)}")

        if edges:
            lines.append("엣지:")
            for e in edges:
                if e.get("type") in ("same", "similar"):
                    lines.append(f"  {e['source']} ──({e['type']})── {e['target']}")
                else:
                    label = e.get("label", "?")
                    lines.append(f"  {e['source']} ──({label})──▶ {e['target']}")

    lines.append("판정: [  OK  /  수정필요  /  프롬프트보정  ]")
    lines.append("---")
    return "\n".join(lines)


def review(ratio: float = 0.15, count: int | None = None):
    """Sample and display entries for review."""
    entries = []
    with open(TRAINING_FILE, encoding="utf-8") as f:
        for line in f:
            entries.append(json.loads(line))

    if count:
        sample_size = min(count, len(entries))
    else:
        sample_size = max(1, int(len(entries) * ratio))

    indices = sorted(random.sample(range(len(entries)), sample_size))

    print(f"=== Sample Review: {sample_size}/{len(entries)} entries ({sample_size/len(entries)*100:.1f}%) ===\n")

    for idx in indices:
        print(format_entry(idx, entries[idx]))
        print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sample review for human inspection")
    parser.add_argument("--ratio", type=float, default=0.15, help="Sample ratio (default: 0.15)")
    parser.add_argument("--count", type=int, help="Exact sample count (overrides ratio)")
    args = parser.parse_args()

    review(ratio=args.ratio, count=args.count)
