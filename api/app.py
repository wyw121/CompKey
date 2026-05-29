from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import yaml
import os
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import re


STOPWORDS = {
    '什么', '怎么', '为何', '为啥', '如何', '好吗', '好么',
    '的', '了', '在', '是', '和', '与', '及', '就', '都', '而', '且', '并',
    '我', '你', '他', '她', '它', '我们', '你们', '他们', '她们',
    '一个', '一下', '这个', '那个', '哪些', '多少', '哪里', '怎样',
    '吗', '呢', '吧', '啊', '呀', '哦', '好',
}


def is_noise_token(token: str) -> bool:
    if token is None:
        return True
    s = str(token).strip()
    if not s:
        return True
    if len(s) < 2:
        return True
    if s in STOPWORDS:
        return True
    if s.isdigit():
        return True
    if not any(ch.isalnum() or ('\u4e00' <= ch <= '\u9fff') for ch in s):
        return True
    return False


def normalize_token(token: str) -> str:
    s = str(token or '').strip()
    s = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff]+', '', s)
    return s

CONFIG_PATH_DEFAULT = os.path.join(os.path.dirname(__file__), '..', 'config', 'competition_params.yaml')
APP_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))

DEFAULT_DEMO_SOURCES = {
    'edgar': {
        'label': 'EDGAR demo',
        'description': '近年公开检索/访问日志',
        'db_path': './compkey_demo.sqlite3',
    },
    'aol': {
        'label': 'AOL demo',
        'description': '经典 query log（用户会话集合）',
        'db_path': './compkey_aol_demo.sqlite3',
    },
}


app = FastAPI(title='CompKey API')

# 允许前端本地调试跨域访问（静态服务器通常跑在 8001）
default_origins = [
    'http://127.0.0.1:8001',
    'http://localhost:8001',
    'http://127.0.0.1:5500',
    'http://localhost:5500',
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=default_origins,
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
    expose_headers=['X-CompKey-Data-Source', 'X-CompKey-Data-Range', 'X-CompKey-Window-Days'],
)


def load_config():
    cfg_path = os.environ.get('COMPKY_CONFIG') or CONFIG_PATH_DEFAULT
    if os.path.exists(cfg_path):
        return yaml.safe_load(open(cfg_path, 'r', encoding='utf-8-sig'))
    return {}


def get_param(name: str, default):
    cfg = load_config()
    return cfg.get(name, default)


def project_path(path: str) -> str:
    if not path:
        return path
    if os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(APP_ROOT, path))


def get_demo_source_configs() -> Dict[str, Dict[str, str]]:
    cfg = load_config()
    demo_sources = cfg.get('demo_sources')
    resolved = dict(DEFAULT_DEMO_SOURCES)
    if isinstance(demo_sources, dict):
        for key, value in demo_sources.items():
            if not isinstance(value, dict):
                continue
            merged = dict(resolved.get(key, {}))
            merged.update({k: v for k, v in value.items() if v is not None})
            resolved[key] = merged
    return resolved


def normalize_demo_source(source: Optional[str]) -> str:
    cfg = load_config()
    default_source = str(cfg.get('default_demo_source', 'edgar')).strip().lower() or 'edgar'
    key = str(source or default_source).strip().lower()
    configs = get_demo_source_configs()
    if key not in configs:
        return default_source if default_source in configs else 'edgar'
    return key


def get_demo_source_profile(source: Optional[str]) -> Dict[str, str]:
    key = normalize_demo_source(source)
    configs = get_demo_source_configs()
    profile = dict(configs.get(key, DEFAULT_DEMO_SOURCES['edgar']))
    profile['source'] = key
    profile['label'] = profile.get('label') or key
    profile['description'] = profile.get('description') or ''
    profile['db_path'] = project_path(profile.get('db_path', './compkey_p4.sqlite3'))
    return profile


def get_db_conn(source: Optional[str] = None):
    profile = get_demo_source_profile(source)
    conn = sqlite3.connect(profile['db_path'])
    conn.row_factory = sqlite3.Row
    return conn


