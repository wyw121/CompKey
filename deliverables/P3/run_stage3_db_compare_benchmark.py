from __future__ import annotations

import csv
import math
import random
import shutil
import sqlite3
import statistics
import sys
import tempfile
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pymysql
from pymysql.cursors import DictCursor

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from compkey_p3.config import get_settings
from compkey_p3.database import DatabaseManager


@dataclass(frozen=True)
class SourceSnapshot:
    keywords: list[tuple[Any, ...]]
    mediators: list[tuple[Any, ...]]
    competition_results: list[tuple[Any, ...]]
    search_logs: list[tuple[Any, ...]]
    user_feedback: list[tuple[Any, ...]]


def _ms(seconds: float) -> float:
    return seconds * 1000.0


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    vals = sorted(values)
    if len(vals) == 1:
        return vals[0]
    idx = (len(vals) - 1) * pct
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return vals[int(idx)]
    return vals[lo] * (hi - idx) + vals[hi] * (idx - lo)


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA busy_timeout = 5000;")
    return conn


def _connect_mysql(db_name: str | None = None):
    return pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password="",
        database=db_name,
        charset="utf8mb4",
        autocommit=False,
        cursorclass=DictCursor,
    )


def _load_source_snapshot(source_db_path: Path) -> SourceSnapshot:
    with _connect_sqlite(source_db_path) as conn:
        keyword_rows = conn.execute(
            "SELECT keyword, domain, description, source, created_at FROM keyword ORDER BY id"
        ).fetchall()
        mediator_rows = conn.execute(
            """
            SELECT seed_keyword, mediator_keyword, support_count, query_count, global_frequency, weight, created_at
            FROM intermediary_keyword
            ORDER BY id
            """
        ).fetchall()
        competition_rows = conn.execute(
            """
            SELECT seed_keyword, candidate_keyword, competition_score, rank_no, evidence_source, computed_at
            FROM competition_result
            ORDER BY id
            """
        ).fetchall()
        search_log_rows = conn.execute(
            """
            SELECT query_text, matched_seed, token_count, query_time, latency_ms, source_file, created_at
            FROM search_log
            ORDER BY id
            """
        ).fetchall()
        feedback_rows = conn.execute(
            """
            SELECT seed_keyword, candidate_keyword, feedback_score, confidence, note, created_at
            FROM user_feedback
            ORDER BY id
            """
        ).fetchall()

    return SourceSnapshot(
        keywords=[tuple(row) for row in keyword_rows],
        mediators=[tuple(row) for row in mediator_rows],
        competition_results=[tuple(row) for row in competition_rows],
        search_logs=[tuple(row) for row in search_log_rows],
        user_feedback=[tuple(row) for row in feedback_rows],
    )


def _create_mysql_schema(conn) -> None:
    schema_sql = """
    SET FOREIGN_KEY_CHECKS=0;

    DROP TABLE IF EXISTS user_feedback;
    DROP TABLE IF EXISTS search_log;
    DROP TABLE IF EXISTS competition_result;
    DROP TABLE IF EXISTS intermediary_keyword;
    DROP TABLE IF EXISTS keyword;

    CREATE TABLE keyword (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        keyword VARCHAR(255) NOT NULL UNIQUE,
        domain TEXT,
        description TEXT,
        source TEXT,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE intermediary_keyword (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        seed_keyword VARCHAR(255) NOT NULL,
        mediator_keyword VARCHAR(255) NOT NULL,
        support_count INT NOT NULL DEFAULT 0,
        query_count INT NOT NULL DEFAULT 0,
        global_frequency INT NOT NULL DEFAULT 0,
        weight DOUBLE NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_intermediary(seed_keyword, mediator_keyword),
        KEY idx_intermediary_seed(seed_keyword),
        KEY idx_intermediary_weight(seed_keyword, weight DESC),
        CONSTRAINT fk_intermediary_seed FOREIGN KEY(seed_keyword) REFERENCES keyword(keyword) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE competition_result (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        seed_keyword VARCHAR(255) NOT NULL,
        candidate_keyword VARCHAR(255) NOT NULL,
        competition_score DOUBLE NOT NULL DEFAULT 0,
        rank_no INT NOT NULL DEFAULT 0,
        evidence_source TEXT,
        computed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE KEY uq_competition(seed_keyword, candidate_keyword),
        KEY idx_competition_seed(seed_keyword),
        KEY idx_competition_score(seed_keyword, competition_score DESC),
        CONSTRAINT fk_competition_seed FOREIGN KEY(seed_keyword) REFERENCES keyword(keyword) ON DELETE CASCADE,
        CONSTRAINT fk_competition_candidate FOREIGN KEY(candidate_keyword) REFERENCES keyword(keyword) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE search_log (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        query_text TEXT NOT NULL,
        matched_seed VARCHAR(255),
        token_count INT NOT NULL DEFAULT 0,
        query_time TEXT,
        latency_ms DOUBLE,
        source_file TEXT,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_search_log_seed(matched_seed(191)),
        KEY idx_search_log_query(query_text(191))
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    CREATE TABLE user_feedback (
        id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
        seed_keyword VARCHAR(255) NOT NULL,
        candidate_keyword VARCHAR(255) NOT NULL,
        feedback_score INT NOT NULL DEFAULT 0,
        confidence DOUBLE NOT NULL DEFAULT 0,
        note TEXT,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_feedback_seed(seed_keyword),
        KEY idx_feedback_candidate(candidate_keyword),
        CONSTRAINT fk_feedback_seed FOREIGN KEY(seed_keyword) REFERENCES keyword(keyword) ON DELETE CASCADE,
        CONSTRAINT fk_feedback_candidate FOREIGN KEY(candidate_keyword) REFERENCES keyword(keyword) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

    SET FOREIGN_KEY_CHECKS=1;
    """
    with conn.cursor() as cursor:
        for statement in [s.strip() for s in schema_sql.split(";") if s.strip()]:
            cursor.execute(statement)
    conn.commit()


