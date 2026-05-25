# Tokenizer 横向基准（P3 扩展）

- 输入文件：`D:/material/大三下学期2025-2026-2/数据分析与商务智能/CompKey/deliverables/P1/run_train_v2_full/seed_related_queries_v1.csv`
- 抽样条数：265

| 方法 | queries/sec | tokens/sec | avg tokens/query | unique_tokens | single_char_ratio |
|---|---:|---:|---:|---:|---:|
| jieba_precise | 10849.63 | 49416.99 | 4.55 | 446 | 0.2552 |
| jieba_search | 9251.47 | 53204.67 | 5.75 | 491 | 0.2021 |
| regex | 1158216.80 | 1459790.24 | 1.26 | 249 | 0.0000 |
| thulac | 1809.59 | 9621.54 | 5.32 | 497 | 0.4564 |
