"""
Cleaning script — resolve statuses, remove duplicates, report data quality
==============================================================================

Step 3 of the data pipeline:
- Reads data/interim/01_merged.csv (output of 02_merge_sources.py)
- Parses launch dates and extracts year
- Splits launches into "resolved" (final outcome: Success / Failure / Partial
  Failure) vs "pending" (Go, TBD, Hold, In Flight, To Be Confirmed) using the
  official status_id codes from the Launch Library 2 API — see
  https://ll.thespacedevs.com/2.2.0/config/launchstatus/
- Removes exact duplicate launches (same launch_id)
- Reports missing values per column
- Writes:
    data/interim/02_clean.csv              -> resolved, deduplicated launches
    data/interim/02_excluded_pending.csv   -> pending/ambiguous launches, kept
                                               separately for transparency

This step never modifies data/raw/ or data/interim/01_merged.csv.

Usage:
    python 03_clean.py

Dependencies: pandas
"""

from __future__ import annotations

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

# Official Launch Library 2 status codes (https://ll.thespacedevs.com/2.2.0/config/launchstatus/)
# A launch with one of these status_id values has a final, known outcome.
RESOLVED_STATUS_IDS = {3, 4, 7}  # Launch Successful, Launch Failure, Partial Failure
# These are still pending/uncertain at collection time — not a real outcome yet.
PENDING_STATUS_IDS = {1, 2, 5, 6, 8}  # Go, TBD, Hold, In Flight, To Be Confirmed


def load_merged() -> pd.DataFrame:
    input_path = INTERIM_DIR / "01_merged.csv"
    if not input_path.exists():
        raise FileNotFoundError(f"{input_path} not found — run 02_merge_sources.py first.")
    df = pd.read_csv(input_path)
    logger.info("Loaded %s rows from %s", len(df), input_path.name)
    return df


def report_status_distribution(df: pd.DataFrame) -> None:
    logger.info("Status distribution (status_id : status_name : count):")
    counts = df.groupby(["status_id", "status_name"]).size().sort_values(ascending=False)
    for (status_id, status_name), count in counts.items():
        tag = "resolved" if status_id in RESOLVED_STATUS_IDS else "pending"
        logger.info("  %-4s %-30s %6s  [%s]", int(status_id), status_name, count, tag)

    unknown_ids = {int(x) for x in df["status_id"].dropna().unique()} - RESOLVED_STATUS_IDS - PENDING_STATUS_IDS
    if unknown_ids:
        logger.warning(
            "Unrecognized status_id values found: %s — treating them as pending "
            "(excluded from the clean dataset) until manually reviewed.",
            unknown_ids,
        )


def report_missing_values(df: pd.DataFrame) -> None:
    missing = df.isna().sum()
    missing = missing[missing > 0].sort_values(ascending=False)
    if missing.empty:
        logger.info("No missing values in any column.")
        return
    logger.info("Missing values per column:")
    for col, count in missing.items():
        pct = 100 * count / len(df)
        logger.info("  %-28s %6s  (%.1f%%)", col, count, pct)


def main() -> None:
    df = load_merged()

    # Parse launch date, extract year (needed for time-based analysis later)
    df["net"] = pd.to_datetime(df["net"], utc=True, errors="coerce")
    df["launch_year"] = df["net"].dt.year

    n_bad_dates = df["net"].isna().sum()
    if n_bad_dates:
        logger.warning("%s rows have an unparsable 'net' date — kept, but launch_year will be missing for them.", n_bad_dates)

    report_status_distribution(df)

    # Deduplicate on launch_id (should already be unique, but verify)
    n_before = len(df)
    df = df.drop_duplicates(subset="launch_id", keep="first")
    n_duplicates = n_before - len(df)
    if n_duplicates:
        logger.warning("Removed %s duplicate launch_id rows.", n_duplicates)
    else:
        logger.info("No duplicate launch_id found.")

    # Split resolved vs pending
    is_resolved = df["status_id"].isin(RESOLVED_STATUS_IDS)
    clean_df = df[is_resolved].copy()
    excluded_df = df[~is_resolved].copy()

    report_missing_values(clean_df)

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    clean_path = INTERIM_DIR / "02_clean.csv"
    excluded_path = INTERIM_DIR / "02_excluded_pending.csv"
    clean_df.to_csv(clean_path, index=False, encoding="utf-8")
    excluded_df.to_csv(excluded_path, index=False, encoding="utf-8")

    logger.info(
        "Done: %s resolved launches -> %s | %s pending/excluded launches -> %s",
        len(clean_df), clean_path.name, len(excluded_df), excluded_path.name,
    )


if __name__ == "__main__":
    main()