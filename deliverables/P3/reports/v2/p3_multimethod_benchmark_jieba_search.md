# P3 多方案横向评测（真实运行）

## 1. 实验设置

- 数据文件：`D:/material/大三下学期2025-2026-2/数据分析与商务智能/CompKey/deliverables/P1/run_train_v2_full/tokenized_queries_v1.csv`
- seed 数量：20
- 训练样本 token 数：717
- 训练样本 seed-doc 频次数：405
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
| compkey_current | 53 | 0.3529 | 0.3850 | 0.6522 | 1.0000 | 0.0925 | 0.0091 |
| cooccur_freq | 53 | 0.3706 | 0.3991 | 0.6571 | 1.0000 | 0.0671 | 0.0069 |
| tfidf | 53 | 0.3529 | 0.3960 | 0.6508 | 1.0000 | 0.1023 | 0.0086 |
| pmi | 53 | 0.2592 | 0.3034 | 0.6353 | 1.0000 | 0.0893 | 0.0092 |
| bm25 | 53 | 0.3130 | 0.3420 | 0.6353 | 1.0000 | 0.1294 | 0.0127 |

## 4. 结论（基于本次实测）

- Recall@10 最优：`cooccur_freq`（0.3991）
- MRR@10 最优：`cooccur_freq`（0.6571）
- 无缓存延时最优：`cooccur_freq`（0.0671 ms）
