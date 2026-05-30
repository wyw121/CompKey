import subprocess
import sys
import os
import time
import sqlite3
from fastapi.testclient import TestClient


def ensure_db_and_run_update(repo_root, tmp_inc, dbpath):
    # run update_db_from_incremental.py to create db
    res = subprocess.run([sys.executable, os.path.join(repo_root, 'pipeline', 'update_db_from_incremental.py'), '--db', str(dbpath), '--inc', str(tmp_inc), '--config', os.path.join(repo_root, 'config', 'competition_params.yaml')], capture_output=True, text=True)
    assert res.returncode == 0, f'update_db failed: {res.stderr}'


def test_api_recommend_and_trend(tmp_path):
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    # prepare minimal incremental files
    inc = tmp_path / 'inc'
    inc.mkdir()
    kd = inc / 'keyword_date_counts.csv'
    sc = inc / 'seed_cooccur.csv'
    kd.write_text('keyword,date,freq,uniq_users\niphone,2020-01-01,10,2\n')
    sc.write_text('seed,candidate,cooccur\n苹果,iphone,5\n')
    dbpath = tmp_path / 'test_api.db'
    ensure_db_and_run_update(repo_root, inc, dbpath)

    # point API config to this db by copying config file temporarily
    import shutil
    cfg_src = os.path.join(repo_root, 'config', 'competition_params.yaml')
    cfg_dst = tmp_path / 'competition_params.yaml'
    shutil.copy(cfg_src, cfg_dst)
    # modify dst to point to our db
    txt = cfg_dst.read_text(encoding='utf-8-sig')
    txt = txt.replace('db_path: "./compkey_p4.sqlite3"', f'db_path: "{str(dbpath).replace("\\","/" )}"')
    cfg_dst.write_text(txt, encoding='utf-8-sig')
    # point the API to this temporary config
    os.environ['COMPKY_CONFIG'] = str(cfg_dst)

    # load app with overridden CONFIG_PATH via environment variable hack - simpler: patch file location used by api.app
    # We'll set CWD to repo root so api.app loads ../config/competition_params.yaml by default
    cwd = os.getcwd()
    os.chdir(repo_root)
    from api import app
    client = TestClient(app)

    r = client.get('/recommend', params={'seed': '苹果', 'top': 10})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)

    r2 = client.get('/trend', params={'keyword': 'iphone', 'days': 30})
    assert r2.status_code == 200
    td = r2.json()
    assert td['keyword'] == 'iphone'

    os.chdir(cwd)
