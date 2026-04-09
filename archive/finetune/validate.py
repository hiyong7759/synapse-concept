"""Validate training.jsonl — schema checks, error pattern detection, statistics.

Usage:
    python finetune/validate.py
"""

import json
import sys
from collections import Counter

from config import TRAINING_FILE, VALID_DOMAINS, VALID_EDGE_TYPES, VALIDATION_REPORT_FILE, OUTPUT_DIR


def validate_entry(entry: dict, idx: int) -> list[str]:
    """Validate a single training entry. Returns list of error strings."""
    errors = []
    messages = entry.get("messages", [])

    if len(messages) != 3:
        errors.append(f"message_count:{len(messages)}")
        return errors

    if messages[0]["role"] != "system":
        errors.append("missing_system_role")
    if messages[1]["role"] != "user":
        errors.append("missing_user_role")
    if messages[2]["role"] != "assistant":
        errors.append("missing_assistant_role")

    user_text = messages[1].get("content", "")
    assistant_text = messages[2].get("content", "")

    # Parse assistant JSON
    try:
        data = json.loads(assistant_text)
    except json.JSONDecodeError:
        errors.append("json_parse_error")
        return errors

    if "nodes" not in data:
        errors.append("missing_nodes_key")
    if "edges" not in data:
        errors.append("missing_edges_key")
    if errors:
        return errors

    nodes = data["nodes"]
    edges = data["edges"]
    node_names = {n["name"] for n in nodes if "name" in n}

    # Node validation
    for i, node in enumerate(nodes):
        if "name" not in node:
            errors.append(f"node[{i}]:missing_name")
        if "domain" not in node:
            errors.append(f"node[{i}]:missing_domain")
        elif node["domain"] not in VALID_DOMAINS:
            errors.append(f"node[{i}]:invalid_domain:{node['domain']}")

        if node.get("safety") and not node.get("safety_rule"):
            errors.append(f"node[{i}]:safety_without_rule")

    # Edge validation
    for i, edge in enumerate(edges):
        if "source" not in edge:
            errors.append(f"edge[{i}]:missing_source")
        if "target" not in edge:
            errors.append(f"edge[{i}]:missing_target")

        if edge.get("source") and edge["source"] not in node_names:
            errors.append(f"edge[{i}]:dangling_source:{edge['source']}")
        if edge.get("target") and edge["target"] not in node_names:
            errors.append(f"edge[{i}]:dangling_target:{edge['target']}")

        edge_type = edge.get("type", "link")
        if edge_type not in VALID_EDGE_TYPES:
            errors.append(f"edge[{i}]:invalid_type:{edge_type}")

        if edge_type == "link" and not edge.get("label"):
            errors.append(f"edge[{i}]:link_missing_label")

    # Suspicious empty result (long text but empty nodes)
    if not nodes and not edges and len(user_text) > 20:
        errors.append("suspicious_empty_result")

    # Check for duplicate node names
    name_counts = Counter(n.get("name") for n in nodes)
    for name, count in name_counts.items():
        if count > 1:
            errors.append(f"duplicate_node:{name}")

    return errors


def compute_statistics(entries: list[dict]) -> dict:
    """Compute aggregate statistics over training data."""
    all_domains = Counter()
    all_labels = Counter()
    all_edge_types = Counter()
    node_counts = []
    edge_counts = []
    empty_count = 0

    for entry in entries:
        assistant_text = entry["messages"][2]["content"]
        try:
            data = json.loads(assistant_text)
        except json.JSONDecodeError:
            continue

        nodes = data.get("nodes", [])
        edges = data.get("edges", [])
        node_counts.append(len(nodes))
        edge_counts.append(len(edges))

        if not nodes and not edges:
            empty_count += 1

        for node in nodes:
            if "domain" in node:
                all_domains[node["domain"]] += 1

        for edge in edges:
            if "label" in edge and edge["label"]:
                all_labels[edge["label"]] += 1
            if "type" in edge:
                all_edge_types[edge["type"]] += 1

    avg_nodes = sum(node_counts) / len(node_counts) if node_counts else 0
    avg_edges = sum(edge_counts) / len(edge_counts) if edge_counts else 0
    edge_per_node = avg_edges / avg_nodes if avg_nodes > 0 else 0

    return {
        "total_entries": len(entries),
        "empty_results": empty_count,
        "avg_nodes_per_entry": round(avg_nodes, 2),
        "avg_edges_per_entry": round(avg_edges, 2),
        "edge_per_node_ratio": round(edge_per_node, 2),
        "domain_distribution": dict(all_domains.most_common()),
        "top_labels": dict(all_labels.most_common(30)),
        "edge_type_distribution": dict(all_edge_types.most_common()),
        "unique_labels": len(all_labels),
    }


def validate():
    """Run full validation on training.jsonl."""
    entries = []
    with open(TRAINING_FILE, encoding="utf-8") as f:
        for line in f:
            entries.append(json.loads(line))

    print(f"Validating {len(entries)} training entries...\n")

    all_errors = {}
    error_type_counts = Counter()

    for idx, entry in enumerate(entries):
        errors = validate_entry(entry, idx)
        if errors:
            ep_id = f"entry_{idx:04d}"
            all_errors[ep_id] = errors
            for err in errors:
                error_type_counts[err.split(":")[0]] += 1

    stats = compute_statistics(entries)

    # Warnings
    warnings = []
    top_domain = max(stats["domain_distribution"].values()) if stats["domain_distribution"] else 0
    if top_domain > len(entries) * 0.5:
        warnings.append(f"Domain bias: top domain has {top_domain}/{len(entries)} entries")
    if stats["unique_labels"] < 10:
        warnings.append(f"Low label diversity: only {stats['unique_labels']} unique labels")
    if stats["edge_per_node_ratio"] < 0.5 or stats["edge_per_node_ratio"] > 3.0:
        warnings.append(f"Unusual edge/node ratio: {stats['edge_per_node_ratio']}")

    report = {
        "summary": {
            "total": len(entries),
            "valid": len(entries) - len(all_errors),
            "invalid": len(all_errors),
            "error_rate": round(len(all_errors) / len(entries) * 100, 2) if entries else 0,
        },
        "error_type_counts": dict(error_type_counts.most_common()),
        "errors": all_errors,
        "statistics": stats,
        "warnings": warnings,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(VALIDATION_REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Print summary
    s = report["summary"]
    print(f"Valid:   {s['valid']}/{s['total']} ({100 - s['error_rate']:.1f}%)")
    print(f"Invalid: {s['invalid']}/{s['total']} ({s['error_rate']:.1f}%)")

    if error_type_counts:
        print(f"\nError types:")
        for err_type, count in error_type_counts.most_common(10):
            print(f"  {err_type}: {count}")

    if warnings:
        print(f"\nWarnings:")
        for w in warnings:
            print(f"  ⚠ {w}")

    print(f"\nStatistics:")
    print(f"  Avg nodes/entry: {stats['avg_nodes_per_entry']}")
    print(f"  Avg edges/entry: {stats['avg_edges_per_entry']}")
    print(f"  Edge/node ratio: {stats['edge_per_node_ratio']}")
    print(f"  Unique labels: {stats['unique_labels']}")
    print(f"  Empty results: {stats['empty_results']}")

    print(f"\nFull report: {VALIDATION_REPORT_FILE}")

    if s["error_rate"] > 5:
        print(f"\n⚠ Error rate > 5%. Consider adjusting system_prompt.py and re-generating.")
        sys.exit(1)


if __name__ == "__main__":
    validate()
