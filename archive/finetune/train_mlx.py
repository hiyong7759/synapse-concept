"""Synapse LoRA fine-tuning with mlx-lm on Apple Silicon.

Prerequisites:
    pip install mlx-lm

Usage:
    # 1. Prepare data
    python3 prepare_mlx_data.py --mode all

    # 2. Train (default: all tasks, 3 epochs)
    python3 train_mlx.py

    # 3. Train specific config
    python3 train_mlx.py --iters 2000 --batch-size 8 --lora-layers 16

    # 4. Fuse adapter into model
    python3 train_mlx.py --fuse-only
"""

import argparse
import subprocess
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "mlx_train"
ADAPTER_DIR = BASE_DIR / "models" / "synapse-lora"
FUSED_DIR = BASE_DIR / "models" / "synapse-fused"
QUANT_DIR = BASE_DIR / "models" / "synapse-4bit"

# 풀 프리시전 모델로 학습. 로컬에 없으면 HuggingFace에서 자동 다운로드.
MODEL_ID = "google/gemma-4-E2B-it"


def run(cmd: list[str], desc: str = ""):
    if desc:
        print(f"\n>>> {desc}")
    print(f"$ {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(f"ERROR: exit code {result.returncode}", file=sys.stderr)
        sys.exit(result.returncode)


def train(
    model: str,
    data_dir: Path,
    adapter_dir: Path,
    iters: int,
    batch_size: int,
    lora_layers: int,
    learning_rate: float,
    val_batches: int,
    save_every: int,
):
    adapter_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        "python3.13", "-m", "mlx_lm", "lora",
        "--model", model,
        "--train",
        "--data", str(data_dir),
        "--adapter-path", str(adapter_dir),
        "--iters", str(iters),
        "--batch-size", str(batch_size),
        "--num-layers", str(lora_layers),
        "--learning-rate", str(learning_rate),
        "--val-batches", str(val_batches),
        "--save-every", str(save_every),
        "--grad-checkpoint",        # saves memory on 16GB
        "--mask-prompt",            # only train on assistant turns
    ]
    run(cmd, f"Training LoRA — iters={iters}, batch={batch_size}, layers={lora_layers}")


def fuse(model: str, adapter_dir: Path, fused_dir: Path):
    fused_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python3.13", "-m", "mlx_lm", "fuse",
        "--model", model,
        "--adapter-path", str(adapter_dir),
        "--save-path", str(fused_dir),
    ]
    run(cmd, "Fusing adapter into model (full precision)")


def quantize(fused_dir: Path, quant_dir: Path, q_bits: int = 4):
    quant_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "python3.13", "-m", "mlx_lm", "convert",
        "--hf-path", str(fused_dir),
        "--mlx-path", str(quant_dir),
        "-q",
        "--q-bits", str(q_bits),
    ]
    run(cmd, f"Quantizing to {q_bits}bit → {quant_dir}")


def main():
    parser = argparse.ArgumentParser(description="Synapse MLX LoRA fine-tuning")
    parser.add_argument("--model", default=MODEL_ID)
    parser.add_argument("--data-dir", default=str(DATA_DIR))
    parser.add_argument("--adapter-dir", default=str(ADAPTER_DIR))
    parser.add_argument("--fused-dir", default=str(FUSED_DIR))
    parser.add_argument("--quant-dir", default=str(QUANT_DIR))
    parser.add_argument("--q-bits", type=int, default=4)

    # Training hyperparams (M4 16GB 기준)
    parser.add_argument("--iters", type=int, default=1500,
                        help="Total training iterations (~3 epochs on 5k examples)")
    parser.add_argument("--batch-size", type=int, default=6,
                        help="Batch size (M4 16GB: 6~8 권장)")
    parser.add_argument("--lora-layers", type=int, default=8,
                        help="Number of transformer layers to apply LoRA")
    parser.add_argument("--learning-rate", type=float, default=1e-4)
    parser.add_argument("--val-batches", type=int, default=25)
    parser.add_argument("--save-every", type=int, default=200)

    # Modes
    parser.add_argument("--fuse-only", action="store_true",
                        help="Skip training, only fuse existing adapter")
    parser.add_argument("--no-fuse", action="store_true",
                        help="Train only, skip fuse step")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    adapter_dir = Path(args.adapter_dir)
    fused_dir = Path(args.fused_dir)

    # Validate data
    if not args.fuse_only:
        for split in ("train.jsonl", "valid.jsonl"):
            if not (data_dir / split).exists():
                print(f"ERROR: {data_dir / split} not found.")
                print("Run: python3 prepare_mlx_data.py first.")
                sys.exit(1)

        # Count examples
        train_count = sum(1 for _ in open(data_dir / "train.jsonl"))
        valid_count = sum(1 for _ in open(data_dir / "valid.jsonl"))
        print(f"\n=== Synapse MLX LoRA Training ===")
        print(f"Model:       {args.model}")
        print(f"Train:       {train_count} examples")
        print(f"Valid:       {valid_count} examples")
        print(f"Iters:       {args.iters}")
        print(f"Batch size:  {args.batch_size}")
        print(f"LoRA layers: {args.lora_layers}")
        print(f"LR:          {args.learning_rate}")
        print(f"Adapter →    {adapter_dir}")

        train(
            model=args.model,
            data_dir=data_dir,
            adapter_dir=adapter_dir,
            iters=args.iters,
            batch_size=args.batch_size,
            lora_layers=args.lora_layers,
            learning_rate=args.learning_rate,
            val_batches=args.val_batches,
            save_every=args.save_every,
        )

    if not args.no_fuse:
        fuse(args.model, adapter_dir, fused_dir)
        print(f"\n✓ Fused model (full precision) → {fused_dir}")

        quant_dir = Path(args.quant_dir)
        quantize(fused_dir, quant_dir, args.q_bits)
        print(f"✓ {args.q_bits}bit 양자화 완료 → {quant_dir}")
        print("\nNext step — Ollama에 등록:")
        print(f"  ollama create synapse-gemma -f Modelfile")

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
