from __future__ import annotations

import sqlite3
from typing import Iterable, List, Sequence

from .models import (
    CompetitionResultRecord,
    KeywordRecord,
    MediatorKeywordRecord,
    SearchLogRecord,
    UserFeedbackRecord,
)


class CompKeyRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def upsert_keywords(self, rows: Sequence[KeywordRecord]) -> None:
        self.conn.executemany(
            """
            INSERT INTO keyword(keyword, domain, description, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(keyword) DO UPDATE SET
                domain = COALESCE(excluded.domain, keyword.domain),
                description = COALESCE(excluded.description, keyword.description),
                source = COALESCE(excluded.source, keyword.source)
            """,
            [(r.keyword, r.domain, r.description, r.source) for r in rows],
        )

    def upsert_mediators(self, rows: Sequence[MediatorKeywordRecord]) -> None:
        self.conn.executemany(
            """
            INSERT INTO intermediary_keyword(
                seed_keyword, mediator_keyword, support_count, query_count, global_frequency, weight
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(seed_keyword, mediator_keyword) DO UPDATE SET
                support_count = excluded.support_count,
                query_count = excluded.query_count,
                global_frequency = excluded.global_frequency,
                weight = excluded.weight
            """,
            [
                (
                    r.seed_keyword,
                    r.mediator_keyword,
                    r.support_count,
                    r.query_count,
                    r.global_frequency,
                    r.weight,
                )
                for r in rows
            ],
        )

    def upsert_competition_results(self, rows: Sequence[CompetitionResultRecord]) -> None:
        self.conn.executemany(
            """
            INSERT INTO competition_result(
                seed_keyword, candidate_keyword, competition_score, rank_no, evidence_source
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(seed_keyword, candidate_keyword) DO UPDATE SET
                competition_score = excluded.competition_score,
                rank_no = excluded.rank_no,
                evidence_source = excluded.evidence_source,
                computed_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    r.seed_keyword,
                    r.candidate_keyword,
                    r.competition_score,
                    r.rank_no,
                    r.evidence_source,
                )
                for r in rows
            ],
        )

    def insert_search_logs(self, rows: Sequence[SearchLogRecord]) -> None:
        self.conn.executemany(
            """
            INSERT INTO search_log(query_text, matched_seed, token_count, query_time, latency_ms, source_file)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    r.query_text,
                    r.matched_seed,
                    r.token_count,
                    r.query_time,
                    r.latency_ms,
                    r.source_file,
                )
                for r in rows
            ],
        )

    def insert_feedback(self, row: UserFeedbackRecord) -> None:
        self.conn.execute(
            """
            INSERT INTO user_feedback(seed_keyword, candidate_keyword, feedback_score, confidence, note)
            VALUES (?, ?, ?, ?, ?)
            """,
            (row.seed_keyword, row.candidate_keyword, row.feedback_score, row.confidence, row.note),
        )

    def fetch_results_for_seed(self, seed_keyword: str, limit: int = 10) -> List[sqlite3.Row]:
        cursor = self.conn.execute(
            """
            SELECT seed_keyword, candidate_keyword, competition_score, rank_no, evidence_source, computed_at
            FROM competition_result
            WHERE seed_keyword = ?
            ORDER BY competition_score DESC, rank_no ASC
            LIMIT ?
            """,
            (seed_keyword, limit),
        )
        return list(cursor.fetchall())

    def count_table_rows(self, table_name: str) -> int:
        cursor = self.conn.execute(f"SELECT COUNT(*) AS n FROM {table_name}")
        return int(cursor.fetchone()["n"])
