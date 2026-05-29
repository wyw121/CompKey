"""
update_db_from_incremental.py

将 ingest_incremental 的输出写入 SQLite（可配置为其它 DB），并为受影响的 seeds 重算 competition 值（局部重算）。

用法示例：
  python update_db_from_incremental.py --db ./compkey_p4.sqlite3 --inc ./data/incremental

"""
import argparse
import os
import sqlite3
import pandas as pd
import yaml
import math
import re


STOPWORDS = {
    '什么', '怎么', '为何', '为啥', '好吗', '好么', '好吗', '如何',
    '的', '了', '在', '是', '和', '与', '及', '就', '都', '而', '且', '并',
    '我', '你', '他', '她', '它', '我们', '你们', '他们', '她们',
    '一个', '一下', '这个', '那个', '哪些', '多少', '哪里', '怎样',
    '吗', '呢', '吧', '啊', '呀', '哦', '哦哦', '好',
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
    # 只保留中英文与数字，彻底移除空白/标点/隐形字符
    s = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff]+', '', s)
    return s


SCHEMA_SQL = '''
CREATE TABLE IF NOT EXISTS keyword_timeseries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  keyword TEXT NOT NULL,
  date TEXT NOT NULL,
  freq INTEGER NOT NULL DEFAULT 0,
  uniq_users INTEGER DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(keyword, date)
);
CREATE INDEX IF NOT EXISTS idx_timeseries_keyword_date ON keyword_timeseries(keyword, date DESC);

CREATE TABLE IF NOT EXISTS keyword_stats (
  keyword TEXT PRIMARY KEY,
  freq INTEGER NOT NULL DEFAULT 0,
  uniq_users INTEGER DEFAULT 0,
  last_updated TEXT,
  avg_weekly_growth REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS competition_result (
  seed TEXT NOT NULL,
  candidate TEXT NOT NULL,
  cooccur INTEGER DEFAULT 0,
  freq INTEGER DEFAULT 0,
  pmi REAL DEFAULT 0,
  competition REAL DEFAULT 0,
  PRIMARY KEY(seed, candidate)
);
'''


def upsert_timeseries(conn, df_ts):
    cur = conn.cursor()
    for _, row in df_ts.iterrows():
        cur.execute('''INSERT INTO keyword_timeseries(keyword,date,freq,uniq_users) VALUES (?,?,?,?)
                       ON CONFLICT(keyword,date) DO UPDATE SET freq=keyword_timeseries.freq+excluded.freq, uniq_users=excluded.uniq_users''',
                    (row['keyword'], row['date'], int(row['freq']), int(row.get('uniq_users', 0))))
    conn.commit()


def upsert_stats(conn, df_ts):
    cur = conn.cursor()
    # aggregate total freq per keyword
    agg = df_ts.groupby('keyword')['freq'].sum().reset_index()
    for _, row in agg.iterrows():
        kw = row['keyword']
        freq = int(row['freq'])
        # insert or update
        cur.execute('SELECT freq FROM keyword_stats WHERE keyword=?', (kw,))
        r = cur.fetchone()
        if r:
            newf = r[0] + freq
            cur.execute('UPDATE keyword_stats SET freq=?, last_updated=CURRENT_TIMESTAMP WHERE keyword=?', (newf, kw))
        else:
            cur.execute('INSERT INTO keyword_stats(keyword,freq,last_updated) VALUES (?,?,CURRENT_TIMESTAMP)', (kw, freq))
    conn.commit()


