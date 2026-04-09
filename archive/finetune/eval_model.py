"""Evaluate fine-tuned model vs Opus ground truth.

Run on remote WSL2:
    python eval_model.py --model synapse-decompose-lora-merged --data training.jsonl

Metrics:
    - Node recall/precision (name match)
    - Edge recall/precision (source+target+label match)
    - Domain accuracy
    - Empty result accuracy (greeting → empty)
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from unsloth import FastModel


def load_ground_truth(data_path: str) -> list[dict]:
    """Load training.jsonl as ground truth."""
    examples = []
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            user_text = entry["messages"][1]["content"]
            expected = json.loads(entry["messages"][2]["content"])
            examples.append({"input": user_text, "expected": expected})
    return examples


def extract_node_set(data: dict) -> set[str]:
    return {n["name"] for n in data.get("nodes", [])}


def extract_edge_set(data: dict) -> set[tuple]:
    return {
        (e.get("source", ""), e.get("target", ""), e.get("label", ""))
        for e in data.get("edges", [])
    }


def evaluate(
    model_path: str,
    data_path: str,
    sample_size: int = 100,
    max_seq_length: int = 2048,
):
    """Run evaluation."""
    print(f"Loading model: {model_path}")
    model, tokenizer = FastModel.from_pretrained(
        model_name=model_path,
        max_seq_length=max_seq_length,
        load_in_4bit=False,
        full_finetuning=False,
    )
    FastModel.for_inference(model)

    examples = load_ground_truth(data_path)
    if sample_size and sample_size < len(examples):
        import random
        random.seed(42)
        examples = random.sample(examples, sample_size)

    print(f"Evaluating {len(examples)} examples...\n")

    # System prompt from training
    from system_prompt import SYSTEM_PROMPT

    node_precisions, node_recalls = [], []
    edge_precisions, edge_recalls = [], []
    domain_correct, domain_total = 0, 0
    empty_correct, empty_total = 0, 0
    parse_errors = 0

    for i, ex in enumerate(examples):
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": ex["input"]},
        ]

        input_text = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True,
        )
        inputs = tokenizer(input_text, return_tensors="pt").to(model.device)

        outputs = model.generate(
            **inputs,
            max_new_tokens=1024,
            temperature=0.1,
            do_sample=True,
        )
        response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()

        # Parse predicted JSON
        try:
            predicted = json.loads(response)
        except json.JSONDecodeError:
            if "```" in response:
                try:
                    json_str = response.split("```")[1]
                    if json_str.startswith("json"):
                        json_str = json_str[4:]
                    predicted = json.loads(json_str.strip())
                except (json.JSONDecodeError, IndexError):
                    parse_errors += 1
                    continue
            else:
                parse_errors += 1
                continue

        expected = ex["expected"]

        # Empty result check
        if not expected["nodes"] and not expected["edges"]:
            empty_total += 1
            if not predicted.get("nodes") and not predicted.get("edges"):
                empty_correct += 1
            continue

        # Node metrics
        exp_nodes = extract_node_set(expected)
        pred_nodes = extract_node_set(predicted)
        if pred_nodes:
            node_precisions.append(len(exp_nodes & pred_nodes) / len(pred_nodes))
        if exp_nodes:
            node_recalls.append(len(exp_nodes & pred_nodes) / len(exp_nodes))

        # Edge metrics
        exp_edges = extract_edge_set(expected)
        pred_edges = extract_edge_set(predicted)
        if pred_edges:
            edge_precisions.append(len(exp_edges & pred_edges) / len(pred_edges))
        if exp_edges:
            edge_recalls.append(len(exp_edges & pred_edges) / len(exp_edges))

        # Domain accuracy
        for node in predicted.get("nodes", []):
            domain_total += 1
            exp_node = next((n for n in expected["nodes"] if n["name"] == node.get("name")), None)
            if exp_node and exp_node.get("domain") == node.get("domain"):
                domain_correct += 1

        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(examples)}]...")

    # Report
    avg = lambda lst: sum(lst) / len(lst) if lst else 0

    print(f"\n{'='*50}")
    print(f"=== Evaluation Report ({len(examples)} samples) ===")
    print(f"{'='*50}")
    print(f"\nNode Precision: {avg(node_precisions):.3f}")
    print(f"Node Recall:    {avg(node_recalls):.3f}")
    print(f"Edge Precision: {avg(edge_precisions):.3f}")
    print(f"Edge Recall:    {avg(edge_recalls):.3f}")
    print(f"Domain Acc:     {domain_correct}/{domain_total} ({domain_correct/domain_total:.3f})" if domain_total else "Domain Acc: N/A")
    print(f"Empty Acc:      {empty_correct}/{empty_total} ({empty_correct/empty_total:.3f})" if empty_total else "Empty Acc: N/A")
    print(f"Parse Errors:   {parse_errors}/{len(examples)} ({parse_errors/len(examples):.3f})")

    # Quality gate
    node_f1 = 2 * avg(node_precisions) * avg(node_recalls) / (avg(node_precisions) + avg(node_recalls)) if (avg(node_precisions) + avg(node_recalls)) > 0 else 0
    print(f"\nNode F1: {node_f1:.3f}")

    if node_f1 < 0.7:
        print("\n⚠ Node F1 < 0.7 — 데이터 보강 또는 하이퍼파라미터 조정 필요")
    else:
        print("\n✓ 기준 통과")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate fine-tuned model")
    parser.add_argument("--model", required=True, help="Path to merged model")
    parser.add_argument("--data", default="training.jsonl")
    parser.add_argument("--samples", type=int, default=100)
    args = parser.parse_args()

    evaluate(model_path=args.model, data_path=args.data, sample_size=args.samples)
