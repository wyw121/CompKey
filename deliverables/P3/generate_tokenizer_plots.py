from __future__ import annotations

import csv
from pathlib import Path
import matplotlib.pyplot as plt
import numpy as np

from compkey_p3.config import get_settings


def read_csv(path: Path):
    rows = []
    with open(path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def plot_recall_by_tokenizer(rows, out_path: Path):
    # rows: list of dicts with keys tokenizer, method, recall@10
    tokenizers = sorted(set(r["tokenizer"] for r in rows))
    methods = sorted(set(r["method"] for r in rows))

    data = {m: [] for m in methods}
    for t in tokenizers:
        for m in methods:
            v = next((float(r["recall@10"]) for r in rows if r["tokenizer"] == t and r["method"] == m), 0.0)
            data[m].append(v)

    x = np.arange(len(tokenizers))
    width = 0.12

    fig, ax = plt.subplots(figsize=(10, 5))
    for i, m in enumerate(methods):
        ax.bar(x + (i - len(methods)/2) * width, data[m], width, label=m)

    ax.set_xticks(x)
    ax.set_xticklabels(tokenizers)
    ax.set_ylabel("Recall@10")
    ax.set_title("Recall@10 by tokenizer and method")
    ax.legend()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)


def plot_mrr_by_tokenizer(rows, out_path: Path):
    tokenizers = sorted(set(r["tokenizer"] for r in rows))
    methods = sorted(set(r["method"] for r in rows))
    data = {m: [] for m in methods}
    for t in tokenizers:
        for m in methods:
            v = next((float(r["mrr@10"]) for r in rows if r["tokenizer"] == t and r["method"] == m), 0.0)
            data[m].append(v)

    x = np.arange(len(tokenizers))
    width = 0.12

    fig, ax = plt.subplots(figsize=(10, 5))
    for i, m in enumerate(methods):
        ax.bar(x + (i - len(methods)/2) * width, data[m], width, label=m)

    ax.set_xticks(x)
    ax.set_xticklabels(tokenizers)
    ax.set_ylabel("MRR@10")
    ax.set_title("MRR@10 by tokenizer and method")
    ax.legend()
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)


def plot_tokenizer_speed(rows_speed, out_path: Path):
    # rows_speed from p3_tokenizer_benchmark.csv
    tokenizers = [r["method"] for r in rows_speed]
    qps = [float(r["queries_per_sec"]) for r in rows_speed]
    tps = [float(r["tokens_per_sec"]) for r in rows_speed]

    x = range(len(tokenizers))
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(x, qps, label="queries/sec")
    ax.set_xticks(x)
    ax.set_xticklabels(tokenizers)
    ax.set_ylabel("queries/sec")
    ax.set_title("Tokenizer throughput (queries/sec)")
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)


def plot_scale_curve(rows_scale, out_path: Path):
    # rows_scale has label,target_tokens,build_ms_mean,build_ms_std,build_ms_ci95,...
    labels = [r["label"] for r in rows_scale]
    targets = [int(r["target_tokens"]) for r in rows_scale]
    times = [float(r.get("build_ms_mean") or r.get("build_ms") or 0.0) for r in rows_scale]
    stds = [float(r.get("build_ms_std") or 0.0) for r in rows_scale]
    ci95 = [float(r.get("build_ms_ci95") or 0.0) for r in rows_scale]
    yerr = ci95 if any(v > 0 for v in ci95) else stds
    yerr_label = "95% CI" if any(v > 0 for v in ci95) else "std"

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.errorbar(targets, times, yerr=yerr, fmt="-o", capsize=4, color="#1f77b4", ecolor="#1f77b4", elinewidth=1.2)
    ax.set_xscale("log")
    ax.set_xlabel("target tokens (log scale)")
    ax.set_ylabel("build ms")
    ax.set_title("Offline build time vs tokens (mean ± 95% CI)")
    for x, y in zip(targets, times):
        ax.text(x, y, f"{y:.0f}ms", fontsize=8, ha="left", va="bottom")
    # compute and plot linear fit (in original scale) and annotate R^2
    if len(targets) >= 2:
        import numpy as _np
        x = _np.array(targets, dtype=float)
        y = _np.array(times, dtype=float)
        a, b = _np.polyfit(x, y, 1)
        x_line = _np.linspace(x.min(), x.max(), 200)
        y_line = a * x_line + b
        ax.plot(x_line, y_line, linestyle="--", color="#666666", label=f"linear fit R²={_np.round(1 - _np.sum((y - (a * x + b))**2) / _np.sum((y - y.mean())**2), 3)}")
        ax.legend(fontsize=8)
        ax.text(
            0.03,
            0.03,
            f"error bars = {yerr_label}; runs_per_scale=3",
            transform=ax.transAxes,
            fontsize=8,
            va="bottom",
            ha="left",
            bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.8, edgecolor="#bbbbbb"),
        )
        if len(targets) <= 3:
            ax.text(
                0.03,
                0.97,
                "Few sampled points; fit may be unreliable",
                transform=ax.transAxes,
                fontsize=8,
                va="top",
                ha="left",
                bbox=dict(boxstyle="round,pad=0.25", facecolor="white", alpha=0.8, edgecolor="#bbbbbb"),
            )
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path)


def main():
    settings = get_settings()
    report_dir = settings.report_dir

    combined = read_csv(report_dir / "p3_multimethod_tokenizer_compare.csv")
    speed = read_csv(report_dir / "p3_tokenizer_benchmark.csv")
    scale = read_csv(report_dir / "p3_scale_benchmark.csv")

    fig1 = report_dir / "fig_recall_by_tokenizer.png"
    fig2 = report_dir / "fig_mrr_by_tokenizer.png"
    fig3 = report_dir / "fig_tokenizer_qps.png"
    fig4 = report_dir / "fig_scale_build_time.png"

    plot_recall_by_tokenizer(combined, fig1)
    plot_mrr_by_tokenizer(combined, fig2)
    plot_tokenizer_speed(speed, fig3)
    plot_scale_curve(scale, fig4)

    # update markdown
    md = report_dir / "p3_multimethod_tokenizer_compare.md"
    with open(md, "w", encoding="utf-8") as f:
        f.write("# Tokenizer × Method 比较（带图）\n\n")
        f.write("## 可视化摘要\n\n")
        f.write(f"![Recall@10]({fig1.name})\n\n")
        f.write(f"![MRR@10]({fig2.name})\n\n")
        f.write(f"![Tokenizer throughput]({fig3.name})\n\n")
        f.write(f"![Scale build time]({fig4.name})\n\n")
        f.write("## 原始表格（详见 CSV）\n\n")
        f.write("已生成并保存到 report 目录下的 CSV 文件，可在本仓库中查看原始数值。\n")

    print("Plots and markdown updated in reports/")


if __name__ == "__main__":
    main()
