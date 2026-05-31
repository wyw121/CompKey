"""
build_aol_snapshot.py

把公开的 AOL User Session Collection 标准化成可复用的离线日志快照：
  - raw/：按来源保存原始 TXT / 压缩包 / 下载文件
  - normalized/：输出 canonical 日志与 tokenized 日志
  - manifest.json：记录文件、字段、样本统计，方便隔离与回溯

说明：
  AOL 日志本身就是经典 query log，包含 Query / QueryTime / ItemRank / ClickURL，
  非常适合直接跑现有的“时间聚合 + 关键词共现”流水线。

用法示例：
  python pipeline/build_aol_snapshot.py \
    --input https://www.cim.mcgill.ca/~dudek/206/Logs/AOL-user-ct-collection/user-ct-test-collection-01.txt \
    --seed-file ./deliverables/P1/seed_keywords_v1.csv \
    --outdir ./data/source_logs/aol
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import urllib.parse
import urllib.request
import gzip
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterator, List, Sequence, Tuple

from dateutil import parser as dateparser


AOL_STOPWORDS = {
    "www",
    "com",
    "net",
    "org",
    "http",
    "https",
    "m",
    "www2",
    "search",
    "query",
}


@dataclass(frozen=True)
class AOLLogRecord:
    event_dt: datetime
    event_time: str
    user_id: str
    query_text: str
    clicked_url: str
    item_rank: str
    tokens: Tuple[str, ...]
    matched_seed: str
    source_file: str


def _normalize_text(text: str) -> str:
    text = (text or "").strip()
    text = text.replace("\r\n", " ").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"[\s_\-/\\.]+", " ", text)
    text = re.sub(r"[\u00a0]+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _parse_event_time(raw_time: str) -> str:
    dt = dateparser.parse(str(raw_time).strip())
    return dt.isoformat(sep=" ")


def _parse_event_dt(raw_time: str) -> datetime:
    return dateparser.parse(str(raw_time).strip())


def _extract_tokens(query_text: str) -> Tuple[str, ...]:
    cleaned = _normalize_text(query_text).lower()
    tokens: List[str] = []
    seen = set()
    for token in re.findall(r"[0-9A-Za-z\u4e00-\u9fff]+", cleaned):
        token = token.strip().lower()
        if not token or len(token) < 2:
            continue
        if token in AOL_STOPWORDS:
            continue
        if token.isdigit():
            continue
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tuple(tokens)


def _load_seed_phrases(seed_file: Path | None) -> List[str]:
    if seed_file is None or not seed_file.exists():
        return []

    seed_phrases: List[str] = []
    with seed_file.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames or []
        keyword_col = "keyword" if "keyword" in fieldnames else (fieldnames[0] if fieldnames else None)
        if keyword_col is None:
            return []
        for row in reader:
            raw = (row.get(keyword_col) or "").strip()
            if not raw:
                continue
            seed_phrases.append(_normalize_text(raw).lower())
    return seed_phrases


def _match_seed(query_text: str, tokens: Sequence[str], seed_phrases: Sequence[str]) -> str:
    if not seed_phrases:
        return ""

    haystack = _normalize_text(query_text).lower()
    best = ""
    for seed in seed_phrases:
        if seed and seed in haystack and len(seed) > len(best):
            best = seed
    if best:
        return best

    token_set = set(tokens)
    for seed in seed_phrases:
        compact = seed.replace(" ", "")
        if compact in token_set:
            return seed
    return ""


def _copy_source_file(source_path: Path, raw_dir: Path) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    target = raw_dir / source_path.name
    if source_path.resolve() != target.resolve():
        shutil.copy2(source_path, target)
    return target


def _download_url(url: str, raw_dir: Path) -> Path:
    parsed = urllib.parse.urlparse(url)
    filename = Path(parsed.path).name or "aol_download.txt"
    target = raw_dir / filename
    raw_dir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 compkey/aol-adapter test@example.com",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as response, target.open("wb") as f:
        shutil.copyfileobj(response, f)
    return target


def _iter_tab_rows(handle) -> Iterator[Dict[str, str]]:
    reader = csv.DictReader(handle, delimiter="\t")
    for row in reader:
        if not row:
            continue
        yield {str(k).strip().strip('"'): (v or "") for k, v in row.items()}


def _iter_rows_from_file(path: Path) -> Iterator[Dict[str, str]]:
    if path.suffix.lower() == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", errors="replace", newline="") as f:
            yield from _iter_tab_rows(f)
        return

    with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
        yield from _iter_tab_rows(f)


def _collect_sources(inputs: Sequence[str], raw_dir: Path) -> List[Path]:
    resolved: List[Path] = []
    for item in inputs:
        if re.match(r"^https?://", item, flags=re.IGNORECASE):
            resolved.append(_download_url(item, raw_dir))
            continue

        path = Path(item)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in {".txt", ".gz"}:
                    resolved.append(_copy_source_file(child, raw_dir))
        elif path.is_file():
            resolved.append(_copy_source_file(path, raw_dir))
        else:
            raise FileNotFoundError(f"input not found: {item}")
    return resolved


def build_snapshot(inputs: Sequence[str], outdir: Path, seed_file: Path | None = None, max_rows: int = 0) -> Dict[str, object]:
    raw_dir = outdir / "raw"
    normalized_dir = outdir / "normalized"
    raw_dir.mkdir(parents=True, exist_ok=True)
    normalized_dir.mkdir(parents=True, exist_ok=True)

    seed_phrases = _load_seed_phrases(seed_file)

    canonical_rows: List[Dict[str, str]] = []
    tokenized_rows: List[Dict[str, str]] = []
    records: List[AOLLogRecord] = []
    files_info: List[Dict[str, object]] = []
    total_events = 0
    total_token_rows = 0
    min_date = None
    max_date = None

    source_files = _collect_sources(inputs, raw_dir)
    for source_path in source_files:
        file_events = 0
        file_tokens = 0
        file_rows = 0

        for row in _iter_rows_from_file(source_path):
            if max_rows and total_events >= max_rows:
                break

            raw_user_id = (row.get("AnonID") or row.get("anonid") or "").strip()
            raw_query = (row.get("Query") or row.get("query") or "").strip()
            raw_time = (row.get("QueryTime") or row.get("querytime") or "").strip()
            raw_rank = (row.get("ItemRank") or row.get("itemrank") or "").strip()
            raw_click = (row.get("ClickURL") or row.get("clickurl") or "").strip()

            if not raw_query or not raw_time:
                continue

            event_dt = _parse_event_dt(raw_time)
            event_time = event_dt.isoformat(sep=" ")
            query_date = event_time[:10]
            query_text = _normalize_text(raw_query)
            tokens = _extract_tokens(raw_query)
            matched_seed = _match_seed(query_text, tokens, seed_phrases)

            record = AOLLogRecord(
                event_dt=event_dt,
                event_time=event_time,
                user_id=raw_user_id,
                query_text=query_text,
                clicked_url=raw_click,
                item_rank=raw_rank,
                tokens=tokens,
                matched_seed=matched_seed,
                source_file=source_path.name,
            )

            canonical_rows.append(
                {
                    "event_time": record.event_time,
                    "user_id": record.user_id,
                    "query_text": record.query_text,
                    "clicked_url": record.clicked_url,
                    "item_rank": record.item_rank,
                    "source": "aol",
                    "source_file": record.source_file,
                    "token_count": str(len(record.tokens)),
                    "matched_seed": record.matched_seed,
                }
            )

            for token in record.tokens:
                tokenized_rows.append(
                    {
                        "query_time": record.event_time,
                        "user_id": record.user_id,
                        "query": record.query_text,
                        "token": token,
                        "matched_seed": record.matched_seed,
                    }
                )
                file_tokens += 1
                total_token_rows += 1

            records.append(record)

            file_events += 1
            file_rows += 1
            total_events += 1
            if min_date is None or query_date < min_date:
                min_date = query_date
            if max_date is None or query_date > max_date:
                max_date = query_date

        files_info.append(
            {
                "file": source_path.name,
                "events": file_events,
                "token_rows": file_tokens,
                "rows_read": file_rows,
            }
        )

    seed_cooccur: Dict[Tuple[str, str], int] = {}
    records_by_user: Dict[str, List[AOLLogRecord]] = {}
    for record in records:
        if not record.tokens:
            continue
        records_by_user.setdefault(record.user_id or "__unknown__", []).append(record)

    window_queries = 2
    session_gap_minutes = 45
    for user_records in records_by_user.values():
        user_records.sort(key=lambda item: item.event_dt)
        for idx, anchor in enumerate(user_records):
            anchor_seed = anchor.matched_seed or (anchor.tokens[0] if anchor.tokens else "")
            if not anchor_seed:
                continue

            candidate_tokens = set()
            left = max(0, idx - window_queries)
            right = min(len(user_records) - 1, idx + window_queries)
            for j in range(left, right + 1):
                neighbor = user_records[j]
                if abs((neighbor.event_dt - anchor.event_dt).total_seconds()) > session_gap_minutes * 60:
                    continue
                for token in neighbor.tokens:
                    cand = token.strip().lower()
                    if not cand or cand == anchor_seed:
                        continue
                    if cand in AOL_STOPWORDS or len(cand) < 2 or cand.isdigit():
                        continue
                    candidate_tokens.add(cand)

            for cand in candidate_tokens:
                seed_cooccur[(anchor_seed, cand)] = seed_cooccur.get((anchor_seed, cand), 0) + 1

    canonical_path = normalized_dir / "canonical_logs.csv"
    tokenized_path = normalized_dir / "tokenized_queries.csv"
    seed_cooccur_path = normalized_dir / "seed_cooccur.csv"
    manifest_path = outdir / "manifest.json"

    with canonical_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["event_time", "user_id", "query_text", "clicked_url", "item_rank", "source", "source_file", "token_count", "matched_seed"],
        )
        writer.writeheader()
        writer.writerows(canonical_rows)

    with tokenized_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["query_time", "user_id", "query", "token", "matched_seed"])
        writer.writeheader()
        writer.writerows(tokenized_rows)

    with seed_cooccur_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["seed", "candidate", "cooccur"])
        writer.writeheader()
        for (seed, cand), cnt in sorted(seed_cooccur.items()):
            writer.writerow({"seed": seed, "candidate": cand, "cooccur": cnt})

    manifest = {
        "source": "aol",
        "dataset": "AOL User Session Collection",
        "input_count": len(inputs),
        "file_count": len(source_files),
        "total_events": total_events,
        "token_rows": total_token_rows,
        "seed_count": len(seed_phrases),
        "date_range": {"start": min_date, "end": max_date},
        "files": files_info,
        "outputs": {
            "canonical": str(canonical_path),
            "tokenized": str(tokenized_path),
            "seed_cooccur": str(seed_cooccur_path),
        },
        "session_cooccur": {
            "window_queries": window_queries,
            "gap_minutes": session_gap_minutes,
            "fallback_seed_strategy": "matched_seed_or_first_token",
        },
        "note": "AOL 是经典 query log，保留 Query、QueryTime、ItemRank 和 ClickURL，适合直接复用现有 pipeline。",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] wrote AOL snapshot to {outdir}")
    print(f"[OK] events={total_events}, token_rows={total_token_rows}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build separated AOL snapshots for the CompKey pipeline")
    parser.add_argument("--input", action="append", default=[], help="Input file/dir/URL; repeatable")
    parser.add_argument("--outdir", default="data/source_logs/aol", help="Output directory for separated AOL data")
    parser.add_argument("--seed-file", default="deliverables/P1/seed_keywords_v1.csv", help="Seed keyword CSV for optional matching")
    parser.add_argument("--max-rows", type=int, default=0, help="Limit processed rows across all inputs; 0 means all")
    args = parser.parse_args()

    if not args.input:
        raise SystemExit("At least one --input path or URL is required")

    outdir = Path(args.outdir)
    seed_file = Path(args.seed_file) if args.seed_file else None
    build_snapshot(args.input, outdir, seed_file=seed_file, max_rows=args.max_rows)


if __name__ == "__main__":
    main()