class RecommendItem(BaseModel):
    candidate: str
    competition: float
    freq: int
    pmi: float


class HotKeywordItem(BaseModel):
    keyword: str
    recent_freq: int
    prev_freq: int
    growth_pct: float
    last_date: str


class SeedSuggestionItem(BaseModel):
    seed: str
    candidate_count: int
    best_competition: float


class DemoSourceItem(BaseModel):
    source: str
    label: str
    description: str
    db_exists: bool


class DemoSourceList(BaseModel):
    default_source: str
    items: List[DemoSourceItem]


@app.get('/sources', response_model=DemoSourceList)
def demo_sources():
    cfg = load_config()
    default_source = normalize_demo_source(cfg.get('default_demo_source', 'edgar'))
    items = []
    for key, profile in get_demo_source_configs().items():
        db_path = project_path(profile.get('db_path', ''))
        items.append(
            DemoSourceItem(
                source=key,
                label=profile.get('label', key),
                description=profile.get('description', ''),
                db_exists=os.path.exists(db_path),
            )
        )
    return DemoSourceList(default_source=default_source, items=items)


@app.get('/recommend', response_model=List[RecommendItem])
def recommend(seed: str, top: int = 20, source: str = 'edgar'):
    if not seed:
        raise HTTPException(status_code=400, detail='seed required')
    min_freq = int(get_param('min_freq', 5))
    conn = get_db_conn(source)
    cur = conn.cursor()
    cur.execute('SELECT candidate,competition,freq,pmi FROM competition_result WHERE seed=? ORDER BY competition DESC LIMIT ?', (seed, top))
    rows = cur.fetchall()
    if not rows:
        # try fallback: compute on-the-fly by looking for candidates that cooccurred
        cur.execute('SELECT candidate,cooccur FROM competition_result WHERE seed=? ORDER BY cooccur DESC LIMIT ?', (seed, top))
        rows = cur.fetchall()
    res = []
    for r in rows:
        cand = normalize_token(r['candidate'])
        freq = int(r['freq']) if 'freq' in r.keys() and r['freq'] is not None else 0
        if is_noise_token(cand):
            continue
        if freq < min_freq:
            continue
        res.append(RecommendItem(candidate=cand, competition=float(r['competition']) if 'competition' in r.keys() else 0.0,
                                 freq=freq, pmi=float(r['pmi']) if 'pmi' in r.keys() else 0.0))
        if len(res) >= top:
            break
    conn.close()
    return res


@app.get('/trend')
def trend(keyword: str, days: int = 90, source: str = 'edgar'):
    if not keyword:
        raise HTTPException(status_code=400, detail='keyword required')
    profile = get_demo_source_profile(source)
    conn = get_db_conn(profile['source'])
    cur = conn.cursor()
    cur.execute('SELECT date,freq FROM keyword_timeseries WHERE keyword=? ORDER BY date DESC LIMIT ?', (keyword, days))
    rows = cur.fetchall()
    cur.execute('SELECT MAX(date) AS max_date FROM keyword_timeseries WHERE keyword=?', (keyword,))
    max_row = cur.fetchone()
    conn.close()
    existing = {r['date']: int(r['freq']) for r in rows}

    # 补齐最近 N 天缺失日期，避免图上只剩 1~2 个点时看起来“断掉”
    if max_row and max_row['max_date']:
        end_date = datetime.strptime(max_row['max_date'], '%Y-%m-%d').date()
    else:
        end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=max(1, days) - 1)
    series = []
    d = start_date
    while d <= end_date:
        ds = d.isoformat()
        series.append({'date': ds, 'freq': int(existing.get(ds, 0))})
        d += timedelta(days=1)
    # 若完全没有可用时间戳数据，明确告知前端，不返回伪时间轴
    has_time_data = bool(rows)
    note = '' if has_time_data else '该关键词暂无可解析时间戳数据，无法绘制真实时间轴。'
    return {
        'keyword': keyword,
        'series': series if has_time_data else [],
        'has_time_data': has_time_data,
        'note': note,
        'source': profile['source'],
        'source_label': profile['label'],
    }


