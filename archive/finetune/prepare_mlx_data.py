"""Prepare fine-tuning data for mlx-lm LoRA training.

Merges personal + org JSONL files, shuffles, splits 90/10 into
train.jsonl / valid.jsonl under data/mlx_train/.

Usage:
    python3 prepare_mlx_data.py [--mode personal|org|all] [--tasks 1,2,3]
"""

import argparse
import json
import random
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
OUT_DIR = DATA_DIR / "mlx_train"

PERSONAL_FILES = {
    1:    DATA_DIR / "task1_state_change.jsonl",
    2:    DATA_DIR / "task2_pronoun_adverb.jsonl",
    3:    DATA_DIR / "task3_retrieval_filter.jsonl",
    4:    DATA_DIR / "task4_retrieval_expand.jsonl",
    "5a": DATA_DIR / "task5a_sensitivity_triple.jsonl",
    "5b": DATA_DIR / "task5b_sensitivity_context.jsonl",
}

ORG_FILES = {
    0:    DATA_DIR / "org" / "task0_augment_routing.jsonl",
    1:    DATA_DIR / "org" / "task1_state_change.jsonl",
    2:    DATA_DIR / "org" / "task2_subject_resolution.jsonl",
    3:    DATA_DIR / "org" / "task3_retrieval_filter.jsonl",
    4:    DATA_DIR / "org" / "task4_retrieval_expand.jsonl",
    "5a": DATA_DIR / "org" / "task5a_sensitivity_triple.jsonl",
    "5b": DATA_DIR / "org" / "task5b_sensitivity_context.jsonl",
}


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        print(f"  WARN: {path} not found, skipping")
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="all", choices=["personal", "org", "all"])
    parser.add_argument("--tasks", default=None, help="Comma-separated task ids (e.g. 1,2,3,5a)")
    parser.add_argument("--val-ratio", type=float, default=0.1)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    # Select files
    files = {}
    if args.mode in ("personal", "all"):
        files.update({f"p{k}": v for k, v in PERSONAL_FILES.items()})
    if args.mode in ("org", "all"):
        files.update({f"o{k}": v for k, v in ORG_FILES.items()})

    # Filter by task if specified
    if args.tasks:
        allowed = set(args.tasks.split(","))
        files = {k: v for k, v in files.items()
                 if str(k).lstrip("po") in allowed}

    # Load all
    all_examples = []
    for key, path in files.items():
        examples = load_jsonl(path)
        all_examples.extend(examples)
        print(f"  {path.name}: {len(examples)} examples")

    print(f"\nTotal: {len(all_examples)} examples")

    # Shuffle + split
    random.seed(args.seed)
    random.shuffle(all_examples)

    n_val = max(1, int(len(all_examples) * args.val_ratio))
    valid = all_examples[:n_val]
    train = all_examples[n_val:]

    print(f"Train: {len(train)}, Valid: {len(valid)}")

    # Write
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for split, data in [("train", train), ("valid", valid)]:
        path = OUT_DIR / f"{split}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for e in data:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"  → {path}")

    print("\nDone. Ready for mlx_lm.lora training.")


if __name__ == "__main__":
    main()
