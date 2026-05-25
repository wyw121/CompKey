# P3 数据库横向对比（真实运行）

## 1. 实验设置

- 源数据库：`D:/material/大三下学期2025-2026-2/数据分析与商务智能/CompKey/deliverables/P3/compkey_stage3.sqlite3`
- 备份快照：SQLite 临时库 + MySQL 临时库
- 样本 seed 数量：11
- search_log 基础样本数：210
- 负载类型：导入、单条查询、批量写入、读写混合并发

## 2. 汇总结果

| backend | init_ms | import_ms | read_avg_ms | read_p95_ms | read_qps | write_avg_batch_ms | write_p95_batch_ms | write_rows_per_sec | mixed_read_avg_ms | mixed_write_avg_ms | mixed_read_errors | mixed_write_errors |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sqlite | 79.214 | 16.676 | 0.749 | 1.545 | 4769.37 | 2.184 | 2.837 | 10577.03 | 0.636 | 3.178 | 0 | 0 |
| mysql | 409.419 | 121.791 | 3.670 | 6.495 | 797.49 | 10.050 | 14.476 | 2459.46 | 4.879 | 9.526 | 0 | 0 |

## 3. 解释与结论

- 单条查询平均延时更优：`sqlite`
- 批量写入吞吐更优：`sqlite`
- 若 SQLite 在混合并发中出现错误，说明其在写入并发下更容易受锁竞争影响；MySQL 一般更适合多连接并发写入场景。
- 由于两种后端使用同一份源数据与同一套 schema，结果可直接用于横向比较。
