# Phase 1 Pipeline (Foundation + Ingestion + Cleaning)

This folder implements combined Phase 1 from `Architecture.md`.

## What it does
- Validates fixed configuration and policy constraints.
- Fetches public Groww Play Store reviews from the last 12 weeks.
- Stores raw reviews in JSON sorted by latest review date.
- Cleans and filters reviews (language, short text, spam/noise, dedup).
- Writes processed and omitted review artifacts for manual audit.

## Outputs
- `outputs/config_check.json`
- `outputs/raw_reviews.json`
- `outputs/ingestion_report.json`
- `outputs/processed_reviews.json`
- `outputs/omitted_reviews.json`
- `outputs/omitted_reviews_sample.json`
- `outputs/cleaning_report.json`

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r phase1_pipeline/requirements.txt
```

## Run
```bash
PYTHONPATH=. python3 phase1_pipeline/scripts/run_phase1.py
```
