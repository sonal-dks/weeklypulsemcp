# Phase 4 Insights + One-Page Composition (Integrated)

Implements Phase 4 from `Architecture.md`.

## Inputs
- `phase2_theming/outputs/themes_<week>.json`
- `phase3_clustering/outputs/review_theme_map.json`
- `phase3_clustering/outputs/cluster_distribution.json`

## Outputs
- `phase4_insights/outputs/insights_<week>.json`
- `phase4_insights/outputs/pulse_<week>.md`

## What it does
- Deterministic analytics:
  - ranks top themes from clustered distribution
  - selects 3 representative user quotes
  - sanitizes quotes for PII
- LLM synthesis (Gemini Flash 2.5):
  - generates 3 action ideas from top themes + user voice
  - composes the final one-page pulse in strict format
- Validation:
  - section structure
  - exactly 3 bullets/quotes/actions
  - <=250 words
  - no PII

## Run
```bash
source .venv/bin/activate
export GEMINI_API_KEY=your_key
PYTHONPATH=. python3 phase4_insights/scripts/run_phase4.py
```
