# P3 实验要求对照与补充说明

本文档用于补充说明两个容易被问到的问题：**种子关键词是怎么来的**，以及**第三阶段作业 3.3 的四项内容在本项目里分别对应什么**。它不是新的实验结果，而是对现有系统说明文档的整理补强，方便提交和答辩时快速定位。

## 1. 种子关键词来源说明

P3 的种子关键词来自 P1 阶段的 `deliverables/P1/seed_keywords_v1.csv`。这份文件不是从搜索日志里自动抽取出来的，而是**人工整理的控制种子表**，共 15 个词，字段包括：

- `keyword`：种子词本身
- `domain`：所属领域
- `reason`：选取理由
- `owner`：当前项目中保留的归属字段

这组种子词的作用是：

1. 作为离线统计与推荐构建的输入集合；
2. 作为对比实验的稳定锚点，保证不同 tokenizer / 不同候选方法之间可以在同一批 seed 上比较；
3. 便于解释推荐结果的业务含义，而不是让系统直接对整份日志“无差别泛化”。

在 P1 与 P3 的处理链路中，种子词都被显式读取和使用，例如：

- `deliverables/P1/log_pipeline.py`
- `deliverables/P1/extract_seed_lines.py`
- `deliverables/P1/count_seed_occurrences.py`
- `deliverables/P3/compkey_p3/offline_pipeline.py`

因此，如果被问到“seed keyword 是哪里来的”，最准确的回答是：

> 它来自 P1 阶段人工整理的 `seed_keywords_v1.csv`，属于项目预先定义的控制种子集，用来驱动离线统计、候选生成和横向评估。

## 2. 3.3 内容与本项目产物的对应关系

第三阶段作业要求中的 3.3 内容，本项目已经按“系统化材料 + 真实实现 + 评估证据”的方式对应起来了。

### 2.1 软件系统概述

对应内容：

- 系统目标：把搜索日志分析、分词统计、候选生成和推荐查询整合成一个可运行的关键词推荐系统。
- 数据来源：原始搜索日志 + P1 输出（清洗、分词、词频、种子词相关记录）。
- 使用方式：离线构建数据库，在线按 seed 查询推荐结果。

建议对应文档：

- `deliverables/P3/SRS_v1.md`
- `deliverables/P3/reports/p3_final_summary.md`

### 2.2 软件系统结构设计

对应内容：

- 采用离线 / 在线分离架构；
- 数据层、处理层、算法层、服务层、展示层分工明确；
- 离线侧负责重计算，在线侧负责快速查询与日志写入。

建议对应文档：

- `deliverables/P3/architecture_design_v1.md`

### 2.3 功能模块设计

对应内容：

- `config`：统一配置路径与参数；
- `database`：初始化数据库与连接；
- `repository`：封装 CRUD 与查询；
- `offline_pipeline`：离线导入、聚合、写表；
- `service`：在线推荐、缓存、反馈；
- `benchmark`：性能与横向对比评估。

建议对应文档：

- `deliverables/P3/module_design_v1.md`
- `deliverables/P3/compkey_p3/`

### 2.4 数据库设计

对应内容：

- `keyword`：关键词基础信息；
- `intermediary_keyword`：seed 与中介词的支持度、权重；
- `competition_result`：候选词与竞争分数；
- `search_log`：在线/离线样本日志；
- `user_feedback`：反馈回写。

建议对应文档：

- `deliverables/P3/db_schema_v1.sql`
- `deliverables/P3/db_dictionary_v1.csv`

## 3. 这次实验“看起来偏”的地方，如何解释

如果老师或同学觉得本次材料里 benchmark 比例偏大，可以这样解释：

1. **benchmark 不是主线本身，而是系统设计的证据**。第三阶段不是单纯做算法比赛，而是要证明系统可运行、可复现、可比较。
2. **系统文档已经覆盖 3.3 四项要求**，benchmark 只是说明“为什么这个架构、这个模块、这个数据库设计是合理的”。
3. **当前实现以 CLI + SQLite 为主**，这是为了优先完成可交付的系统骨架；网页 UI、分布式数据库等内容不属于第三阶段的必要范围。
4. **横向对比是加分项，不是偏题项**。它说明我们不是只写了一个脚本，而是做了 tokenizer、方法、数据库、规模扩展等维度的验证。

## 4. 可直接放进报告的简短表述

如果需要在正文里补一句总括，可以直接写：

> 本项目的 seed keyword 来自 P1 阶段人工整理的 `seed_keywords_v1.csv`，属于预定义控制种子集。第三阶段在此基础上完成了系统概述、架构设计、功能模块设计与数据库设计，并通过分词、方法、数据库与规模扩展等横向实验验证了系统方案的可运行性与可扩展性。
