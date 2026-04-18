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
import dataclasses
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
    alpha: float = 8.0  # scale = alpha/rank = 1.0
    iters: int = 2000
    batch_size: int = 2
    gradient_accumulation_steps: int = 8  # effective batch = 16
    lr: float = 2e-4
    lora_dropout: float = 0.05
    weight_decay: float = 0.01
    max_seq_length: int = 2048
    eval_steps: int = 50
    save_steps: int = 50
    layers_to_transform: int = 8  # last N layers only
    target_modules: list[str] = field(default_factory=lambda: [
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
        "per_layer_input_gate", "per_layer_projection",
    ])


def build_synapse_tasks(data_root: str, output_root: str) -> list[TaskConfig]:
    """시냅스 태스크 목록 생성."""
    tasks = []

    # extract-core — 노드/엣지/카테고리/retention 추출 (1798건, eff_batch=16 → 112/ep × 3 = 336)
    tasks.append(TaskConfig(
        name="extract-core",
        data_dir=f"{data_root}/tasks/extract-core",
        adapter_out=f"{output_root}/extract-core",
        iters=400,
    ))

    # extract-state — deactivate 모순 탐지 (490건, eff_batch=16 → 31/ep × 3 = 93)
    tasks.append(TaskConfig(
        name="extract-state",
        data_dir=f"{data_root}/tasks/extract-state",
        adapter_out=f"{output_root}/extract-state",
        iters=100,
    ))

    # 나머지 태스크 (tasks/ 하위)
    # iters 계산: ceil(train_count / eff_batch) * 3 epochs, early stopping이 알아서 멈춤
    task_configs = {
        "save-pronoun":        {"iters": 120},   # 580건 → 36/ep × 3
        "retrieve-filter":     {"iters": 240},   # 1269건 → 79/ep × 3
        "retrieve-expand":     {"iters": 70},    # 363건 → 23/ep × 3
        "retrieve-expand-org": {"iters": 60},    # 270건 → 17/ep × 3
        "routing":             {"iters": 60},    # 265건 → 17/ep × 3
        "save-state-personal": {"iters": 90},    # 438건 → 27/ep × 3
        "save-state-org":      {"iters": 70},    # 366건 → 23/ep × 3
        "save-subject-org":    {"iters": 70},    # 358건 → 22/ep × 3
        "security-access":     {"iters": 60},    # 269건 → 17/ep × 3
        "security-context":    {"iters": 70},    # 365건 → 23/ep × 3
        "security-org":        {"iters": 90},    # 447건 → 28/ep × 3
        "security-personal":   {"iters": 100},   # 495건 → 31/ep × 3
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

    # 통합 태스크 (옵션 A) — 255건 → 16/ep × 3 = 48
    a_dir = f"{data_root}/gabjil-extract-a"
    if Path(a_dir).exists():
        tasks.append(TaskConfig(
            name="gabjil-extract-a",
            data_dir=a_dir,
            adapter_out=f"{output_root}/gabjil-extract-a",
            iters=60,
        ))

    # 분할 태스크 (옵션 B) — 각 255건 → 16/ep × 3 = 48
    for leaf in ["weakness", "strength", "trait", "feeling", "episode"]:
        leaf_dir = f"{data_root}/gabjil-extract-{leaf}"
        if Path(leaf_dir).exists():
            tasks.append(TaskConfig(
                name=f"gabjil-extract-{leaf}",
                data_dir=leaf_dir,
                adapter_out=f"{output_root}/gabjil-extract-{leaf}",
                iters=60,
            ))

    return tasks


# ── 학습 ─────────────────────────────────────────────────

def train_task(config: TaskConfig, dry_run: bool = False) -> dict:
    """단일 태스크 학습. unsloth 사용."""
    print(f"\n{'='*60}")
    print(f"Training: {config.name}")
    print(f"  data:     {config.data_dir}")
    print(f"  output:   {config.adapter_out}")
    print(f"  rank:     {config.rank}, alpha: {config.alpha}, scale: {config.alpha/config.rank:.1f}")
    print(f"  iters:    {config.iters}, eff_batch: {config.batch_size * config.gradient_accumulation_steps}")
    print(f"  lr:       {config.lr}, dropout: {config.lora_dropout}, wd: {config.weight_decay}")
    print(f"  layers:   last {config.layers_to_transform}, modules: {len(config.target_modules)}")
    print(f"{'='*60}")

    # 데이터 존재 확인
    train_file = Path(config.data_dir) / "train.jsonl"
    valid_file = Path(config.data_dir) / "valid.jsonl"
    if not train_file.exists():
        print(f"  SKIP: {train_file} not found")
        return {"status": "skipped", "reason": "no data"}

    with open(train_file) as f:
        train_count = sum(1 for _ in f)
    if valid_file.exists():
        with open(valid_file) as f:
            valid_count = sum(1 for _ in f)
    else:
        valid_count = 0
    print(f"  train: {train_count}, valid: {valid_count}")

    if dry_run:
        print("  DRY-RUN: skipping actual training")
        return {"status": "dry-run"}

    # 이미 완료된 어댑터는 스킵
    adapter_file = Path(config.adapter_out) / "adapter_model.safetensors"
    if adapter_file.exists():
        print(f"  SKIP: adapter already exists at {adapter_file}")
        return {"status": "skipped", "reason": "already done"}

    # 출력 디렉토리 생성
    Path(config.adapter_out).mkdir(parents=True, exist_ok=True)

    # 각 태스크를 별도 프로세스로 실행 (VRAM 누수 방지)
    start = time.time()
    result = subprocess.run(
        [sys.executable, __file__, "--_subprocess_train",
         json.dumps(dataclasses.asdict(config))],
        capture_output=False,
    )
    elapsed = time.time() - start

    if result.returncode == 0 and adapter_file.exists():
        print(f"  Done in {elapsed:.0f}s")
        return {"status": "success", "elapsed_sec": elapsed}
    else:
        print(f"  FAILED (exit code {result.returncode})")
        return {"status": "failed", "error": f"exit code {result.returncode}"}


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

    # 마지막 N개 레이어만 LoRA 적용
    num_layers = getattr(model.config, 'num_hidden_layers', None) or model.config.text_config.num_hidden_layers  # gemma-4-E2B: 35
    layers = list(range(num_layers - config.layers_to_transform, num_layers))

    model = FastLanguageModel.get_peft_model(
        model,
        r=config.rank,
        lora_alpha=config.alpha,
        target_modules=config.target_modules,
        layers_to_transform=layers,
        lora_dropout=config.lora_dropout,
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

    from transformers import EarlyStoppingCallback
    from trl import DataCollatorForCompletionOnlyLM

    # 응답 토큰에만 loss 적용 (프롬프트 마스킹 — MLX의 --mask-prompt와 동일)
    response_template = "<|turn>model\n"
    collator = DataCollatorForCompletionOnlyLM(
        response_template=response_template,
        tokenizer=tokenizer,
    )

    has_eval = dataset.get("validation") is not None

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset["train"],
        eval_dataset=dataset.get("validation"),
        data_collator=collator,
        args=SFTConfig(
            output_dir=config.adapter_out,
            max_steps=config.iters,
            per_device_train_batch_size=config.batch_size,
            gradient_accumulation_steps=config.gradient_accumulation_steps,
            learning_rate=config.lr,
            weight_decay=config.weight_decay,
            logging_steps=10,
            eval_steps=config.eval_steps,
            save_steps=config.save_steps,
            eval_strategy="steps" if has_eval else "no",
            save_strategy="steps",
            load_best_model_at_end=has_eval,
            metric_for_best_model="eval_loss" if has_eval else None,
            greater_is_better=False if has_eval else None,
            save_total_limit=3,
            fp16=False,
            bf16=True,
            seed=42,
            max_seq_length=config.max_seq_length,
        ),
        callbacks=[EarlyStoppingCallback(early_stopping_patience=3)] if has_eval else [],
    )

    trainer.train()
    model.save_pretrained(config.adapter_out)
    tokenizer.save_pretrained(config.adapter_out)


def _train_with_peft(config: TaskConfig):
    """PEFT fallback (unsloth 없을 때)."""
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer
    from peft import LoraConfig, get_peft_model
    from datasets import load_dataset

    import torch
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="auto",
    )

    # Filter target_modules to only include modules that exist as Linear layers
    valid_modules = []
    for name, module in model.named_modules():
        if hasattr(module, 'weight') and len(module.weight.shape) == 2:
            short_name = name.split('.')[-1]
            if short_name in config.target_modules and short_name not in valid_modules:
                valid_modules.append(short_name)

    num_layers = getattr(model.config, 'num_hidden_layers', None) or model.config.text_config.num_hidden_layers
    layers = list(range(num_layers - config.layers_to_transform, num_layers))

    lora_config = LoraConfig(
        r=config.rank,
        lora_alpha=config.alpha,
        target_modules=valid_modules or ["q_proj", "k_proj", "v_proj", "o_proj"],
        layers_to_transform=layers,
        lora_dropout=config.lora_dropout,
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
        fp16=False,
        bf16=True,
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
    parser.add_argument("--synapse-data", default="data/finetune",
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
    results_path = Path(args.output) / "training_results.json"
    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(results_path), "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to {results_path}")


def _subprocess_main(config_json: str):
    """서브프로세스에서 단일 태스크 학습. VRAM 격리."""
    config_dict = json.loads(config_json)
    config = TaskConfig(**config_dict)

    print(f"  [subprocess] Training {config.name}...")
    try:
        _train_with_unsloth(config)
        print(f"  [subprocess] {config.name} completed successfully.")
    except Exception as e:
        print(f"  [subprocess] unsloth failed: {e}, trying PEFT fallback...")
        try:
            _train_with_peft(config)
            print(f"  [subprocess] {config.name} completed (PEFT fallback).")
        except Exception as e2:
            print(f"  [subprocess] {config.name} FAILED: {e2}")
            sys.exit(1)


if __name__ == "__main__":
    # 서브프로세스 모드
    if len(sys.argv) >= 3 and sys.argv[1] == "--_subprocess_train":
        _subprocess_main(sys.argv[2])
    else:
        main()
