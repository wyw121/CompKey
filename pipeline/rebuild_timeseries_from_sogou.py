"""
从 Sogou 原始日志重建真实时间轴（按日志文件日期），并回填数据库：
- keyword_timeseries
- keyword_stats
- competition_result 的 freq/pmi/competition

用法：
python pipeline/rebuild_timeseries_from_sogou.py \
  --db ./compkey_p4.sqlite3 \
  --sogou_dir "./数据分析与商务智能数据/搜索日志/SogouQ/SogouQ" \
  --report ./data/incremental_real/sogou_rebuild_report.json
"""

import argparse
import glob
import json
import math
import os
import re
import sqlite3
from collections import defaultdict
from datetime import datetime

try:
    import ahocorasick  # type: ignore
except Exception:
    ahocorasick = None


DATE_RE = re.compile(r"access_log\.(\d{8})\.decode\.filter$")


def infer_date_from_filename(path: str):
    m = DATE_RE.search(os.path.basename(path))
    if not m:
        return None
    d = m.group(1)
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def normalize_query(q: str):
    q = (q or "").strip()
    if q.startswith("[") and q.endswith("]") and len(q) >= 2:
        q = q[1:-1]
    return q.strip()


def get_keyword_set(conn: sqlite3.Connection):
    cur = conn.cursor()
    kw = set()

    def valid_keyword(x: str):
        if not x:
            return False
        s = x.strip()
        if len(s) < 2:
            return False
        # 过滤纯符号/空白
        if not any(ch.isalnum() or ('\u4e00' <= ch <= '\u9fff') for ch in s):
            return False
        return True

    cur.execute("SELECT DISTINCT candidate FROM competition_result")
    kw.update([r[0] for r in cur.fetchall() if r and valid_keyword(r[0])])
    cur.execute("SELECT DISTINCT seed FROM competition_result")
    kw.update([r[0] for r in cur.fetchall() if r and valid_keyword(r[0])])
    return kw


def parse_line(line: str):
    """
    支持两种格式：
    - 4列: user_id, [query], "rank click", url
    - 5列: time, user_id, [query], "rank click", url
    """
    parts = line.rstrip("\n").split("\t")
    if len(parts) >= 5:
        user_id = parts[1]
        query = parts[2]
    elif len(parts) >= 4:
        user_id = parts[0]
        query = parts[1]
    else:
        return None, None
    return user_id, normalize_query(query)


def build_matcher(keyword_set):
    if ahocorasick is None:
        return None
    automaton = ahocorasick.Automaton()
    for kw in keyword_set:
        if kw and kw.strip():
            automaton.add_word(kw, kw)
    automaton.make_automaton()
    return automaton


def match_keywords(query: str, keyword_set, matcher):
    if not query:
        return set()
    hits = set()
    if matcher is not None:
        for _, kw in matcher.iter(query):
            hits.add(kw)
        return hits
    # fallback: 小数据时使用 contains（慢）
    for kw in keyword_set:
        if kw in query:
            hits.add(kw)
    return hits


