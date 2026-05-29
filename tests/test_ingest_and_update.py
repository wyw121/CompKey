import subprocess
import sys
import os
import json
import pandas as pd


def write_tokenized_csv(path):
    df = pd.DataFrame([
        {'query_time': '2020-01-01 10:00:00', 'user_id': 'u1', 'query': '苹果 手机', 'token': 'iphone', 'matched_seed': '苹果'},
        {'query_time': '2020-01-01 10:01:00', 'user_id': 'u2', 'query': '苹果 手机', 'token': '三星', 'matched_seed': '苹果'},
        {'query_time': '2020-01-02 11:00:00', 'user_id': 'u1', 'query': '苹果 手机', 'token': '华为', 'matched_seed': '苹果'},
        {'query_time': 'not_a_time', 'user_id': 'u3', 'query': '其他', 'token': '小米', 'matched_seed': None},
    ])
    df.to_csv(path, index=False)


def test_ingest_and_update(tmp_path):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    tokenized = tmp_path / 'tokenized.csv'
    outdir = tmp_path / 'inc'
    dbpath = tmp_path / 'test.db'
    write_tokenized_csv(str(tokenized))

    # run ingest_incremental.py
    res = subprocess.run([sys.executable, os.path.join(repo_root, 'pipeline', 'ingest_incremental.py'), '--tokenized', str(tokenized), '--outdir', str(outdir)], capture_output=True, text=True)
    assert res.returncode == 0, f'ingest failed: {res.stderr}'

    # check files
    kd = outdir / 'keyword_date_counts.csv'
    sc = outdir / 'seed_cooccur.csv'
    assert kd.exists() and sc.exists()

    # run update_db_from_incremental.py
    res2 = subprocess.run([sys.executable, os.path.join(repo_root, 'pipeline', 'update_db_from_incremental.py'), '--db', str(dbpath), '--inc', str(outdir), '--config', os.path.join(repo_root, 'config', 'competition_params.yaml')], capture_output=True, text=True)
    if res2.returncode != 0:
        print('STDOUT:', res2.stdout)
        print('STDERR:', res2.stderr)
    assert res2.returncode == 0, f'update_db failed: {res2.stderr}'

    # check sqlite db contains tables
    import sqlite3
    conn = sqlite3.connect(str(dbpath))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {r[0] for r in cur.fetchall()}
    assert 'keyword_timeseries' in tables
    assert 'competition_result' in tables
    conn.close()