def update_cooccur_and_recompute(conn, df_co, params):
    cur = conn.cursor()
    # write cooccur increments
    affected_seeds = set()
    for _, row in df_co.iterrows():
        seed = normalize_token(row['seed'])
        cand = normalize_token(row['candidate'])
        if is_noise_token(cand):
            continue
        inc = int(row['cooccur'])
        affected_seeds.add(seed)
        cur.execute('SELECT cooccur FROM competition_result WHERE seed=? AND candidate=?', (seed, cand))
        r = cur.fetchone()
        if r:
            newc = r[0] + inc
            cur.execute('UPDATE competition_result SET cooccur=? WHERE seed=? AND candidate=?', (newc, seed, cand))
        else:
            # insert with freq 0 for now; will fill freq/pmi/competition later
            cur.execute('INSERT INTO competition_result(seed,candidate,cooccur) VALUES (?,?,?)', (seed, cand, inc))
    conn.commit()

    # recompute competition for affected seeds
    alpha = params.get('alpha', 0.5)
    beta = params.get('beta', 0.3)
    gamma = params.get('gamma', 0.2)

    for seed in affected_seeds:
        # get all candidates for seed
        cur.execute('SELECT candidate,cooccur FROM competition_result WHERE seed=?', (seed,))
        rows = cur.fetchall()
        if not rows:
            continue
        # build arrays
        candidates = [r[0] for r in rows]
        cooccurs = [r[1] for r in rows]
        # get freq for candidates from keyword_stats
        freqs = []
        for c in candidates:
            cur.execute('SELECT freq FROM keyword_stats WHERE keyword=?', (c,))
            r = cur.fetchone()
            freqs.append(r[0] if r else 0)

        # compute pmi approx: log( (cooccur/total) / (P(s)P(w)) ) -- using safeties
        total_queries = max(1, sum(freqs))
        pmi_vals = []
        for co, f in zip(cooccurs, freqs):
            try:
                p = (co + 1) / (total_queries + 1)
                ps = sum(cooccurs) / (total_queries + 1)
                pw = (f + 1) / (total_queries + 1)
                pmi = math.log(p / (ps * pw + 1e-9) + 1e-9)
            except Exception:
                pmi = 0.0
            pmi_vals.append(pmi)

        # normalize: log(1+x) then divide by max
        norm_co = [math.log(1 + x) for x in cooccurs]
        norm_freq = [math.log(1 + x) for x in freqs]
        norm_pmi = [math.log(1 + max(0, x)) for x in pmi_vals]
        max_co = max(norm_co) if norm_co else 1
        max_fr = max(norm_freq) if norm_freq else 1
        max_pmi = max(norm_pmi) if norm_pmi else 1

        for c, co, fr, pmi, nc, nf, npmi in zip(candidates, cooccurs, freqs, pmi_vals, norm_co, norm_freq, norm_pmi):
            val_co = nc / max_co if max_co > 0 else 0
            val_fr = nf / max_fr if max_fr > 0 else 0
            val_pmi = npmi / max_pmi if max_pmi > 0 else 0
            competition = alpha * val_co + beta * val_fr + gamma * val_pmi
            # update row
            cur.execute('UPDATE competition_result SET freq=?, pmi=?, competition=? WHERE seed=? AND candidate=?',
                        (fr, pmi, competition, seed, c))
    conn.commit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', default='./compkey_p4.sqlite3', help='sqlite db path')
    parser.add_argument('--inc', required=True, help='incremental dir produced by ingest')
    parser.add_argument('--config', default='./config/competition_params.yaml', help='params yaml')
    args = parser.parse_args()

    params = yaml.safe_load(open(args.config, 'r')) if os.path.exists(args.config) else {}

    # ensure files exist
    kd = os.path.join(args.inc, 'keyword_date_counts.csv')
    sc = os.path.join(args.inc, 'seed_cooccur.csv')
    if not os.path.exists(kd) or not os.path.exists(sc):
        print('Missing incrementals in', args.inc)
        return

    def read_csv_with_fallback(path):
        for enc in ('utf-8', 'utf-8-sig', 'gb18030', 'latin1'):
            try:
                return pd.read_csv(path, encoding=enc)
            except Exception:
                continue
        # last resort
        return pd.read_csv(path, encoding='utf-8', engine='python', errors='replace')

    df_ts = read_csv_with_fallback(kd)
    df_co = read_csv_with_fallback(sc)

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()
    cur.executescript(SCHEMA_SQL)
    conn.commit()

    upsert_timeseries(conn, df_ts)
    upsert_stats(conn, df_ts)
    update_cooccur_and_recompute(conn, df_co, params)

    print('Database updated at', args.db)


if __name__ == '__main__':
    main()
