from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterator


class DatabaseManager:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("PRAGMA journal_mode = WAL;")
        return conn

    def initialize_schema(self, conn: sqlite3.Connection) -> None:
        schema_path = self.db_path.parent / "db_schema_v1.sql"
        if not schema_path.exists():
            schema_path = Path(__file__).resolve().parents[1] / "db_schema_v1.sql"
        schema_sql = schema_path.read_text(encoding="utf-8")
        conn.executescript(schema_sql)
        conn.commit()

    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
