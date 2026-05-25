# reports 目录索引

这个目录保存了 P3 所有已完成实验的**原始结果**、**汇总文档**和**图表**。建议优先查看下面这些文件：

## 汇总文档

- `p3_methods_horizontal_compare.md`：横向对比总文档（推荐作为主入口）
- `p3_final_summary.md`：阶段最终摘要
- `p3_multimethod_tokenizer_compare.md`：Tokenizer × Method 组合对比
- `p3_db_compare_benchmark.md`：数据库对比（SQLite vs MySQL）
- `p3_scale_benchmark.md`：100k / 1M token 扩展性测试
- `p3_tokenizer_benchmark.md`：Tokenizer 速度基准

## 关键图表

- `fig_recall_by_tokenizer.png`
- `fig_mrr_by_tokenizer.png`
- `fig_tokenizer_qps.png`
- `fig_scale_build_time.png`
- `fig_method_avg_recall_mrr.png`（如果后续重新生成）
- `fig_db_compare_latency.png`（如果后续重新生成）
- `fig_db_compare_throughput.png`（如果后续重新生成）

## 原始 CSV

- `p3_multimethod_tokenizer_compare.csv`
- `p3_tokenizer_benchmark.csv`
- `p3_scale_benchmark.csv`
- `p3_db_compare_benchmark.csv`
- `p3_multimethod_benchmark_*.csv`

## 临时/大文件

- `tokenized_scaled_100k.csv`
- `tokenized_scaled_1M.csv`
- `compkey_scale_100k.db`
- `compkey_scale_1M.db`

这些文件保留用于复现实验；若只关心最终报告，可以只保留 Markdown、CSV 摘要和图表。
