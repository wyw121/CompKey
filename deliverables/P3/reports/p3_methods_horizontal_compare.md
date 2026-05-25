# P3 各方法横向对比（模块化视角）

本文档总结了在本次多方法真实评测中对各模块（离线处理、在线服务、数据库与表、分词、日志、缓存等）分别进行了哪些横向对比、度量了哪些指标、以及当前缺失和后续改进建议。

## 1 概览
- 评测方法（已真实运行并产出结果）：`compkey_current`（当前方案）、`cooccur_freq`、`tfidf`、`pmi`。
- 主要评估指标：Recall@K（K=10）、MRR@K（K=10）、无缓存平均延时（ms）、验证查询数（本次样本：53）。
- 主要输入：`deliverables/P1/run_train_v2_full/tokenized_queries_v1.csv` 与 `deliverables/P1/seed_keywords_v1.csv`。

## 2 离线处理（candidate generation 与 scoring）
- 对比内容：
  - `compkey_current`：基于 seed 内 token 的 local_share * rarity + support 对数放大（项目离线 pipeline 的 `competition_score` 公式）。
  - `cooccur_freq`：只按 seed—token 共现次数排序（简单频次基线）。
  - `tfidf`：TF（support/seed_total） * IDF（log((1+N)/(1+df))），抑制通用 token、放大区分性 token。
  - `pmi`：点互信息（log P(token|seed)/P(token)），强调强关联但对低频敏感。
- 度量项：候选覆盖（Recall@10）、排序质量（MRR@10）、构建耗时（离线写入总体耗时，可见 `p3_performance_summary.md`）。
- 本次发现：TF-IDF 在 Recall@10 上表现最好（0.2839），cooccur_freq 在 MRR 上较优，pmi 对低频噪声敏感。
- 建议：
  - 增加 BM25 与 embedding-based（语义检索）作为候选得分基线；
  - 在离线阶段记录每种方法的候选集合大小与 Top-K 交集（Jaccard）用于分析覆盖与差异源；
  - 为大型样本使用分布式/分批处理并记录 IO/批次延时。

## 3 在线服务（recommendation service）
- 对比内容：不同打分方法在在线查询下的响应时延（无缓存冷查询延时被记录）。
- 度量项：平均无缓存延时（ms）、缓存命中率对延时的影响。实验结果显示：
  - `tfidf` 无缓存平均延时约 0.1091 ms，`compkey_current` 约 0.1149 ms，`pmi` 稍慢（0.1730 ms）。
- 说明：在线服务实现（`RecommendationService`）对方法调用接口统一，延时差异主要来自评分计算与结果排序成本。
- 建议：
  - 对方法调用加入异步批处理/向量化计算以缩短高复杂度方法（如embedding/pmi）延时；
  - 增加端到端 95/99 百分位延时采样以评估尾延迟；
  - 在服务层添加 A/B 流量分配（真实线上验证不同方法效果）。

## 4 数据库与表（存储设计与索引影响）
- 当前实现：SQLite（WAL 模式），表见 `db_schema_v1.sql`：`keyword`、`intermediary_keyword`、`competition_result`、`search_log` 等。
- 对比内容：本次实验未直接在多种 DB（Postgres/MySQL）上做横向实测；度量包含：DB 初始化耗时、离线导入耗时、单行写入平均成本（估算）。
- 本次观察：离线导入总耗时约 114.985 ms（小规模数据），单行写入估算 ~0.115 ms/row。
- 建议：
  - 在中/大规模场景对比 SQLite vs PostgreSQL（重点测并发写入/并发查询延时）;
  - 在 PostgreSQL 上使用 COPY / 批量插入与合适索引策略做吞吐测试；
  - 添加 DB 层基准脚本（带并发 worker）并度量吞吐、P95 延时与锁等待。

