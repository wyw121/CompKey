# P3 v2 横向评估入口

本目录保存 v2 版本的横向评估产物。v2 的特点是：

- 种子关键词升级为 `deliverables/P1/seed_keywords_v2.csv`
- 支持通过环境变量切换 seed / 报告目录 / 数据目录
- 横向方法仍沿用业界常见基线：`compkey_current`、`cooccur_freq`、`tfidf`、`pmi`、`bm25`

## 已完成

### 1. 多方法对比（已跑）

- 输入：`deliverables/P1/run_train_v2_full/tokenized_queries_v1.csv`
- seed：20 个
- 输出：`p3_multimethod_benchmark.csv` / `p3_multimethod_benchmark.md`

### 2. 当前结论

- Recall@10 最优：`tfidf`
- MRR@10 最优：`cooccur_freq`
- 无缓存延时最优：`compkey_current`

## 运行方式

当前 v2 实验通过环境变量控制：

- `COMPKEY_SEED_CSV`：指定 seed 文件
- `COMPKEY_REPORT_DIR`：指定报告输出目录
- `COMPKEY_P1_OUTPUT_DIR`：指定 P1 token 化输出目录
- `COMPKEY_DB_PATH`：指定数据库文件

## 后续可继续补的内容

- Tokenizer 横向评估（`jieba_precise` / `jieba_search` / `regex` / `thulac`）
- SQLite vs MySQL 数据库横向评估
- 规模扩展测试（10k / 100k / 300k / 500k / 1M token）