def _import_sqlite_snapshot(conn: sqlite3.Connection, snapshot: SourceSnapshot) -> float:
    start = time.perf_counter()
    conn.execute("BEGIN")
    conn.executemany(
        "INSERT INTO keyword(keyword, domain, description, source, created_at) VALUES (?, ?, ?, ?, ?)",
        snapshot.keywords,
    )
    conn.executemany(
        """
        INSERT INTO intermediary_keyword(
            seed_keyword, mediator_keyword, support_count, query_count, global_frequency, weight, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        snapshot.mediators,
    )
    conn.executemany(
        """
        INSERT INTO competition_result(
            seed_keyword, candidate_keyword, competition_score, rank_no, evidence_source, computed_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        snapshot.competition_results,
    )
    conn.executemany(
        """
        INSERT INTO search_log(query_text, matched_seed, token_count, query_time, latency_ms, source_file, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        snapshot.search_logs,
    )
    if snapshot.user_feedback:
        conn.executemany(
            """
            INSERT INTO user_feedback(seed_keyword, candidate_keyword, feedback_score, confidence, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            snapshot.user_feedback,
        )
    conn.commit()
    return _ms(time.perf_counter() - start)


def _import_mysql_snapshot(conn, snapshot: SourceSnapshot) -> float:
    start = time.perf_counter()
    with conn.cursor() as cursor:
        cursor.executemany(
            "INSERT INTO keyword(keyword, domain, description, source, created_at) VALUES (%s, %s, %s, %s, %s)",
            snapshot.keywords,
        )
        cursor.executemany(
            """
            INSERT INTO intermediary_keyword(
                seed_keyword, mediator_keyword, support_count, query_count, global_frequency, weight, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            snapshot.mediators,
        )
        cursor.executemany(
            """
            INSERT INTO competition_result(
                seed_keyword, candidate_keyword, competition_score, rank_no, evidence_source, computed_at
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            snapshot.competition_results,
        )
        cursor.executemany(
            """
            INSERT INTO search_log(query_text, matched_seed, token_count, query_time, latency_ms, source_file, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            snapshot.search_logs,
        )
        if snapshot.user_feedback:
            cursor.executemany(
                """
                INSERT INTO user_feedback(seed_keyword, candidate_keyword, feedback_score, confidence, note, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                snapshot.user_feedback,
            )
    conn.commit()
    return _ms(time.perf_counter() - start)


def _fetch_seeds_sqlite(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute("SELECT DISTINCT seed_keyword FROM competition_result ORDER BY seed_keyword").fetchall()
    return [row[0] for row in rows]


def _fetch_seeds_mysql(conn) -> list[str]:
    with conn.cursor() as cursor:
        cursor.execute("SELECT DISTINCT seed_keyword FROM competition_result ORDER BY seed_keyword")
        return [row["seed_keyword"] for row in cursor.fetchall()]


def _fetch_search_rows_sqlite(conn: sqlite3.Connection) -> list[tuple[Any, ...]]:
    rows = conn.execute(
        "SELECT query_text, matched_seed, token_count, query_time, latency_ms, source_file, created_at FROM search_log ORDER BY id"
    ).fetchall()
    return [tuple(row) for row in rows]


def _fetch_search_rows_mysql(conn) -> list[tuple[Any, ...]]:
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT query_text, matched_seed, token_count, query_time, latency_ms, source_file, created_at FROM search_log ORDER BY id"
        )
        return [tuple(row.values()) for row in cursor.fetchall()]


def _read_query_sqlite(conn: sqlite3.Connection, seed: str, top_n: int = 10):
    return conn.execute(
        """
        SELECT seed_keyword, candidate_keyword, competition_score, rank_no, evidence_source, computed_at
        FROM competition_result
        WHERE seed_keyword = ?
        ORDER BY competition_score DESC, rank_no ASC
        LIMIT ?
        """,
        (seed, top_n),
    ).fetchall()


def _read_query_mysql(conn, seed: str, top_n: int = 10):
    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT seed_keyword, candidate_keyword, competition_score, rank_no, evidence_source, computed_at
            FROM competition_result
            WHERE seed_keyword = %s
            ORDER BY competition_score DESC, rank_no ASC
            LIMIT %s
            """,
            (seed, top_n),
        )
        return cursor.fetchall()


def _run_read_workload(conn_factory, seeds: list[str], total_ops: int = 800, workers: int = 4):
    ops_per_worker = max(total_ops // workers, 1)
    latencies: list[float] = []
    errors = 0
    wall_start = time.perf_counter()

    def worker(worker_id: int):
        local_latencies: list[float] = []
        local_errors = 0
        rng = random.Random(2026 + worker_id)
        conn = conn_factory()
        try:
            for _ in range(ops_per_worker):
                seed = rng.choice(seeds)
                start = time.perf_counter()
                try:
                    _ = _read_query(conn, seed)
                    local_latencies.append(_ms(time.perf_counter() - start))
                except Exception:
                    local_errors += 1
        finally:
            conn.close()
        return local_latencies, local_errors

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for worker_latencies, worker_errors in pool.map(worker, range(workers)):
            latencies.extend(worker_latencies)
            errors += worker_errors

    wall_elapsed = time.perf_counter() - wall_start

    return {
        "ops": len(latencies),
        "avg_ms": statistics.mean(latencies) if latencies else 0.0,
        "p95_ms": _percentile(latencies, 0.95),
        "qps": (len(latencies) / wall_elapsed) if wall_elapsed else 0.0,
        "errors": errors,
    }


def _read_query(conn, seed: str):
    if isinstance(conn, sqlite3.Connection):
        return _read_query_sqlite(conn, seed)
    return _read_query_mysql(conn, seed)


def _insert_search_log(conn, rows: list[tuple[Any, ...]]):
    if isinstance(conn, sqlite3.Connection):
        conn.executemany(
            """
            INSERT INTO search_log(query_text, matched_seed, token_count, query_time, latency_ms, source_file, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    else:
        with conn.cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO search_log(query_text, matched_seed, token_count, query_time, latency_ms, source_file, created_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )


def _run_write_workload(conn_factory, search_rows: list[tuple[Any, ...]], workers: int = 2, batches_per_worker: int = 30, batch_size: int = 20):
    pool_rows = deque(search_rows)
    latencies: list[float] = []
    errors = 0
    lock = threading.Lock()
    wall_start = time.perf_counter()

    def next_batch() -> list[tuple[Any, ...]]:
        with lock:
            batch: list[tuple[Any, ...]] = []
            for _ in range(batch_size):
                if not pool_rows:
                    pool_rows.extend(search_rows)
                batch.append(pool_rows.popleft())
            return batch

    def worker(worker_id: int):
        local_latencies: list[float] = []
        local_errors = 0
        conn = conn_factory()
        try:
            for _ in range(batches_per_worker):
                batch = next_batch()
                start = time.perf_counter()
                try:
                    _insert_search_log(conn, batch)
                    conn.commit()
                    local_latencies.append(_ms(time.perf_counter() - start))
                except Exception:
                    local_errors += 1
                    try:
                        conn.rollback()
                    except Exception:
                        pass
        finally:
            conn.close()
        return local_latencies, local_errors

    with ThreadPoolExecutor(max_workers=workers) as pool:
        for worker_latencies, worker_errors in pool.map(worker, range(workers)):
            latencies.extend(worker_latencies)
            errors += worker_errors

    rows_written = len(latencies) * batch_size
    total_sec = time.perf_counter() - wall_start
    return {
        "batches": len(latencies),
        "rows": rows_written,
        "avg_batch_ms": statistics.mean(latencies) if latencies else 0.0,
        "p95_batch_ms": _percentile(latencies, 0.95),
        "rows_per_sec": (rows_written / total_sec) if total_sec else 0.0,
        "errors": errors,
    }


def _run_mixed_workload(conn_factory, seeds: list[str], search_rows: list[tuple[Any, ...]], readers: int = 3, writers: int = 2):
    read_latencies: list[float] = []
    write_latencies: list[float] = []
    read_errors = 0
    write_errors = 0

    start_event = threading.Event()

    def reader(worker_id: int):
        nonlocal read_errors
        rng = random.Random(9000 + worker_id)
        conn = conn_factory()
        local_latencies: list[float] = []
        local_errors = 0
        try:
            start_event.wait()
            for _ in range(120):
                seed = rng.choice(seeds)
                start = time.perf_counter()
                try:
                    _ = _read_query(conn, seed)
                    local_latencies.append(_ms(time.perf_counter() - start))
                except Exception:
                    local_errors += 1
        finally:
            conn.close()
        return local_latencies, local_errors

    def writer(worker_id: int):
        nonlocal write_errors
        conn = conn_factory()
        local_latencies: list[float] = []
        local_errors = 0
        base = worker_id * 2000
        try:
            start_event.wait()
            for batch_index in range(25):
                batch = []
                for offset in range(12):
                    src = search_rows[(base + batch_index * 12 + offset) % len(search_rows)]
                    batch.append(src)
                start = time.perf_counter()
                try:
                    _insert_search_log(conn, batch)
                    conn.commit()
                    local_latencies.append(_ms(time.perf_counter() - start))
                except Exception:
                    local_errors += 1
                    try:
                        conn.rollback()
                    except Exception:
                        pass
        finally:
            conn.close()
        return local_latencies, local_errors

    futures = []
    with ThreadPoolExecutor(max_workers=readers + writers) as pool:
        for i in range(readers):
            futures.append(("read", pool.submit(reader, i)))
        for i in range(writers):
            futures.append(("write", pool.submit(writer, i)))
        start_event.set()
        for role, fut in futures:
            latencies, errors = fut.result()
            if role == "read":
                read_latencies.extend(latencies)
                read_errors += errors
            else:
                write_latencies.extend(latencies)
                write_errors += errors

    return {
        "read_ops": len(read_latencies),
        "write_batches": len(write_latencies),
        "read_avg_ms": statistics.mean(read_latencies) if read_latencies else 0.0,
        "read_p95_ms": _percentile(read_latencies, 0.95),
        "write_avg_batch_ms": statistics.mean(write_latencies) if write_latencies else 0.0,
        "write_p95_batch_ms": _percentile(write_latencies, 0.95),
        "read_errors": read_errors,
        "write_errors": write_errors,
    }


def _prepare_sqlite_backend(root: Path, snapshot: SourceSnapshot):
    temp_dir = Path(tempfile.mkdtemp(prefix="compkey_sqlite_bench_"))
    db_path = temp_dir / "sqlite_benchmark.db"
    shutil.copy2(root / "deliverables" / "P3" / "db_schema_v1.sql", temp_dir / "db_schema_v1.sql")
    manager = DatabaseManager(db_path)
    start = time.perf_counter()
    with manager.connect() as conn:
        manager.initialize_schema(conn)
        import_ms = _import_sqlite_snapshot(conn, snapshot)
    init_ms = _ms(time.perf_counter() - start)
    return temp_dir, db_path, init_ms, import_ms


def _prepare_mysql_backend(snapshot: SourceSnapshot, db_name: str):
    admin_conn = _connect_mysql()
    try:
        with admin_conn.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{db_name}`")
            cursor.execute(f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        admin_conn.commit()
    finally:
        admin_conn.close()

    conn = _connect_mysql(db_name)
    start = time.perf_counter()
    _create_mysql_schema(conn)
    init_ms = _ms(time.perf_counter() - start)
    import_ms = _import_mysql_snapshot(conn, snapshot)
    return conn, init_ms, import_ms


def _build_report_rows(name: str, init_ms: float, import_ms: float, read_metrics: dict[str, float], write_metrics: dict[str, float], mixed_metrics: dict[str, float]) -> list[tuple[str, str, float]]:
    return [
        (name, "init_ms", init_ms),
        (name, "import_ms", import_ms),
        (name, "read_avg_ms", read_metrics["avg_ms"]),
        (name, "read_p95_ms", read_metrics["p95_ms"]),
        (name, "read_qps", read_metrics["qps"]),
        (name, "read_errors", float(read_metrics["errors"])),
        (name, "write_avg_batch_ms", write_metrics["avg_batch_ms"]),
        (name, "write_p95_batch_ms", write_metrics["p95_batch_ms"]),
        (name, "write_rows_per_sec", write_metrics["rows_per_sec"]),
        (name, "write_errors", float(write_metrics["errors"])),
        (name, "mixed_read_avg_ms", mixed_metrics["read_avg_ms"]),
        (name, "mixed_read_p95_ms", mixed_metrics["read_p95_ms"]),
        (name, "mixed_write_avg_ms", mixed_metrics["write_avg_batch_ms"]),
        (name, "mixed_write_p95_ms", mixed_metrics["write_p95_batch_ms"]),
        (name, "mixed_read_errors", float(mixed_metrics["read_errors"])),
        (name, "mixed_write_errors", float(mixed_metrics["write_errors"])),
    ]


def main() -> None:
    settings = get_settings()
    settings.report_dir.mkdir(parents=True, exist_ok=True)

    source_db = settings.db_path
    if not source_db.exists():
        raise FileNotFoundError(f"source SQLite DB not found: {source_db}")

    snapshot = _load_source_snapshot(source_db)
    if not snapshot.keywords or not snapshot.competition_results:
        raise ValueError("source DB snapshot is empty; cannot run database benchmark")

    # SQLite benchmark backend
    sqlite_temp_dir, sqlite_db_path, sqlite_init_ms, sqlite_import_ms = _prepare_sqlite_backend(settings.root_dir, snapshot)
    try:
        sqlite_conn = _connect_sqlite(sqlite_db_path)
        sqlite_seeds = _fetch_seeds_sqlite(sqlite_conn)
        sqlite_search_rows = _fetch_search_rows_sqlite(sqlite_conn)
        sqlite_read_metrics = _run_read_workload(lambda: _connect_sqlite(sqlite_db_path), sqlite_seeds)
        sqlite_write_metrics = _run_write_workload(lambda: _connect_sqlite(sqlite_db_path), sqlite_search_rows)
        sqlite_mixed_metrics = _run_mixed_workload(lambda: _connect_sqlite(sqlite_db_path), sqlite_seeds, sqlite_search_rows)
        sqlite_conn.close()
    finally:
        sqlite_temp_dir and shutil.rmtree(sqlite_temp_dir, ignore_errors=True)

    # MySQL benchmark backend
    mysql_db_name = "compkey_p3_benchmark"
    mysql_conn, mysql_init_ms, mysql_import_ms = _prepare_mysql_backend(snapshot, mysql_db_name)
    try:
        mysql_seeds = _fetch_seeds_mysql(mysql_conn)
        mysql_search_rows = _fetch_search_rows_mysql(mysql_conn)
        mysql_read_metrics = _run_read_workload(lambda: _connect_mysql(mysql_db_name), mysql_seeds)
        mysql_write_metrics = _run_write_workload(lambda: _connect_mysql(mysql_db_name), mysql_search_rows)
        mysql_mixed_metrics = _run_mixed_workload(lambda: _connect_mysql(mysql_db_name), mysql_seeds, mysql_search_rows)
    finally:
        try:
            mysql_conn.close()
        except Exception:
            pass

    report_rows = []
    report_rows.extend(_build_report_rows("sqlite", sqlite_init_ms, sqlite_import_ms, sqlite_read_metrics, sqlite_write_metrics, sqlite_mixed_metrics))
    report_rows.extend(_build_report_rows("mysql", mysql_init_ms, mysql_import_ms, mysql_read_metrics, mysql_write_metrics, mysql_mixed_metrics))

    csv_path = settings.report_dir / "p3_db_compare_benchmark.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["backend", "metric", "value"])
        for backend, metric, value in report_rows:
            writer.writerow([backend, metric, f"{value:.6f}"])

    md_path = settings.report_dir / "p3_db_compare_benchmark.md"
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# P3 数据库横向对比（真实运行）\n\n")
        f.write("## 1. 实验设置\n\n")
        f.write(f"- 源数据库：`{source_db.as_posix()}`\n")
        f.write(f"- 备份快照：SQLite 临时库 + MySQL 临时库\n")
        f.write(f"- 样本 seed 数量：{len(set(sqlite_seeds))}\n")
        f.write(f"- search_log 基础样本数：{len(snapshot.search_logs)}\n")
        f.write("- 负载类型：导入、单条查询、批量写入、读写混合并发\n\n")

        f.write("## 2. 汇总结果\n\n")
        f.write("| backend | init_ms | import_ms | read_avg_ms | read_p95_ms | read_qps | write_avg_batch_ms | write_p95_batch_ms | write_rows_per_sec | mixed_read_avg_ms | mixed_write_avg_ms | mixed_read_errors | mixed_write_errors |\n")
        f.write("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n")
        for backend in ("sqlite", "mysql"):
            m = {metric: value for b, metric, value in report_rows if b == backend}
            f.write(
                "| {backend} | {init_ms:.3f} | {import_ms:.3f} | {read_avg_ms:.3f} | {read_p95_ms:.3f} | {read_qps:.2f} | {write_avg_batch_ms:.3f} | {write_p95_batch_ms:.3f} | {write_rows_per_sec:.2f} | {mixed_read_avg_ms:.3f} | {mixed_write_avg_ms:.3f} | {mixed_read_errors:.0f} | {mixed_write_errors:.0f} |\n".format(
                    backend=backend,
                    init_ms=m.get("init_ms", 0.0),
                    import_ms=m.get("import_ms", 0.0),
                    read_avg_ms=m.get("read_avg_ms", 0.0),
                    read_p95_ms=m.get("read_p95_ms", 0.0),
                    read_qps=m.get("read_qps", 0.0),
                    write_avg_batch_ms=m.get("write_avg_batch_ms", 0.0),
                    write_p95_batch_ms=m.get("write_p95_batch_ms", 0.0),
                    write_rows_per_sec=m.get("write_rows_per_sec", 0.0),
                    mixed_read_avg_ms=m.get("mixed_read_avg_ms", 0.0),
                    mixed_write_avg_ms=m.get("mixed_write_avg_ms", 0.0),
                    mixed_read_errors=m.get("mixed_read_errors", 0.0),
                    mixed_write_errors=m.get("mixed_write_errors", 0.0),
                )
            )

        f.write("\n## 3. 解释与结论\n\n")
        sqlite_read = {metric: value for b, metric, value in report_rows if b == "sqlite"}
        mysql_read = {metric: value for b, metric, value in report_rows if b == "mysql"}
        faster_read_backend = "sqlite" if sqlite_read.get("read_avg_ms", 0.0) <= mysql_read.get("read_avg_ms", 0.0) else "mysql"
        better_write_backend = "sqlite" if sqlite_read.get("write_rows_per_sec", 0.0) >= mysql_read.get("write_rows_per_sec", 0.0) else "mysql"
        f.write(f"- 单条查询平均延时更优：`{faster_read_backend}`\n")
        f.write(f"- 批量写入吞吐更优：`{better_write_backend}`\n")
        f.write("- 若 SQLite 在混合并发中出现错误，说明其在写入并发下更容易受锁竞争影响；MySQL 一般更适合多连接并发写入场景。\n")
        f.write("- 由于两种后端使用同一份源数据与同一套 schema，结果可直接用于横向比较。\n")

    # close mysql database and remove temp schema after report has been written
    try:
        try:
            mysql_conn.close()
        except Exception:
            pass
    finally:
        admin_conn = _connect_mysql()
        try:
            with admin_conn.cursor() as cursor:
                cursor.execute(f"DROP DATABASE IF EXISTS `{mysql_db_name}`")
            admin_conn.commit()
        finally:
            admin_conn.close()

    print(f"[OK] db benchmark CSV written: {csv_path}")
    print(f"[OK] db benchmark summary written: {md_path}")


if __name__ == "__main__":
    main()