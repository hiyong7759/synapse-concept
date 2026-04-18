#!/usr/bin/env python3
"""Sequential MLX QLoRA trainer for all Synapse tasks.

Usage:
  python scripts/mlx/train_all.py              # run all tasks
  python scripts/mlx/train_all.py --only extract-core --iters 100   # smoke test
  python scripts/mlx/train_all.py --skip extract-core,retrieve-filter

Base config: configs/mlx/_base.yaml
Data:        data/finetune/tasks/<task>/{train,valid}.jsonl
Adapters:    runpod_output/mlx_adapters/<task>/
Logs:        runpod_output/mlx_logs/<task>.log
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS_DIR = ROOT / "data/finetune/tasks"
BASE_CFG = ROOT / "configs/mlx/_base.yaml"
ADAPTER_ROOT = ROOT / "runpod_output/mlx_adapters"
LOG_ROOT = ROOT / "runpod_output/mlx_logs"

EPOCHS = 3
EFFECTIVE_BATCH = 4  # batch_size(1) * grad_accumulation_steps(4)
MIN_ITERS = 150


def count_lines(p: Path) -> int:
    with p.open() as f:
        return sum(1 for _ in f)


def discover_tasks() -> list[str]:
    return sorted(
        p.name for p in TASKS_DIR.iterdir()
        if p.is_dir() and (p / "train.jsonl").exists() and (p / "valid.jsonl").exists()
    )


def compute_iters(task: str) -> int:
    n = count_lines(TASKS_DIR / task / "train.jsonl")
    return max(MIN_ITERS, (n * EPOCHS) // EFFECTIVE_BATCH)


def run_task(task: str, iters_override: int | None) -> bool:
    iters = iters_override or compute_iters(task)
    data_dir = TASKS_DIR / task
    adapter_dir = ADAPTER_ROOT / task
    log_path = LOG_ROOT / f"{task}.log"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable, "-m", "mlx_lm", "lora",
        "-c", str(BASE_CFG),
        "--data", str(data_dir),
        "--adapter-path", str(adapter_dir),
        "--iters", str(iters),
    ]

    banner = f"\n===== [{task}] iters={iters} data={data_dir.name} ====="
    print(banner, flush=True)
    t0 = time.time()
    with log_path.open("w") as log:
        log.write(banner + "\n")
        log.flush()
        proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT)
    dt = time.time() - t0
    ok = proc.returncode == 0
    status = "OK" if ok else f"FAIL(rc={proc.returncode})"
    print(f"  -> {status}  {dt/60:.1f} min  log: {log_path}", flush=True)
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated task subset")
    ap.add_argument("--skip", help="comma-separated tasks to skip")
    ap.add_argument("--iters", type=int, help="override iters (for smoke test)")
    ap.add_argument("--stop-on-fail", action="store_true")
    args = ap.parse_args()

    tasks = discover_tasks()
    if args.only:
        wanted = {t.strip() for t in args.only.split(",")}
        tasks = [t for t in tasks if t in wanted]
    if args.skip:
        drop = {t.strip() for t in args.skip.split(",")}
        tasks = [t for t in tasks if t not in drop]

    print(f"Tasks to run ({len(tasks)}): {tasks}", flush=True)
    results = {}
    for t in tasks:
        results[t] = run_task(t, args.iters)
        if args.stop_on_fail and not results[t]:
            break

    print("\n===== SUMMARY =====")
    for t, ok in results.items():
        print(f"  {'OK  ' if ok else 'FAIL'}  {t}")
    failed = [t for t, ok in results.items() if not ok]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
