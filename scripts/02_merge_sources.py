"""
Merge script — combine launches with agencies, pads, launcher_configs
========================================================================

Step 2 of the data pipeline:
- Loads every raw page saved by 01_collect_launch_library.py (data/raw/<endpoint>/)
- Builds lookup tables (by id) for agencies, pads, launcher_configs
- For each launch, joins in the extra detail fields from those lookups
  (the launch record itself only embeds a lightweight id+name reference)
- Writes ONE merged table to data/interim/01_merged.csv

This step does not clean or transform values (see 03_clean.py for that) —
it only joins the sources together. Nothing here overwrites data/raw/.

Usage:
    python 02_merge_sources.py

Dependencies: pandas (pip install pandas)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"


# --------------------------------------------------------------------------
# Loading raw pages
# --------------------------------------------------------------------------

def read_json_file(path: Path) -> dict[str, Any]:
    """Read a JSON file, tolerating pages saved with Windows' cp1252 encoding
    before the UTF-8 fix in 01_collect_launch_library.py. Never rewrites the
    file — raw data stays exactly as originally saved."""
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning(
            "%s is not valid UTF-8 (likely collected before the encoding fix) — "
            "falling back to cp1252 for this file only.",
            path.name,
        )
        text = path.read_text(encoding="cp1252")
    return json.loads(text)


def load_raw_results(endpoint_name: str) -> list[dict[str, Any]]:
    """Read every page file for an endpoint and concatenate their 'results' lists."""
    endpoint_dir = RAW_DIR / endpoint_name
    if not endpoint_dir.exists():
        raise FileNotFoundError(
            f"No raw data found for '{endpoint_name}' — run 01_collect_launch_library.py first."
        )

    page_files = sorted(endpoint_dir.glob("page_offset_*.json"))
    if not page_files:
        raise FileNotFoundError(f"No page files found in {endpoint_dir}")

    all_results: list[dict[str, Any]] = []
    for page_file in page_files:
        record = read_json_file(page_file)
        all_results.extend(record["raw_response"]["results"])

    logger.info("Loaded %s raw '%s' records from %s pages", len(all_results), endpoint_name, len(page_files))
    return all_results


def build_lookup(records: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    """Index a list of records by their 'id' field for fast joining."""
    return {record["id"]: record for record in records if record.get("id") is not None}


def safe_get(d: dict | None, *keys: str, default: Any = None) -> Any:
    """Safely walk a chain of nested dict keys, returning `default` if anything is missing."""
    current: Any = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


# --------------------------------------------------------------------------
# Merging
# --------------------------------------------------------------------------

def merge_launch(
    launch: dict[str, Any],
    agencies_lookup: dict[int, dict[str, Any]],
    pads_lookup: dict[int, dict[str, Any]],
    launcher_configs_lookup: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    """Build one flat row for a launch, enriched with agency/pad/launcher detail."""
    agency_id = safe_get(launch, "launch_service_provider", "id")
    pad_id = safe_get(launch, "pad", "id")
    config_id = safe_get(launch, "rocket", "configuration", "id")

    agency = agencies_lookup.get(agency_id, {})
    pad = pads_lookup.get(pad_id, {})
    launcher_config = launcher_configs_lookup.get(config_id, {})

    return {
        # --- launch core fields ---
        "launch_id": launch.get("id"),
        "launch_name": launch.get("name"),
        "net": launch.get("net"),  # scheduled/actual launch datetime (UTC, ISO 8601)
        "status_id": safe_get(launch, "status", "id"),
        "status_name": safe_get(launch, "status", "name"),
        "orbit_name": safe_get(launch, "mission", "orbit", "name"),
        "orbit_abbrev": safe_get(launch, "mission", "orbit", "abbrev"),
        "mission_type": safe_get(launch, "mission", "type"),

        # --- agency (from the agencies lookup, richer than the embedded reference) ---
        "agency_id": agency_id,
        "agency_name": agency.get("name", safe_get(launch, "launch_service_provider", "name")),
        "agency_type": agency.get("type", safe_get(launch, "launch_service_provider", "type")),
        "agency_country_code": agency.get("country_code"),
        "agency_founding_year": agency.get("founding_year"),

        # --- launch pad / site ---
        # NB: country_code lives under pad.location, not directly on pad
        "pad_id": pad_id,
        "pad_name": pad.get("name", safe_get(launch, "pad", "name")),
        "pad_latitude": pad.get("latitude", safe_get(launch, "pad", "latitude")),
        "pad_longitude": pad.get("longitude", safe_get(launch, "pad", "longitude")),
        "pad_total_launch_count": pad.get("total_launch_count"),
        "location_name": safe_get(pad, "location", "name"),
        "location_country_code": safe_get(pad, "location", "country_code"),
        "location_total_launch_count": safe_get(pad, "location", "total_launch_count"),
        "location_total_landing_count": safe_get(pad, "location", "total_landing_count"),

        # --- rocket / launcher configuration ---
        "launcher_config_id": config_id,
        "launcher_config_name": launcher_config.get("name", safe_get(launch, "rocket", "configuration", "name")),
        "launcher_family": launcher_config.get("family"),
        "launcher_reusable": launcher_config.get("reusable"),
    }


def main() -> None:
    logger.info("Loading raw data...")
    launches = load_raw_results("launches")
    agencies = load_raw_results("agencies")
    pads = load_raw_results("pads")
    launcher_configs = load_raw_results("launcher_configs")

    agencies_lookup = build_lookup(agencies)
    pads_lookup = build_lookup(pads)
    launcher_configs_lookup = build_lookup(launcher_configs)

    logger.info("Merging %s launches with agency/pad/launcher details...", len(launches))
    merged_rows = [
        merge_launch(launch, agencies_lookup, pads_lookup, launcher_configs_lookup)
        for launch in launches
    ]

    df = pd.DataFrame(merged_rows)

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    output_path = INTERIM_DIR / "01_merged.csv"
    df.to_csv(output_path, index=False, encoding="utf-8")

    logger.info("Merged table written to %s (%s rows, %s columns)", output_path, len(df), len(df.columns))
    logger.info("Missing agency match: %s launches", df["agency_name"].isna().sum())
    logger.info("Missing pad match: %s launches", df["pad_name"].isna().sum())
    logger.info("Missing launcher config match: %s launches", df["launcher_config_name"].isna().sum())


if __name__ == "__main__":
    main()