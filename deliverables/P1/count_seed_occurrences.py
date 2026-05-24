import csv
from pathlib import Path

seed_path = Path('deliverables/P1/seed_keywords_v1.csv')
train_path = Path(r'd:\material\大三下学期2025-2026-2\数据分析与商务智能\CompKey\数据分析与商务智能数据\数据\user_tag_query.10W.TRAIN')

seeds = []
with seed_path.open('r', encoding='utf-8-sig', newline='') as f:
    r = csv.DictReader(f)
    for row in r:
        kw = (row.get('keyword') or '').strip()
        if kw:
            seeds.append(kw)

counts = {s:0 for s in seeds}
lines_with_any = 0

with train_path.open('r', encoding='gb18030', errors='replace') as f:
    for i,line in enumerate(f):
        line_lower = line
        matched = False
        for s in seeds:
            if s in line_lower:
                counts[s] += 1
                matched = True
        if matched:
            lines_with_any += 1
        if (i+1) % 20000 == 0:
            print(f"scanned {i+1} lines")

print('lines_with_any:', lines_with_any)
for s in seeds:
    print(s, counts[s])
