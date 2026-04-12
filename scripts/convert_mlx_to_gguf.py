#!/usr/bin/env python3
"""MLX LoRA adapters → GGUF LoRA 변환.

2단계 변환:
  1) MLX safetensors → HF PEFT 포맷 (키 리매핑 + 텐서 전치)
  2) llama.cpp convert_lora_to_gguf.py 호출 → GGUF LoRA 파일

사용법:
  # 단일 어댑터
  python scripts/convert_mlx_to_gguf.py extract

  # 필수 어댑터 전부
  python scripts/convert_mlx_to_gguf.py --all

  # 1단계만 (PEFT 변환, GGUF 변환 없이)
  python scripts/convert_mlx_to_gguf.py extract --peft-only

필요 환경:
  - pip install safetensors torch
  - git clone https://github.com/ggml-org/llama.cpp /tmp/llama.cpp
  - HF 베이스 모델: google/gemma-4-E2B-it (shape 참조용, --base-model로 경로 지정)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file

# ── 경로 ─────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MLX_ADAPTER_BASE = PROJECT_ROOT / "archive" / "finetune" / "models" / "tasks"
PEFT_OUTPUT_BASE = PROJECT_ROOT / "archive" / "finetune" / "models" / "peft"
GGUF_OUTPUT_BASE = PROJECT_ROOT / "archive" / "finetune" / "models" / "gguf"
LLAMA_CPP_DIR = Path("/tmp/llama.cpp")
CONVERT_SCRIPT = LLAMA_CPP_DIR / "convert_lora_to_gguf.py"

# 필수 어댑터 (Phase 0 우선)
PRIORITY_ADAPTERS = [
    "extract",
    "retrieve-filter",
    "retrieve-expand",
    "save-pronoun",
]

# 전체 어댑터
ALL_ADAPTERS = PRIORITY_ADAPTERS + [
    "retrieve-expand-org",
    "routing",
    "save-state-personal",
    "save-state-org",
    "save-subject-org",
    "security-access",
    "security-context",
    "security-org",
    "security-personal",
]


def mlx_to_peft(task: str) -> Path:
    """MLX safetensors → HF PEFT 포맷.

    키 리매핑:
      MLX:  language_model.model.layers.{N}.{module}.lora_a  [in, rank]
      PEFT: base_model.model.model.layers.{N}.{module}.lora_A.weight  [rank, in]

    텐서 전치:
      lora_a [in, rank] → lora_A [rank, in]
      lora_b [rank, out] → lora_B [out, rank]
    """
    mlx_dir = MLX_ADAPTER_BASE / task
    st_path = mlx_dir / "adapters.safetensors"
    cfg_path = mlx_dir / "adapter_config.json"

    if not st_path.exists():
        raise FileNotFoundError(f"safetensors not found: {st_path}")

    # MLX adapter_config 읽기
    with open(cfg_path) as f:
        mlx_cfg = json.load(f)

    lora_params = mlx_cfg.get("lora_parameters", {})
    rank = lora_params.get("rank", 8)
    alpha = lora_params.get("scale", 20.0) * rank  # MLX scale = alpha/rank
    dropout = lora_params.get("dropout", 0.0)

    # 텐서 리매핑
    peft_tensors = {}
    target_modules = set()

    with safe_open(str(st_path), framework="pt") as f:
        for mlx_key in f.keys():
            tensor = f.get_tensor(mlx_key)

            # 키 변환: language_model.model.layers.N.module.lora_a
            # → base_model.model.model.language_model.layers.N.module.lora_A.weight
            #
            # MLX key:  language_model.model.layers.19.self_attn.q_proj.lora_a
            # Base key:     model.language_model.layers.19.self_attn.q_proj.weight
            # PEFT key: base_model.model.model.language_model.layers.19.self_attn.q_proj.lora_A.weight
            #
            # 즉 MLX의 "language_model.model." → PEFT의 "model.language_model."
            peft_key = mlx_key

            # language_model.model.layers → model.language_model.layers
            if peft_key.startswith("language_model.model."):
                peft_key = "model.language_model." + peft_key[len("language_model.model."):]

            # lora_a → lora_A.weight, lora_b → lora_B.weight
            if peft_key.endswith(".lora_a"):
                peft_key = peft_key[:-len(".lora_a")] + ".lora_A.weight"
                tensor = tensor.T.contiguous()  # [in, rank] → [rank, in]
            elif peft_key.endswith(".lora_b"):
                peft_key = peft_key[:-len(".lora_b")] + ".lora_B.weight"
                tensor = tensor.T.contiguous()  # [rank, out] → [out, rank]
            else:
                print(f"  WARNING: unexpected key {mlx_key}, skipping")
                continue

            # base_model.model. 접두어 추가
            peft_key = "base_model.model." + peft_key

            peft_tensors[peft_key] = tensor

            # target_modules 추출
            # base_model.model.model.layers.N.self_attn.q_proj.lora_A.weight
            # → self_attn.q_proj 가 아니라 q_proj
            parts = mlx_key.split(".")
            # module = 마지막에서 lora_a/lora_b 앞의 이름
            module_name = parts[-2]  # q_proj, k_proj, per_layer_input_gate, etc.
            target_modules.add(module_name)

    # PEFT 출력 디렉토리
    peft_dir = PEFT_OUTPUT_BASE / task
    peft_dir.mkdir(parents=True, exist_ok=True)

    # adapter_model.safetensors 저장
    save_file(peft_tensors, str(peft_dir / "adapter_model.safetensors"))

    # HF PEFT adapter_config.json 생성
    peft_config = {
        "auto_mapping": None,
        "base_model_name_or_path": mlx_cfg.get("model", "google/gemma-4-E2B-it"),
        "bias": "none",
        "fan_in_fan_out": False,
        "inference_mode": True,
        "init_lora_weights": True,
        "layers_pattern": None,
        "layers_to_transform": None,
        "lora_alpha": alpha,
        "lora_dropout": dropout,
        "modules_to_save": None,
        "peft_type": "LORA",
        "r": rank,
        "revision": None,
        "target_modules": sorted(target_modules),
        "task_type": "CAUSAL_LM",
        "use_rslora": False,
    }

    with open(peft_dir / "adapter_config.json", "w") as f:
        json.dump(peft_config, f, indent=2)

    n_tensors = len(peft_tensors)
    print(f"  PEFT saved: {peft_dir} ({n_tensors} tensors, rank={rank}, alpha={alpha})")
    print(f"  target_modules: {sorted(target_modules)}")

    return peft_dir


def peft_to_gguf(task: str, base_model: str) -> Path:
    """HF PEFT → GGUF LoRA via llama.cpp convert_lora_to_gguf.py."""
    if not CONVERT_SCRIPT.exists():
        raise FileNotFoundError(
            f"llama.cpp not found at {LLAMA_CPP_DIR}\n"
            "→ git clone https://github.com/ggml-org/llama.cpp /tmp/llama.cpp"
        )

    peft_dir = PEFT_OUTPUT_BASE / task
    gguf_dir = GGUF_OUTPUT_BASE
    gguf_dir.mkdir(parents=True, exist_ok=True)
    gguf_path = gguf_dir / f"{task}.gguf"

    cmd = [
        sys.executable,
        str(CONVERT_SCRIPT),
        "--base", base_model,
        "--outfile", str(gguf_path),
        str(peft_dir),
    ]

    print(f"  Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(LLAMA_CPP_DIR))

    if result.returncode != 0:
        print(f"  STDERR: {result.stderr}")
        raise RuntimeError(f"convert_lora_to_gguf.py failed for {task}")

    size_mb = gguf_path.stat().st_size / 1024 / 1024
    print(f"  GGUF saved: {gguf_path} ({size_mb:.1f} MB)")
    return gguf_path


def convert_adapter(task: str, base_model: str | None, peft_only: bool = False):
    """단일 어댑터 변환."""
    print(f"\n{'='*60}")
    print(f"Converting: {task}")
    print(f"{'='*60}")

    # Step 1: MLX → PEFT
    peft_dir = mlx_to_peft(task)

    # Step 2: PEFT → GGUF
    if not peft_only:
        if base_model is None:
            print("  SKIP GGUF: --base-model not specified (PEFT only)")
        else:
            peft_to_gguf(task, base_model)


def main():
    parser = argparse.ArgumentParser(description="MLX LoRA → GGUF LoRA converter")
    parser.add_argument(
        "tasks", nargs="*",
        help="Adapter task names (e.g. extract retrieve-filter). "
             "Omit with --all to convert all.",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Convert all adapters.",
    )
    parser.add_argument(
        "--priority", action="store_true",
        help="Convert priority adapters only (extract, retrieve-filter, retrieve-expand, save-pronoun).",
    )
    parser.add_argument(
        "--base-model", type=str, default=None,
        help="Path to HF base model (google/gemma-4-E2B-it) for GGUF conversion. "
             "If omitted, only PEFT conversion is done.",
    )
    parser.add_argument(
        "--peft-only", action="store_true",
        help="Only do MLX→PEFT conversion, skip GGUF step.",
    )

    args = parser.parse_args()

    if args.all:
        tasks = ALL_ADAPTERS
    elif args.priority:
        tasks = PRIORITY_ADAPTERS
    elif args.tasks:
        tasks = args.tasks
    else:
        parser.print_help()
        sys.exit(1)

    # 존재 확인
    for task in tasks:
        st = MLX_ADAPTER_BASE / task / "adapters.safetensors"
        if not st.exists():
            print(f"ERROR: {st} not found")
            sys.exit(1)

    print(f"Tasks to convert: {tasks}")
    print(f"Base model: {args.base_model or '(PEFT only)'}")

    for task in tasks:
        convert_adapter(task, args.base_model, args.peft_only)

    print(f"\n{'='*60}")
    print("Done.")
    if args.peft_only or args.base_model is None:
        print(f"PEFT outputs: {PEFT_OUTPUT_BASE}")
    else:
        print(f"GGUF outputs: {GGUF_OUTPUT_BASE}")


if __name__ == "__main__":
    main()
