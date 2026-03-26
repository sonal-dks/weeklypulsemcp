# Groww Play Store Reviews -> Weekly Product Pulse

## Objective
Build an automated weekly system that converts recent Groww Google Play Store reviews into a concise, one-page product pulse for internal teams.

## Scope and Constraints
- Data source: public Google Play reviews for `com.nextbillion.groww`
- Time range: rolling last 12 weeks
- Required fields per review: rating, review text, date, helpful_count
- Output note length: max 250 words
- Theme constraints: exactly 5 themes, never more than 5
- Privacy: no PII in generated outputs
- Artifact naming: all phase outputs use **month-week tags** (`Month-WN-Year`, e.g. `March-W4-2026`). The tag is derived from the **Monday** of the current week; week-of-month N = `((monday.day - 1) // 7) + 1`. Runs within the same week **overwrite** the same artifact files — no duplicates.
- Google Doc ledger: **one block per week** (`===== WEEK: March-W4-2026 =====`). Same-week reruns replace in place; new week appends after page break. **Pulse-only** content in Doc (no fee data).
- Email delivery: **UI-triggered only** (Phase 7). User enters email + admin token + selects week from dropdown + picks fee funds. Email body = weekly pulse + selected fee explainer. **No automatic email in scheduler.**
- Delivery MCPs:
  - Google Docs: [**@a-bonus/google-docs-mcp**](https://github.com/a-bonus/google-docs-mcp) stdio.
  - Gmail: [**GongRzhe Gmail MCP Server**](https://github.com/GongRzhe/Gmail-MCP-Server) stdio only — used **exclusively from Phase 7 UI**, not from the scheduler.

## Week Tag Convention & Overwrite Contract

| Aspect | Detail |
|---|---|
| **Tag format** | `Month-WN-Year` (e.g. `March-W4-2026`) |
| **Derivation** | Monday of the current ISO week → `week_of_month = ((monday.day - 1) // 7) + 1` |
| **Shared utility** | `shared/week_utils.py` → `current_week_tag()`, `week_tag_from_date(d)` |
| **Scheduler cron** | Monday 11:00 AM IST = `30 5 * * 1` UTC |
| **Same-week re-run** | All phase output files are **overwritten** (same filename). Google Doc block for that week is **replaced in place**. No duplicates ever. |
| **New-week run** | New output files created with new tag. Google Doc gets a **page break + new block appended**. |
| **Phases using tag** | Phase 2 (`themes_`, `review_theme_map_`, `theme_runs_`), Phase 4 (`insights_`, `pulse_`), Phase 4.5 (`mf_fee_data_`), Phase 5 (`combined_payload_`, `doc_append_report_`), Phase 6 (`run_summary_`) |

## System Architecture (Phase-wise)

## High-Level Architecture Diagram (Readable View)
```mermaid
flowchart TB
  subgraph sourceLayer [Source]
    playStore[GooglePlayPublicReviews]
  end

  subgraph backendLayer [BackendPipeline — Scheduler]
    sched[Scheduler]
    ingest[IngestAPI]
    clean[CleanAndPII]
    theme[ThemeLLM]
    cluster[ClusterService]
    insight[InsightEngine]
    compose[PulseComposer]
    validate[PolicyGate]
    gdoc[google-docs-mcp Docs upsert — pulse only]
  end

  subgraph dataLayer [DataStores]
    rawJson[RawReviewsJSON]
    procJson[ProcessedReviewsJSON]
    runArtifacts[RunArtifactsJSON]
  end

  subgraph uiLayer [UI — Email Trigger]
    api[BackendAPI]
    ui[SendConsole — week dropdown]
    mail[GongRzheGmailMCP — email only]
    users[InternalTeams]
  end

  sched --> ingest
  playStore --> ingest
  ingest --> rawJson
  rawJson --> clean
  clean --> procJson
  procJson --> theme
  theme --> cluster
  cluster --> insight
  insight --> compose
  compose --> validate
  validate --> runArtifacts
  validate --> gdoc
  runArtifacts --> api
  api --> ui
  ui --> mail
  mail --> users
```

## Backend vs Frontend Scope
- Backend phases: Phase 1 to Phase 6 (automated scheduler — no email)
- Frontend/UI phase: Phase 7 (email triggered by user)

### Phase 1 (Backend): Foundation + Ingestion + Cleaning (Combined)
- Define run cadence: weekly scheduled execution.
- Configure core parameters:
  - `app_id`: `com.nextbillion.groww`
  - `lookback_weeks`: `12` (fixed)
  - `top_reported_themes`: `3` (shown in weekly pulse)
  - `max_themes`: `5` hard cap
  - `theme_count`: `5` (fixed)
  - `email_recipient`: predefined alias/self
- Establish policy gates:
  - max 250 words
  - no PII leakage
  - exactly 3 quotes and 3 action ideas
- Tech:
  - Runtime: Python 3.11+
  - Config: `.env` + Pydantic Settings
  - API contracts: JSON Schema for LLM responses
- Data validation:
  - Validate fixed constraints at startup (`lookback_weeks=12`, `theme_count=5`, `top_reported_themes=3`).
  - Fail fast on missing/invalid required config values.
- Logging:
  - Log run start/end, config snapshot (non-secret), and policy gate values.
  - Include a run identifier and UTC timestamps in all Phase 1 artifacts.
- Error handling:
  - On config validation failure, stop downstream execution and write failure details to `config_check.json`.
  - Ensure partial failures do not silently continue to later phases.
- Manual output to verify:
  - `phase1_pipeline/outputs/config_check.json` showing effective config and policy thresholds

#### Phase 1.1: Data Ingestion (Within Phase 1)
- Use a public Play Store reviews API/library (no auth-gated scraping).
- Fetch latest reviews and filter to configured date window.
- Store data in two layers for auditability:
  - raw reviews (as fetched)
  - processed reviews (post-cleaning)
- Raw review JSON is stored in descending order by `date` (latest posted reviews first).
- Tech:
  - API/library: `google-play-scraper` (public data only)
  - Storage: JSON file (`phase1_pipeline/outputs/raw_reviews.json`)
  - Job entrypoint: FastAPI internal endpoint or CLI job
- Data validation:
  - Validate each ingested record has `review_id`, `rating`, `text`, `date`, `helpful_count`, `ingested_at`.
  - Enforce type checks (`rating`/`helpful_count` numeric, `date` ISO format).
  - Validate output ordering by latest `date` before write.
- Logging:
  - Log fetched count, inserted count, dropped count, date range, and source app id.
  - Log if batching/retries are used during fetch calls.
- Error handling:
  - Capture API/network failures with retry/backoff and explicit failure reason in ingestion report.
  - If write fails, preserve fetched data in-memory run report and mark run as failed.
- Manual output to verify:
  - `phase1_pipeline/outputs/ingestion_report.json` with fetched count, min/max review date, sample 5 records

**Review data contract**
- `review_id` — prefer native Play Store **`reviewId`** when present; otherwise a deterministic hash from rating + text + date
- `rating`
- `text`
- `date`
- `helpful_count` (example: "2 people found this review helpful")
- `ingested_at`

#### Phase 1.2: Cleaning, Deduplication, and Spam Filtering (Within Phase 1)
- Text normalization:
  - whitespace cleanup
  - URL/noise cleanup
  - standard normalization for downstream NLP
- Language and quality filter rules (strict):
  - Keep only reviews where detected language is English (`en`).
  - Filter out any review tagged as non-English, even if written in English letters (transliteration/Roman script).
  - Filter out very short reviews with word count `< 5` after normalization.
- Dedup and spam rules (deterministic):
  - Exact duplicate: same normalized text hash -> keep oldest by date, omit the rest.
  - Near duplicate: text similarity above threshold (for example >= 0.92) -> keep one canonical review.
  - Spam/promo pattern: repetitive referral/promo content, link-only content, or non-informative noise -> omit.
- Dedup strategy:
  - exact dedup by normalized hash
  - near-duplicate removal by similarity threshold
- Spam filtering:
  - very short/noise-only text
  - repetitive/promotional patterns
- Examples of filtered-out reviews:
  - Language filter:
    - "bahut accha app hai" -> filtered (non-English language, Roman script)
    - "kya bakwas app" -> filtered (non-English language, Roman script)
  - Minimum words filter:
    - "Bad" -> filtered (1 word)
    - "Very slow" -> filtered (2 words)
    - "App not opening" -> filtered (3 words)
    - "Worst app ever" -> filtered (3 words)
  - Spam/noise filter:
    - "Use my code ABC123 for bonus" -> filtered (promotional/referral)
    - "http://short.link/xyz" -> filtered (link-only)
    - "!!!!!!!!!" -> filtered (noise-only)
  - Duplicate filter:
    - repeated text "App crashes every login" posted multiple times -> keep one, filter duplicates
- Examples of reviews kept:
  - "Portfolio page takes 8-10 seconds to load after latest update."
  - "Support closed my ticket without resolving KYC verification issue."
  - "Charts are useful, but app freezes when switching between stocks."
- PII scrubbing before LLM:
  - redact emails, phone numbers, account-like identifiers
- Omitted reviews handling:
  - store omitted reviews (deduped, spam, invalid quality) in an audit store for manual review
- Tech:
  - NLP preprocessing: `regex` + `rapidfuzz` + optional `clean-text`
  - Language detection: `langdetect` or `fastText` language ID
  - Processed store: JSON (`phase1_pipeline/outputs/processed_reviews.json`)
  - Omitted review store: JSON (`phase1_pipeline/outputs/omitted_reviews.json`)
  - PII patterns: regex-based detector with replacement tokens
- Data validation:
  - Validate cleaned rows preserve required fields (`review_id`, `text`, `date`, `rating`).
  - Validate omission reason is mandatory for every omitted row.
  - Validate `processed_count + omitted_count == raw_count`.
- Logging:
  - Log per-rule drop counts (`non_english`, `short_text_lt_5_words`, `spam_or_promo`, duplicates).
  - Log dedup thresholds and language-detection settings used in run.
- Error handling:
  - On malformed input rows, move row to omitted with `invalid_record` reason instead of crashing full run.
  - If cleaning artifact write fails, emit failure status and stop Phase 2 trigger.
- Manual output to verify:
  - `phase1_pipeline/outputs/cleaning_report.json` with dedup removed, spam removed, pii_redactions, omitted_count
  - `phase1_pipeline/outputs/omitted_reviews_sample.json` with omission reason (`non_english`, `short_text_lt_5_words`, `spam_or_promo`, `exact_duplicate`, `near_duplicate`)

### Phase 2 (Backend): Theme Generation (LLM)
- Input: `phase1_pipeline/outputs/processed_reviews.json` (cleaned review corpus in the lookback window).
- Output requirement:
  - generate exactly 5 high-level themes
  - each theme must be 1-3 words
- Review-level tagging requirement (included in Phase 2):
  - assign each processed review to one primary theme from the generated 5 themes (all processed reviews must be tagged)
  - output must include `review_id`, `text`, and `primary_theme` for auditability
- Enforce strict schema output (JSON) and retry on malformed/oversized theme list.
- **Weekly overwrite**: output files use month-week tag (`Month-WN-Year`). Re-runs within the same week overwrite the same files — no duplicates.
- Tech:
  - LLM API: Groq API
  - Prompting: constrained JSON output with validation/retry
  - Storage: JSON artifact (`phase2_theming/outputs/theme_runs_<week>.json`)
- Data validation:
  - Enforce exactly 5 unique themes, each 1-3 words.
  - Validate all processed reviews are assigned a `primary_theme` in review-theme map.
  - Validate `sum(theme_summary_counts) == review_count`.
- Logging:
  - Log batch count, per-batch attempts, retry reasons, model used, and reviews processed.
  - Log final theme list and per-theme mapped counts.
- Error handling:
  - Retry on transient API failures and rate limits with backoff.
  - Fail run on schema violations after retries (do not emit partial themes as pass).
  - Persist run-level failure artifact with actionable error message.
- Manual output to verify:
  - `phase2_theming/outputs/themes_<week>.json` containing exactly 5 short themes and `theme_summary_counts`
  - `phase2_theming/outputs/review_theme_map_<week>.json` mapping each review to one theme

### Phase 3 (Backend): Review Clustering (Primary Theme Assignment)
- Validate and optimize the Phase 2 review-theme mapping.
- Recommended approach:
  - Groq LLM classifier for primary theme assignment
  - second-pass Groq classification for ambiguous or low-confidence cases
- Balance control:
  - detect over-dominant theme
  - second-pass reassignment of borderline items to preserve distribution quality
- Tech:
  - LLM API: Groq API
  - Classification: constrained JSON output (`primary_theme` from fixed 5-theme set)
  - Storage: JSON (`phase3_clustering/outputs/review_theme_map.json`)
  - Input resolution: if `THEMES_PATH` / `REVIEW_THEME_MAP_PATH` are empty or stale, Phase 3 resolves latest Phase 2 outputs automatically.
- Data validation:
  - Validate one and only one `primary_theme` per review after rebalancing.
  - Validate all assigned themes belong to the fixed 5-theme set.
  - Validate cluster distribution totals match input review count.
- Logging:
  - Log classifier confidence bands, tie-break decisions, and number of reassigned reviews.
  - Log pre/post rebalancing theme distributions.
- Error handling:
  - If Groq classification call fails, fallback to deterministic rule-based assignment and flag degraded mode.
  - Abort phase if mapping integrity checks fail.
- Manual output to verify:
  - `phase3_clustering/outputs/review_theme_map.json` (rebalanced/final mapping)
  - `phase3_clustering/outputs/cluster_distribution.json` showing per-theme counts and dominance checks

### Phase 4 (Backend): Insights + One-Page Composition (Integrated)
- Compute per-theme metrics:
  - frequency
  - sentiment (average polarity / negative share)
  - week-over-week trend delta (optional but preferred)
- Rank top 3 themes (from the fixed 5-theme set) via weighted score:
  - `score = w1*frequency + w2*negative_intensity + w3*trend_delta`
- Extract:
  - 3 representative user quotes (sanitized, no PII)
  - 3 actionable product insights linked to top pain points
- Render fixed structure:
  - Weekly Groww Product Pulse
  - Top Themes (3 bullets selected from 5 generated themes)
  - User Voice (3 quotes)
  - Action Ideas (3 bullets)
- Composition approach:
  - Gemini Flash 2.5 generates the one-page narrative from the same phase's structured insight outputs.
  - Use a role-based system prompt to control writing style and output behavior.
  - Prompt enforces concise, decision-oriented bullet style and strict section format.
  - Action Ideas are synthesized by Gemini Flash 2.5 from top-ranked themes + user voice quotes.
- Sample system prompt (copy-ready):
```text
You are a senior product analyst writing a weekly internal product pulse for Product, Growth, Support, and Leadership teams.

Your job is to convert structured review insights into a concise, decision-oriented one-page note.

Hard constraints:
1) Output must be <= 250 words.
2) Output must include exactly these sections in order:
   - Weekly Groww Product Pulse
   - Top Themes
   - User Voice
   - Action Ideas
3) Top Themes must contain exactly 3 bullets.
4) User Voice must contain exactly 3 quote bullets.
5) Action Ideas must contain exactly 3 bullets.
6) Do not include any PII (names, emails, phone numbers, IDs, account numbers, ticket IDs).
7) Keep language crisp, scannable, and action-focused. Avoid generic filler.
8) Do not invent facts. Use only provided inputs.

Style rules:
- Prefer short bullets over long paragraphs.
- Use plain business language.
- Highlight what changed or matters this week.
- Make action ideas specific and implementable by product teams.

If any required input is missing, return:
ERROR: MISSING_REQUIRED_INPUT
```
- Enforce length:
  - hard validator for <=250 words
  - compression pass if needed
- Final privacy scan before publication.
- **Weekly overwrite**: output files use month-week tag (`Month-WN-Year`).
- Tech:
  - Sentiment: `vaderSentiment` or transformer-based classifier
  - Ranking: weighted scoring in Python
  - LLM API: Gemini Flash 2.5
  - Prompting: role-based system prompt + constrained markdown generation with section and bullet-count constraints
  - Validation: word counter + PII validator
  - Storage (structured): JSON (`phase4_insights/outputs/insights_<week>.json`)
  - Storage: Markdown artifact (`phase4_insights/outputs/pulse_<week>.md`)
  - Input resolution: if `THEMES_PATH` is empty or stale, Phase 4 resolves latest Phase 2 themes output automatically.
- Data validation:
  - Validate top themes are selected from the approved 5-theme set only.
  - Validate exactly 3 quotes and 3 action items are produced before composition.
  - Validate quotes pass PII checks and are non-empty.
  - Validate output structure sections are present in required order.
  - Validate max 250-word constraint and no PII leakage.
  - Validate exactly 3 top-theme bullets, 3 quotes, and 3 action ideas.
- Logging:
  - Log scoring components per theme (frequency, sentiment, trend).
  - Log quote selection source theme and filtering/redaction actions.
  - Log final word count, section completeness checks, and any compression passes applied.
  - Log PII scan results (match count only, no sensitive values).
- Error handling:
  - If sentiment/trend components fail, fallback to frequency-only ranking and flag in run metadata.
  - Skip invalid quotes/actions and regenerate until constraints are met or fail explicitly.
  - On validation failure, run one automatic LLM rewrite/compression pass before failing.
  - If still invalid, block downstream phases and record failure reason.
- Manual output to verify:
  - `phase4_insights/outputs/insights_<week>.json` with 5 generated themes, top 3 ranked themes, 3 quotes, 3 actions
  - `phase4_insights/outputs/pulse_<week>.md` that follows exact structure and <=250 words

### Phase 4.5 (Backend): Mutual Fund Fee Scraper (Exit Load / Fee Context)
- Purpose:
  - Pull a small public-data "fee context" snapshot from Groww mutual fund pages (no auth) to support internal interpretation of review themes around "fees/charges" (optional context layer).
  - This is a standalone artifact; **fee data is included only in the email body** (Phase 7 UI), not in the Google Doc.
- Input:
  - Static list of fund source URLs (public Groww pages) embedded in code.
- Output:
  - `phase4_5_fee_scraper/outputs/mf_fee_data_<week>.json` (month-week tag naming; same week overwrites).
- Tech:
  - Runtime: Python 3.11+
  - HTTP: `requests`
  - Parsing: `beautifulsoup4` + `lxml` + JSON extraction from `__NEXT_DATA__` where available
  - Render fallback: Playwright (Chromium) when Groww serves JS-only shell pages
- Data validation:
  - Validate the fund list size and that each result includes `fund_name`, `status`, `source_url`, `last_scraped`.
  - Validate `exit_load_bullets` is a list of strings for successful scrapes.
  - Validate `scraped_count + failed_count == total_funds`.
- Logging:
  - Log fetch method (`requests` vs `playwright`) and parse method (`next_data` vs `html_table`) per fund.
  - Log per-fund failures with last error and overall run status (`pass`/`partial`/`fail`).
- Error handling:
  - Retry Playwright fetch with bounded attempts/backoff when enabled.
  - If one fund fails, continue scraping remaining funds and mark run `partial`.
  - If all funds fail, mark run `fail` and still write the output artifact for audit.
- Manual output to verify:
  - `phase4_5_fee_scraper/outputs/mf_fee_data_<week>.json`

### Phase 5 (Backend): Google Doc Append (Scheduler — No Email)
- **Scope change**: Phase 5 in the scheduler only appends the weekly pulse to the Google Doc. It does **not** send email. Email delivery is handled exclusively by Phase 7 UI.
- Delivery model:
  - Maintain one persistent Google Doc as the weekly pulse ledger.
  - **Idempotent weekly blocks (stdio MCP):** each run derives `week_id` as `Month-WN-Year` from the Monday of the pipeline run. The doc body includes delimited sections:
    - `===== WEEK: Month-WN-Year =====` … pulse content … `===== END WEEK: Month-WN-Year =====`
  - If that `week_id` already exists → **deleteRange + insertText** at the same span (update in place, **no** duplicate page).
  - If it does not exist → **insertPageBreak** (when the doc already has body content) then **appendText** (new week only).
  - **Google Doc content is pulse-only** (Top Themes, User Voice, Action Ideas). Fee explainer is NOT written to the Doc.
  - Internal combined JSON artifact is still generated for audit (`combined_payload_<week>.json`).
  - Optional env **`GDOCS_LAST_WEEK_CACHE`**: path to a small JSON file recording last `{ doc_id, week_id }` (debug/ops only).
  - **Latest-artifact resolution:** Phase 5 resolves the newest matching `insights_<week>.json` + `pulse_<week>.md` pair from `phase4_insights/outputs/`. If configured env paths are stale or missing, it automatically uses the latest pair.
- **Google Docs:** [**a-bonus/google-docs-mcp**](https://github.com/a-bonus/google-docs-mcp) — MCP stdio client (`npx -y @a-bonus/google-docs-mcp`). **Pure idempotency helpers** (markers, plain-text span math, `Month-WN-Year` week id): `phase5_delivery/src/gdocs_weekly_idempotent.py` (unit tests: `phase5_delivery/tests/test_gdocs_weekly_idempotent.py`).
  - Auth: OAuth desktop client (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`, run `npx -y @a-bonus/google-docs-mcp auth` once) **or** Workspace service account.
  - MCP tools used: `readDocument`, `deleteRange`, `insertText`, `insertPageBreak`, `appendText`.
- **Gmail is NOT used in Phase 5.** Email delivery is Phase 7 only.
- Tech:
  - Docs: Python [`mcp`](https://github.com/modelcontextprotocol/python-sdk) SDK + stdio with weekly upsert (`Month-WN-Year`).
  - Audit: doc id, section title, delivery status in `phase5_delivery/outputs/doc_append_report_<week>.json`
- Data validation:
  - Validate body is sourced from latest validated artifacts.
  - Validate combined JSON payload contains required keys before doc write.
  - Validate pulse sections (`Top Themes`, `User Voice`, `Action Ideas`) are present.
- Logging:
  - Log docs transport (`stdio`), doc id, MCP tool errors.
- Error handling:
  - Retry transient failures with bounded backoff.
  - Doc write failure → `doc_append_failed`.
- Manual output to verify:
  - `phase5_delivery/outputs/doc_append_report_<week>.json`
  - `phase5_delivery/outputs/combined_payload_<week>.json`

### Phase 6 (Backend): Orchestration, Observability, and QA
- Weekly scheduler triggers full pipeline (Phases 1–5 Doc append + 6 QA).
- Per-run logs:
  - fetched count, cleaned count, dedup removed, spam removed
  - theme distribution
  - sentiment summary
  - word count and pii redaction count
  - doc append result
- Quality gates before marking pass:
  - themes count is exactly 5
  - exactly 3 quotes and 3 actions
  - note length <=250 words
  - PII check passes
  - Doc append succeeded
- Fail-safe:
  - store artifacts and error reason for review
- Tech:
  - Orchestration: **GitHub Actions scheduled workflow only** (no cron / no APScheduler)
  - Scheduler sub-phase files: `scheduler/` (install + run scripts)
    - `scheduler/scripts/install_deps.sh`
    - `scheduler/scripts/run_weekly_pipeline.sh`
  - Workflow file: `.github/workflows/weekly_pulse.yml` (invokes scheduler scripts)
  - GitHub Actions secrets/env required (minimum):
    - `GROQ_API_KEY`: required for Phase 2 and Phase 3 (Groq LLM calls)
    - `GEMINI_API_KEY`: required for Phase 4 (Gemini Flash 2.5)
    - `GOOGLE_DOC_ID`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`: required for Phase 5 Doc append
  - GitHub Actions runner prerequisites (minimum):
    - Python 3.11+ available
    - Node.js available (so `npx` can run MCP servers in Phase 5)
    - Phase 5 MCP OAuth tokens are pre-created and persist on the runner machine:
      - Google Docs MCP tokens: `~/.config/google-docs-mcp/`
    - **Gmail MCP tokens are NOT needed on the runner** — email is sent from UI only.
  - Runner requirement for MCP Doc append:
    - Phase 5 uses **stdio MCP** (`npx ...`) and relies on persisted OAuth tokens in the runner home directory.
    - Recommended: use a **self-hosted GitHub Actions runner** (so tokens can persist).
  - Observability: structured logs + lightweight metrics dashboard
  - QA: pre-send assertions as automated checks
- Data validation:
  - Validate inter-phase artifact contracts before each phase starts.
  - Validate run completeness (all required outputs present and parseable).
- Logging:
  - Centralize phase-level status, duration, counts, and failure reasons under one run id.
  - Emit success/failure summary per scheduled run.
- Error handling:
  - Short-circuit downstream phases when upstream validation fails.
  - Support safe reruns with idempotent artifact overwrite behavior.
- Manual output to verify:
  - `phase6_ops/outputs/run_summary_<week>.json` with pass/fail for all quality gates

#### Phase 6.1 (Backend Sub-phase): Scheduler Packaging
- Purpose:
  - Keep orchestration assets isolated from phase logic for easier ops ownership and workflow maintenance.
- Folder:
  - `scheduler/` contains dependency bootstrap and ordered phase execution scripts.
- Triggering:
  - GitHub Actions schedule: **Monday 11:00 AM IST (cron `30 5 * * 1` UTC)** and `workflow_dispatch`.
- Week propagation:
  - Scheduler computes one month-week tag (`Month-WN-Year`, e.g. `March-W4-2026`) per workflow run via `shared.week_utils.current_week_tag()`.
  - It exports week-specific paths before downstream phases (`THEMES_PATH`, `REVIEW_THEME_MAP_PATH`, `PULSE_PATH`, `INSIGHTS_PATH`, `WEEK_TAG`) so all phases use consistent naming.
- Runner model:
  - `runs-on: self-hosted` to preserve MCP stdio OAuth token state for Google Docs.

### Phase 7 (Frontend/UI): Send console (email trigger)
- Purpose: operator screen to deliver the weekly note + fee explainer **via email only**.
- **Key change**: email is sent only when the user manually enters email IDs, token, and clicks send. The scheduler does NOT send email.
- UI shows:
  - **Week selector dropdown** — lists all available weeks (newest first) from `phase4_insights/outputs/`. Selecting a week loads that week's pulse preview and fee data.
  - Multi-recipient email input (comma/newline separated).
  - Mutual fund **multi-select** (choose 1, 2, 3, … or all) from the fee artifact for the selected week, plus **Select all funds** and **Clear selection**.
  - Token input: operator must enter a valid admin token before send is accepted.
  - One primary action: **send email** to all listed recipients.
    - Email body = weekly pulse + selected fee explainer (HTML formatted).
    - Google Doc is **not updated from UI** — Doc is managed by the scheduler.
  - Below the action button, show two preview cards in one row:
    - left card: weekly pulse preview (for selected week)
    - right card: fee explainer preview (email-only; scrollable when multiple funds are selected)
- UI responsiveness: `public/index.html` uses a mobile-first CSS layout (single-column previews on small screens, two-column layout on desktop/tablet).
- **Why this solves the runner issue**: Gmail MCP requires stdio + OAuth tokens. Since email is now UI-only (not in the scheduler), the GitHub Actions runner does NOT need Gmail MCP tokens. Only Google Docs MCP tokens are needed on the runner.
- UI design:
  - **Light mode**, inspired by ChatGPT's clean aesthetic.
  - Color scheme: white surface (`#ffffff`), light gray page background (`#f7f7f8`), subtle gray borders (`#e5e5e5`), dark text (`#0d0d0d`), muted secondary text (`#6e6e80`), green accent (`#10a37f`) for primary actions.
  - Typography: system sans-serif stack, 15px base, clean spacing.
  - Streamlit config: `.streamlit/config.toml` enforces `base = "light"` with matching palette.
- Tech:
  - Production frontend: static web app (`public/index.html`) deployed on Vercel.
  - Backend API: FastAPI (`phase7_ui/api.py`) served by Vercel Python function entry (`api/index.py`).
  - Local fallback UI (optional): Streamlit (`phase7_ui/app.py`) for operator testing.
  - Delivery: reuses Phase 5 Gmail MCP stdio helpers for email only. Multi-recipient sends call Gmail with **`mode=send`** explicitly.
  - API endpoints:
    - `GET /weeks` — list available week tags
    - `GET /pulse/{week}` — pulse markdown for a specific week
    - `GET /funds?week=` — fund names from fee artifact for a week
    - `GET /preview/fee?fund_names=&week=` — plain-text fee preview
    - `POST /deliver` — send email (recipients, fund_names, delivery_token, week)
- Data validation:
  - Block send on invalid email addresses.
  - Block send when token is missing or incorrect; return clear message to get token from admin.
  - Phase 4 insights must be `pass` when building the combined body.
- Logging:
  - UI-triggered sends append to `phase7_ui/outputs/ui_delivery_runs.jsonl`.
  - Load/delivery errors append to `phase7_ui/outputs/ui_load_errors.log`.
- Manual output to verify:
  - UI preview cards show exact content the user should expect in email.
  - Email contains pulse + fee explainer for selected funds; Google Doc contains pulse only.

## High-Level Data Flow
```mermaid
flowchart TD
  scheduler[WeeklyScheduler] --> ingest[PlayStoreIngest]
  ingest --> rawStore[RawReviewStore]
  rawStore --> clean[CleanDedupSpamPII]
  clean --> procStore[ProcessedReviewStore]
  procStore --> themeGen[LLMThemeGeneration]
  themeGen --> cluster[ThemeAssignment]
  cluster --> insights[InsightsEngine]
  insights --> note[OnePageComposer]
  note --> policy[PIIAndWordCountValidator]
  policy --> docappend[google-docs-mcp weekly upsert — pulse only]
  policy --> archive[PulseArchive]
  ui[Phase7 UI — week dropdown] -->|user clicks send| email[GongRzhe Gmail MCP stdio]
  email --> users[InternalTeams]
```

## Output Template (Target Format)

### Google Doc content (pulse only — appended by scheduler)
**Weekly Groww Product Pulse**

**Top Themes**
- Theme 1: short insight
- Theme 2: short insight
- Theme 3: short insight

**User Voice**
- "Quote 1"
- "Quote 2"
- "Quote 3"

**Action Ideas**
- Action 1
- Action 2
- Action 3

### Email content (pulse + fee explainer — sent from UI)
The email includes the full pulse above **plus** the fee explainer section below (based on funds selected by the user in the UI):

**Fee Explainer** (one block per selected mutual fund)

Fund Name A

- Fee-related bullet 1
- Fee-related bullet 2
- Fee-related bullet 3

Links: https://...

Fund Name B

- Fee-related bullet 1
- Fee-related bullet 2
- Fee-related bullet 3

Links: https://...

### Google Doc ledger envelope (Phase 5 idempotency)
What is **actually stored** in the shared Google Doc is the pulse text above (no fee data), wrapped for **weekly upsert** (stdio MCP):

```text
===== WEEK: March-W4-2026 =====
Weekly Groww Product Pulse - March-W4-2026
... pulse body (Top Themes, User Voice, Action Ideas) ...
===== END WEEK: March-W4-2026 =====
```

- The tag comes from `shared.week_utils.current_week_tag()` — derived from the Monday of the pipeline run week.
- Reruns within the same week **replace** the span between these markers (idempotent overwrite, no duplicates); a **new** week **appends** (after an optional page break if the doc is non-empty).

## Suggested Delivery Milestones
- Week 1: ingestion + cleaning + storage + scheduler
- Week 2: LLM theming + clustering + ranking logic
- Week 3: integrated insights + one-page composition + policy validators
- Week 4: Google Docs **idempotent weekly ledger** (`Month-WN-Year`) + Gmail MCP (UI-only) + observability + end-to-end hardening

## Deployment (Vercel)
- Right now (single source of truth):
  - Frontend on Vercel: static send console (`public/index.html`) with week dropdown.
  - Backend on Vercel: FastAPI endpoints from `phase7_ui/api.py` via `api/index.py`.
  - Scheduler: GitHub Actions workflow `.github/workflows/weekly_pulse.yml` (self-hosted runner).
- Delivery tech in deployed stack:
  - Google Docs: MCP stdio (`@a-bonus/google-docs-mcp`) with `Month-WN-Year` upsert — **scheduler only**.
  - Gmail: MCP stdio (`@gongrzhe/server-gmail-autoauth-mcp`) — **Phase 7 UI only**.
- Fallback options (explicit):
  - If Vercel runtime cannot host stdio/OAuth token state for Gmail MCP, run email delivery from the self-hosted runner or local Streamlit console where stdio MCP is available.
  - No bridge layer is used.
- Secrets/config on Vercel:
  - Configure only runtime env vars required by Phase 7 API and delivery paths; keep secrets in Vercel settings.
  - Do not commit runtime secrets or OAuth token files.
- Manual verification after deploy:
  - Confirm weekly GitHub Actions scheduled run logs.
  - Confirm latest `run_summary_<week>.json` and Phase 5 doc append reports are generated.
  - Confirm Google Doc append for a scheduled run (pulse only).
  - Confirm email delivery from UI (pulse + fee explainer).

## Definition of Done (v1)
- Weekly automated run succeeds end-to-end (Phases 1–6).
- Uses only public data from configured rolling 12-week window.
- Produces one note that is <=250 words, no PII, and exactly 5 themes.
- All artifacts use month-week tag naming (`Month-WN-Year`, e.g. `March-W4-2026`); re-runs within the same week overwrite — no duplicate files or Doc entries.
- Scheduler writes the weekly pulse (no fee data) to **one** persistent Google Doc via [google-docs-mcp](https://github.com/a-bonus/google-docs-mcp) **stdio** using **`Month-WN-Year` markers**: at most **one block per week**; same-week reruns **replace** that block (no duplicate pages). **New** weeks get a **page break** then append.
- Email is sent **only from Phase 7 UI**: user selects week from dropdown, enters email + token, picks fee funds. Email body includes pulse + fee explainer.
- Gmail MCP is NOT required on the GitHub Actions runner.
- Stores run artifacts and metrics for audit and trend comparison.
