# P3 目录说明

这个目录里现在主要分成四类内容：**核心代码**、**实验脚本**、**报告结果**、**临时/大文件产物**。为了避免文件越来越散，建议按下面的方式理解和浏览。

## 推荐的目录结构

```text
P3/
├── compkey_p3/                 # P3 核心实现：离线构建、仓储、服务、配置
├── reports/                    # 所有 benchmark 输出、Markdown 汇总、图表
├── run_stage3_*.py             # 各类实验脚本（多方法、数据库、tokenizer、scale）
├── generate_*.py               # 报告图表生成脚本
├── architecture_design_v1.md   # 架构设计
├── module_design_v1.md         # 模块设计
├── SRS_v1.md                   # 需求说明
└── db_schema_v1.sql / db_dictionary_v1.csv
```

## 当前最重要的入口

- `reports/p3_methods_horizontal_compare.md`：P3 横向对比总汇总（方法、数据库、分词、扩展性、图表入口）
- `reports/p3_final_summary.md`：阶段性最终摘要
- `reports/p3_multimethod_tokenizer_compare.md`：Tokenizer × Method 详细对比
- `reports/p3_db_compare_benchmark.md`：SQLite vs MySQL 真实数据库对比
- `reports/p3_scale_benchmark.md`：100k / 1M token 扩展性测试

## 脚本分工

- `run_stage3_multimethod_benchmark.py`：多候选方法对比（compkey_current / cooccur_freq / tfidf / pmi / BM25）
- `run_stage3_db_compare_benchmark.py`：数据库对比（SQLite / MySQL）
- `run_stage3_tokenizer_scale_benchmark.py`：Tokenizer 基准 + 规模扩展测试
- `run_tokenizer_full_evals.py`：不同 tokenizer 下的完整方法评测
- `generate_tokenizer_plots.py`：Tokenizer 与 scale 图表
- `generate_tokenizer_compare_report.py`：Tokenizer × Method 汇总表
- `generate_horizontal_compare_plots.py`：横向对比总览图表

## 备注

- `reports/` 里既包含最终要交付的汇总文档，也包含 benchmark 过程中生成的 CSV / PNG。若后面还要继续做实验，建议优先把新增产物写进 `reports/`，避免散落在根目录。
- 目前的大文件（如 `tokenized_scaled_1M.csv`）是为了扩展性测试保留的，如后续不再需要，可以单独清理以减少仓库体积。
