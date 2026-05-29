# 第四阶段：竞争性关键词推荐系统（下）——数据审计、算法参数与数据库 schema 设计

本文档记录对当前仓库数据的扫描与审计结论、面向广告投放场景的算法参数建议、数据库 schema 建议、增量更新策略与下一步实施要点，供后续开发与验收参考。

## 1 总结结论（要点）
- 仓库中已有可用的搜索日志与清洗/分词产物，可直接用于原型开发：
  - `数据分析与商务智能数据/数据/user_tag_query.10W.TRAIN` 与 `...TEST`（各 100k 行样本，见 cleaning_log.json）
  - `数据分析与商务智能数据/搜索日志/SogouQ/...` （SogouQ 原始/解码样本，包含 query 字段与 URL 等）
  - 预处理与分词产物位于 `deliverables/P1/` 与 `deliverables/P3/reports/v2/`（例如 `tokenized_queries_jieba_search.csv`），字段头为 `query_time,user_id,query,token,matched_seed`。
- 数据可满足“推荐关键词 + 竞争度 + 热度 + 趋势”功能：若希望展示趋势，需要依赖时间字段（若某些 tokenized 文件中 `query_time` 未保存真实时间，可改用 `cleaned_queries_v1.csv` 或直接重新从 SogouQ 原始日志抽取时间戳）。

## 2 数据审计（发现）
- 清洗日志样本：
  - `deliverables/P1/run_train_v2_full/cleaning_log.json` 中显示 total_lines=100000, cleaned_query_count=100000，seed_related_count=265（说明已有 100k 级别样本可用）。
  - `deliverables/P1/run_experiment1_with_seeds_v1/cleaning_log.json` 同样记录 100000 行样本。
- 分词/命中产物：
  - `deliverables/P3/reports/v2/tokenized_queries_jieba_search.csv` 有列 `query_time,user_id,query,token,matched_seed`，但实测大量行中 `query_time` 存的是一个 ID/hash，表示在分词步骤并未保留标准时间戳；cleaned_queries 文件中有多条记录包含明显的日期字符串（例如 `2011-05-27`），因此时间戳信息在原始数据中存在，需决定使用哪个中间产物做趋势统计。
- SogouQ 原始日志：
  - 文件 `数据分析与商务智能数据/搜索日志/SogouQ/SogouQ/access_log.*.decode.filter` 含有可解析字段（数据说明：时间戳 \t 用户ID \t [查询] \t URL ...），来源足够用于做基于时间的热度/趋势统计。

结论：现有数据充足做原型；若要保证趋势可靠，优先从 SogouQ 原始或 `cleaned_queries_v1.csv` 中提取 `query_time` 字段并确保其标准化为 ISO 日期时间。

## 3 推荐的指标与算法（默认参数）
目标：给广告投放场景下的“种子词 → 竞争关键词”提供可解释、可操作的排序与数值（竞争度）。

指标定义（基础量）：
- freq(w): 关键词 w 在日志中的总搜索频次（或最近 N 天内的频次）
- cooccur(s,w): 在同一查询或同一会话中 seed s 与词 w 共现的次数
- pmi(s,w): 点互信息估计：log( P(s,w) / (P(s)P(w)) )，或用 smoothed PMI
- uniq_users(w): 搜索词 w 的独立用户数（若可用）

推荐的竞争度函数（可解释、线性组合）：
competition(s,w) = α * norm_cooccur(s,w) + β * norm_freq(w) + γ * norm_pmi(s,w)

默认参数（起始值，可通过离线实验调优）：
- α = 0.5（共现支撑广告竞争）
- β = 0.3（高热度词通常竞争更激烈）
- γ = 0.2（高PMI提示强相关但稀有词也被放入）

归一化与平滑：
- norm_* 使用 log(1 + x) 之后按列最大值归一化到 [0,1]，以减少长尾影响。
- 对 cooccur 使用拉普拉斯平滑（+1）避免除以零。

阈值与候选过滤：
- 最小共现 cooccur(s,w) >= 3
- 全局频次 freq(w) >= 5
- top_k 默认 50（前端展示 top-20/30 可配置）

趋势和热度：
- 热度：使用 rolling-window（建议 7 天或 30 天）内的 freq 作为热度指标
- 趋势：按日/周统计 freq_t 序列，前端展示折线并做简单平滑（EMA，alpha=0.3）

排序输出：主排序按 competition 降序，同时返回 freq、pmi、cooccur、trend_series 供前端展示与判读。

