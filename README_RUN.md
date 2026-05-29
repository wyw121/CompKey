# CompKey - 运行说明（快速上手）

准备（Windows 示例）：

1. 创建虚拟环境并安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

2. 生成前端示例数据（可选）

```powershell
python scripts/generate_sample_json.py --limit 20000
```

3. 运行增量 ingest（将根据 tokenized CSV 生成 `data/incremental` 下的增量文件）

```powershell
python pipeline/ingest_incremental.py --tokenized deliverables/P3/reports/v2/tokenized_queries_jieba_search.csv --outdir data/incremental
```

（注意：若文件很大，可调整 --limit 或用分块读取）

4. 将增量写入数据库并重算 competition

```powershell
python pipeline/update_db_from_incremental.py --db ./compkey_p4.sqlite3 --inc ./data/incremental --config ./config/competition_params.yaml
```

5. 启动后端（FastAPI）

```powershell
uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
```

6. 打开前端页面

在浏览器打开 `frontend/index.html`（本地直接打开或使用一个轻量静态文件服务器，如 `python -m http.server 8001`，然后访问 `http://127.0.0.1:8001/frontend/index.html`）。

备注与说明：
- 所有脚本都可以在没有完整数据集的情况下运行（会生成合成示例或在找不到 tokenized 文件时跳过），但要做真实交互请确保 `deliverables/P3/reports/v2/tokenized_queries_jieba_search.csv` 或 `deliverables/P1/*/cleaned_queries_v1.csv` 可用。
- `config/competition_params.yaml` 中可调整 alpha/beta/gamma、阈值与 SQLite 路径。

## 外部热榜数据接入（本次新增）

如果你想把“时下流行关键词”单独作为一个新数据源跑实验，可以用下面的分层流程：

1. 把每个来源的页面快照分别保存到 `data/external_trending/captures/`。
2. 运行标准化脚本，把不同来源统一成 canonical CSV：

```powershell
python pipeline/build_trending_snapshot.py --capture baidu=... --capture zhihu=... --capture weibo=... --outdir data/external_trending
```

3. 把合并层写进一个**独立** demo 库：

```powershell
python pipeline/update_db_from_incremental.py --db ./compkey_trend_demo.sqlite3 --inc ./data/external_trending/merged --config ./config/trending_demo.yaml
```

4. 如需查看结果，启动独立 API：

```powershell
$env:COMPKY_CONFIG='config/trending_demo.yaml'
python -m uvicorn api.app:app --host 127.0.0.1 --port 8002
```

说明：
- 原始快照、标准化层、合并层是分开的，方便定位字段差异。
- demo 库不会覆盖原来的 `compkey_p4.sqlite3`。
