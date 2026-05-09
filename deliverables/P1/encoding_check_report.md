# P1 编码与数据结构核验报告（v3）

## 1. 核验对象

- `数据分析与商务智能数据/数据/user_tag_query.10W.TRAIN`
- `数据分析与商务智能数据/数据/user_tag_query.10W.TEST`
- `数据分析与商务智能数据/搜索日志/数据说明.txt`
- `数据分析与商务智能数据/搜索日志/SogouQ.reduced/SogouQ.reduced`

## 2. 结论

1. 文件规模较大：
   - TRAIN 约 224,899,985 bytes（~214.5MB）
   - TEST 约 416,205,020 bytes（~397.0MB）
2. 控制台直接读取文本时出现中文乱码，说明存在**编码不一致或终端解码方式不匹配**。
3. 数据行结构表现为“用户ID + 年龄 + 性别 + 教育 + Query列表（多查询词）”的混合结构，字段之间包含空白符，后续解析需基于明确分隔规则。
4. 搜索日志（SogouQ）为更贴近课程“搜索行为日志”目标的数据源，阶段一提交口径调整为：
   - **主结果**：`run_log_v1_main`（搜索日志口径）
   - **对照补充**：`run_train_v2_full`（user_tag_query 口径）

## 3. 编码探测实验结果（已完成）

基于日志口径主结果 `deliverables/P1/run_log_v1_main/encoding_probe_result_v1.csv`：

| encoding | readable_ratio |
| -------- | -------------: |
| utf-8    |         0.0000 |
| gb18030  |         1.0000 |
| utf-16   |         0.0000 |

**最终结论：统一读取编码采用 `gb18030`，中间结果统一输出为 `utf-8-sig`。**

## 4. 阶段一编码处理策略（执行建议）

- 优先尝试编码顺序：`utf-8` → `gb18030`（兼容GBK）→ `utf-16`。
- 使用“抽样行可读率”作为判定标准（例如抽样1000行中可正常显示中文比例）。
- 固定编码后，统一写出为 UTF-8（带BOM可选）作为中间清洗数据。

## 5. 证据要求

- 截图1：原始读取乱码画面。
- 截图2：修正编码后的可读画面。
- 输出文件：`encoding_check_report.md`（本文件） + `encoding_probe_result_v1.csv`。

## 6. 已完成与待执行项

- [x] 对搜索日志（SogouQ.reduced）完成多编码可读率对比并打分。
- [x] 输出 `encoding_probe_result_v1.csv`（encoding, readable_ratio）。
- [x] 锁定统一编码并更新本报告为 v3。
- [ ] 对 TEST 全量数据执行同样探测并补充对比结论（建议作为v3）。
