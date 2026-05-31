import csv
import io
import json
import sqlite3
import subprocess
import sys
from pathlib import Path


def _write_seed_csv(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["keyword", "domain", "reason", "owner"])
        writer.writeheader()
        writer.writerow({"keyword": "staple", "domain": "test", "reason": "test", "owner": "test"})


def _write_aol_sample(path: Path) -> None:
    text = io.StringIO()
    writer = csv.writer(text, delimiter="\t")
    writer.writerow(["AnonID", "Query", "QueryTime", "ItemRank", "ClickURL"])
    writer.writerow(["142", "rentdirect.com", "2006-03-01 07:17:12", "", ""])
    writer.writerow(["142", "staple.com", "2006-03-17 21:19:29", "1", "http://www.staple.com"])

    path.write_text(text.getvalue(), encoding="utf-8")


def test_aol_adapter_end_to_end(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    aol_txt = tmp_path / "user-ct-test-collection-01.txt"
    seed_csv = tmp_path / "seed_keywords.csv"
    outdir = tmp_path / "aol_out"
    inc_dir = tmp_path / "inc"
    dbpath = tmp_path / "aol.db"

    _write_aol_sample(aol_txt)
    _write_seed_csv(seed_csv)

    res = subprocess.run(
        [
            sys.executable,
            str(repo_root / "pipeline" / "build_aol_snapshot.py"),
            "--input",
            str(aol_txt),
            "--seed-file",
            str(seed_csv),
            "--outdir",
            str(outdir),
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0, f"build_aol_snapshot failed: {res.stderr}\n{res.stdout}"

    tokenized = outdir / "normalized" / "tokenized_queries.csv"
    seed_cooccur = outdir / "normalized" / "seed_cooccur.csv"
    manifest = outdir / "manifest.json"
    assert tokenized.exists()
    assert seed_cooccur.exists()
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
    cur.execute("SELECT COUNT(*) FROM competition_result")
    assert cur.fetchone()[0] > 0
    conn.close()

    with manifest.open("r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["source"] == "aol"
    assert data["dataset"] == "AOL User Session Collection"
    assert data["total_events"] == 2