"""
从 tokenized CSV（小样本）生成用于前端 demo 的 sample JSON 和将其写入数据库的脚本（便于演示）。

用法示例：
  python scripts/generate_sample_json.py --tokenized deliverables/P3/reports/v2/tokenized_queries_jieba_search.csv --out sample.json --limit 50000

如果找不到文件，会生成一个小的合成示例。
"""
import argparse
import os
import pandas as pd
import json
from collections import defaultdict
from datetime import datetime


def build_sample(tokenized_path, out_path, limit=20000):
    if os.path.exists(tokenized_path):
        df = pd.read_csv(tokenized_path, nrows=limit, encoding='utf-8', low_memory=False)
    else:
        df = None

    # fallback synthetic
    if df is None or df.shape[0] == 0:
        items = [
            {'candidate':'iphone','competition':0.89,'freq':1200,'pmi':1.2},
            {'candidate':'三星','competition':0.73,'freq':800,'pmi':0.9},
            {'candidate':'华为','competition':0.65,'freq':700,'pmi':0.8},
        ]
        json.dump(items, open(out_path,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
        print('Wrote synthetic sample to', out_path)
        return

    # derive simple cooccurrence and freq
    # expected columns: query_time,user_id,query,token,matched_seed
    cand_counts = defaultdict(int)
    seed_pairs = defaultdict(lambda: defaultdict(int))
    for _, row in df.iterrows():
        tok = row.get('token')
        seed = row.get('matched_seed')
        if pd.isna(tok):
            continue
        cand_counts[tok] += 1
        if pd.notna(seed):
            seed_pairs[seed][tok] += 1

    # take largest seed
    if seed_pairs:
        seed = next(iter(seed_pairs))
        pairs = seed_pairs[seed]
        items = []
        for cand, co in sorted(pairs.items(), key=lambda x: -x[1])[:50]:
            items.append({'candidate': cand, 'competition': round(0.2 + 0.8 * co / max(1, max(pairs.values())), 3), 'freq': cand_counts.get(cand,0), 'pmi': 0.0})
    else:
        items = [{'candidate':k,'competition':round(0.5,3),'freq':v,'pmi':0.0} for k,v in sorted(cand_counts.items(), key=lambda x:-x[1])[:50]]

    json.dump(items, open(out_path,'w',encoding='utf-8'), ensure_ascii=False, indent=2)
    print('Wrote sample to', out_path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tokenized', default='./deliverables/P3/reports/v2/tokenized_queries_jieba_search.csv')
    parser.add_argument('--out', default='./frontend/sample_recommendations.json')
    parser.add_argument('--limit', type=int, default=20000)
    args = parser.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    build_sample(args.tokenized, args.out, args.limit)


if __name__ == '__main__':
    main()
