import argparse

from compkey_p3.config import get_settings
from compkey_p3.database import DatabaseManager
from compkey_p3.offline_pipeline import load_seed_keywords
from compkey_p3.repository import CompKeyRepository
from compkey_p3.service import RecommendationService


def _print_results(seed: str, res: list[dict], top_n: int) -> None:
    print(f"\nseed: {seed}")
    if not res:
        print("  (no candidates)")
        return
    for r in res[:top_n]:
        print(" ", r)


def main():
    parser = argparse.ArgumentParser(description="CompKey 终端交互版推荐查询")
    parser.add_argument("--seed", type=str, default="", help="直接查询一个 seed 关键词；不传则进入交互模式")
    parser.add_argument("--top-n", type=int, default=5, help="返回前 N 个推荐结果")
    args = parser.parse_args()

    settings = get_settings()
    with DatabaseManager(settings.db_path).connect() as conn:
        repo = CompKeyRepository(conn)
        service = RecommendationService(repo)
        seeds = [s.keyword for s in load_seed_keywords(settings.seed_csv)]

        if args.seed.strip():
            seed = args.seed.strip()
            res = service.recommend_as_dicts(seed, top_n=args.top_n)
            _print_results(seed, res, args.top_n)
            return

        print("=== CompKey 终端交互版 ===")
        print(f"已加载种子词 {len(seeds)} 个。输入关键词后回车即可查询；直接回车或输入 exit 退出。")
        print(f"示例种子：{', '.join(seeds[:5])}")

        while True:
            seed = input("\n请输入关键词: ").strip()
            if not seed or seed.lower() in {"exit", "quit", "q"}:
                print("已退出。")
                break

            res = service.recommend_as_dicts(seed, top_n=args.top_n)
            if seed not in seeds:
                print("[提示] 这个词不一定是系统里已有的 seed，但仍会尝试查询。")
            _print_results(seed, res, args.top_n)


if __name__ == "__main__":
    main()
