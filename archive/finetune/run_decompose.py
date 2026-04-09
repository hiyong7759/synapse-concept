"""Run node decomposition on episodes using claude CLI.

Reads episodes.jsonl, calls `claude -p` for each episode with the system prompt,
and writes results to decompose_results.jsonl.

Usage:
    python3 finetune/run_decompose.py [--resume] [--workers 5] [--model opus]
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from config import (
    CLAUDE_CMD,
    CLAUDE_DECOMPOSE_MODEL,
    DECOMPOSE_RESULTS_FILE,
    EPISODES_FILE,
    OUTPUT_DIR,
    PARALLEL_WORKERS,
)
from system_prompt import SYSTEM_PROMPT


def decompose_one(episode: dict, model: str) -> dict:
    """Call claude -p with system prompt for a single episode."""
    ep_id = episode["id"]
    text = episode["text"]

    try:
        result = subprocess.run(
            [
                CLAUDE_CMD, "-p",
                "--model", model,
                "--system-prompt", SYSTEM_PROMPT,
                text,
            ],
            capture_output=True, text=True, timeout=120,
        )

        if result.returncode != 0:
            return {
                "id": ep_id,
                "input": text,
                "output": None,
                "error": result.stderr[:300],
            }

        raw = result.stdout.strip()

        # Try to parse JSON
        try:
            parsed = json.loads(raw)
            output = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
        except json.JSONDecodeError:
            # Try extracting from code block
            if "```" in raw:
                json_str = raw.split("```")[1]
                if json_str.startswith("json"):
                    json_str = json_str[4:]
                json_str = json_str.strip()
                try:
                    parsed = json.loads(json_str)
                    output = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
                except json.JSONDecodeError:
                    return {"id": ep_id, "input": text, "output": None, "error": "json_parse_error", "raw": raw[:500]}
            else:
                return {"id": ep_id, "input": text, "output": None, "error": "json_parse_error", "raw": raw[:500]}

        return {"id": ep_id, "input": text, "output": output, "error": None}

    except subprocess.TimeoutExpired:
        return {"id": ep_id, "input": text, "output": None, "error": "timeout"}
    except Exception as e:
        return {"id": ep_id, "input": text, "output": None, "error": str(e)[:200]}


def run(resume: bool = False, workers: int = PARALLEL_WORKERS, model: str = CLAUDE_DECOMPOSE_MODEL):
    """Run decomposition on all episodes."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load episodes
    episodes = []
    with open(EPISODES_FILE, encoding="utf-8") as f:
        for line in f:
            episodes.append(json.loads(line))

    print(f"Loaded {len(episodes)} episodes", flush=True)

    # Resume: skip already processed
    done_ids = set()
    if resume and DECOMPOSE_RESULTS_FILE.exists():
        with open(DECOMPOSE_RESULTS_FILE, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                if r.get("output"):  # only count successful ones
                    done_ids.add(r["id"])
        print(f"Resuming: {len(done_ids)} already done, {len(episodes) - len(done_ids)} remaining")

    remaining = [ep for ep in episodes if ep["id"] not in done_ids]

    if not remaining:
        print("All episodes already processed.")
        return

    print(f"Processing {len(remaining)} episodes with {workers} workers (model: {model})", flush=True)
    print(f"Output: {DECOMPOSE_RESULTS_FILE}", flush=True)
    sys.stdout.flush()

    success = 0
    errors = 0
    start = time.time()

    # Open in append mode for resume support
    mode = "a" if resume and done_ids else "w"
    with open(DECOMPOSE_RESULTS_FILE, mode, encoding="utf-8") as f:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(decompose_one, ep, model): ep
                for ep in remaining
            }

            for i, future in enumerate(as_completed(futures), 1):
                result = future.result()
                f.write(json.dumps(result, ensure_ascii=False) + "\n")
                f.flush()

                ep = futures[future]
                status = "OK" if result["output"] else f"ERR: {result.get('error', '?')[:40]}"
                elapsed = time.time() - start
                rate = i / elapsed if elapsed > 0 else 0

                if rate > 0:
                    print(f"  [{i}/{len(remaining)}] {ep['id']} {status} "
                          f"({rate:.1f}/s, ~{(len(remaining)-i)/rate:.0f}s left)", flush=True)
                else:
                    print(f"  [{i}/{len(remaining)}] {ep['id']} {status}", flush=True)

                if result["output"]:
                    success += 1
                else:
                    errors += 1

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.0f}s")
    print(f"  Success: {success}")
    print(f"  Errors: {errors}")
    print(f"  Total: {success + errors}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run decomposition via claude CLI")
    parser.add_argument("--resume", action="store_true", help="Skip already processed episodes")
    parser.add_argument("--workers", type=int, default=PARALLEL_WORKERS)
    parser.add_argument("--model", type=str, default=CLAUDE_DECOMPOSE_MODEL)
    args = parser.parse_args()

    run(resume=args.resume, workers=args.workers, model=args.model)
