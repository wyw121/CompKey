# CompKey

CompKey 是一个面向“竞争性关键词推荐”的课程项目。它结合搜索日志/公开日志、SQLite 数据库、FastAPI 后端和前端可视化页面，提供以下能力：

- 输入一个种子词，查看竞争性候选词推荐结果
- 查看关键词时间趋势
- 浏览热词榜单和数据量趋势
- 在不同 demo 数据源之间切换，便于演示和对比

## 项目能做什么

当前仓库包含三类常用演示场景：

- `P4 主库`：项目主数据库，适合查看完整实验结果
- `AOL demo`：经典英文 query log 示例，适合做搜索行为演示
- `热词榜单 / 趋势图`：用于展示关键词的近期变化和数据规模

如果你只是想“先跑起来看效果”，直接按下面的快速启动即可。

## 环境要求

- Windows 10/11
- Python 3.10 或更高版本
- 建议使用虚拟环境 `venv`
- 浏览器：Edge / Chrome 均可

## 仓库结构速览

- `api/`：FastAPI 后端
- `frontend/`：前端静态页面
- `pipeline/`：数据构建、增量更新、快照生成脚本
- `config/`：运行参数和 demo 数据源配置
- `data/`：中间数据、快照与增量结果
- `deliverables/`：阶段性实验材料、报告和辅助脚本
- `tests/`：自动化测试
- `compkey_*.sqlite3`：现成的 SQLite 演示数据库

## 先安装依赖

在项目根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

如果你在 PowerShell 中第一次激活虚拟环境时提示执行策略限制，可以先临时放开当前窗口：

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned
```

然后再重新执行激活命令。

## 最推荐的启动方式

### 1）启动后端 API

在项目根目录执行：

```powershell
python -m uvicorn api.app:app --reload --host 127.0.0.1 --port 8000
```

启动成功后，接口会监听在：

- `http://127.0.0.1:8000`
- Swagger 文档：`http://127.0.0.1:8000/docs`

### 2）启动前端页面

为了避免浏览器跨域限制，建议使用静态文件服务器打开 `frontend/`：

```powershell
python -m http.server 8001 -d frontend
```

然后访问：

- `http://127.0.0.1:8001/index.html`
- `http://127.0.0.1:8001/trending.html`

> 也可以直接双击打开 HTML，但如果浏览器拦截本地 `fetch` 请求，优先改用静态服务器。

## 3 分钟快速验证

1. 启动后端。
2. 打开前端页面。
3. 在“种子词查询”输入框中输入例如：`苹果`、`手机`、`旅游`。
4. 点击“查询”，查看推荐结果和趋势图。
5. 如果页面能切换数据源，说明 `P4 主库` 和 `AOL demo` 配置都正常。

## 后端接口说明

后端使用 FastAPI，常见接口包括：

- `GET /sources`：查看可用 demo 数据源
- `GET /recommend?seed=...`：根据种子词获取竞争性候选词
- `GET /trend?keyword=...`：查看关键词趋势
- `GET /hot_keywords`：获取热词榜单
- `GET /source_volume`：查看数据量趋势
- `GET /seed_suggestions`：获取快捷种子词

你可以直接访问 `http://127.0.0.1:8000/docs` 在线调试这些接口。

## 配置文件说明

默认配置文件位于 `config/competition_params.yaml`，主要控制：

- `alpha / beta / gamma`：竞争度计算参数
- `min_cooccur / min_freq`：过滤阈值
- `top_k`：候选词数量上限
- `db_path`：默认 SQLite 数据库路径
- `default_demo_source`：默认数据源
- `demo_sources`：各 demo 数据源的数据库配置

### 切换配置文件

后端会优先读取环境变量 `COMPKY_CONFIG` 指向的 YAML 文件。PowerShell 示例：

```powershell
$env:COMPKY_CONFIG = 'config/trending_demo.yaml'
python -m uvicorn api.app:app --host 127.0.0.1 --port 8002
```

如果你想切回主库，只要取消环境变量即可：

```powershell
Remove-Item Env:COMPKY_CONFIG
```

## 数据库与数据文件

仓库中已经包含多个可直接演示的 SQLite 文件：

- `compkey_p4.sqlite3`
- `compkey_demo.sqlite3`
- `compkey_aol_demo.sqlite3`
- `compkey_trend_demo.sqlite3`

这些文件让你无需重新构建即可直接演示。

如果你要重建增量数据或更新数据库，可以参考下面的流程。

## 重新生成增量与更新数据库

### 1）生成增量中间文件

```powershell
python pipeline/ingest_incremental.py --tokenized <你的tokenized_csv路径> --outdir data/incremental
```

