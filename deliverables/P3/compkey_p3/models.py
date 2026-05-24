from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class KeywordRecord:
    keyword: str
    domain: Optional[str] = None
    description: Optional[str] = None
    source: Optional[str] = None


@dataclass
class MediatorKeywordRecord:
    seed_keyword: str
    mediator_keyword: str
    support_count: int
    query_count: int
    global_frequency: int
    weight: float


@dataclass
class CompetitionResultRecord:
    seed_keyword: str
    candidate_keyword: str
    competition_score: float
    rank_no: int
    evidence_source: Optional[str] = None


@dataclass
class SearchLogRecord:
    query_text: str
    matched_seed: Optional[str]
    token_count: int = 0
    query_time: Optional[str] = None
    latency_ms: Optional[float] = None
    source_file: Optional[str] = None


@dataclass
class UserFeedbackRecord:
    seed_keyword: str
    candidate_keyword: str
    feedback_score: int
    confidence: float = 0.0
    note: Optional[str] = None
