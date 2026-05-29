from fastapi.testclient import TestClient
from pathlib import Path
import sqlite3

from api.app import app


client = TestClient(app)


def test_demo_source_switch_endpoints_are_isolated():
    repo_root = Path(__file__).resolve().parents[1]
    sources = client.get('/sources')
    assert sources.status_code == 200
    payload = sources.json()
    assert payload['default_source'] == 'edgar'

    source_map = {item['source']: item for item in payload['items']}
    assert 'edgar' in source_map
    assert 'aol' in source_map
    assert source_map['edgar']['db_exists'] is True
    assert source_map['aol']['db_exists'] is True

    edgar_hot = client.get('/hot_keywords', params={'source': 'edgar', 'limit': 5, 'window_days': 7})
    aol_hot = client.get('/hot_keywords', params={'source': 'aol', 'limit': 5, 'window_days': 7})
    assert edgar_hot.status_code == 200
    assert aol_hot.status_code == 200

    edgar_payload = edgar_hot.json()
    aol_payload = aol_hot.json()
    assert edgar_payload['source'] == 'EDGAR demo'
    assert aol_payload['source'] == 'AOL demo'
    assert edgar_payload['source_key'] == 'edgar'
    assert aol_payload['source_key'] == 'aol'

    edgar_conn = sqlite3.connect(str(repo_root / 'compkey_demo.sqlite3'))
    aol_conn = sqlite3.connect(str(repo_root / 'compkey_aol_demo.sqlite3'))
    try:
        edgar_cur = edgar_conn.cursor()
        aol_cur = aol_conn.cursor()
        edgar_cur.execute('SELECT keyword FROM keyword_timeseries ORDER BY date DESC, freq DESC LIMIT 1')
        aol_cur.execute('SELECT keyword FROM keyword_timeseries ORDER BY date DESC, freq DESC LIMIT 1')
        edgar_keyword = edgar_cur.fetchone()[0]
        aol_keyword = aol_cur.fetchone()[0]
    finally:
        edgar_conn.close()
        aol_conn.close()

    edgar_trend = client.get('/trend', params={'source': 'edgar', 'keyword': edgar_keyword, 'days': 30})
    aol_trend = client.get('/trend', params={'source': 'aol', 'keyword': aol_keyword, 'days': 30})
    assert edgar_trend.status_code == 200
    assert aol_trend.status_code == 200

    edgar_trend_payload = edgar_trend.json()
    aol_trend_payload = aol_trend.json()
    assert edgar_trend_payload['source_label'] == 'EDGAR demo'
    assert aol_trend_payload['source_label'] == 'AOL demo'
    assert edgar_trend_payload['has_time_data'] is True
    assert aol_trend_payload['has_time_data'] is True