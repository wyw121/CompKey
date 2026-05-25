from __future__ import annotations

import csv
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import jieba

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


def build_tokenizers():
    tokenizers = {
        "jieba_precise": lambda s: [t for t in jieba.lcut(s) if t.strip()],
        "jieba_search": lambda s: [t for t in jieba.lcut_for_search(s) if t.strip()],
        "regex": lambda s: __import__("re").findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}", s),
    }

    if thulac:
        try:
            thu = thulac.thulac(seg_only=True)
            tokenizers["thulac"] = lambda s: [t for t in thu.cut(s, text=True).split() if t.strip()]
        except Exception:
            pass

    if hanlp:
        try:
            tok = hanlp.load("CTB6_CONV_SEG") if hasattr(hanlp, "load") else None
            if tok:
                tokenizers["hanlp"] = lambda s: [t for t in tok(s) if str(t).strip()]
        except Exception:
            try:
                p = hanlp.pipeline() if hasattr(hanlp, "pipeline") else None
                if p:
                    tokenizers["hanlp"] = lambda s: p(s, tasks=["tok/fine"])["tok/fine"][0]
            except Exception:
                pass

    return tokenizers


def load_query_seed_pairs(tokenized_csv: Path):
    enc = _pick_csv_encoding(tokenized_csv)
    pairs = []
    with open(tokenized_csv, "r", encoding=enc, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # preserve query_time and user_id if present
            query_time = row.get("query_time", "")
            user_id = row.get("user_id", "")
            query = (row.get("query") or "").strip()
            matched_seed = (row.get("matched_seed") or "").strip()
            if not query:
                continue
            pairs.append((query_time, user_id, query, matched_seed))
    # deduplicate while preserving order
    seen = set()
    uniq = []
    for p in pairs:
        key = (p[0], p[1], p[2], p[3])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(p)
    return uniq


def write_tokenized_csv(out_path: Path, rows):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["query_time", "user_id", "query", "token", "matched_seed"]
    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for query_time, user_id, query, matched_seed, tokens in rows:
            for t in tokens:
                writer.writerow({
                    "query_time": query_time,
                    "user_id": user_id,
                    "query": query,
                    "token": t,
                    "matched_seed": matched_seed,
                })


def run_benchmark_for_method(method: str, tokenized_src: Path, settings):
    report_dir = settings.report_dir
    out_tokenized = report_dir / f"tokenized_queries_{method}.csv"
    pairs = load_query_seed_pairs(tokenized_src)
    tokenizers = build_tokenizers()
    if method not in tokenizers:
        print(f"[WARN] tokenizer {method} not available, skipping")
        return False

    func = tokenizers[method]
    rows = []
    for (qt, uid, q, seed) in pairs:
        try:
            tokens = func(q)
        except Exception:
            tokens = []
        rows.append((qt, uid, q, seed, tokens))

    write_tokenized_csv(out_tokenized, rows)

    # backup original
    p1_dir = settings.p1_output_dir
    orig = p1_dir / "tokenized_queries_v1.csv"
    backup = p1_dir / "tokenized_queries_v1.csv.bak"
    if not orig.exists():
        print(f"[ERROR] original tokenized file not found: {orig}")
        return False
    shutil.copy(orig, backup)
    try:
        shutil.copy(out_tokenized, orig)
        # run multimethod benchmark
        cmd = [sys.executable, str(Path(__file__).parent / "run_stage3_multimethod_benchmark.py")]
        print(f"[RUN] {cmd} for tokenizer {method}")
        start = time.perf_counter()
        subprocess.check_call(cmd)
        elapsed = time.perf_counter() - start

        # move outputs
        report_csv = settings.report_dir / "p3_multimethod_benchmark.csv"
        report_md = settings.report_dir / "p3_multimethod_benchmark.md"
        if report_csv.exists():
            shutil.move(str(report_csv), str(settings.report_dir / f"p3_multimethod_benchmark_{method}.csv"))
        if report_md.exists():
            shutil.move(str(report_md), str(settings.report_dir / f"p3_multimethod_benchmark_{method}.md"))

        print(f"[OK] benchmark for {method} completed in {elapsed:.1f}s")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] benchmark failed for {method}: {e}")
        return False
    finally:
        # restore original
        if backup.exists():
            shutil.copy(backup, orig)
            backup.unlink()


def main():
    settings = get_settings()
    settings.report_dir.mkdir(parents=True, exist_ok=True)

    tokenized_src = settings.p1_output_dir / "tokenized_queries_v1.csv"
    tokenizers = list(build_tokenizers().keys())
    print(f"Found tokenizers: {tokenizers}")

    results = {}
    for method in tokenizers:
        ok = run_benchmark_for_method(method, tokenized_src, settings)
        results[method] = ok

    print("Run summary:")
    for m, ok in results.items():
        print(f" - {m}: {'OK' if ok else 'SKIPPED/ERR'}")


if __name__ == "__main__":
    main()
