import argparse
import csv
import re
from typing import Dict, List

QUERY_BRACKET_PATTERN = re.compile(r"\[(.*?)\]")


def load_seeds(seed_csv: str) -> List[str]:
    seeds = []
    with open(seed_csv, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            kw = (row.get("keyword") or "").strip()
            if kw:
                seeds.append(kw)
    return list(dict.fromkeys(seeds))


def extract_queries_from_line(line: str) -> List[str]:
    """Extract all query-like fields from one record.

    user_tag_query.* files are tab-separated:
    ID, age, gender, education, then a variable-length query list.
    We scan every field after the first 4 columns as a potential query.
    """

    parts = [p.strip() for p in line.rstrip("\n\r").split("\t")]
    if len(parts) <= 4:
        parts = [p.strip() for p in re.split(r"\s+", line.strip())]
    if len(parts) <= 4:
        return []

    queries: List[str] = []
    for field in parts[4:]:
        if not field:
            continue
        m = QUERY_BRACKET_PATTERN.search(field)
        query = (m.group(1) if m else field).strip().strip("[]")
        if query:
            queries.append(query)
    return queries


def main(input_path: str, seed_csv: str, out_dir: str, sample_per_seed: int = 3):
    seeds = load_seeds(seed_csv)
    counts: Dict[str, int] = {s: 0 for s in seeds}
    samples: Dict[str, List[str]] = {s: [] for s in seeds}

    with open(input_path, "r", encoding="gb18030", errors="replace") as f:
        for line in f:
            queries = extract_queries_from_line(line)
            if not queries:
                continue
            for q in queries:
                for s in seeds:
                    if s in q:
                        counts[s] += 1
                        if len(samples[s]) < sample_per_seed:
                            samples[s].append(q)

    # write counts
    import os
    os.makedirs(out_dir, exist_ok=True)
    counts_path = os.path.join(out_dir, "seed_presence_counts.csv")
    with open(counts_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["seed", "count"])
        for s in seeds:
            writer.writerow([s, counts.get(s, 0)])

    samples_path = os.path.join(out_dir, "seed_presence_samples.csv")
    with open(samples_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["seed", "sample_query"])
        for s in seeds:
            for q in samples[s]:
                writer.writerow([s, q])

    print("Wrote:", counts_path)
    print("Wrote:", samples_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--seeds", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--sample-per-seed", type=int, default=3)
    args = parser.parse_args()
    main(args.input, args.seeds, args.out, args.sample_per_seed)
