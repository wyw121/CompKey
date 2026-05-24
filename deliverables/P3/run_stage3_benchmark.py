from __future__ import annotations

import csv
import statistics
import sys
import time
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from compkey_p3.config import get_settings
from compkey_p3.database import DatabaseManager
from compkey_p3.offline_pipeline import build_offline_assets, load_seed_keywords
from compkey_p3.repository import CompKeyRepository
from compkey_p3.service import RecommendationService


def _ms(value: float) -> float:
    return value * 1000.0


def benchmark_service(service: RecommendationService, seeds: list[str], rounds: int = 5, use_cache: bool = False) -> list[float]:
    timings: list[float] = []
    for _ in range(rounds):
        for seed in seeds:
            start = time.perf_counter()
            _ = service.recommend(seed, top_n=10, use_cache=use_cache)
            timings.append(_ms(time.perf_counter() - start))
    return timings


def main() -> None:
    settings = get_settings()
    settings.report_dir.mkdir(parents=True, exist_ok=True)
    if settings.db_path.exists():
        settings.db_path.unlink()

    seeds = [row.keyword for row in load_seed_keywords(settings.seed_csv)]
    sample_seeds = seeds[: min(8, len(seeds))]

    db = DatabaseManager(settings.db_path)
    start_total = time.perf_counter()
    with db.connect() as conn:
        init_start = time.perf_counter()
        db.initialize_schema(conn)
        init_ms = _ms(time.perf_counter() - init_start)

        repo = CompKeyRepository(conn)

        build_start = time.perf_counter()
        summary = build_offline_assets(
            repo,
            seed_csv=settings.seed_csv,
            tokenized_csv=settings.p1_output_dir / "tokenized_queries_v1.csv",
            word_freq_csv=settings.p1_output_dir / "word_freq_v1.csv",
            seed_related_csv=settings.p1_output_dir / "seed_related_queries_v1.csv",
        )
        build_ms = _ms(time.perf_counter() - build_start)

        service = RecommendationService(repo)

        cold_timings = benchmark_service(service, sample_seeds, rounds=2, use_cache=False)
        warm_timings = benchmark_service(service, sample_seeds, rounds=2, use_cache=True)

        query_timings = []
        for seed in sample_seeds:
            q_start = time.perf_counter()
            _ = repo.fetch_results_for_seed(seed, 10)
            query_timings.append(_ms(time.perf_counter() - q_start))

        total_ms = _ms(time.perf_counter() - start_total)

        summary_rows = [
            ("数据库初始化耗时(ms)", init_ms),
            ("离线导入耗时(ms)", build_ms),
            ("seed查询平均耗时(ms)", statistics.mean(query_timings) if query_timings else 0.0),
            ("seed查询中位数耗时(ms)", statistics.median(query_timings) if query_timings else 0.0),
            ("推荐冷启动平均耗时(ms)", statistics.mean(cold_timings) if cold_timings else 0.0),
            ("推荐缓存命中平均耗时(ms)", statistics.mean(warm_timings) if warm_timings else 0.0),
            ("端到端总耗时(ms)", total_ms),
        ]

        csv_path = settings.report_dir / "p3_performance_benchmark.csv"
        with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["metric", "value_ms"])
            for metric, value in summary_rows:
                writer.writerow([metric, f"{value:.3f}"])

        md_path = settings.report_dir / "p3_performance_summary.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# 第三阶段性能评估摘要\n\n")
            f.write("## 1. 评估口径\n\n")
            f.write(f"- 样本 seed 数量：{len(sample_seeds)}\n")
            f.write(f"- 采用数据源：P1 预处理结果与种子词表\n")
            f.write(f"- 数据库：SQLite\n")
            f.write("- 推荐模式：冷查询 / 缓存命中双模式\n\n")
            f.write("## 2. 指标结果\n\n")
            f.write("| 指标 | 数值(ms) |\n|---|---:|\n")
            for metric, value in summary_rows:
                f.write(f"| {metric} | {value:.3f} |\n")
            f.write("\n## 3. 当前版本的优化建议\n\n")
            f.write("1. seed_keyword 与 candidate_keyword 已建立索引，查询路径更稳定。\n")
            f.write("2. 在线查询应优先使用缓存，避免重复排序。\n")
            f.write("3. 离线导入使用批量写入，减少事务开销。\n")
            f.write("4. 后续若并发增大，可将 SQLite 升级为 MySQL/PostgreSQL。\n")

    print(f"[OK] summary rows written to {settings.report_dir}")
    print(f"[OK] offline summary: {summary}")


if __name__ == "__main__":
    main()
