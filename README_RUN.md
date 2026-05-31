# CompKey - 快速上手

更完整的使用说明请看根目录的 `README.md`。这里保留最短可执行流程，适合第一次跑项目时快速确认环境是否正常。

## Windows 快速启动

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
python -m http.server 8001 -d frontend
```

然后打开：


### 运行测试

```powershell
python -m pytest
```

### 切换 demo 配置

```powershell
$env:COMPKY_CONFIG = 'config/trending_demo.yaml'
python -m uvicorn api.app:app --host 127.0.0.1 --port 8002
```

### 重建增量数据

```powershell
python pipeline/ingest_incremental.py --tokenized <tokenized_csv路径> --outdir data/incremental
python pipeline/update_db_from_incremental.py --db .\compkey_p4.sqlite3 --inc .\data\incremental --config .\config\competition_params.yaml
```

## 数据源说明

- `P4 主库`：主项目演示数据库
- `AOL demo`：经典 query log 示例
- `trending_demo`：热榜/趋势演示配置

如果前端页面打开后没有数据，优先检查后端是否正在 `127.0.0.1:8000` 运行。

