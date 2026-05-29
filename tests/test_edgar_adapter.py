import csv
import io
import json
import os
import sqlite3
import subprocess
import sys
import zipfile
from pathlib import Path


def _write_seed_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["keyword", "domain", "reason", "owner"])
        writer.writeheader()
        writer.writerow({"keyword": "alpha", "domain": "test", "reason": "test", "owner": "test"})


def _write_edgar_zip(path: Path) -> None:
    csv_bytes = io.StringIO()
    writer = csv.writer(csv_bytes)
    writer.writerow(["time", "uri_path"])
    writer.writerow(["2025-06-30T23:59:58.997-0400", "/Archives/edgar/data/12345/alpha-beta.txt"])
    writer.writerow(["2025-06-30T23:59:57.997-0400", "/Archives/edgar/data/67890/gamma-delta.xml"])

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("log20250630.csv", csv_bytes.getvalue())


def test_edgar_adapter_end_to_end(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    edgar_zip = tmp_path / "log20250630.zip"
    seed_csv = tmp_path / "seed_keywords.csv"
    outdir = tmp_path / "edgar_out"
    inc_dir = tmp_path / "inc"
    dbpath = tmp_path / "edgar.db"

    _write_edgar_zip(edgar_zip)
    _write_seed_csv(seed_csv)

    res = subprocess.run(
        [
            sys.executable,
            str(repo_root / "pipeline" / "build_edgar_snapshot.py"),
            "--input",
            str(edgar_zip),
            "--seed-file",
            str(seed_csv),
            "--outdir",
            str(outdir),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"build_edgar_snapshot failed: {res.stderr}\n{res.stdout}"

    tokenized = outdir / "normalized" / "tokenized_queries.csv"
    manifest = outdir / "manifest.json"
    assert tokenized.exists()
    assert manifest.exists()

    res2 = subprocess.run(
        [
            sys.executable,
            str(repo_root / "pipeline" / "ingest_incremental.py"),
            "--tokenized",
            str(tokenized),
            "--outdir",
            str(inc_dir),
        ],
        capture_output=True,
        text=True,
    )
    assert res2.returncode == 0, f"ingest_incremental failed: {res2.stderr}\n{res2.stdout}"

    res3 = subprocess.run(
        [
            sys.executable,
            str(repo_root / "pipeline" / "update_db_from_incremental.py"),
            "--db",
            str(dbpath),
            "--inc",
            str(inc_dir),
            "--config",
            str(repo_root / "config" / "competition_params.yaml"),
        ],
        capture_output=True,
        text=True,
    )
    assert res3.returncode == 0, f"update_db_from_incremental failed: {res3.stderr}\n{res3.stdout}"

    conn = sqlite3.connect(str(dbpath))
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM keyword_timeseries")
    assert cur.fetchone()[0] > 0
    cur.execute("SELECT COUNT(*) FROM keyword_stats")
    assert cur.fetchone()[0] > 0
    conn.close()

    with manifest.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["source"] == "edgar"
    assert data["total_events"] == 2