可替代/补充算法：
- 若需更精细排序，可把 competition 交给轻量学习到排序（LTR）模型训练，特征包括 cooccur、freq、pmi、uniq_users、最近增长率等。但课程项目阶段建议先用可解释公式。

## 4 建议数据库 schema（基于仓库已有 `db_schema_v1.sql` 的扩展）
仓库已包含良好的 schema（见 `deliverables/P3/db_schema_v1.sql`），建议在此基础上添加：

1) timeseries 表——保存关键词按日期聚合的热度（用于趋势展示）

CREATE TABLE IF NOT EXISTS keyword_timeseries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  keyword TEXT NOT NULL,
  date TEXT NOT NULL, -- ISO date YYYY-MM-DD
  freq INTEGER NOT NULL DEFAULT 0,
  uniq_users INTEGER DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(keyword, date),
  FOREIGN KEY(keyword) REFERENCES keyword(keyword) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_timeseries_keyword_date ON keyword_timeseries(keyword, date DESC);

2) keyword_stats 表——汇总统计，快速查询热度/全量频次/最后更新时间

CREATE TABLE IF NOT EXISTS keyword_stats (
  keyword TEXT PRIMARY KEY,
  freq INTEGER NOT NULL DEFAULT 0,
  uniq_users INTEGER DEFAULT 0,
  last_updated TEXT,
  avg_weekly_growth REAL DEFAULT 0
);

注意：`intermediary_keyword` 与 `competition_result` 表已包含核心字段，可直接复用；仅补充 timeseries 与 stats 以加速趋势/热度查询。

## 5 增量更新策略（离线实现，不在前端）
工作流程（日批或文件到达触发）：
1. 新日志文件到达 → 运行 `ingest_new_logs.py`：
   - 清洗、解析（保持与主 pipeline 一致的分词/匹配口径）
   - 计算增量聚合：freq 增量、cooccur 增量、timeseries 日粒度增量
2. 将增量写入数据库（UPSERT）：
   - 更新 `keyword_stats.freq`、`keyword_timeseries`（按 date UPSERT）
   - 对受影响的 seed-key 对局部重算 competition 值并更新 `competition_result`（仅计算受影响 candidate）
3. 触发 snapshot（可选）：保存计算时间戳 `computed_at` 及来源 `evidence_source`。

脚本建议：
- `pipeline/ingest_incremental.py`：读取新日志目录，输出增量 CSV（keyword, date, freq; seed,candidate,cooccur_delta）
- `pipeline/update_db_from_incremental.py`：将增量写入 SQLite/Postgres，执行 UPSERT 与局部重算

重算策略：只对受影响 seed 的 top-N 候选执行重算，避免全量重算（效率友好）。

## 6 前端设计（极简，按你的要求）
- 单页：搜索框（输入种子词）→ 调用 API `/recommend?seed=xxx&top=20`
- 结果表格：候选词 | 竞争度 | 热度（数值/小条） | 相关度 | 示例查询（展开）
- 点击候选词或“趋势”按钮弹出折线图（调用 `/trend?keyword=yyy`）
- 不在前端实现任何增量写入或复杂计算，所有更新由离线管道完成。

## 7 验收清单（可量化）
- 输入种子词，返回 top-20 候选并显示 competition、freq、相关度与趋势图。
- 离线增量脚本完成一次样本导入并在 DB 中更新 timeseries 与 competition_result。
- 提供至少一页文档说明：如何运行离线管道、如何重算、如何启动后端 API 与前端小页。

## 8 下一步/我可以现在执行的事项
1. 我已完成数据扫描/审计并记录在本文件中（done）。
2. 建议下一步：我可以为你生成：
   - 离线管道模板脚本（`pipeline/ingest_incremental.py`、`pipeline/update_db_from_incremental.py`）
   - 后端 API minimal 实现（FastAPI）与前端 demo 页面（HTML+ECharts）
   - 并把默认参数写入 `config/competition_params.yaml`

请选择你希望我下一步实现哪个模块（或允许我按里程碑顺序开始实现：算法实现 → 离线管道 → DB schema 增补 → API → 前端 demo）。

## 9 公开搜索日志数据源筛选：成熟系统通常怎么做
当用户真正需要的是“可下载、近些年、像搜索日志”的公开数据时，成熟系统的做法不是强行找一个完美同构的数据集，而是先分三类：

