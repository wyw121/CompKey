from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    p1_output_dir: Path
    seed_csv: Path
    db_path: Path
    report_dir: Path
    default_top_n: int = 10
    candidate_limit: int = 50


def get_settings() -> Settings:
    p3_dir = ROOT_DIR / "deliverables" / "P3"
    return Settings(
        root_dir=ROOT_DIR,
        p1_output_dir=ROOT_DIR / "deliverables" / "P1" / "run_train_v2_full",
        seed_csv=ROOT_DIR / "deliverables" / "P1" / "seed_keywords_v1.csv",
        db_path=p3_dir / "compkey_stage3.sqlite3",
        report_dir=p3_dir / "reports",
    )
