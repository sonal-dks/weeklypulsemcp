#!/usr/bin/env bash
set -euo pipefail

PY_BIN="${PY_BIN:-python3}"
if [[ -x ".venv/bin/python" ]]; then
  PY_BIN=".venv/bin/python"
fi

"${PY_BIN}" -m pip install --upgrade pip
"${PY_BIN}" -m pip install -r phase1_pipeline/requirements.txt
"${PY_BIN}" -m pip install -r phase2_theming/requirements.txt
"${PY_BIN}" -m pip install -r phase3_clustering/requirements.txt
"${PY_BIN}" -m pip install -r phase4_insights/requirements.txt
"${PY_BIN}" -m pip install -r phase4_5_fee_scraper/requirements.txt
"${PY_BIN}" -m pip install -r phase5_delivery/requirements.txt
"${PY_BIN}" -m pip install -r phase6_ops/requirements.txt
