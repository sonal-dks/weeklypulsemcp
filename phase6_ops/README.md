# Phase 6 Orchestration, Observability, and QA

Implements Phase 6 from `Architecture.md`.

## What it does
- Loads latest weekly artifacts from Phase 1–5.
- Runs pre-send quality gates (themes=5, 3 quotes/actions, <=250 words, no PII, delivery status).
- Writes a single run summary JSON for audit and UI consumption.

## Output
- `phase6_ops/outputs/run_summary_<week>.json`

## Run
```bash
source .venv/bin/activate
PYTHONPATH=. python3 phase6_ops/scripts/run_phase6.py
```

