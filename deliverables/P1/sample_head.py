import codecs
p=r'd:\material\大三下学期2025-2026-2\数据分析与商务智能\CompKey\数据分析与商务智能数据\数据\user_tag_query.10W.TRAIN'
with codecs.open(p,'r','gb18030',errors='replace') as f:
    for i,line in enumerate(f):
        print(line.rstrip('\n'))
        if i>=49:
            break
