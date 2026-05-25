from __future__ import annotations

import csv
from pathlib import Path

from compkey_p3.config import get_settings


def main():
    settings = get_settings()
    report_dir = settings.report_dir
    files = list(report_dir.glob("p3_multimethod_benchmark_*.csv"))
    if not files:
        print("no per-tokenizer benchmark files found")
        return

    out_csv = report_dir / "p3_multimethod_tokenizer_compare.csv"
    out_md = report_dir / "p3_multimethod_tokenizer_compare.md"

    rows = []
    for f in files:
        method_name = f.stem.replace("p3_multimethod_benchmark_", "")
        with open(f, "r", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for r in reader:
                r2 = dict(r)
                r2["tokenizer"] = method_name
                rows.append(r2)

    fieldnames = ["tokenizer", "method", "eval_queries", "recall@5", "recall@10", "mrr@10", "coverage@10", "avg_latency_no_cache_ms", "avg_latency_cache_ms"]
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, "") for k in fieldnames})

    # write markdown summary grouped by tokenizer
    with open(out_md, "w", encoding="utf-8") as f:
        f.write("# Tokenizer × Method 比较\n\n")
        f.write("此表将每个 tokenizer 下的多方法指标并列，便于横向对比。\n\n")
        tokenizers = sorted(set(r["tokenizer"] for r in rows))
        for t in tokenizers:
            f.write(f"## {t}\n\n")
            f.write("| method | eval_queries | recall@5 | recall@10 | mrr@10 | coverage@10 | no_cache_ms | cache_ms |\n")
            f.write("|---|---:|---:|---:|---:|---:|---:|---:|\n")
            for r in rows:
                if r["tokenizer"] != t:
                    continue
                f.write(f"| {r['method']} | {r['eval_queries']} | {float(r['recall@5']):.4f} | {float(r['recall@10']):.4f} | {float(r['mrr@10']):.4f} | {float(r['coverage@10']):.4f} | {float(r['avg_latency_no_cache_ms']):.4f} | {float(r['avg_latency_cache_ms']):.4f} |\n")
            f.write("\n")

    print(f"wrote {out_csv} and {out_md}")


if __name__ == "__main__":
    main()