1. **原生搜索日志类**：保留 query / session / click / timestamp 等核心字段，最适合复用旧 pipeline。
2. **门户/站内检索日志类**：更“新”，通常官方可下载，但字段语义会偏访问/站内搜索，不一定有完整的 session 结构。
3. **研究型补充数据**：可以补足实验规模，但不应被当成主数据源。

### 候选源对比

- **SEC EDGAR Log File Data Sets（推荐作为“最近公开数据”的主候选）**
  - 官方提供 2020-05-19 到 2025-06-30 的日志文件，格式为按日下载的 ZIP/CSV。
  - 优点：近、公开、可下载、官方来源稳定。
  - 适合：做“最近一段时间的搜索/检索日志”实验，作为新数据输入旧流程前的测试样本。
  - 局限：它更像站内检索/访问日志，不一定和经典搜索引擎日志完全同构。

- **Jeff Huang 的 Web Search Query Log Downloads（推荐作为“经典搜索日志”对照）**
  - 包含 AOL 2006、MSN 2006/2007、Sogou 2008、Yandex 2009 等。
  - 优点：更接近传统搜索日志语义，常见字段包括 user/session/click/query。
  - 局限：年份较早，不满足“较新数据”的要求；但非常适合做对照实验和兼容性回归。

- **AOL User Session Collection（本次已验证可匿名下载的经典 query log）**
  - McGill 镜像可直接访问，文件包含 `AnonID / Query / QueryTime / ItemRank / ClickURL`。
  - 优点：字段最贴近本项目的 query/session/time/click 需求，且无需登录即可下载样本。
  - 局限：年份较老，但作为“经典查询日志”主对照非常合适。

- **archive-query-log（更适合作为补充研究工具）**
  - 目标更偏向从网络档案中挖掘搜索结果页/查询痕迹。
  - 优点：研究味道浓，适合补充实验。
  - 局限：它不是最标准的“下载即用搜索日志”，更像工具或研究项目。

### 推荐结论

如果你的目标是：

- **“最近几年 + 官方可下载 + 能跑本地实验”** → 先选 **SEC EDGAR**。
- **“最像经典搜索引擎日志 + 可做兼容性对照”** → 优先用 **AOL**，再扩展到 **Sogou / MSN / Yandex** 这类老日志做 benchmark。
- **“想再补一个研究型数据源”** → 再考虑 **archive-query-log**。

### 隔离接入建议

对新日志不要直接混进旧目录或旧库，建议固定成下面这种结构：

- `data/source_logs/<source_name>/raw/`：原始下载文件
- `data/source_logs/<source_name>/normalized/`：统一后的 canonical CSV
- `data/source_logs/<source_name>/manifest.json`：字段映射、下载日期、版本、来源说明
- `compkey_<source_name>.sqlite3`：单独 demo 数据库

统一字段建议至少保留：

- `event_time`
- `query_text`
- `user_id` 或 `session_id`
- `clicked_url`（如果有）
- `source`
- `raw_line` 或 `raw_payload`

这样做的好处是：

- 旧 Sogou 数据与新来源完全隔离，不会互相污染。
- 每个来源只需要写一个 adapter/mapping，不用改整条主流程。
- 先在独立 demo 库里跑通，再决定是否纳入主库。

## 10 本次本地验证结论
- 现阶段结论不是“热榜接入”，而是：**公开搜索日志的最佳近期候选是 SEC EDGAR，经典 query log 的最佳可下载候选是 AOL**。
- 下一步如果要落地，建议先下载 **1 天的 AOL 样本**，把它映射成 canonical CSV，再跑一遍现有 P1/P3 处理链路，验证字段兼容性和隔离策略；EDGAR 则保留为“较新公开数据”的补充基线。
- 当前仓库里已有的热榜 demo 仍然保留，但它属于误判分支，只能作为“独立多源数据接入”的工程示例，不能替代搜索日志任务本身。

结论：
> 对你现在这个题目，最稳妥的路线是“**AOL 作为经典 query log 主线 + SEC EDGAR 作为近期公开补充 + 新旧数据完全隔离 + 先在独立 demo 库验证**”。这样既符合课程实验可落地，也不会把老数据体系弄脏。

---
（审计基于仓库内文件：`deliverables/P1/*`, `deliverables/P3/*`, `数据分析与商务智能数据/搜索日志/*` 的抽样检查；若你希望，我下一步可以直接把 **EDGAR → canonical CSV** 的小型适配器脚本补出来，再配一个独立 demo 库导入流程。）
