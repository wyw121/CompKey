from __future__ import annotations

import argparse
import csv
import math
import os
import random
import statistics
import time
from collections import Counter
from pathlib import Path
from statistics import median, mean

import jieba
import matplotlib.pyplot as plt

try:
    import thulac
except Exception:
    thulac = None

try:
    import hanlp
except Exception:
    hanlp = None

from compkey_p3.config import get_settings
from compkey_p3.offline_pipeline import _pick_csv_encoding


TOKEN_PATTERN = __import__("re").compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}")


def load_queries(csv_path: Path, max_rows: int = 20000) -> list[str]:
    queries = []
    enc = _pick_csv_encoding(csv_path)
    with open(csv_path, "r", encoding=enc, newline="") as f:
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


def build_thulac_tokenizer():
    if thulac is None:
        return None
    try:
        thu = thulac.thulac(seg_only=True)
        return lambda s: [t for t in thu.cut(s, text=True).split() if t.strip()]
    except Exception:
        return None


def build_hanlp_tokenizer():
    if hanlp is None:
        return None
    try:
        # try a generic tokenizer pipeline; if model unavailable, this may fail and we will skip
        tok = hanlp.load("CTB6_CONV_SEG") if hasattr(hanlp, "load") else None
        if tok is None:
            return None
        return lambda s: [t for t in tok(s) if str(t).strip()]
    except Exception:
        try:
            # fallback: use hanlp.pipeline if available
            p = hanlp.pipeline() if hasattr(hanlp, "pipeline") else None
            if p:
                return lambda s: p(s, tasks=["tok/fine"])["tok/fine"][0]
        except Exception:
            return None


def benchmark_tokenizer(name: str, func, queries: list[str], rounds: int = 3) -> dict:
    # prewarm
    for q in queries[: min(200, len(queries))]:
        try:
            _ = func(q)
        except Exception:
            pass

    elapsed_rounds = []
    token_counts = []
    all_tokens = Counter()
    single_char = 0

    for i in range(rounds):
        start = time.perf_counter()
        if i == 0:
            for q in queries:
                tokens = func(q)
                token_counts.append(len(tokens))
                for t in tokens:
                    all_tokens[t] += 1
                    if len(t) == 1:
                        single_char += 1
        else:
            for q in queries:
                _ = func(q)
        elapsed_rounds.append(time.perf_counter() - start)

    elapsed = median(elapsed_rounds)
    qps = len(queries) / elapsed if elapsed else 0
    tps = sum(token_counts) / elapsed if elapsed and token_counts else 0

    return {
        "method": name,
        "queries": len(queries),
        "elapsed_sec": elapsed,
        "queries_per_sec": qps,
        "tokens_per_sec": tps,
        "total_tokens": sum(token_counts),
        "avg_tokens_per_query": mean(token_counts) if token_counts else 0,
        "unique_tokens": len(all_tokens),
        "single_char_ratio": (single_char / sum(token_counts)) if sum(token_counts) else 0,
    }


def expand_tokenized_csv(src_tokenized_csv: Path, out_csv: Path, target_tokens: int):
    enc = _pick_csv_encoding(src_tokenized_csv)
    rows = []
    with open(src_tokenized_csv, "r", encoding=enc, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    if not rows:
        raise ValueError("source tokenized CSV empty")

    out_dir = out_csv.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys())

    written = 0
    idx = 0
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        while written < target_tokens:
            r = rows[idx % len(rows)]
            writer.writerow(r)
            written += 1
            idx += 1