@app.get('/hot_keywords')
def hot_keywords(limit: int = 20, window_days: int = 7, source: str = 'edgar'):
    """
    返回“时下流行”关键词榜单：按最近 window_days 相比前一窗口的增长率排序。
    """
    if limit <= 0:
        raise HTTPException(status_code=400, detail='limit must be positive')
    if window_days <= 0:
        raise HTTPException(status_code=400, detail='window_days must be positive')

    min_freq = int(get_param('min_freq', 5))
    growth_smoothing = int(get_param('growth_smoothing', max(min_freq, 5)))

    profile = get_demo_source_profile(source)
    conn = get_db_conn(profile['source'])
    cur = conn.cursor()

    cur.execute('SELECT MAX(date) AS max_date FROM keyword_timeseries')
    max_row = cur.fetchone()
    if max_row and max_row['max_date']:
        end_date = datetime.strptime(max_row['max_date'], '%Y-%m-%d').date()
    else:
        end_date = datetime.utcnow().date()
    recent_start = end_date - timedelta(days=window_days - 1)
    prev_end = recent_start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=window_days - 1)

    cur.execute(
        '''
        SELECT
            keyword,
            SUM(CASE WHEN date BETWEEN ? AND ? THEN freq ELSE 0 END) AS recent_freq,
            SUM(CASE WHEN date BETWEEN ? AND ? THEN freq ELSE 0 END) AS prev_freq,
            MAX(date) AS last_date
        FROM keyword_timeseries
        GROUP BY keyword
        HAVING recent_freq >= ?
        ''',
        (recent_start.isoformat(), end_date.isoformat(), prev_start.isoformat(), prev_end.isoformat(), min_freq)
    )
    rows = cur.fetchall()
    conn.close()

    items = []
    for r in rows:
        kw = normalize_token(r['keyword'])
        if is_noise_token(kw):
            continue
        recent = int(r['recent_freq'] or 0)
        prev = int(r['prev_freq'] or 0)
        growth = ((recent + growth_smoothing) / (prev + growth_smoothing) - 1.0) * 100.0
        items.append(
            HotKeywordItem(
                keyword=kw,
                recent_freq=recent,
                prev_freq=prev,
                growth_pct=float(growth),
                last_date=r['last_date'] or ''
            )
        )

    items.sort(key=lambda x: (x.recent_freq, x.growth_pct), reverse=True)

    return {
        'items': items[:limit],
        'source': profile['label'],
        'source_key': profile['source'],
        'date_range': {
            'start': recent_start.isoformat(),
            'end': end_date.isoformat(),
        },
        'window_days': window_days,
    }


@app.get('/seed_suggestions', response_model=List[SeedSuggestionItem])
def seed_suggestions(limit: int = 12, source: str = 'edgar'):
    if limit <= 0:
        raise HTTPException(status_code=400, detail='limit must be positive')
    conn = get_db_conn(source)
    cur = conn.cursor()
    cur.execute(
        '''
        SELECT
            seed,
            COUNT(*) AS candidate_count,
            MAX(competition) AS best_competition
        FROM competition_result
        WHERE freq >= ?
        GROUP BY seed
        HAVING candidate_count > 0
        ORDER BY candidate_count DESC, best_competition DESC, seed ASC
        LIMIT ?
        ''',
        (int(get_param('min_freq', 5)), limit)
    )
    rows = cur.fetchall()
    conn.close()
    return [
        SeedSuggestionItem(
            seed=r['seed'],
            candidate_count=int(r['candidate_count'] or 0),
            best_competition=float(r['best_competition'] or 0.0),
        )
        for r in rows
    ]


@app.get('/health')
def health():
    return {'status': 'ok'}
