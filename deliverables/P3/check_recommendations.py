from compkey_p3.config import get_settings
from compkey_p3.database import DatabaseManager
from compkey_p3.repository import CompKeyRepository
from compkey_p3.service import RecommendationService
from compkey_p3.offline_pipeline import load_seed_keywords


def main():
    settings = get_settings()
    with DatabaseManager(settings.db_path).connect() as conn:
        repo = CompKeyRepository(conn)
        service = RecommendationService(repo)
        seeds = [s.keyword for s in load_seed_keywords(settings.seed_csv)]
        sample = seeds[:3]
        print("sample seeds:", sample)
        for seed in sample:
            res = service.recommend_as_dicts(seed, top_n=5)
            print(f"\nseed: {seed}")
            if not res:
                print("  (no candidates)")
            for r in res:
                print(" ", r)


if __name__ == "__main__":
    main()
