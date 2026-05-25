from __future__ import annotations

import csv
import hashlib
import math
import statistics
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from compkey_p3.config import get_settings
from compkey_p3.offline_pipeline import STOPWORDS, _pick_csv_encoding, load_seed_keywords


METHODS = (
    "compkey_current",
    "cooccur_freq",
    "tfidf",
    "pmi",
    "bm25",
)


@dataclass(frozen=True)
class EvalSample:
    seed: str
    user_id: str
    query: str
    truth_tokens: frozenset[str]


def _is_valid_token(seed: str, token: str) -> bool:
    token = (token or "").strip()
    if not token:
        return False
    if token in STOPWORDS:
        return False
    if token == seed:
        return False
    return True


def _split_key(seed: str, user_id: str, query: str) -> bool:
    """True -> validation, False -> training."""
    raw = f"{seed}|{user_id}|{query}".encode("utf-8", errors="ignore")
    h = hashlib.md5(raw).hexdigest()
    return int(h[:2], 16) < 51  # ~20%


def _load_token_rows(tokenized_csv: Path) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    encoding = _pick_csv_encoding(tokenized_csv)
    with open(tokenized_csv, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            seed = (row.get("matched_seed") or "").strip()
            token = (row.get("token") or "").strip()
            user_id = (row.get("user_id") or "").strip()
            query = (row.get("query") or "").strip()
            if not seed or not query:
                continue
            rows.append((seed, user_id, query, token))
    return rows


def _build_train_eval(
    rows: list[tuple[str, str, str, str]], seed_set: set[str]
) -> tuple[dict[str, Counter], Counter, Counter, Counter, list[EvalSample]]:
    seed_token_counts: dict[str, Counter] = defaultdict(Counter)
    seed_total_tokens: Counter = Counter()
    global_token_counts: Counter = Counter()
    seed_doc_freq: Counter = Counter()

    eval_query_tokens: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    seed_seen_tokens: dict[str, set[str]] = defaultdict(set)

    for seed, user_id, query, token in rows:
        if seed not in seed_set or not _is_valid_token(seed, token):
            continue

        is_val = _split_key(seed, user_id, query)
        if is_val:
            eval_query_tokens[(seed, user_id, query)].add(token)
        else:
            seed_token_counts[seed][token] += 1
            seed_total_tokens[seed] += 1
            global_token_counts[token] += 1
            if token not in seed_seen_tokens[seed]:
                seed_seen_tokens[seed].add(token)
                seed_doc_freq[token] += 1

    eval_samples = [
        EvalSample(seed=seed, user_id=user_id, query=query, truth_tokens=frozenset(tokens))
        for (seed, user_id, query), tokens in eval_query_tokens.items()
        if tokens
    ]

    return seed_token_counts, seed_total_tokens, global_token_counts, seed_doc_freq, eval_samples


def _rank_for_seed(
    method: str,
    seed: str,
    seed_token_counts: dict[str, Counter],
    seed_total_tokens: Counter,
    global_token_counts: Counter,
    seed_doc_freq: Counter,
    total_global_tokens: int,
    total_seed_docs: int,
    top_n: int,
) -> list[str]:
    token_counter = seed_token_counts.get(seed)
    if not token_counter:
        return []

    total_seed = max(seed_total_tokens.get(seed, 0), 1)
    total_global = max(total_global_tokens, 1)
    avg_seed_len = max(sum(seed_total_tokens.values()) / max(total_seed_docs, 1), 1.0)

    scored: list[tuple[str, float, int]] = []
    for token, c in token_counter.items():
        g = max(global_token_counts.get(token, 0), 1)
        if method == "compkey_current":
            local_share = c / total_seed
            rarity = 1.0 / (1.0 + math.log1p(g))
            score = local_share * (1.0 + math.log1p(c)) * rarity * rarity
        elif method == "cooccur_freq":
            score = float(c)
        elif method == "tfidf":
            tf = c / total_seed
            idf = math.log((1.0 + total_global) / (1.0 + g))
            score = tf * idf
        elif method == "pmi":
            p_token_given_seed = c / total_seed
            p_token = g / total_global
            score = math.log((p_token_given_seed + 1e-12) / (p_token + 1e-12))
        elif method == "bm25":
            df = max(seed_doc_freq.get(token, 0), 1)
            k1 = 1.5
            b = 0.75
            idf = math.log(1.0 + (total_seed_docs - df + 0.5) / (df + 0.5))
            norm = c + k1 * (1.0 - b + b * (total_seed / avg_seed_len))
            score = idf * (c * (k1 + 1.0)) / norm if norm else 0.0
        else:
            raise ValueError(f"unknown method: {method}")

        scored.append((token, score, c))

    scored.sort(key=lambda x: (-x[1], -x[2], x[0]))
    return [t for t, _, _ in scored[:top_n]]


def _evaluate_method(
    method: str,
    eval_samples: list[EvalSample],
    seed_token_counts: dict[str, Counter],
    seed_total_tokens: Counter,
    global_token_counts: Counter,
    seed_doc_freq: Counter,
    top_n: int = 10,
) -> dict[str, float]:
    total_global_tokens = sum(global_token_counts.values())
    total_seed_docs = max(len(seed_total_tokens), 1)

    recall_at_5: list[float] = []
    recall_at_10: list[float] = []
    mrr_at_10: list[float] = []

    no_cache_latencies: list[float] = []
    cache_latencies: list[float] = []

    cache: dict[str, list[str]] = {}
    non_empty_pred = 0

    for sample in eval_samples:
        truth = sample.truth_tokens
        if not truth:
            continue

        t0 = time.perf_counter()
        pred = _rank_for_seed(
            method,
            sample.seed,
            seed_token_counts,
            seed_total_tokens,
            global_token_counts,
            seed_doc_freq,
            total_global_tokens,
            total_seed_docs,
            top_n,
        )
        no_cache_latencies.append((time.perf_counter() - t0) * 1000.0)

        t1 = time.perf_counter()
        if sample.seed not in cache:
            cache[sample.seed] = _rank_for_seed(
                method,
                sample.seed,
                seed_token_counts,
                seed_total_tokens,
                global_token_counts,
                seed_doc_freq,
                total_global_tokens,
                total_seed_docs,
                top_n,
            )
        pred_cached = cache[sample.seed]
        cache_latencies.append((time.perf_counter() - t1) * 1000.0)

        if pred:
            non_empty_pred += 1

        top5 = pred[:5]
        top10 = pred[:10]
        hit5 = len(set(top5) & truth)
        hit10 = len(set(top10) & truth)
        recall_at_5.append(hit5 / len(truth))
        recall_at_10.append(hit10 / len(truth))

        rr = 0.0
        for idx, token in enumerate(top10, start=1):
            if token in truth:
                rr = 1.0 / idx
                break
        mrr_at_10.append(rr)

    n = max(len(eval_samples), 1)
    return {
        "eval_queries": float(len(eval_samples)),
        "recall@5": statistics.mean(recall_at_5) if recall_at_5 else 0.0,
        "recall@10": statistics.mean(recall_at_10) if recall_at_10 else 0.0,
        "mrr@10": statistics.mean(mrr_at_10) if mrr_at_10 else 0.0,
        "coverage@10": non_empty_pred / n,
        "avg_latency_no_cache_ms": statistics.mean(no_cache_latencies) if no_cache_latencies else 0.0,
        "avg_latency_cache_ms": statistics.mean(cache_latencies) if cache_latencies else 0.0,
    }


def main() -> None:
    settings = get_settings()
    settings.report_dir.mkdir(parents=True, exist_ok=True)

    seeds = [row.keyword for row in load_seed_keywords(settings.seed_csv)]
    seed_set = set(seeds)

    tokenized_csv = settings.p1_output_dir / "tokenized_queries_v1.csv"
    rows = _load_token_rows(tokenized_csv)
    seed_token_counts, seed_total_tokens, global_token_counts, seed_doc_freq, eval_samples = _build_train_eval(rows, seed_set)

    result_rows: list[tuple[str, dict[str, float]]] = []
    for method in METHODS:
        metrics = _evaluate_method(
            method,
            eval_samples,
            seed_token_counts,
            seed_total_tokens,
            global_token_counts,
            seed_doc_freq,
            top_n=10,
        )
        result_rows.append((method, metrics))

    csv_path = settings.report_dir / "p3_multimethod_benchmark.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "method",
                "eval_queries",
                "recall@5",
                "recall@10",
                "mrr@10",
                "coverage@10",
                "avg_latency_no_cache_ms",
                "avg_latency_cache_ms",
            ]
        )
        for method, m in result_rows:
            writer.writerow(
                [
                    method,
                    int(m["eval_queries"]),
                    f"{m['recall@5']:.6f}",
                    f"{m['recall@10']:.6f}",
                    f"{m['mrr@10']:.6f}",
                    f"{m['coverage@10']:.6f}",
                    f"{m['avg_latency_no_cache_ms']:.6f}",
                    f"{m['avg_latency_cache_ms']:.6f}",
                ]
            )

    md_path = settings.report_dir / "p3_multimethod_benchmark.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# P3 多方案横向评测（真实运行）\n\n")
        f.write("## 1. 实验设置\n\n")
        f.write(f"- 数据文件：`{tokenized_csv.as_posix()}`\n")
        f.write(f"- seed 数量：{len(seed_set)}\n")
        f.write(f"- 训练样本 token 数：{sum(seed_total_tokens.values())}\n")
        f.write(f"- 训练样本 seed-doc 频次数：{sum(seed_doc_freq.values())}\n")
        f.write(f"- 验证查询数：{len(eval_samples)}（按 query 稳定哈希约 8:2 切分）\n")
        f.write("- 评估指标：Recall@5、Recall@10、MRR@10、Coverage@10、平均延时（缓存开/关）\n\n")

        f.write("## 2. 方法说明\n\n")
        f.write("1. `compkey_current`：当前项目方案（local share + rarity + log 支持度）\n")
        f.write("2. `cooccur_freq`：共现频次基线\n")
        f.write("3. `tfidf`：TF-IDF 风格打分（IR 常用）\n")
        f.write("4. `pmi`：点互信息（关联规则常用）\n\n")
        f.write("5. `bm25`：BM25 强检索基线（更强调词频饱和与文档长度归一）\n\n")

        f.write("## 3. 结果\n\n")
        f.write("| method | eval_queries | recall@5 | recall@10 | mrr@10 | coverage@10 | no_cache_ms | cache_ms |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|---:|\n")
        for method, m in result_rows:
            f.write(
                "| {} | {} | {:.4f} | {:.4f} | {:.4f} | {:.4f} | {:.4f} | {:.4f} |\n".format(
                    method,
                    int(m["eval_queries"]),
                    m["recall@5"],
                    m["recall@10"],
                    m["mrr@10"],
                    m["coverage@10"],
                    m["avg_latency_no_cache_ms"],
                    m["avg_latency_cache_ms"],
                )
            )

        f.write("\n## 4. 结论（基于本次实测）\n\n")
        best_recall = max(result_rows, key=lambda x: x[1]["recall@10"])
        best_mrr = max(result_rows, key=lambda x: x[1]["mrr@10"])
        fastest = min(result_rows, key=lambda x: x[1]["avg_latency_no_cache_ms"])
        f.write(f"- Recall@10 最优：`{best_recall[0]}`（{best_recall[1]['recall@10']:.4f}）\n")
        f.write(f"- MRR@10 最优：`{best_mrr[0]}`（{best_mrr[1]['mrr@10']:.4f}）\n")
        f.write(f"- 无缓存延时最优：`{fastest[0]}`（{fastest[1]['avg_latency_no_cache_ms']:.4f} ms）\n")

    print(f"[OK] multi-method benchmark written: {csv_path}")
    print(f"[OK] multi-method summary written: {md_path}")


if __name__ == "__main__":
    main()
