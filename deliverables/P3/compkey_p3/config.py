from __future__ import annotations

import os
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
    p1_output_dir = Path(os.getenv("COMPKEY_P1_OUTPUT_DIR", str(ROOT_DIR / "deliverables" / "P1" / "run_train_v2_full")))
    seed_csv = Path(os.getenv("COMPKEY_SEED_CSV", str(ROOT_DIR / "deliverables" / "P1" / "seed_keywords_v1.csv")))
    db_path = Path(os.getenv("COMPKEY_DB_PATH", str(p3_dir / "compkey_stage3.sqlite3")))
    report_dir = Path(os.getenv("COMPKEY_REPORT_DIR", str(p3_dir / "reports")))
    return Settings(
        root_dir=ROOT_DIR,
        p1_output_dir=p1_output_dir,
        seed_csv=seed_csv,
        db_path=db_path,
        report_dir=report_dir,
    )
