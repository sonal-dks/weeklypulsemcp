# Phase 2 Theming (Groq LLM)

Implements Phase 2 from `Architecture.md`.

## Input
- `phase1_pipeline/outputs/processed_reviews.json`

## Output
- `phase2_theming/outputs/theme_runs_<week>.json`
- `phase2_theming/outputs/themes_<week>.json`
- `phase2_theming/outputs/review_theme_map_<week>.json`

## Rules enforced
- exactly 5 themes
- each theme 1-3 words
- retry if malformed output
- batching over full processed corpus + final consolidation

## Setup
```bash
source .venv/bin/activate
pip install -r phase2_theming/requirements.txt
```

## Run
```bash
export GROQ_API_KEY=your_key
PYTHONPATH=. python3 phase2_theming/scripts/run_phase2.py
```
