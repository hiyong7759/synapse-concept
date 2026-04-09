"""Convert decompose_results.jsonl → training.jsonl (ChatML format).

Usage:
    python3 finetune/collect_results.py
"""

import json

from config import DECOMPOSE_RESULTS_FILE, OUTPUT_DIR, TRAINING_FILE
from system_prompt import SYSTEM_PROMPT


def collect():
    """Parse decompose results and create training JSONL."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results = []
    with open(DECOMPOSE_RESULTS_FILE, encoding="utf-8") as f:
        for line in f:
            results.append(json.loads(line))

    print(f"Loaded {len(results)} decompose results")

    training_data = []
    skipped = 0

    for result in results:
        if not result.get("output"):
            skipped += 1
            continue

        user_text = result["input"]
        assistant_text = result["output"]

        # Validate JSON structure
        try:
            parsed = json.loads(assistant_text)
        except json.JSONDecodeError:
            skipped += 1
            continue

        if "nodes" not in parsed or "edges" not in parsed:
            skipped += 1
            continue

        # Ensure minified
        assistant_text = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))

        entry = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text},
                {"role": "assistant", "content": assistant_text},
            ]
        }
        training_data.append(entry)

    with open(TRAINING_FILE, "w", encoding="utf-8") as f:
        for entry in training_data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\nTraining entries: {len(training_data)}")
    print(f"Skipped: {skipped}")
    print(f"Saved to {TRAINING_FILE}")


if __name__ == "__main__":
    collect()
