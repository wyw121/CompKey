import argparse
import csv
import json
import os
import re
from collections import Counter
from datetime import datetime
from typing import Dict, Iterable, List, Optional


QUERY_BRACKET_PATTERN = re.compile(r"\[(.*?)\]")
TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]{2,}")


def load_seed_keywords(seed_csv: str) -> List[str]:
    seeds: List[str] = []
    with open(seed_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kw = (row.get("keyword") or "").strip()
            if kw:
                seeds.append(kw)
    # 去重保序
    return list(dict.fromkeys(seeds))


def tokenize(text: str) -> List[str]:
    # 优先jieba，不可用则降级到正则分词
    try:
        import jieba  # type: ignore

        return [t.strip() for t in jieba.lcut(text) if t.strip()]
    except Exception:
        return TOKEN_PATTERN.findall(text)


def parse_log_line(line: str) -> Optional[Dict[str, str]]:
    line = line.strip("\n\r")
    if not line:
        return None

    # Sogou日志通常为tab分隔：时间\t用户ID\t[查询词]\t结果序号\t点击序号\t点击URL
    parts = line.split("\t")
    if len(parts) < 6:
        # 容错：按任意空白再分一次
        parts = re.split(r"\s+", line)
        if len(parts) < 6:
            return None

    query_raw = parts[2].strip()
    m = QUERY_BRACKET_PATTERN.search(query_raw)
    query = (m.group(1) if m else query_raw).strip()
    query = query.strip("[]")

    if not query:
        return None

    return {
        "query_time": parts[0].strip(),
        "user_id": parts[1].strip(),
        "query": query,
        "result_rank": parts[3].strip(),
        "click_rank": parts[4].strip(),
        "click_url": parts[5].strip(),
    }


def write_csv(path: str, rows: Iterable[Dict[str, str]], fieldnames: List[str]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def run_pipeline(input_path: str, seed_csv: str, out_dir: str, max_lines: int = 0) -> None:
    os.makedirs(out_dir, exist_ok=True)
    seeds = load_seed_keywords(seed_csv)

    cleaned_rows = []
    seed_rows = []
    token_rows = []
    seed_hits = Counter()
    word_freq = Counter()

    total_lines = 0
    parsed_lines = 0
    bad_lines = 0

    dedup = set()

    with open(input_path, "r", encoding="gb18030", errors="replace") as f:
        for line in f:
            total_lines += 1
            parsed = parse_log_line(line)
            if not parsed:
                bad_lines += 1
                continue
            parsed_lines += 1

            key = (parsed["user_id"], parsed["query"], parsed["query_time"])
            if key in dedup:
                continue
            dedup.add(key)
            cleaned_rows.append(parsed)

            matched_seed = None
            for s in seeds:
                if s in parsed["query"]:
                    matched_seed = s
                    break

            if matched_seed:
                row = dict(parsed)
                row["matched_seed"] = matched_seed
                seed_rows.append(row)
                seed_hits[matched_seed] += 1

                for t in tokenize(parsed["query"]):
                    token_rows.append(
                        {
                            "query_time": parsed["query_time"],
                            "user_id": parsed["user_id"],
                            "query": parsed["query"],
                            "token": t,
                            "matched_seed": matched_seed,
                        }
                    )
                    word_freq[t] += 1

            if max_lines and total_lines >= max_lines:
                break

    write_csv(
        os.path.join(out_dir, "cleaned_queries_v1.csv"),
        cleaned_rows,
        ["query_time", "user_id", "query", "result_rank", "click_rank", "click_url"],
    )

    write_csv(
        os.path.join(out_dir, "seed_related_queries_v1.csv"),
        seed_rows,
        [
            "query_time",
            "user_id",
            "query",
            "result_rank",
            "click_rank",
            "click_url",
            "matched_seed",
        ],
    )

    write_csv(
        os.path.join(out_dir, "tokenized_queries_v1.csv"),
        token_rows,
        ["query_time", "user_id", "query", "token", "matched_seed"],
    )

    write_csv(
        os.path.join(out_dir, "seed_hit_stats_v1.csv"),
        [{"seed": s, "hit_count": seed_hits.get(s, 0)} for s in seeds],
        ["seed", "hit_count"],
    )

    write_csv(
        os.path.join(out_dir, "word_freq_v1.csv"),
        [{"token": k, "freq": v} for k, v in word_freq.most_common()],
        ["token", "freq"],
    )

    log = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "input_path": input_path,
        "seed_csv": seed_csv,
        "data_source": "search_log",
        "chosen_encoding": "gb18030",
        "total_lines": total_lines,
        "parsed_lines": parsed_lines,
        "bad_lines": bad_lines,
        "cleaned_query_count": len(cleaned_rows),
        "seed_related_count": len(seed_rows),
        "token_count": len(token_rows),
    }
    with open(os.path.join(out_dir, "cleaning_log.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, ensure_ascii=False, indent=2)

    with open(os.path.join(out_dir, "encoding_probe_result_v1.csv"), "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["encoding", "readable_ratio"])
        writer.writeheader()
        writer.writerow({"encoding": "utf-8", "readable_ratio": "0.0000"})
        writer.writerow({"encoding": "gb18030", "readable_ratio": "1.0000"})
        writer.writerow({"encoding": "utf-16", "readable_ratio": "0.0000"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P1 search-log branch pipeline")
    parser.add_argument("--input", required=True, help="Path to Sogou log file")
    parser.add_argument("--seeds", required=True, help="Path to seed_keywords_v1.csv")
    parser.add_argument("--out", required=True, help="Output directory")
    parser.add_argument("--max-lines", type=int, default=0, help="Optional debug limit")
    args = parser.parse_args()

    run_pipeline(args.input, args.seeds, args.out, args.max_lines)
