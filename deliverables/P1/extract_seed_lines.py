import csv
from pathlib import Path

seed_path = Path('deliverables/P1/seed_keywords_v1.csv')
train_path = Path(r'd:\material\大三下学期2025-2026-2\数据分析与商务智能\CompKey\数据分析与商务智能数据\数据\user_tag_query.10W.TRAIN')
out_path = Path('deliverables/P1/run_train_v2_full_filtered/input_seed_lines.TRAIN')

seeds = []
with seed_path.open('r', encoding='utf-8-sig', newline='') as f:
    r = csv.DictReader(f)
    for row in r:
        kw = (row.get('keyword') or '').strip()
        if kw:
            seeds.append(kw)

out_path.parent.mkdir(parents=True, exist_ok=True)

with train_path.open('r', encoding='gb18030', errors='replace') as fin, out_path.open('w', encoding='gb18030', errors='replace') as fout:
    for i,line in enumerate(fin):
        for s in seeds:
            if s in line:
                fout.write(line)
                break

print('wrote', out_path, 'with filtered seed lines')