## 5 分词（tokenizer）
- 当前使用：`jieba`（项目 P1/P3 pipeline），并保留了基于正则的回退方案。
- 对比内容：本次 P3 多方法评测主要用 `jieba` 的 tokenized 输入；P1 目录下已有 `tokenizer_compare` 的 jieba_precise / jieba_search / regex 基准产物，但这些 tokenizer 未全部在 P3 横向方法评测中复用（除 jieba 与 regex 外未逐一集成）。
- 建议：
  - 将 P1 的 tokenizer 基准结果整合进 P3 流水线，分别用 HanLP、THULAC、jieba_precise/jieba_search/regex 生成候选并比较：
    - token_count、候选覆盖数、Top-K 重叠（Jaccard）、最终 Recall/MRR 差异；
  - 评估分词对低频/复合词（如长尾词）的影响，并考虑用分词结合词典/命名实体识别提升候选质量；
  - 如引入 embedding（语义候选），比较语义分词后与基于 token 的差异。

## 6 日志与度量埋点
- 已实现：在线查询写入 `search_log`；离线任务有阶段性耗时日志（读取/聚合/写入）。
- 对比内容：日志本身未作为比较维度（主要用于离线溯源和错误分析）。
- 建议：
  - 明确每次在线查询需采集的字段：`timestamp, seed, user_id (可选脱敏), latency_ms, cache_hit, result_count, method`；
  - 集成简单的指标上报（Prometheus / statsd 或本地 CSV 聚合），定期生成 P95/P99 报表；
  - 对空结果与异常做专门标记，便于离线回溯与样本补采。

## 7 缓存策略
- 当前实现：LRU cache，默认大小 128（`RecommendationCache`）。实测带来显著延时下降：冷启动 0.103 ms → 缓存命中 0.001 ms。
- 对比内容：不同方法在缓存命中情况下延时差异被压缩；无缓存时 `tfidf`/`compkey_current` 更优。
- 建议：
  - 做缓存大小敏感性试验（例如 64/128/512/2048）并绘制命中率曲线；
  - 对热点 seed 做预热策略（基于访问频率异步预填充）；
  - 考虑二级缓存（内存 LRU + 本地快速文件或 Redis）来应对更大数据集和多实例部署。

## 8 缺失项（未覆盖的横向对比）与优先级建议
1. 数据库横向对比（高优先）：SQLite vs PostgreSQL/MySQL 与并发写入/查询负载测试（需要部署 DB 实例）。
2. 更丰富的候选/排序基线（中高）：BM25、embedding（FAISS/Annoy）+ re-rank、学习到排序（LTR）。
3. Tokenizer 全面对比（中）：将 P1 中的 HanLP/THULAC 等纳入 P3 流水线，评估分词对最终指标的影响。
4. 大规模扩展测试（中）：用 100k / 1M token 数据跑规模实验并绘制扩展性曲线（耗时/吞吐/延时）。
5. 并发与尾延迟测试（中）：端到端 95/99 百分位时延测量与并发 worker 压测。
6. 在线 A/B 与用户信号回路（低中）：线上真实流量 A/B 验证与 feedback-based 学习。

### 8.1 数据库横向对比实验设计（高优先，建议先做）
- 对比对象：
  - `SQLite`：当前基线，零运维、单机轻量、适合交付与小规模实验。
  - `PostgreSQL`：推荐的高并发关系型基线，支持更强的并发写入、索引优化和事务控制。
  - `MySQL`：常见业务型数据库基线，可与 PostgreSQL 做实现与性能对照。
- 核心负载：
  - 离线批量写入：初始化建表、批量导入 `keyword / intermediary_keyword / competition_result / search_log`。
  - 在线读负载：按 seed 进行 Top-K 查询，比较冷查询与缓存命中场景。
  - 并发混合负载：N 个写入 worker + M 个查询 worker 同时运行，观察锁竞争与尾延迟。
- 关键指标：
  - 吞吐：rows/s、queries/s、batch commit/s。
  - 延时：平均延时、P95、P99、最大值。
  - 稳定性：超时率、失败率、锁等待/重试次数。
  - 资源占用：CPU、内存、磁盘 IO、数据库连接数。
