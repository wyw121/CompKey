import argparse
import csv
import os
import re
import time
from collections import Counter
from statistics import median
from statistics import mean

import matplotlib.pyplot as plt
import jieba

TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}")


def load_queries(csv_path: str, max_rows: int) -> list[str]:
    queries: list[str] = []
    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = (row.get("query") or "").strip()
            if q:
                queries.append(q)
            if max_rows and len(queries) >= max_rows:
                break
    return queries


def tokenize_jieba_precise(text: str) -> list[str]:
    return [t.strip() for t in jieba.lcut(text) if t.strip()]


def tokenize_jieba_search(text: str) -> list[str]:
    return [t.strip() for t in jieba.lcut_for_search(text) if t.strip()]


def tokenize_regex(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(text)


def benchmark(name: str, func, queries: list[str]) -> dict:
    # 预热：避免首次调用开销污染结果
    for q in queries[: min(200, len(queries))]:
        _ = func(q)

    elapsed_rounds = []
    token_counts = []
    all_tokens = Counter()
    single_char = 0
    total_tokens = 0

    rounds = 3
    for i in range(rounds):
        start = time.perf_counter()

        # 第一轮同时收集质量相关统计，后续轮仅测速
        if i == 0:
            for q in queries:
                tokens = func(q)
                token_counts.append(len(tokens))
                for t in tokens:
                    all_tokens[t] += 1
                    total_tokens += 1
                    if len(t) == 1:
                        single_char += 1
        else:
            for q in queries:
                _ = func(q)

        elapsed_rounds.append(time.perf_counter() - start)

    elapsed = median(elapsed_rounds)
    qps = len(queries) / elapsed if elapsed else 0
    tps = total_tokens / elapsed if elapsed else 0
    single_ratio = (single_char / total_tokens) if total_tokens else 0

    return {
        "method": name,
        "queries": len(queries),
        "elapsed_sec": elapsed,
        "queries_per_sec": qps,
        "tokens_per_sec": tps,
        "total_tokens": total_tokens,
        "avg_tokens_per_query": mean(token_counts) if token_counts else 0,
        "unique_tokens": len(all_tokens),
        "single_char_ratio": single_ratio,
    }


def save_csv(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "method",
                "queries",
                "elapsed_sec",
                "queries_per_sec",
                "tokens_per_sec",
                "total_tokens",
                "avg_tokens_per_query",
                "unique_tokens",
                "single_char_ratio",
            ],
        )
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def save_plot(path: str, rows: list[dict]) -> None:
    methods = [r["method"] for r in rows]
    qps = [r["queries_per_sec"] for r in rows]
    avg_tokens = [r["avg_tokens_per_query"] for r in rows]

    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial Unicode MS"]
    plt.rcParams["axes.unicode_minus"] = False

    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

    axes[0].bar(methods, qps)
    axes[0].set_title("分词速度对比（queries/sec）")
    axes[0].set_ylabel("queries/sec")

    axes[1].bar(methods, avg_tokens)
    axes[1].set_title("分词粒度对比（avg tokens/query）")
    axes[1].set_ylabel("avg tokens/query")

    for ax in axes:
        ax.grid(axis="y", linestyle="--", alpha=0.3)

    fig.tight_layout()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def save_markdown(path: str, rows: list[dict], input_file: str, sample_size: int) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("# 分词方法横向对比（P1）\n\n")
        f.write(f"- 输入文件：`{input_file}`\n")
        f.write(f"- 抽样条数：`{sample_size}`\n\n")
        f.write("| 方法 | queries/sec | tokens/sec | 平均每条token数 | 唯一token数 | 单字token占比 |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for r in rows:
            f.write(
                f"| {r['method']} | {r['queries_per_sec']:.2f} | {r['tokens_per_sec']:.2f} | {r['avg_tokens_per_query']:.2f} | {r['unique_tokens']} | {r['single_char_ratio']:.4f} |\n"
            )

        f.write("\n## 初步结论\n")
        f.write("1. 正则分词通常速度最高，但语义边界粗，适合快速预筛。\n")
        f.write("2. jieba精确模式在速度与可解释性上更平衡，适合作为默认方案。\n")
        f.write("3. jieba搜索模式粒度更细，适合召回优先场景，但会增加噪声。\n")


def main():
    parser = argparse.ArgumentParser(description="Tokenizer benchmark and visualization")
    parser.add_argument("--input", required=True, help="CSV file containing query column")
    parser.add_argument("--out-dir", required=True, help="Output folder")
    parser.add_argument("--max-rows", type=int, default=20000, help="Sample row count")
    args = parser.parse_args()

    queries = load_queries(args.input, args.max_rows)
    if not queries:
        raise ValueError("No query data loaded from input CSV")

    # 显式初始化jieba词典，避免首次加载影响单个方法
    jieba.initialize()

    rows = [
        benchmark("jieba_precise", tokenize_jieba_precise, queries),
        benchmark("jieba_search", tokenize_jieba_search, queries),
        benchmark("regex", tokenize_regex, queries),
    ]

    csv_path = os.path.join(args.out_dir, "tokenizer_benchmark.csv")
    png_path = os.path.join(args.out_dir, "tokenizer_benchmark.png")
    md_path = os.path.join(args.out_dir, "tokenizer_benchmark.md")

    save_csv(csv_path, rows)
    save_plot(png_path, rows)
    save_markdown(md_path, rows, args.input, len(queries))


if __name__ == "__main__":
    main()
