"""
ingest_incremental.py

读取分词/清洗产物（支持大文件分块读取），输出增量聚合文件：
  - keyword_date_counts.csv -> columns: keyword,date,freq,uniq_users
  - seed_cooccur.csv -> columns: seed,candidate,cooccur

用法示例：
  python ingest_incremental.py --tokenized ./deliverables/P3/reports/v2/tokenized_queries_jieba_search.csv --outdir ./data/incremental

"""
import argparse
import os
import pandas as pd
from dateutil import parser as dateparser


def safe_parse_date(s):
    if pd.isna(s):
        return None
    try:
        # 尝试解析常见时间戳/日期
        dt = dateparser.parse(str(s))
        return dt.date().isoformat()
    except Exception:
        # 可能是 ID/hash，返回 None
        return None


def ingest_tokenized(tokenized_path, outdir, chunksize=200000, seed_cooccur_path=None):
    os.makedirs(outdir, exist_ok=True)
    keyword_date = {}
    seed_cooccur = {}
    keyword_users = {}
    total_rows = 0
    parsed_time_rows = 0
    skipped_time_rows = 0

    cols = None
    for chunk in pd.read_csv(tokenized_path, chunksize=chunksize, encoding='utf-8', low_memory=False):
        if cols is None:
            cols = chunk.columns.tolist()
        # Ensure expected columns
        # expected: query_time,user_id,query,token,matched_seed
        qt = chunk.get('query_time') if 'query_time' in chunk.columns else None
        uid = chunk.get('user_id') if 'user_id' in chunk.columns else None
        token = chunk.get('token') if 'token' in chunk.columns else None
        matched = chunk.get('matched_seed') if 'matched_seed' in chunk.columns else None

        for i in range(len(chunk)):
            total_rows += 1
            t = qt.iloc[i] if qt is not None else None
            date = safe_parse_date(t)
            user = uid.iloc[i] if uid is not None else None
            cand = token.iloc[i] if token is not None else None
            seed = matched.iloc[i] if matched is not None else None
            if pd.isna(cand) or cand is None:
                continue
            if date is not None:
                parsed_time_rows += 1
                key = (cand, date)
                keyword_date[key] = keyword_date.get(key, 0) + 1
                if user is not None and not pd.isna(user):
                    keyword_users.setdefault((cand, date), set()).add(user)
            else:
                skipped_time_rows += 1
            if seed and not pd.isna(seed):
                pair = (seed, cand)
                seed_cooccur[pair] = seed_cooccur.get(pair, 0) + 1

    seed_cooccur_override = seed_cooccur_path or os.path.join(os.path.dirname(tokenized_path), 'seed_cooccur.csv')
    if os.path.exists(seed_cooccur_override):
        try:
            df_override = pd.read_csv(seed_cooccur_override, encoding='utf-8-sig')
            if not df_override.empty and {'seed', 'candidate', 'cooccur'}.issubset(df_override.columns):
                seed_cooccur = {}
                for _, row in df_override.iterrows():
                    seed = row.get('seed')
                    cand = row.get('candidate')
                    if pd.isna(seed) or pd.isna(cand):
                        continue
                    seed = str(seed).strip()
                    cand = str(cand).strip()
                    if not seed or not cand:
                        continue
                    cnt = int(row.get('cooccur', 0) or 0)
                    if cnt <= 0:
                        continue
                    seed_cooccur[(seed, cand)] = seed_cooccur.get((seed, cand), 0) + cnt
        except Exception:
            # 只要当前 tokenized 能正常导入，就不让辅助 cooccur 文件影响主流程
            pass

    # write keyword_date_counts.csv
    kd_path = os.path.join(outdir, 'keyword_date_counts.csv')
    with open(kd_path, 'w', encoding='utf-8') as f:
        f.write('keyword,date,freq,uniq_users\n')
        for (kw, date), freq in keyword_date.items():
            uniq = len(keyword_users.get((kw, date), set()))
            f.write(f'"{kw}",{date},{freq},{uniq}\n')

    sc_path = os.path.join(outdir, 'seed_cooccur.csv')
    with open(sc_path, 'w', encoding='utf-8') as f:
        f.write('seed,candidate,cooccur\n')
        for (seed, cand), cnt in seed_cooccur.items():
            f.write(f'"{seed}","{cand}",{cnt}\n')

    # write ingestion report for data quality transparency
    report_path = os.path.join(outdir, 'ingest_report.json')
    report = {
        'total_rows': int(total_rows),
        'parsed_time_rows': int(parsed_time_rows),
        'skipped_time_rows': int(skipped_time_rows),
        'parsed_time_ratio': float(parsed_time_rows / total_rows) if total_rows else 0.0,
        'seed_cooccur_override': bool(os.path.exists(seed_cooccur_override)),
        'note': '仅可解析时间戳的行会进入 keyword_timeseries；不再使用当前日期兜底。'
    }
    import json
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print('Wrote:', kd_path, sc_path, report_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tokenized', required=True, help='tokenized CSV path')
    parser.add_argument('--outdir', required=True, help='output directory for incrementals')
    parser.add_argument('--seed-cooccur', default=None, help='optional seed_cooccur CSV path; defaults to sibling seed_cooccur.csv next to tokenized input when present')
    args = parser.parse_args()
    ingest_tokenized(args.tokenized, args.outdir, seed_cooccur_path=args.seed_cooccur)


if __name__ == '__main__':
    main()
