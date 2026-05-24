from __future__ import annotations

from collections import OrderedDict
from dataclasses import asdict
from typing import Dict, List, Optional

from .models import CompetitionResultRecord, UserFeedbackRecord
from .repository import CompKeyRepository


class RecommendationCache:
    def __init__(self, max_size: int = 128):
        self.max_size = max_size
        self._store: OrderedDict[str, List[CompetitionResultRecord]] = OrderedDict()

    def get(self, key: str) -> Optional[List[CompetitionResultRecord]]:
        if key not in self._store:
            return None
        value = self._store.pop(key)
        self._store[key] = value
        return value

    def set(self, key: str, value: List[CompetitionResultRecord]) -> None:
        if key in self._store:
            self._store.pop(key)
        self._store[key] = value
        while len(self._store) > self.max_size:
            self._store.popitem(last=False)


class RecommendationService:
    def __init__(self, repository: CompKeyRepository, cache_size: int = 128):
        self.repository = repository
        self.cache = RecommendationCache(cache_size)

    def recommend(self, seed_keyword: str, top_n: int = 10, use_cache: bool = True) -> List[CompetitionResultRecord]:
        seed_keyword = (seed_keyword or "").strip()
        if not seed_keyword:
            return []

        if use_cache:
            cached = self.cache.get(seed_keyword)
            if cached is not None:
                return cached[:top_n]

        rows = self.repository.fetch_results_for_seed(seed_keyword, top_n)
        results = [
            CompetitionResultRecord(
                seed_keyword=row["seed_keyword"],
                candidate_keyword=row["candidate_keyword"],
                competition_score=float(row["competition_score"]),
                rank_no=int(row["rank_no"]),
                evidence_source=row["evidence_source"],
            )
            for row in rows
        ]
        self.cache.set(seed_keyword, results)
        return results

    def update_feedback(self, feedback: UserFeedbackRecord) -> None:
        self.repository.insert_feedback(feedback)

    def recommend_as_dicts(self, seed_keyword: str, top_n: int = 10) -> List[Dict[str, object]]:
        return [asdict(r) for r in self.recommend(seed_keyword, top_n=top_n)]
