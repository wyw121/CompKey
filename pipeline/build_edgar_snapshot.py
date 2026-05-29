"""
build_edgar_snapshot.py

把公开的 SEC EDGAR 日志（ZIP/CSV）标准化成可复用的离线日志快照：
  - raw/：按来源保存原始 ZIP 或 CSV
  - normalized/：输出 canonical 日志与 tokenized 日志
  - manifest.json：记录文件、字段、样本统计，方便隔离与回溯

说明：
  EDGAR 2020+ 日志更接近“站内检索/访问日志”，核心字段通常只有 time 和 uri_path。
  因此脚本会把 uri_path 规范化为 query_text，并从路径中抽取 token，方便复用现有 P1/P3 管线做小范围实验。

用法示例：
  python pipeline/build_edgar_snapshot.py \
    --input https://www.sec.gov/dera/data/Public-EDGAR-log-file-data/2025/Qtr2/log20250630.zip \
    --seed-file ./deliverables/P1/seed_keywords_v1.csv \
    --outdir ./data/source_logs/edgar
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Sequence, Tuple

from dateutil import parser as dateparser


EDGAR_STOPWORDS = {
    "archives",
    "edgar",
    "data",
    "sec",
    "gov",
    "www",
    "html",
    "htm",
    "txt",
    "xml",
    "json",
    "csv",
    "pre",
    "index",
    "headers",
    "cgi",
    "bin",
}


@dataclass(frozen=True)
class EdgarLogRecord:
    event_time: str
    uri_path: str
    query_text: str
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
    return dt.isoformat()


def _extract_tokens(uri_path: str) -> Tuple[str, ...]:
    cleaned = _normalize_text(uri_path).lower()
    tokens: List[str] = []
    seen = set()
    for token in re.findall(r"[0-9A-Za-z\u4e00-\u9fff]+", cleaned):
        token = token.strip().lower()
        if not token:
            continue
        if len(token) < 2:
            continue
        if token in EDGAR_STOPWORDS:
            continue
        if token.isdigit():
            continue
        # 过滤大部分纯文件格式/路径噪声
        if len(re.sub(r"[0-9]", "", token)) == 0:
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
    filename = Path(parsed.path).name or "edgar_download.zip"
    target = raw_dir / filename
    raw_dir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 compkey/edgar-adapter test@example.com",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as response, target.open("wb") as f:
        shutil.copyfileobj(response, f)
    return target


def _iter_csv_rows_from_handle(handle: io.TextIOBase) -> Iterator[Dict[str, str]]:
    reader = csv.DictReader(handle, skipinitialspace=True)
    for row in reader:
        if not row:
            continue
        yield {str(k).strip().strip('"'): (v or "") for k, v in row.items()}


def _iter_rows_from_file(path: Path) -> Iterator[Tuple[str, str]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path, "r") as zf:
            csv_name = next((name for name in zf.namelist() if name.lower().endswith(".csv")), None)
            if csv_name is None:
                raise RuntimeError(f"未在压缩包中找到 CSV: {path}")
            with zf.open(csv_name, "r") as raw:
                text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
                for row in _iter_csv_rows_from_handle(text):
                    yield row.get("time", ""), row.get("uri_path", "")
    else:
        with path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            for row in _iter_csv_rows_from_handle(f):
                yield row.get("time", ""), row.get("uri_path", "")


def _collect_sources(inputs: Sequence[str], raw_dir: Path) -> List[Path]:
    resolved: List[Path] = []
    for item in inputs:
        if re.match(r"^https?://", item, flags=re.IGNORECASE):
            resolved.append(_download_url(item, raw_dir))
            continue

        path = Path(item)
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file() and child.suffix.lower() in {".zip", ".csv"}:
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

        for raw_time, raw_path in _iter_rows_from_file(source_path):
            if max_rows and total_events >= max_rows:
                break

            event_time = _parse_event_time(raw_time)
            query_date = event_time[:10]
            query_text = _normalize_text(raw_path)
            tokens = _extract_tokens(raw_path)
            matched_seed = _match_seed(query_text, tokens, seed_phrases)

            record = EdgarLogRecord(
                event_time=event_time,
                uri_path=raw_path,
                query_text=query_text,
                tokens=tokens,
                matched_seed=matched_seed,
                source_file=source_path.name,
            )
            canonical_rows.append(
                {
                    "event_time": record.event_time,
                    "uri_path": record.uri_path,
                    "query_text": record.query_text,
                    "source": "edgar",
                    "source_file": record.source_file,
                    "token_count": str(len(record.tokens)),
                    "matched_seed": record.matched_seed,
                }
            )

            for token in record.tokens:
                tokenized_rows.append(
                    {
                        "query_time": record.event_time,
                        "user_id": "",
                        "query": record.query_text,
                        "token": token,
                        "matched_seed": record.matched_seed,
                    }
                )
                file_tokens += 1
                total_token_rows += 1

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

    canonical_path = normalized_dir / "canonical_logs.csv"
    tokenized_path = normalized_dir / "tokenized_queries.csv"
    manifest_path = outdir / "manifest.json"

    with canonical_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["event_time", "uri_path", "query_text", "source", "source_file", "token_count", "matched_seed"],
        )
        writer.writeheader()
        writer.writerows(canonical_rows)

    with tokenized_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["query_time", "user_id", "query", "token", "matched_seed"])
        writer.writeheader()
        writer.writerows(tokenized_rows)

    manifest = {
        "source": "edgar",
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
        },
        "note": "EDGAR 日志更接近站内检索/访问日志；脚本将 uri_path 映射为 query_text 以便复用现有日志处理流程。",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] wrote EDGAR snapshot to {outdir}")
    print(f"[OK] events={total_events}, token_rows={total_token_rows}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build separated EDGAR snapshots for the CompKey pipeline")
    parser.add_argument("--input", action="append", default=[], help="Input file/dir/URL; repeatable")
    parser.add_argument("--outdir", default="data/source_logs/edgar", help="Output directory for separated EDGAR data")
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