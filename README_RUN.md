# CompKey - 运行说明（快速上手）

准备（Windows 示例）：

- 第 1 步：创建虚拟环境并安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

- 第 2 步：生成前端示例数据（可选）

```powershell
python scripts/generate_sample_json.py --limit 20000
```

- 第 3 步：运行增量 ingest（将根据 tokenized CSV 生成 `data/incremental` 下的增量文件）

```powershell
python pipeline/ingest_incremental.py --tokenized deliverables/P3/reports/v2/tokenized_queries_jieba_search.csv --outdir data/incremental
```

（注意：若文件很大，可调整 --limit 或用分块读取）

- 第 4 步：将增量写入数据库并重算 competition

```powershell
python pipeline/update_db_from_incremental.py --db ./compkey_p4.sqlite3 --inc ./data/incremental --config ./config/competition_params.yaml
```

- 第 5 步：启动后端（FastAPI）

```powershell
uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
```

- 第 6 步：打开前端页面

在浏览器打开 `frontend/index.html`（本地直接打开或使用一个轻量静态文件服务器，如 `python -m http.server 8001`，然后访问 `http://127.0.0.1:8001/frontend/index.html`）。

备注与说明：

- 所有脚本都可以在没有完整数据集的情况下运行（会生成合成示例或在找不到 tokenized 文件时跳过），但要做真实交互请确保 `deliverables/P3/reports/v2/tokenized_queries_jieba_search.csv` 或 `deliverables/P1/*/cleaned_queries_v1.csv` 可用。
- `config/competition_params.yaml` 中可调整 alpha/beta/gamma、阈值与 SQLite 路径。

## 外部热榜数据接入（本次新增）

如果你想把“时下流行关键词”单独作为一个新数据源跑实验，可以用下面的分层流程：

- 把每个来源的页面快照分别保存到 `data/external_trending/captures/`。
- 运行标准化脚本，把不同来源统一成 canonical CSV：

```powershell
python pipeline/build_trending_snapshot.py --capture baidu=... --capture zhihu=... --capture weibo=... --outdir data/external_trending
```

- 把合并层写进一个**独立** demo 库：

```powershell
python pipeline/update_db_from_incremental.py --db ./compkey_trend_demo.sqlite3 --inc ./data/external_trending/merged --config ./config/trending_demo.yaml
```

- 如需查看结果，启动独立 API：

```powershell
$env:COMPKY_CONFIG='config/trending_demo.yaml'
python -m uvicorn api.app:app --host 127.0.0.1 --port 8002
```

说明：

- 原始快照、标准化层、合并层是分开的，方便定位字段差异。
- demo 库不会覆盖原来的 `compkey_p4.sqlite3`。

## 公开日志接入（EDGAR 近期样本）

如果你想做“最近几年、官方可下载、并尽量复用现有日志流程”的实验，可以先拿 SEC 的 EDGAR 日志做一个独立隔离版：

- 下载/准备日志样本后，先构建独立快照：

```powershell
python pipeline/build_edgar_snapshot.py --input https://www.sec.gov/dera/data/Public-EDGAR-log-file-data/2025/Qtr2/log20250630.zip --outdir data/source_logs/edgar
```

- 用现有增量脚本继续处理生成的 tokenized 文件：

```powershell
python pipeline/ingest_incremental.py --tokenized data/source_logs/edgar/normalized/tokenized_queries.csv --outdir data/source_logs/edgar/merged
```

- 把增量写入一个**单独** demo 数据库：

```powershell
python pipeline/update_db_from_incremental.py --db ./compkey_edgar_demo.sqlite3 --inc ./data/source_logs/edgar/merged --config ./config/competition_params.yaml
```

说明：

- `EDGAR` 样本更接近站内检索/访问日志，不是经典搜索引擎 query log；因此这里的 `query_text` 是从 `uri_path` 规范化得到的，主要用于兼容性和流程验证。
- 新旧数据仍然保持完全隔离：原始文件、标准化文件、增量中间件和 demo 库都放在独立目录里。
- 如果你后续找到更像搜索引擎 query 的开放数据源，只需要再增加一个新的 adapter，不需要改主流程。

## 公开日志接入（AOL 经典 query log）

如果你想先做“最像真实搜索引擎查询日志”的对照实验，可以直接用 AOL 用户会话集合（McGill 镜像可匿名访问）：

- 下载/准备日志样本后，先构建独立快照：

```powershell
python pipeline/build_aol_snapshot.py --input https://www.cim.mcgill.ca/~dudek/206/Logs/AOL-user-ct-collection/user-ct-test-collection-01.txt --outdir data/source_logs/aol
```

- 用现有增量脚本继续处理生成的 tokenized 文件：

```powershell
python pipeline/ingest_incremental.py --tokenized data/source_logs/aol/normalized/tokenized_queries.csv --outdir data/source_logs/aol/merged
```

- 把增量写入一个**单独** demo 数据库：

```powershell
python pipeline/update_db_from_incremental.py --db ./compkey_aol_demo.sqlite3 --inc ./data/source_logs/aol/merged --config ./config/competition_params.yaml
```

说明：

- AOL 日志比 EDGAR 更像经典 query log，保留了 `Query / QueryTime / ItemRank / ClickURL`。
- 与旧数据完全隔离：原始文件、标准化文件、增量文件和 demo 库都放在独立目录里。
- 这份数据更适合做“经典搜索日志”的兼容性 benchmark；如果你后续想测“较新公开数据”，再切回 EDGAR 就行。
