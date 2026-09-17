"""
Raw collection script — Launch Library 2 API (thespacedevs.com)
====================================================================

Step 1 of the data pipeline (see the DALAS course data pipeline):
- Queries the API for one or more endpoints (launches, agencies, pads, launcher_configs)
- Respects the 15 requests/hour limit (free, unauthenticated tier)
- Saves EVERY raw page as-is (no transformation) under data/raw/<endpoint>/
- Automatically resumes where it left off after an interruption (checkpoint)
- Never modifies files already written: raw data is read-only

Usage:
    python 01_collect_launch_library.py --endpoint launches
    python 01_collect_launch_library.py --endpoint agencies pads launcher_configs
    python 01_collect_launch_library.py --endpoint launches --count-only   # just check the volume, 1 request
    python 01_collect_launch_library.py --endpoint launches --delay 5      # only use if you have an API key with a higher quota

Dependencies: requests (pip install requests)
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

BASE_URL = "https://ll.thespacedevs.com/2.0.0"

# Logical name -> API endpoint path
ENDPOINTS: dict[str, str] = {
    "launches": "/launch/",
    "agencies": "/agencies/",
    "pads": "/pad/",
    "launcher_configs": "/config/launcher/",
}

PAGE_SIZE = 100  # maximum allowed by the API
# 15 requests/hour -> 1 request every 240s to stay comfortably under the limit
DEFAULT_DELAY_SECONDS = 245

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Collection functions
# --------------------------------------------------------------------------

def fetch_page(endpoint_path: str, offset: int, limit: int = PAGE_SIZE) -> dict:
    """Fetch one page of results from the API, handling 429/5xx errors."""
    url = f"{BASE_URL}{endpoint_path}"
    params = {"limit": limit, "offset": offset}

    max_attempts = 6
    for attempt in range(1, max_attempts + 1):
        try:
            response = requests.get(url, params=params, timeout=60)
        except requests.exceptions.RequestException as exc:
            # Timeout, dropped connection, DNS, unstable wifi, etc.: retry with backoff
            wait_seconds = min(30 * attempt, 180)
            logger.warning(
                "Network error (%s) — retrying in %ss (attempt %s/%s)",
                exc.__class__.__name__, wait_seconds, attempt, max_attempts,
            )
            time.sleep(wait_seconds)
            continue

        if response.status_code == 200:
            return response.json()

        if response.status_code == 429:
            # Rate limit exceeded. The Retry-After header the API returns is sometimes
            # too optimistic (the hourly quota is genuinely exhausted, not just a brief
            # spike): apply a progressive backoff that grows with each consecutive 429,
            # up to a full hour if needed.
            retry_after = int(response.headers.get("Retry-After", 60))
            wait_seconds = min(max(retry_after, 60) * attempt, 3600)
            logger.warning(
                "429 Too Many Requests — waiting %ss before retrying (attempt %s/%s)",
                wait_seconds, attempt, max_attempts,
            )
            time.sleep(wait_seconds)
            continue

        if response.status_code >= 500:
            # Temporary server error: retry as well
            wait_seconds = min(30 * attempt, 180)
            logger.warning(
                "Server error %s — retrying in %ss (attempt %s/%s)",
                response.status_code, wait_seconds, attempt, max_attempts,
            )
            time.sleep(wait_seconds)
            continue

        logger.error("HTTP error %s for %s (offset=%s)", response.status_code, url, offset)
        response.raise_for_status()

    raise RuntimeError(f"Failed after {max_attempts} attempts for offset={offset} on {endpoint_path}")


def load_checkpoint(checkpoint_path: Path) -> dict:
    if checkpoint_path.exists():
        return json.loads(checkpoint_path.read_text(encoding="utf-8"))
    return {"next_offset": 0, "done": False, "total_count": None}


def save_checkpoint(checkpoint_path: Path, checkpoint: dict) -> None:
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2), encoding="utf-8")


def collect_endpoint(
    endpoint_name: str,
    delay_seconds: int = DEFAULT_DELAY_SECONDS,
    count_only: bool = False,
) -> None:
    """Collect an entire endpoint, page by page, resuming from its checkpoint."""
    endpoint_path = ENDPOINTS[endpoint_name]
    output_dir = DATA_DIR / endpoint_name
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / "_checkpoint.json"

    checkpoint = load_checkpoint(checkpoint_path)

    if checkpoint["done"] and not count_only:
        logger.info("Endpoint '%s' already fully collected (see checkpoint). Nothing to do.", endpoint_name)
        return

    offset = checkpoint["next_offset"]
    total_count = checkpoint["total_count"]

    while True:
        logger.info("Collecting '%s' — offset=%s", endpoint_name, offset)
        page = fetch_page(endpoint_path, offset)

        if total_count is None:
            total_count = page["count"]
            checkpoint["total_count"] = total_count
            logger.info("Total volume detected for '%s': %s items", endpoint_name, total_count)

        if count_only:
            logger.info("--count-only mode: stopping after the first request.")
            return

        # Save the raw, unmodified page, timestamped for reproducibility
        page_file = output_dir / f"page_offset_{offset:06d}.json"
        record = {
            "collected_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_url": f"{BASE_URL}{endpoint_path}",
            "offset": offset,
            "limit": PAGE_SIZE,
            "raw_response": page,
        }
        page_file.write_text(
            json.dumps(record, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        offset += PAGE_SIZE
        checkpoint["next_offset"] = offset
        save_checkpoint(checkpoint_path, checkpoint)

        if page["next"] is None:
            checkpoint["done"] = True
            save_checkpoint(checkpoint_path, checkpoint)
            logger.info("Collection of '%s' complete: %s items retrieved.", endpoint_name, total_count)
            break

        logger.info("Pausing %ss before the next request (API limit: 15/hour)...", delay_seconds)
        time.sleep(delay_seconds)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Raw collection — Launch Library 2 API")
    parser.add_argument(
        "--endpoint",
        nargs="+",
        choices=list(ENDPOINTS.keys()),
        required=True,
        help="One or more endpoints to collect",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=DEFAULT_DELAY_SECONDS,
        help="Delay in seconds between two requests (default 245s to stay under 15/h)",
    )
    parser.add_argument(
        "--count-only",
        action="store_true",
        help="Make a single request just to display the total available volume",
    )
    args = parser.parse_args()

    try:
        for endpoint_name in args.endpoint:
            collect_endpoint(endpoint_name, delay_seconds=args.delay, count_only=args.count_only)
    except (RuntimeError, KeyboardInterrupt) as exc:
        logger.warning(
            "Script stopped (%s). No data lost: rerun the exact same command "
            "to automatically resume where you left off.",
            exc.__class__.__name__,
        )


if __name__ == "__main__":
    main()