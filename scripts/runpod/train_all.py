#!/usr/bin/env python3
"""RunPod 통합 학습 스크립트 — 시냅스 + gabjil 어댑터 일괄 학습.

FP16 베이스(google/gemma-4-E2B-it) 위에서 LoRA 학습.
MLX 4bit 양자화 불일치 문제 해결.

사용법:
  # 전체 (시냅스 + gabjil)
  python train_all.py

  # 시냅스만
  python train_all.py --synapse-only

  # gabjil만
  python train_all.py --gabjil-only

  # 특정 태스크만
  python train_all.py --tasks extract save-pronoun

  # dry-run (실제 학습 없이 설정 확인)
  python train_all.py --dry-run

RunPod 환경 세팅:
  pip install unsloth peft transformers datasets accelerate bitsandbytes
  # 또는
  pip install trl peft transformers datasets accelerate bitsandbytes

필요 GPU: A100 40GB / H100 권장 (FP16 2B 모델 + LoRA)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# ── 설정 ─────────────────────────────────────────────────

BASE_MODEL = "google/gemma-4-E2B-it"

@dataclass
class TaskConfig:
    name: str
    data_dir: str
    adapter_out: str
    rank: int = 8
    alpha: float = 160.0  # scale(20.0) * rank(8)
    iters: int = 2000
    batch_size: int = 1
    lr: float = 1e-5
    max_seq_length: int = 2048
    eval_steps: int = 200
    save_steps: int = 200
    target_modules: list[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
        "per_layer_input_gate", "per_layer_projection",
    ])


def build_synapse_tasks(data_root: str, output_root: str) -> list[TaskConfig]:
    """시냅스 태스크 목록 생성."""
    tasks = []

    # extract (task6) — 메인 추출기
    tasks.append(TaskConfig(
        name="extract",
        data_dir=f"{data_root}/mlx_train_task6",
        adapter_out=f"{output_root}/extract",
        iters=2000,
    ))

    # 나머지 태스크 (tasks/ 하위)
    task_configs = {
        "save-pronoun":        {"iters": 1500},
        "retrieve-filter":     {"iters": 1500},
        "retrieve-expand":     {"iters": 1000},
        "retrieve-expand-org": {"iters": 1000},
        "routing":             {"iters": 800},
        "save-state-personal": {"iters": 1000},
        "save-state-org":      {"iters": 1000},
        "save-subject-org":    {"iters": 1000},
        "security-access":     {"iters": 800},
        "security-context":    {"iters": 1000},
        "security-org":        {"iters": 1000},
        "security-personal":   {"iters": 1000},
    }

    for task_name, overrides in task_configs.items():
        task_dir = f"{data_root}/tasks/{task_name}"
        if not Path(task_dir).exists():
            continue
        tasks.append(TaskConfig(
            name=task_name,
            data_dir=task_dir,
            adapter_out=f"{output_root}/{task_name}",
            **overrides,
        ))

    return tasks


def build_gabjil_tasks(data_root: str, output_root: str) -> list[TaskConfig]:
    """gabjil 태스크 목록 생성."""
    tasks = []

    # 통합 태스크 (옵션 A)
    a_dir = f"{data_root}/gabjil-extract-a"
    if Path(a_dir).exists():
        tasks.append(TaskConfig(
            name="gabjil-extract-a",
            data_dir=a_dir,
            adapter_out=f"{output_root}/gabjil-extract-a",
            iters=800,
        ))

    # 분할 태스크 (옵션 B)
    for leaf in ["weakness", "strength", "trait", "feeling", "episode"]:
        leaf_dir = f"{data_root}/gabjil-extract-{leaf}"
        if Path(leaf_dir).exists():
            tasks.append(TaskConfig(
                name=f"gabjil-extract-{leaf}",
                data_dir=leaf_dir,
                adapter_out=f"{output_root}/gabjil-extract-{leaf}",
                iters=800,
            ))

    return tasks


# ── 학습 ─────────────────────────────────────────────────

def train_task(config: TaskConfig, dry_run: bool = False) -> dict:
    """단일 태스크 학습. unsloth 사용."""
    print(f"\n{'='*60}")
    print(f"Training: {config.name}")
    print(f"  data:     {config.data_dir}")
    print(f"  output:   {config.adapter_out}")
    print(f"  rank:     {config.rank}")
    print(f"  iters:    {config.iters}")
    print(f"  lr:       {config.lr}")
    print(f"  modules:  {len(config.target_modules)}")
    print(f"{'='*60}")

    # 데이터 존재 확인
    train_file = Path(config.data_dir) / "train.jsonl"
    valid_file = Path(config.data_dir) / "valid.jsonl"
    if not train_file.exists():
        print(f"  SKIP: {train_file} not found")
        return {"status": "skipped", "reason": "no data"}

    train_count = sum(1 for _ in open(train_file))
    valid_count = sum(1 for _ in open(valid_file)) if valid_file.exists() else 0
    print(f"  train: {train_count}, valid: {valid_count}")

    if dry_run:
        print("  DRY-RUN: skipping actual training")
        return {"status": "dry-run"}

    # 출력 디렉토리 생성
    Path(config.adapter_out).mkdir(parents=True, exist_ok=True)

    start = time.time()

    try:
        _train_with_unsloth(config)
        elapsed = time.time() - start
        print(f"  Done in {elapsed:.0f}s")
        return {"status": "success", "elapsed_sec": elapsed}
    except Exception as e:
        print(f"  FAILED: {e}")
        try:
            _train_with_peft(config)
            elapsed = time.time() - start
            print(f"  Done (PEFT fallback) in {elapsed:.0f}s")
            return {"status": "success_peft", "elapsed_sec": elapsed}
        except Exception as e2:
            print(f"  PEFT FAILED too: {e2}")
            return {"status": "failed", "error": str(e2)}


def _train_with_unsloth(config: TaskConfig):
    """unsloth LoRA 학습."""
    from unsloth import FastLanguageModel
    from trl import SFTTrainer, SFTConfig
    from datasets import load_dataset

    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=BASE_MODEL,
        max_seq_length=config.max_seq_length,
        load_in_4bit=False,  # FP16 학습!
    )

    model = FastLanguageModel.get_peft_model(
        model,
        r=config.rank,
        lora_alpha=config.alpha,
        target_modules=config.target_modules,
        lora_dropout=0.0,
        bias="none",
    )

    # 데이터 로드 (messages JSONL)
    dataset = load_dataset("json", data_files={
        "train": str(Path(config.data_dir) / "train.jsonl"),
        "validation": str(Path(config.data_dir) / "valid.jsonl"),
    })

    def format_chat(example):
        return {"text": tokenizer.apply_chat_template(
            example["messages"], tokenize=False, add_generation_prompt=False
        )}

    dataset = dataset.map(format_chat)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset["train"],
        eval_dataset=dataset.get("validation"),
        args=SFTConfig(
            output_dir=config.adapter_out,
            max_steps=config.iters,
            per_device_train_batch_size=config.batch_size,
            learning_rate=config.lr,
            logging_steps=10,
            eval_steps=config.eval_steps,
            save_steps=config.save_steps,
            eval_strategy="steps" if dataset.get("validation") else "no",
            save_strategy="steps",
            fp16=True,
            gradient_accumulation_steps=1,
            seed=42,
            max_seq_length=config.max_seq_length,
        ),
    )

    trainer.train()
    model.save_pretrained(config.adapter_out)
    tokenizer.save_pretrained(config.adapter_out)


def _train_with_peft(config: TaskConfig):
    """PEFT fallback (unsloth 없을 때)."""
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer
    from peft import LoraConfig, get_peft_model
    from datasets import load_dataset

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype="float16",
        device_map="auto",
    )

    lora_config = LoraConfig(
        r=config.rank,
        lora_alpha=config.alpha,
        target_modules=config.target_modules,
        lora_dropout=0.0,
        bias="none",
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(model, lora_config)

    dataset = load_dataset("json", data_files={
        "train": str(Path(config.data_dir) / "train.jsonl"),
        "validation": str(Path(config.data_dir) / "valid.jsonl"),
    })

    def tokenize(example):
        text = tokenizer.apply_chat_template(
            example["messages"], tokenize=False, add_generation_prompt=False
        )
        return tokenizer(text, truncation=True, max_length=config.max_seq_length)

    dataset = dataset.map(tokenize, remove_columns=dataset["train"].column_names)

    args = TrainingArguments(
        output_dir=config.adapter_out,
        max_steps=config.iters,
        per_device_train_batch_size=config.batch_size,
        learning_rate=config.lr,
        logging_steps=10,
        eval_steps=config.eval_steps,
        save_steps=config.save_steps,
        eval_strategy="steps" if "validation" in dataset else "no",
        fp16=True,
        seed=42,
    )

    trainer = Trainer(
        model=model,
        args=args,
        train_dataset=dataset["train"],
        eval_dataset=dataset.get("validation"),
    )

    trainer.train()
    model.save_pretrained(config.adapter_out)


# ── GGUF 변환 ────────────────────────────────────────────

def convert_to_gguf(adapter_dir: str, base_model: str = BASE_MODEL):
    """학습된 PEFT 어댑터 → GGUF LoRA 변환."""
    gguf_dir = str(Path(adapter_dir).parent.parent / "gguf")
    os.makedirs(gguf_dir, exist_ok=True)
    task_name = Path(adapter_dir).name
    gguf_path = f"{gguf_dir}/{task_name}.gguf"

    # llama.cpp convert_lora_to_gguf.py 필요
    converter = Path(__file__).parent.parent.parent / "llama.cpp" / "convert_lora_to_gguf.py"
    if not converter.exists():
        # fallback: /tmp/llama.cpp
        converter = Path("/tmp/llama.cpp/convert_lora_to_gguf.py")
    if not converter.exists():
        print(f"  SKIP GGUF: converter not found at {converter}")
        return None

    cmd = [
        sys.executable, str(converter),
        "--base", base_model,
        "--outfile", gguf_path,
        adapter_dir,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  GGUF conversion failed: {result.stderr[-200:]}")
        return None

    size_mb = os.path.getsize(gguf_path) / 1024 / 1024
    print(f"  GGUF: {gguf_path} ({size_mb:.1f} MB)")
    return gguf_path


# ── 메인 ─────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RunPod batch LoRA training")
    parser.add_argument("--synapse-only", action="store_true")
    parser.add_argument("--gabjil-only", action="store_true")
    parser.add_argument("--tasks", nargs="*", help="Specific task names")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--convert-gguf", action="store_true",
                        help="Convert trained adapters to GGUF after training")
    parser.add_argument("--synapse-data", default="archive/finetune/data",
                        help="Synapse training data root")
    parser.add_argument("--gabjil-data", default="../gabjil/finetune/datasets",
                        help="Gabjil training data root")
    parser.add_argument("--output", default="runpod_output/adapters",
                        help="Output root for trained adapters")
    args = parser.parse_args()

    all_tasks = []

    if not args.gabjil_only:
        synapse_tasks = build_synapse_tasks(args.synapse_data, args.output)
        all_tasks.extend(synapse_tasks)

    if not args.synapse_only:
        gabjil_tasks = build_gabjil_tasks(args.gabjil_data, args.output)
        all_tasks.extend(gabjil_tasks)

    # 특정 태스크 필터
    if args.tasks:
        all_tasks = [t for t in all_tasks if t.name in args.tasks]

    if not all_tasks:
        print("No tasks to train.")
        sys.exit(1)

    print(f"Tasks to train: {len(all_tasks)}")
    for t in all_tasks:
        print(f"  {t.name}: {t.data_dir}")

    # 학습 실행
    results = {}
    for task in all_tasks:
        result = train_task(task, dry_run=args.dry_run)
        results[task.name] = result

        # GGUF 변환
        if args.convert_gguf and result.get("status", "").startswith("success"):
            convert_to_gguf(task.adapter_out)

    # 결과 출력
    print(f"\n{'='*60}")
    print("Results:")
    for name, result in results.items():
        status = result.get("status", "unknown")
        elapsed = result.get("elapsed_sec", 0)
        print(f"  {name}: {status}" + (f" ({elapsed:.0f}s)" if elapsed else ""))

    # 결과 저장
    results_path = f"{args.output}/training_results.json"
    os.makedirs(os.path.dirname(results_path), exist_ok=True)
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {results_path}")


if __name__ == "__main__":
    main()
