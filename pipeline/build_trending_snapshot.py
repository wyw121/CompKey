"""
build_trending_snapshot.py

将公开热榜页面的文本快照标准化为课程实验可复用的数据文件：
  - 各来源独立保存 raw / normalized 文件，便于排查字段差异
  - 归一化后再合并为 `keyword_date_counts.csv`，以便复用现有增量入库脚本
  - 额外输出空的 `seed_cooccur.csv`，保持与现有更新脚本接口兼容

输入格式：
  该脚本支持把浏览器页面的 `document.body.innerText` 导出文本作为输入。
  例如通过 VS Code 浏览器工具抓取后保存为 `.txt` 文件，再以 `--capture source=path` 方式传入。

示例：
  python pipeline/build_trending_snapshot.py \
    --capture baidu=./snapshots/baidu.txt \
    --capture zhihu=./snapshots/zhihu.txt \
    --capture weibo=./snapshots/weibo.txt \
    --outdir ./data/external_trending
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


RANK_HEAT_RE = re.compile(r"^(\d+)\.\s*(.*?)\s+(\d+(?:\.\d+)?)(万|亿)(?:\s*热度)?$")
RANK_ONLY_RE = re.compile(r"^(\d+)\.\s*$")
HEAT_RE = re.compile(r"(\d+(?:\.\d+)?)(万|亿)?(?:热度)?")


@dataclass(frozen=True)
class TrendRecord:
    source: str
    rank: int
    keyword: str
    raw_heat: float
    heat_unit: str


def _clean_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\t", " ")
    text = text.replace("", " ")
    text = text.replace("|", " ")
    text = re.sub(r"[ \u00a0]+", " ", text)
    return text


def _parse_capture_text(source: str, text: str) -> List[TrendRecord]:
    lines = [line.strip() for line in _clean_text(text).split("\n")]
    records: List[TrendRecord] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if not line:
            i += 1
            continue

        # 一行内同时包含 rank、标题和热度的场景（百度/微博常见）
        compact = re.sub(r"\s+", " ", line).strip()
        m = RANK_HEAT_RE.match(compact)
        if m:
            rank = int(m.group(1))
            keyword = m.group(2).strip()
            raw_heat = float(m.group(3))
            heat_unit = m.group(4)
            if keyword:
                records.append(TrendRecord(source=source, rank=rank, keyword=keyword, raw_heat=raw_heat, heat_unit=heat_unit))
            i += 1
            continue

        # rank 独占一行，标题与热度分离（知乎常见）
        m = RANK_ONLY_RE.match(compact)
        if m:
            rank = int(m.group(1))
            title = ""
            heat_text = ""

            j = i + 1
            while j < len(lines) and not lines[j]:
                j += 1
            if j < len(lines):
                title = lines[j].strip()
            j += 1
            while j < len(lines) and not lines[j]:
                j += 1
            if j < len(lines):
                heat_text = lines[j].strip()

            heat_match = HEAT_RE.search(heat_text)
            raw_heat = float(heat_match.group(1)) if heat_match else 0.0
            heat_unit = heat_match.group(2) or ""

            if title:
                records.append(TrendRecord(source=source, rank=rank, keyword=title, raw_heat=raw_heat, heat_unit=heat_unit))
            i = max(i + 1, j + 1)
            continue

        i += 1

    return records


def _normalize_records(records: List[TrendRecord], snapshot_date: str) -> List[Dict[str, str]]:
    if not records:
        return []

    max_heat = max((r.raw_heat for r in records), default=0.0)
    normalized: List[Dict[str, str]] = []
    for r in records:
        if max_heat > 0:
            freq = max(1, int(round(1000.0 * r.raw_heat / max_heat)))
        else:
            freq = max(1, 1000 - r.rank + 1)
        normalized.append(
            {
                "keyword": r.keyword,
                "date": snapshot_date,
                "freq": str(freq),
                "uniq_users": "0",
                "source": r.source,
                "source_rank": str(r.rank),
                "raw_heat": f"{r.raw_heat:g}",
                "raw_heat_unit": r.heat_unit,
            }
        )
    return normalized


def _write_csv(path: Path, rows: Iterable[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _parse_capture_arg(value: str) -> Tuple[str, Path]:
    if "=" not in value:
        raise ValueError(f"invalid capture spec: {value!r}; expected source=path")
    source, raw_path = value.split("=", 1)
    source = source.strip().lower()
    path = Path(raw_path.strip())
    if not source:
        raise ValueError(f"invalid capture spec: {value!r}; source is empty")
    return source, path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build separated trending snapshots from browser text captures")
    parser.add_argument(
        "--capture",
        action="append",
        default=[],
        help="Capture input in the form source_id=path_to_text_snapshot; repeatable",
    )
    parser.add_argument("--outdir", default="data/external_trending", help="Output directory for separated trend data")
    parser.add_argument("--snapshot-date", default=datetime.now().date().isoformat(), help="ISO date used in keyword_date_counts")
    args = parser.parse_args()

    if not args.capture:
        raise SystemExit("At least one --capture source=path is required")

    outdir = Path(args.outdir)
    raw_dir = outdir / "raw"
    normalized_dir = outdir / "normalized"
    merged_dir = outdir / "merged"

    all_normalized: List[Dict[str, str]] = []
    report: Dict[str, Dict[str, str]] = {}

    for capture_spec in args.capture:
        source, path = _parse_capture_arg(capture_spec)
        if not path.exists():
            raise FileNotFoundError(f"capture not found: {path}")

        text = path.read_text(encoding="utf-8", errors="replace")
        records = _parse_capture_text(source, text)
        normalized = _normalize_records(records, args.snapshot_date)
        all_normalized.extend(normalized)

        raw_target = raw_dir / f"{source}.txt"
        raw_target.parent.mkdir(parents=True, exist_ok=True)
        raw_target.write_text(text, encoding="utf-8")

        normalized_target = normalized_dir / f"{source}.csv"
        _write_csv(
            normalized_target,
            normalized,
            ["keyword", "date", "freq", "uniq_users", "source", "source_rank", "raw_heat", "raw_heat_unit"],
        )

        report[source] = {
            "capture_path": str(path),
            "records": str(len(records)),
            "normalized_rows": str(len(normalized)),
            "top_keyword": normalized[0]["keyword"] if normalized else "",
        }

    # 合并层：仅保留更新脚本需要的核心字段，方便直接导入现有 SQLite 结构
    merged_bucket: Dict[Tuple[str, str], int] = defaultdict(int)
    merged_users: Dict[Tuple[str, str], int] = defaultdict(int)
    for row in all_normalized:
        key = (row["keyword"], row["date"])
        merged_bucket[key] += int(row["freq"])
        merged_users[key] = max(merged_users[key], int(row["uniq_users"]))

    merged_rows = [
        {
            "keyword": keyword,
            "date": date,
            "freq": str(freq),
            "uniq_users": str(merged_users[(keyword, date)]),
        }
        for (keyword, date), freq in sorted(merged_bucket.items(), key=lambda item: (-item[1], item[0][0]))
    ]

    _write_csv(merged_dir / "keyword_date_counts.csv", merged_rows, ["keyword", "date", "freq", "uniq_users"])
    _write_csv(merged_dir / "seed_cooccur.csv", [], ["seed", "candidate", "cooccur"])

    report_path = merged_dir / "ingest_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "snapshot_date": args.snapshot_date,
                "source_count": len(args.capture),
                "merged_keyword_count": len(merged_rows),
                "sources": report,
                "note": "raw/normalized 分层保留了来源差异，merged 层仅输出与现有增量入库兼容的核心字段。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"[OK] wrote separated trend snapshots to {outdir}")
    print(f"[OK] merged rows: {len(merged_rows)}")


if __name__ == "__main__":
    main()