### 2）写入 SQLite 并重算结果

```powershell
python pipeline/update_db_from_incremental.py --db .\compkey_p4.sqlite3 --inc .\data\incremental --config .\config\competition_params.yaml
```

如果你使用的是演示数据源，建议先复制一份数据库再更新，避免覆盖原库。

## 公开日志演示入口

仓库里保留了两个公开日志示例流程，方便做扩展演示：

### AOL demo

AOL 更接近经典搜索引擎 query log。当前仓库里的 AOL demo 已通过会话窗口共现重建了 `competition_result`，因此不仅能看热词和趋势，也可以直接用于种子词推荐。

```powershell
python pipeline/build_aol_snapshot.py --input https://www.cim.mcgill.ca/~dudek/206/Logs/AOL-user-ct-collection/user-ct-test-collection-01.txt --outdir data/source_logs/aol
python pipeline/ingest_incremental.py --tokenized data/source_logs/aol/normalized/tokenized_queries.csv --outdir data/source_logs/aol/merged
python pipeline/update_db_from_incremental.py --db .\compkey_aol_demo.sqlite3 --inc .\data\source_logs\aol\merged --config .\config\competition_params.yaml
```

如果你是基于仓库内置的 `data/source_logs/aol` 目录重新生成，`build_aol_snapshot.py` 会自动输出 `normalized/seed_cooccur.csv`，`ingest_incremental.py` 也会优先读取它，从而把 AOL 的候选词真正写入数据库。

### AOL demo — 适合 / 不适合

适合看什么：AOL demo 很适合用于教学与演示场景，尤其是展示基于“会话窗口”的共现如何产生候选词、观察短查询（多为 1–2 词）之间的联想路径，以及对阈值参数（如 min_cooccur、min_freq、top_k）敏感性的可视化对比。若你想快速演示 pipeline（快照→tokenize→ingest→更新数据库）或做算法参数敏感性测试，AOL 是轻量且直观的选择。

不适合看什么：AOL 并不代表生产级、当代的搜索流量——样本有限、采样与时间窗口有偏、数据已做匿名化/清洗处理，因此不适合用于商业决策、完整行业竞争分析或跨语言/跨地域的泛化结论。AOL 以英语短查询为主，长尾/多词查询场景、复杂意图识别以及实时流量分析在此示例上效果有限。使用示例数据时请注意数据隐私与伦理限制。

### EDGAR demo

EDGAR 更适合做“公开访问/检索日志”风格的兼容实验。

```powershell
python pipeline/build_edgar_snapshot.py --input https://www.sec.gov/dera/data/Public-EDGAR-log-file-data/2025/Qtr2/log20250630.zip --outdir data/source_logs/edgar
python pipeline/ingest_incremental.py --tokenized data/source_logs/edgar/normalized/tokenized_queries.csv --outdir data/source_logs/edgar/merged
python pipeline/update_db_from_incremental.py --db .\compkey_edgar_demo.sqlite3 --inc .\data\source_logs\edgar\merged --config .\config\competition_params.yaml
```

## 常见问题

### 1）`ModuleNotFoundError` 或依赖找不到

先确认虚拟环境已经激活，再执行：

```powershell
python -m pip install -r requirements.txt
```

### 2）前端页面能打开，但没有数据

通常是后端没启动、端口不对，或者浏览器的跨域请求被拦截。请确认：

- 后端运行在 `http://127.0.0.1:8000`
- 前端通过 `http.server` 打开在 `http://127.0.0.1:8001`

### 3）查询结果为空

可能是：

- 种子词不在数据库里
- 当前数据源不对
- `min_freq` / `min_cooccur` 阈值较高

可以尝试更常见的词，或者在 `config/competition_params.yaml` 中调低阈值。

### 4）想换数据库但不想改代码

直接改 `config/competition_params.yaml`，或者用 `COMPKY_CONFIG` 指向新的 YAML 文件即可。

## 开发与测试

如需跑测试：

```powershell
python -m pytest
```

如果只想检查后端接口相关用例，也可以针对某个测试文件执行。

## 想提交到 GitHub

如果仓库已经配置了远端 `origin`，你只需要在根目录执行：

```powershell
git add README.md README_RUN.md
git commit -m "docs: add detailed startup guide"
git push origin main
```

如果你当前分支不是 `main`，把最后一行的分支名改成实际分支即可。

## 说明

本项目的目标是让“关键词竞争分析”这套流程能被快速复现、快速演示、快速扩展。你现在看到的这份 README，优先面向“别人第一次打开仓库就能跑起来”的场景。