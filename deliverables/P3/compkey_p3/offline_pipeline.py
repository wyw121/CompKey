from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .models import CompetitionResultRecord, KeywordRecord, MediatorKeywordRecord, SearchLogRecord
from .repository import CompKeyRepository


STOPWORDS = {
    "的",
    "了",
    "吗",
    "怎么",
    "什么",
    "和",
    "是",
    "有",
    "可以",
    "能",
    "用",
    "好",
    "哪个",
    "多少",
    "呢",
    "在",
    "与",
    "也",
    "很",
}


def _pick_csv_encoding(path: Path, preferred: Sequence[str] = ("utf-8-sig", "gb18030", "utf-8")) -> str:
    for encoding in preferred:
        try:
            with open(path, "r", encoding=encoding, errors="strict", newline="") as f:
                sample = f.read(4096)
            if "\ufffd" in sample:
                continue
            return encoding
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    return preferred[0]


def load_seed_keywords(seed_csv: Path) -> List[KeywordRecord]:
    rows: List[KeywordRecord] = []
    encoding = _pick_csv_encoding(seed_csv)
    with open(seed_csv, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keyword = (row.get("keyword") or "").strip()
            if not keyword:
                continue
            rows.append(
                KeywordRecord(
                    keyword=keyword,
                    domain=(row.get("domain") or "").strip() or None,
                    description=(row.get("reason") or row.get("description") or "").strip() or None,
                    source="seed_keywords_v1.csv",
                )
            )
    return rows


def load_global_frequency(word_freq_csv: Path) -> Counter:
    freq = Counter()
    encoding = _pick_csv_encoding(word_freq_csv)
    with open(word_freq_csv, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            token = (row.get("token") or "").strip()
            if not token:
                continue
            try:
                count = int(float(row.get("freq") or 0))
            except ValueError:
                count = 0
            freq[token] = count
    return freq


def _query_key(user_id: str, query: str) -> Tuple[str, str]:
    return user_id.strip(), query.strip()


@dataclass
class OfflineBuildSummary:
    seed_count: int
    mediator_count: int
    competition_count: int
    search_log_count: int


def build_offline_assets(
    repo: CompKeyRepository,
    seed_csv: Path,
    tokenized_csv: Path,
    word_freq_csv: Path,
    seed_related_csv: Optional[Path] = None,
    candidate_limit: int = 50,
) -> OfflineBuildSummary:
    seeds = load_seed_keywords(seed_csv)
    seed_names = {row.keyword for row in seeds}
    global_freq = load_global_frequency(word_freq_csv)

    keyword_map: Dict[str, KeywordRecord] = {row.keyword: row for row in seeds}

    token_support: Dict[Tuple[str, str], int] = Counter()
    token_query_sets: Dict[Tuple[str, str], set] = defaultdict(set)
    seed_total_tokens: Counter = Counter()
    seed_query_tokens: Dict[str, Counter] = defaultdict(Counter)

    query_token_count: Dict[Tuple[str, str, str], int] = Counter()

    tokenized_encoding = _pick_csv_encoding(tokenized_csv)
    with open(tokenized_csv, "r", encoding=tokenized_encoding, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            seed = (row.get("matched_seed") or "").strip()
            token = (row.get("token") or "").strip()
            user_id = (row.get("user_id") or "").strip()
            query = (row.get("query") or "").strip()
            if not seed or not token or seed not in seed_names:
                continue
            if token in STOPWORDS or token == seed:
                continue
            token_support[(seed, token)] += 1
            token_query_sets[(seed, token)].add(_query_key(user_id, query))
            seed_total_tokens[seed] += 1
            seed_query_tokens[seed][token] += 1
            query_token_count[(user_id, query, seed)] += 1

    mediator_rows: List[MediatorKeywordRecord] = []
    competition_rows: List[CompetitionResultRecord] = []

    for seed in sorted(seed_names):
        items = []
        total_tokens = max(seed_total_tokens.get(seed, 0), 1)
        for token, support_count in seed_query_tokens.get(seed, {}).items():
            if token in STOPWORDS or token == seed:
                continue
            if token not in keyword_map:
                keyword_map[token] = KeywordRecord(keyword=token, source="derived_from_p1")
            query_count = len(token_query_sets[(seed, token)]) or support_count
            global_frequency = int(global_freq.get(token, support_count))
            local_share = support_count / total_tokens
            rarity = 1.0 / (1.0 + math.log1p(max(global_frequency, 1)))
            weight = round(local_share * rarity, 6)
            items.append(
                (
                    token,
                    support_count,
                    query_count,
                    global_frequency,
                    weight,
                )
            )

        items.sort(key=lambda x: (-x[4], -x[1], x[0]))
        for token, support_count, query_count, global_frequency, weight in items:
            mediator_rows.append(
                MediatorKeywordRecord(
                    seed_keyword=seed,
                    mediator_keyword=token,
                    support_count=support_count,
                    query_count=query_count,
                    global_frequency=global_frequency,
                    weight=weight,
                )
            )

        for rank_no, (token, support_count, query_count, global_frequency, weight) in enumerate(
            items[:candidate_limit], start=1
        ):
            score = round(weight * (1.0 + math.log1p(support_count)) * (1.0 / (1.0 + math.log1p(global_frequency))), 6)
            competition_rows.append(
                CompetitionResultRecord(
                    seed_keyword=seed,
                    candidate_keyword=token,
                    competition_score=score,
                    rank_no=rank_no,
                    evidence_source="offline_token_frequency",
                )
            )

    search_logs: List[SearchLogRecord] = []
    if seed_related_csv and seed_related_csv.exists():
        seen = set()
        seed_related_encoding = _pick_csv_encoding(seed_related_csv)
        with open(seed_related_csv, "r", encoding=seed_related_encoding, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                query = (row.get("query") or "").strip()
                seed = (row.get("matched_seed") or "").strip()
                user_id = (row.get("user_id") or "").strip()
                if not query or not seed:
                    continue
                key = (user_id, query, seed)
                if key in seen:
                    continue
                seen.add(key)
                token_count = int(query_token_count.get(key, 0))
                search_logs.append(
                    SearchLogRecord(
                        query_text=query,
                        matched_seed=seed,
                        token_count=token_count,
                        source_file=seed_related_csv.name,
                    )
                )

    repo.upsert_keywords(list(keyword_map.values()))
    repo.upsert_mediators(mediator_rows)
    repo.upsert_competition_results(competition_rows)
    if search_logs:
        repo.insert_search_logs(search_logs)

    return OfflineBuildSummary(
        seed_count=len(seeds),
        mediator_count=len(mediator_rows),
        competition_count=len(competition_rows),
        search_log_count=len(search_logs),
    )
