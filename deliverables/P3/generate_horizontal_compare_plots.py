from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from compkey_p3.config import get_settings


def read_csv(path: Path):
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows.extend(reader)
    return rows


def pivot_metrics(rows):
    by_backend = defaultdict(dict)
    for r in rows:
        by_backend[r["backend"]][r["metric"]] = float(r["value"])
    return by_backend


def plot_method_average(rows, out_path: Path):
    methods = sorted({r["method"] for r in rows})
    recall = []
    mrr = []
    for m in methods:
        subset = [r for r in rows if r["method"] == m]
        recall.append(sum(float(r["recall@10"]) for r in subset) / len(subset))
        mrr.append(sum(float(r["mrr@10"]) for r in subset) / len(subset))

    x = np.arange(len(methods))
    width = 0.35
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(x - width / 2, recall, width, label="avg recall@10")
    ax.bar(x + width / 2, mrr, width, label="avg mrr@10")
    ax.set_xticks(x)
    ax.set_xticklabels(methods, rotation=20)
    ax.set_ylim(0, max(max(recall), max(mrr)) * 1.2)
    ax.set_title("Average Recall@10 / MRR@10 across tokenizers")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path)


def plot_db_latency(metric_map, out_path: Path):
    backends = list(metric_map.keys())
    read_avg = [metric_map[b].get("read_avg_ms", 0.0) for b in backends]
    mixed_read = [metric_map[b].get("mixed_read_avg_ms", 0.0) for b in backends]

    x = np.arange(len(backends))
    width = 0.35
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(x - width / 2, read_avg, width, label="read_avg_ms")
    ax.bar(x + width / 2, mixed_read, width, label="mixed_read_avg_ms")
    ax.set_xticks(x)
    ax.set_xticklabels(backends)
    ax.set_ylabel("ms")
    ax.set_title("Database read latency comparison")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path)


def plot_db_throughput(metric_map, out_path: Path):
    backends = list(metric_map.keys())
    write_rows = [metric_map[b].get("write_rows_per_sec", 0.0) for b in backends]
    read_qps = [metric_map[b].get("read_qps", 0.0) for b in backends]

    x = np.arange(len(backends))
    width = 0.35
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.bar(x - width / 2, write_rows, width, label="write_rows_per_sec")
    ax.bar(x + width / 2, read_qps, width, label="read_qps")
    ax.set_xticks(x)
    ax.set_xticklabels(backends)
    ax.set_ylabel("ops / sec")
    ax.set_title("Database throughput comparison")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_path)


def main():
    settings = get_settings()
    report_dir = settings.report_dir

    multimethod = read_csv(report_dir / "p3_multimethod_tokenizer_compare.csv")
    db_rows = read_csv(report_dir / "p3_db_compare_benchmark.csv")
    db_map = pivot_metrics(db_rows)

    out1 = report_dir / "fig_method_avg_recall_mrr.png"
    out2 = report_dir / "fig_db_compare_latency.png"
    out3 = report_dir / "fig_db_compare_throughput.png"

    plot_method_average(multimethod, out1)
    plot_db_latency(db_map, out2)
    plot_db_throughput(db_map, out3)

    print("Generated:")
    print(out1)
    print(out2)
    print(out3)


if __name__ == "__main__":
    main()
