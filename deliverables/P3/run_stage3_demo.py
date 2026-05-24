from __future__ import annotations

import json
import sys
from pathlib import Path

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from compkey_p3.config import get_settings
from compkey_p3.database import DatabaseManager
from compkey_p3.offline_pipeline import build_offline_assets
from compkey_p3.repository import CompKeyRepository
from compkey_p3.service import RecommendationService


def main() -> None:
    settings = get_settings()
    if settings.db_path.exists():
        settings.db_path.unlink()
    db = DatabaseManager(settings.db_path)
    with db.connect() as conn:
        db.initialize_schema(conn)
        repo = CompKeyRepository(conn)
        summary = build_offline_assets(
            repo,
            seed_csv=settings.seed_csv,
            tokenized_csv=settings.p1_output_dir / "tokenized_queries_v1.csv",
            word_freq_csv=settings.p1_output_dir / "word_freq_v1.csv",
            seed_related_csv=settings.p1_output_dir / "seed_related_queries_v1.csv",
        )
        service = RecommendationService(repo)
        sample_seed = "口红"
        results = service.recommend(sample_seed, top_n=settings.default_top_n)

    print("=== Stage 3 demo summary ===")
    print(json.dumps(summary.__dict__, ensure_ascii=False, indent=2))
    print(f"\nTop recommendations for {sample_seed}:")
    for item in results:
        print(f"- {item.rank_no}. {item.candidate_keyword}  score={item.competition_score:.6f}")


if __name__ == "__main__":
    main()