- 推荐实验口径：
  - 固定相同 schema、相同 seed/查询集、相同 top-k；
  - 统一索引策略后再比较“数据库本身”差异；
  - 先单机单实例，再测并发 worker，最后测读写混合场景。
- 预期结论方向：
  - SQLite 在小样本、低并发场景最省心、启动快；
  - PostgreSQL 更适合并发写入与更复杂索引策略，尾延迟通常更稳；
  - MySQL 可作为业务型数据库对照，重点比较事务与并发读写行为。

### 8.2 候选/排序基线扩展实验设计（中高，建议并行做）
- `BM25`：作为比 TF-IDF 更稳健的词项检索基线，适合检验“短文本/种子词”场景下的词频饱和效应。
  - 关注点：候选召回、排序前列命中、对高频通用词的抑制能力。
- `embedding + re-rank`：
  - 先用向量召回（如 `FAISS` / `Annoy`）拿到语义近邻候选；
  - 再用现有规则分数、BM25 或轻量交叉编码器做 re-rank。
  - 适合验证“仅靠词频是否遗漏语义相关候选”。
- `LTR`（Learning to Rank）：
  - 用现有特征训练排序模型，例如支持度、全局频次、PMI、TF-IDF、seed 长度、token 位置等；
  - 可先从轻量模型（Logistic Regression / XGBoost / LightGBM ranker）开始，再逐步升级。
- 关键指标：
  - 召回类：Recall@10 / Recall@20；
  - 排序类：MRR@10、NDCG@10；
  - 成本类：离线构建耗时、在线冷查询延时、候选数规模；
  - 可解释性：Top-K 重叠率、与当前方案的 Jaccard 差异。
- 推荐实验口径：
  - 保持同一训练/验证切分；
  - 统一 top-k 与候选上限；
  - 对 embedding 方法额外记录向量维度、索引构建耗时和内存占用。
- 预期结论方向：
  - `BM25` 往往是最值得加入的文本检索强基线；
  - `embedding + re-rank` 更可能提升语义覆盖，但在线成本更高；
  - `LTR` 的上限最好，但依赖特征工程与标注/伪标注质量。

### 8.3 推荐的执行顺序
1. 先做数据库对比，因为它直接影响离线构建与在线服务的整体性能上限。
2. 再做 `BM25`，它实现成本低、解释性强，适合作为新的强基线。
3. 然后补 `embedding + re-rank`，用于验证语义召回收益。
4. 最后做 `LTR`，把多种规则分数融合成统一排序模型，作为最终提升方向。

### 8.4 本轮已完成的真实运行结果补充
- 多方法评测已新增 `BM25`：在本次 53 条验证查询上，`BM25` 的 Recall@10 为 0.2120、MRR@10 为 0.3191、无缓存平均延时为 0.1509 ms。
- 对比结论保持不变但更完整：`tfidf` 仍是 Recall@10 最优，`cooccur_freq` 仍是 MRR@10 最优；`BM25` 作为更标准的 IR 基线已验证，但在当前样本上没有超过已有简单基线。
- 数据库对比已真实运行：SQLite 在本机小样本与低并发下更快；MySQL 在当前配置下读写平均延时更高，但作为可扩展后端更适合未来的并发/部署实验。

## 9 如何复现与位置
- 核心脚本：`deliverables/P3/run_stage3_multimethod_benchmark.py`（生成 `deliverables/P3/reports/p3_multimethod_benchmark.csv` 与 `.md`）。
- 离线 pipeline：`deliverables/P3/compkey_p3/offline_pipeline.py`。
- 在线服务：`deliverables/P3/compkey_p3/service.py` 与 `deliverables/P3/compkey_p3/repository.py`。
- 分词基准（P1）：`deliverables/P1/tokenizer_compare/`。

---

本轮报告中的数据库横向对比与 BM25 真实评测已经完成，并已同步到 `p3_final_summary.md` 与对应的结果文件中，可直接作为第三阶段补充实验材料提交。