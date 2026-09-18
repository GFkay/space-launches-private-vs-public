"""
Enrichment targets — which launcher families are worth researching
======================================================================

Step 4a of the data pipeline (preparation, not enrichment itself):
- Reads data/interim/02_clean.csv
- Counts launches per launcher_family
- Writes data/external/enrichment_targets.csv listing families sorted by
  launch count, with empty columns ready to be filled in manually:
  cost_per_launch_usd, cost_source_url, notes

Rationale: with ~100+ distinct launcher families in the raw data, manually
researching cost data for all of them isn't a good use of time (see the
course's "collecting is sampling" principle — quality over exhaustiveness).
This script tells you which ~15-20 families cover the large majority of
launches, so research effort goes where it matters.

Usage:
    python 04_part_A_list_enrichment_targets.py
    python 04_part_A_list_enrichment_targets.py --top 25   # change how many families to list

Dependencies: pandas
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
EXTERNAL_DIR = PROJECT_ROOT / "data" / "external"


def main() -> None:
    parser = argparse.ArgumentParser(description="List top launcher families to research for enrichment")
    parser.add_argument("--top", type=int, default=20, help="How many top families to list (default 20)")
    args = parser.parse_args()

    input_path = INTERIM_DIR / "02_clean.csv"
    if not input_path.exists():
        raise FileNotFoundError(f"{input_path} not found — run 03_clean.py first.")

    df = pd.read_csv(input_path)
    logger.info("Loaded %s resolved launches", len(df))

    n_missing_family = df["launcher_family"].isna().sum()
    if n_missing_family:
        logger.warning("%s launches have no launcher_family value — excluded from this ranking.", n_missing_family)

    counts = df["launcher_family"].value_counts()
    top_families = counts.head(args.top)
    coverage_pct = 100 * top_families.sum() / len(df)

    logger.info(
        "Top %s families cover %s / %s launches (%.1f%%)",
        args.top, top_families.sum(), len(df), coverage_pct,
    )
    for family, count in top_families.items():
        logger.info("  %-25s %5s launches", family, count)

    targets_df = pd.DataFrame({
        "launcher_family": top_families.index,
        "launch_count": top_families.values,
        "cost_per_launch_usd": "",     # to fill in manually, with a source
        "cost_source_url": "",
        "notes": "",
    })

    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EXTERNAL_DIR / "enrichment_targets.csv"
    targets_df.to_csv(output_path, index=False, encoding="utf-8")
    logger.info("Wrote research template to %s — fill in the empty columns.", output_path)


if __name__ == "__main__":
    main()