def main():
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-rows", type=int, default=20000)
    args = parser.parse_args()

    # input queries for tokenizer benchmark: use seed_related_queries or cleaned_queries
    p1_dir = settings.p1_output_dir
    candidate_inputs = [p1_dir / "seed_related_queries_v1.csv", p1_dir / "cleaned_queries_v1.csv"]
    input_csv = next((p for p in candidate_inputs if p.exists()), candidate_inputs[-1])

    queries = load_queries(input_csv, max_rows=args.max_rows)
    if not queries:
        raise RuntimeError(f"no queries loaded from {input_csv}")

    # build tokenizer list
    tokenizers = [
        ("jieba_precise", tokenize_jieba_precise),
        ("jieba_search", tokenize_jieba_search),
        ("regex", tokenize_regex),
    ]

    th = build_thulac_tokenizer()
    if th:
        tokenizers.append(("thulac", th))

    han = build_hanlp_tokenizer()
    if han:
        tokenizers.append(("hanlp", han))

    rows = []
    for name, func in tokenizers:
        r = benchmark_tokenizer(name, func, queries)
        rows.append(r)

    report_dir = settings.report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    csv_path = report_dir / "p3_tokenizer_benchmark.csv"
    md_path = report_dir / "p3_tokenizer_benchmark.md"

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow(r)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Tokenizer 横向基准（P3 扩展）\n\n")
        f.write(f"- 输入文件：`{input_csv.as_posix()}`\n")
        f.write(f"- 抽样条数：{len(queries)}\n\n")
        f.write("| 方法 | queries/sec | tokens/sec | avg tokens/query | unique_tokens | single_char_ratio |\n")
        f.write("|---|---:|---:|---:|---:|---:|\n")
        for r in rows:
            f.write(f"| {r['method']} | {r['queries_per_sec']:.2f} | {r['tokens_per_sec']:.2f} | {r['avg_tokens_per_query']:.2f} | {r['unique_tokens']} | {r['single_char_ratio']:.4f} |\n")

    print(f"[OK] tokenizer benchmark written: {csv_path}")
    print(f"[OK] tokenizer markdown: {md_path}")

    # --- 大规模扩展测试（构造 100k / 1M token 规模的 tokenized CSV 并跑 build_offline_assets）
    tokenized_src = settings.p1_output_dir / "tokenized_queries_v1.csv"
    if not tokenized_src.exists():
        print("[WARN] source tokenized CSV not found, skipping scale benchmarks")
        return

    scales = [(100_000, "100k"), (1_000_000, "1M")]
    from compkey_p3.offline_pipeline import build_offline_assets
    from compkey_p3.repository import CompKeyRepository
    from compkey_p3.database import DatabaseManager

    scale_results = []
    for target, label in scales:
        tmp_csv = report_dir / f"tokenized_scaled_{label}.csv"
        print(f"building scaled tokenized CSV: {tmp_csv} tokens={target}")
        expand_tokenized_csv(tokenized_src, tmp_csv, target)

        # prepare temp sqlite DB
        db_path = report_dir / f"compkey_scale_{label}.db"
        if db_path.exists():
            db_path.unlink()
        dbm = DatabaseManager(db_path)
        with dbm.connect() as conn:
            dbm.initialize_schema(conn)
            repo = CompKeyRepository(conn)
            start = time.perf_counter()
            summary = build_offline_assets(
                repo,
                seed_csv=settings.seed_csv,
                tokenized_csv=tmp_csv,
                word_freq_csv=settings.p1_output_dir / "word_freq_v1.csv",
                seed_related_csv=settings.p1_output_dir / "seed_related_queries_v1.csv",
                candidate_limit=50,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000.0
        scale_results.append((label, target, elapsed_ms, summary))

    # write scale results
    scale_csv = report_dir / "p3_scale_benchmark.csv"
    with open(scale_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["label", "target_tokens", "build_ms", "seed_count", "mediator_count", "competition_count", "search_log_count"]) 
        for label, target, ms, s in scale_results:
            writer.writerow([label, target, f"{ms:.3f}", s.seed_count, s.mediator_count, s.competition_count, s.search_log_count])

    md_scale = report_dir / "p3_scale_benchmark.md"
    with open(md_scale, "w", encoding="utf-8") as f:
        f.write("# 大规模扩展测试（离线构建耗时）\n\n")
        f.write("| scale | tokens | build_ms | seed_count | mediator_count | competition_count | search_log_count |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|\n")
        for label, target, ms, s in scale_results:
            f.write(f"| {label} | {target} | {ms:.1f} | {s.seed_count} | {s.mediator_count} | {s.competition_count} | {s.search_log_count} |\n")

    print(f"[OK] scale benchmark written: {scale_csv}")


if __name__ == "__main__":
    main()
