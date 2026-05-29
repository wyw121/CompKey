# P3 多方案横向评测（真实运行）

## 1. 实验设置

- 数据文件：`D:/material/大三下学期2025-2026-2/数据分析与商务智能/CompKey/deliverables/P1/run_train_v2_full/tokenized_queries_v1.csv`
- seed 数量：20
- 训练样本 token 数：223
- 训练样本 seed-doc 频次数：190
- 验证查询数：53（按 query 稳定哈希约 8:2 切分）
- 评估指标：Recall@5、Recall@10、MRR@10、Coverage@10、平均延时（缓存开/关）

## 2. 方法说明

1. `compkey_current`：当前项目方案（local share + rarity + log 支持度）
2. `cooccur_freq`：共现频次基线
3. `tfidf`：TF-IDF 风格打分（IR 常用）
4. `pmi`：点互信息（关联规则常用）

5. `bm25`：BM25 强检索基线（更强调词频饱和与文档长度归一）

## 3. 结果

| method | eval_queries | recall@5 | recall@10 | mrr@10 | coverage@10 | no_cache_ms | cache_ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| compkey_current | 53 | 0.1321 | 0.1368 | 0.1250 | 1.0000 | 0.1584 | 0.0116 |
| cooccur_freq | 53 | 0.1321 | 0.1368 | 0.1250 | 1.0000 | 0.0840 | 0.0101 |
| tfidf | 53 | 0.1321 | 0.1368 | 0.1250 | 1.0000 | 0.0711 | 0.0075 |
| pmi | 53 | 0.1321 | 0.1368 | 0.1250 | 1.0000 | 0.0980 | 0.0079 |
| bm25 | 53 | 0.1321 | 0.1368 | 0.1250 | 1.0000 | 0.0914 | 0.0093 |

## 4. 结论（基于本次实测）

- Recall@10 最优：`compkey_current`（0.1368）
- MRR@10 最优：`compkey_current`（0.1250）
- 无缓存延时最优：`tfidf`（0.0711 ms）