def rebuild_timeseries(conn: sqlite3.Connection, sogou_dir: str, report_path: str, max_files: int = 0):
    keyword_set = get_keyword_set(conn)
    if not keyword_set:
        raise RuntimeError("competition_result 为空，无法建立关键词集合。请先运行 seed/cooccur 入库流程。")

    files = sorted(glob.glob(os.path.join(sogou_dir, "access_log.*.decode.filter")))
    if max_files and max_files > 0:
        files = files[:max_files]
    if not files:
        raise RuntimeError(f"未找到日志文件: {sogou_dir}/access_log.*.decode.filter")

    matcher = build_matcher(keyword_set)

    # 统计
    total_lines = 0
    parsed_lines = 0
    matched_token_hits = 0
    file_count = 0

    keyword_date_freq = defaultdict(int)

    for fp in files:
        date = infer_date_from_filename(fp)
        if not date:
            continue
        file_count += 1
        print(f"[rebuild] processing file {file_count}/{len(files)}: {os.path.basename(fp)} -> {date}")
        with open(fp, "r", encoding="gb18030", errors="ignore") as f:
            for line in f:
                total_lines += 1
                user_id, query = parse_line(line)
                if not query:
                    continue
                if '[' not in line and ']' not in line and len(query) <= 1:
                    continue
                parsed_lines += 1
                hits = match_keywords(query, keyword_set, matcher)
                for kw in hits:
                    keyword_date_freq[(kw, date)] += 1
                    matched_token_hits += 1

    cur = conn.cursor()

    # 清空并重建真实时间轴
    cur.execute("DELETE FROM keyword_timeseries")
    cur.execute("DELETE FROM keyword_stats")

    # 批量写入 keyword_timeseries
    rows = [(k, d, int(v), 0) for (k, d), v in keyword_date_freq.items()]
    cur.executemany(
        "INSERT INTO keyword_timeseries(keyword,date,freq,uniq_users) VALUES (?,?,?,?)",
        rows,
    )

    # 聚合到 keyword_stats
    cur.execute(
        """
        INSERT INTO keyword_stats(keyword,freq,uniq_users,last_updated,avg_weekly_growth)
        SELECT keyword, SUM(freq) AS freq, 0, CURRENT_TIMESTAMP, 0
        FROM keyword_timeseries
        GROUP BY keyword
        """
    )
    conn.commit()

    # 用 keyword_stats 更新 competition_result 的 freq
    cur.execute(
        """
        UPDATE competition_result
        SET freq = COALESCE((SELECT ks.freq FROM keyword_stats ks WHERE ks.keyword = competition_result.candidate), 0)
        """
    )
    conn.commit()

    # 重算 competition（按 seed 分组）
    cur.execute("SELECT DISTINCT seed FROM competition_result")
    seeds = [r[0] for r in cur.fetchall()]

    alpha, beta, gamma = 0.5, 0.3, 0.2

    for seed in seeds:
        cur.execute("SELECT candidate, cooccur, freq FROM competition_result WHERE seed=?", (seed,))
        data = cur.fetchall()
        if not data:
            continue

        cands = [r[0] for r in data]
        cooccurs = [int(r[1] or 0) for r in data]
        freqs = [int(r[2] or 0) for r in data]

        total = max(1, sum(freqs))
        pmi_vals = []
        for co, f in zip(cooccurs, freqs):
            p = (co + 1) / (total + 1)
            ps = (sum(cooccurs) + 1) / (total + 1)
            pw = (f + 1) / (total + 1)
            pmi_vals.append(math.log((p / (ps * pw + 1e-9)) + 1e-9))

        norm_co = [math.log(1 + x) for x in cooccurs]
        norm_fr = [math.log(1 + x) for x in freqs]
        norm_pm = [math.log(1 + max(0, x)) for x in pmi_vals]

        max_co = max(norm_co) if norm_co else 1
        max_fr = max(norm_fr) if norm_fr else 1
        max_pm = max(norm_pm) if norm_pm else 1

        for cand, co, fr, pmi, nco, nfr, npm in zip(cands, cooccurs, freqs, pmi_vals, norm_co, norm_fr, norm_pm):
            val_co = nco / max_co if max_co > 0 else 0
            val_fr = nfr / max_fr if max_fr > 0 else 0
            val_pm = npm / max_pm if max_pm > 0 else 0
            competition = alpha * val_co + beta * val_fr + gamma * val_pm
            cur.execute(
                "UPDATE competition_result SET pmi=?, competition=? WHERE seed=? AND candidate=?",
                (float(pmi), float(competition), seed, cand),
            )

    conn.commit()

    report = {
        "log_files_used": file_count,
        "total_lines": total_lines,
        "parsed_lines": parsed_lines,
        "keyword_hits": matched_token_hits,
        "timeseries_rows": len(rows),
        "distinct_keywords": len({k for k, _ in keyword_date_freq.keys()}),
        "date_range": {
            "min": min([d for _, d in keyword_date_freq.keys()], default=None),
            "max": max([d for _, d in keyword_date_freq.keys()], default=None),
        },
        "created_at": datetime.utcnow().isoformat() + "Z",
    }

    os.makedirs(os.path.dirname(report_path), exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps(report, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="./compkey_p4.sqlite3")
    parser.add_argument("--sogou_dir", default="./数据分析与商务智能数据/搜索日志/SogouQ/SogouQ")
    parser.add_argument("--report", default="./data/incremental_real/sogou_rebuild_report.json")
    parser.add_argument("--max_files", type=int, default=0, help="仅处理前N个日志文件，0表示全量")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    try:
        rebuild_timeseries(conn, args.sogou_dir, args.report, args.max_files)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
