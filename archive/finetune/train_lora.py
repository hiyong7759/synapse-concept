"""Synapse node decomposition — LoRA fine-tuning with Unsloth.

Based on Unsloth official notebook:
https://github.com/unslothai/notebooks/blob/main/nb/Qwen3_(14B)-Reasoning-Conversational.ipynb

Run on remote WSL2 (RTX 3080 10GB):
    source ~/synapse-ft-env/bin/activate
    python train_lora.py --model qwen3-8b --data training.jsonl
"""

import argparse
import json

from datasets import Dataset
from unsloth import FastModel
from trl import SFTTrainer, SFTConfig

# RTX 3080 10GB model presets
MODEL_PRESETS = {
    "qwen3-8b": {
        "name": "unsloth/Qwen3-8B-unsloth-bnb-4bit",
        "max_seq_length": 2048,
        "load_in_4bit": True,
    },
    "qwen3.5-4b": {
        "name": "unsloth/Qwen3.5-4B",
        "max_seq_length": 2048,
        "load_in_4bit": False,
    },
    "qwen3.5-2b": {
        "name": "unsloth/Qwen3.5-2B",
        "max_seq_length": 2048,
        "load_in_4bit": False,
    },
    "qwen3.5-0.8b": {
        "name": "unsloth/Qwen3.5-0.8B",
        "max_seq_length": 2048,
        "load_in_4bit": False,
    },
    "qwen3-4b": {
        "name": "unsloth/Qwen3-4B-unsloth-bnb-4bit",
        "max_seq_length": 2048,
        "load_in_4bit": True,
    },
}


def train(
    model_key: str = "qwen3-8b",
    data_path: str = "training.jsonl",
    output_dir: str = "synapse-decompose-lora",
    epochs: int = 3,
    batch_size: int = 1,
    grad_accum: int = 8,
    lr: float = 2e-4,
    max_steps: int = -1,
    save_merged: bool = True,
):
    preset = MODEL_PRESETS[model_key]
    print(f"\n=== Synapse Fine-tuning ===")
    print(f"Model: {preset['name']}")
    print(f"Data: {data_path}")

    # 1. Load model
    model, tokenizer = FastModel.from_pretrained(
        model_name=preset["name"],
        max_seq_length=preset["max_seq_length"],
        load_in_4bit=preset["load_in_4bit"],
        full_finetuning=False,
    )

    # 2. LoRA
    model = FastModel.get_peft_model(
        model,
        r=16,
        lora_alpha=32,
        target_modules=[
            "q_proj", "k_proj", "v_proj", "o_proj",
            "gate_proj", "up_proj", "down_proj",
        ],
        use_gradient_checkpointing="unsloth",
    )
    model.print_trainable_parameters()

    # 3. Load dataset
    records = []
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            records.append(json.loads(line))
    print(f"Loaded {len(records)} examples")

    # 4. Format with chat template
    texts = []
    for rec in records:
        text = tokenizer.apply_chat_template(
            rec["messages"],
            tokenize=False,
            add_generation_prompt=False,
        )
        texts.append(text)

    dataset = Dataset.from_dict({"text": texts})

    # 5. Train — Unsloth official pattern
    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        eval_dataset=None,
        args=SFTConfig(
            dataset_text_field="text",
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=grad_accum,
            num_train_epochs=epochs,
            max_steps=max_steps,
            learning_rate=lr,
            warmup_steps=5,
            logging_steps=10,
            optim="adamw_8bit",
            weight_decay=0.001,
            lr_scheduler_type="linear",
            seed=42,
            output_dir=output_dir,
            save_strategy="epoch",
            report_to="none",
            padding_free=False,
        ),
    )

    print(f"\nStarting training ({epochs} epochs)...")
    trainer.train()
    trainer.save_model(output_dir)
    print(f"\nLoRA adapter saved to {output_dir}")

    if save_merged:
        merged_dir = f"{output_dir}-merged"
        print(f"Merging → {merged_dir}")
        model.save_pretrained_merged(merged_dir, tokenizer, save_method="merged_16bit")
        print(f"Merged model saved.")

    print("\n=== Done ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=list(MODEL_PRESETS.keys()), default="qwen3-8b")
    parser.add_argument("--data", default="training.jsonl")
    parser.add_argument("--output", default="synapse-decompose-lora")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--no-merge", action="store_true")
    args = parser.parse_args()

    train(
        model_key=args.model,
        data_path=args.data,
        output_dir=args.output,
        epochs=args.epochs,
        batch_size=args.batch_size,
        grad_accum=args.grad_accum,
        lr=args.lr,
        max_steps=args.max_steps,
        save_merged=not args.no_merge,
    )
