# P3 v2 阶段性总结

## 1. v2 目标

v2 的目标不是推翻现有系统，而是把 seed 版本化，并在**业界常见的横向基线**上重新验证推荐链路是否稳定：

- 候选/排序方法：`compkey_current`、`cooccur_freq`、`tfidf`、`pmi`、`bm25`
- 分词器：`jieba_precise`、`jieba_search`、`regex`、`thulac`

## 2. v2 seed 版本

- 文件：`deliverables/P1/seed_keywords_v2.csv`
- seed 数量：20
- 说明：在原有 15 个控制 seed 的基础上，补充了家电、母婴玩具和运动细分场景，使领域覆盖更完整。

### v2 seed 命中情况

| seed | count |
|---|---:|
| 笔记本电脑 | 6958 |
| 手机壳 | 1042 |
| 蓝牙耳机 | 1144 |
| 机械键盘 | 737 |
| 平板电脑 | 1664 |
| 运动鞋 | 1329 |
| 羽绒服 | 399 |
| 口红 | 4028 |
| 面膜 | 14642 |
| 洗发水 | 2621 |
| 咖啡机 | 95 |
| 空气炸锅 | 80 |
| 净水器 | 1207 |
| 在线课程 | 5 |
| 考研培训 | 30 |
| 电饭煲 | 1161 |
| 洗衣机 | 2947 |
| 空调 | 10327 |
| 儿童玩具 | 151 |
| 瑜伽垫 | 88 |

## 3. 已完成的横向评估

### 3.1 多方法评估

结果文件：

- `p3_multimethod_benchmark.csv`
- `p3_multimethod_benchmark.md`

结论（本轮实测）：

- Recall@10 最优：`tfidf`
- MRR@10 最优：`cooccur_freq`
- 无缓存延时最优：`compkey_current`

### 3.2 Tokenizer × Method 评估

结果文件：

- `p3_multimethod_tokenizer_compare.csv`
- `p3_multimethod_tokenizer_compare.md`

结论（本轮实测）：

- `jieba_search` 在整体召回和排序上依然最稳
- `regex` 速度快，但切分过粗，指标明显偏弱
- `thulac` 细粒度更强，但速度相对慢

## 4. 当前可直接用于汇报的话术

> v2 版本使用了人工整理但经过日志命中验证的控制 seed 集，并在 BM25、TF-IDF、PMI、共现频次等业界常用横向基线，以及不同分词器口径下完成了再评估。结果表明，`tfidf` 在召回上最优，`cooccur_freq` 在排序前列命中上最优，而 `jieba_search` 在 tokenizer 层面最均衡。

## 5. 下一步建议

如果继续推进 v2，建议按下面顺序补齐：

1. SQLite vs MySQL 数据库横向评估
2. 规模扩展测试（10k / 100k / 300k / 500k / 1M token）
3. 如有需要，再微调 seed 版本为 v2.1 / v2.2
