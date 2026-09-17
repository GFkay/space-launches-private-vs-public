# 🚀 Has the private sector made space more accessible?

Project carried out as part of the **DALAS** course (Data Science, Learning and ApplicationS) — Sorbonne Université.

## Research question

> Has the private sector (SpaceX, Blue Origin, Rocket Lab...) made access to space more reliable and more frequent than historical public agencies (NASA, Roscosmos, CNES...)?

## Data sources

- **[Launch Library 2 API](https://ll.thespacedevs.com/)** — complete history of orbital launches (~8000 launches), agencies, launch sites, rocket configurations
- **Wikipedia** — enrichment: cost per launch (rocket page infoboxes), key milestone dates (first successful landings, technological breakthroughs)

## Data pipeline

| Step | Script | Description |
|---|---|---|
| 1 | `scripts/01_collect_launch_library.py` | Raw collection via the API (raw, never modified) |
| 2 | `scripts/02_merge_sources.py` | Merge launches / agencies / pads / launcher_configs |
| 3 | `scripts/03_clean.py` | Cleaning (missing values, ambiguous statuses, duplicates) |
| 4 | `scripts/04_enrich_external.py` | Adding external costs + key milestone dates |
| 5 | `scripts/05_compute_metrics.py` | Computing custom metrics (success rate, frequency, reuse) |

Each step reads the output of the previous one and writes a new version — raw data is never modified (`data/raw/` is read-only).

## Progress

- ✅ 01 — Raw collection (Launch Library 2 API) — 7977 launches retrieved
- ⬜ 02 — Merging sources (launches / agencies / pads / launcher_configs)
- ⬜ 03 — Cleaning
- ⬜ 04 — External enrichment (costs, key milestone dates)
- ⬜ 05 — Computing metrics
- ⬜ Dashboard (TME6)
- ⬜ Visual report + technical report (TME9)

## Project structure

```
data/          raw → interim → processed (see pipeline above)
scripts/       one script per step, run in order
notebooks/     exploration (EDA), not meant for production
dashboard/     Streamlit app (TME6)
reports/       course deliverables (TME4, visual report, technical report)
tests/         unit tests on cleaning/metric functions
```

## Installation

```bash
pip install -r requirements.txt
```

## Reproducing the pipeline

```bash
python scripts/01_collect_launch_library.py --endpoint launches agencies pads launcher_configs
python scripts/02_merge_sources.py
python scripts/03_clean.py
python scripts/04_enrich_external.py
python scripts/05_compute_metrics.py
```

## Author

Karim, Group project — DALAS TME