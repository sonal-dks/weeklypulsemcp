#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="${PYTHONPATH:-.}"
PY_BIN="${PY_BIN:-python3}"
if [[ -x ".venv/bin/python" ]]; then
  PY_BIN=".venv/bin/python"
fi

# Compute week tag once: Month-WN-Year (e.g. March-W4-2026)
RUN_WEEK="$("${PY_BIN}" -c "from shared.week_utils import current_week_tag; print(current_week_tag())")"
echo "[scheduler] RUN_WEEK=${RUN_WEEK}"

echo "[scheduler] Phase 1 — ingestion + cleaning"
"${PY_BIN}" phase1_pipeline/scripts/run_phase1.py

echo "[scheduler] Phase 2 — theming"
"${PY_BIN}" phase2_theming/scripts/run_phase2.py

echo "[scheduler] Phase 3 — clustering"
export THEMES_PATH="phase2_theming/outputs/themes_${RUN_WEEK}.json"
export REVIEW_THEME_MAP_PATH="phase2_theming/outputs/review_theme_map_${RUN_WEEK}.json"
"${PY_BIN}" phase3_clustering/scripts/run_phase3.py

echo "[scheduler] Phase 4 — insights + pulse"
export THEMES_PATH="phase2_theming/outputs/themes_${RUN_WEEK}.json"
export REVIEW_THEME_MAP_PATH="phase3_clustering/outputs/review_theme_map.json"
"${PY_BIN}" phase4_insights/scripts/run_phase4.py

echo "[scheduler] Phase 4.5 — fee scraper"
"${PY_BIN}" -m phase4_5_fee_scraper.scripts.run_phase4_5

echo "[scheduler] Phase 5 — Google Doc append (pulse only, no email)"
export PULSE_PATH="phase4_insights/outputs/pulse_${RUN_WEEK}.md"
export INSIGHTS_PATH="phase4_insights/outputs/insights_${RUN_WEEK}.json"
"${PY_BIN}" phase5_delivery/scripts/run_phase5.py

echo "[scheduler] Phase 6 — ops QA summary"
export WEEK_TAG="${RUN_WEEK}"
"${PY_BIN}" phase6_ops/scripts/run_phase6.py
