# Phase 3 Clustering (Validation + Rebalancing)

Implements Phase 3 from `Architecture.md`.

## Inputs
- `phase2_theming/outputs/themes_<week>.json`
- `phase2_theming/outputs/review_theme_map_<week>.json`

## Outputs
- `phase3_clustering/outputs/review_theme_map.json`
- `phase3_clustering/outputs/cluster_distribution.json`

## What it does
- Validates Phase 2 review-theme mapping integrity.
- Identifies low-confidence / ambiguous assignments.
- Reclassifies ambiguous reviews using Groq (bounded subset).
- Rebalances dominant clusters by reassigning low-confidence items.
- Writes final mapping and distribution summary.

## Run
```bash
source .venv/bin/activate
export GROQ_API_KEY=your_key
PYTHONPATH=. python3 phase3_clustering/scripts/run_phase3.py
```
