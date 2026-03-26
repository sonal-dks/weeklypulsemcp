# Weekly Pulse MCP (`weeklypulsemcp`)

**What this is:** an end-to-end **Python** pipeline that turns **public Google Play Store reviews** (Groww app: `com.nextbillion.groww`) into a **short weekly “product pulse”** for internal teams—top themes, user quotes, action ideas, optional **mutual-fund fee explainer**—then **writes it into one shared Google Doc** (ISO-week **upsert**: same calendar week is replaced in place; new weeks append) and **emails stakeholders** a **styled HTML** digest. Delivery uses MCP: Docs via stdio (primary) with optional HTTP bridge fallback, Gmail via stdio MCP only.

**Why it exists:** automate a consistent, gated weekly narrative from noisy review data while keeping outputs short (e.g. word limits, quote/action counts) and avoiding PII in generated text.

---

## How the pipeline fits together

| Phase | Role |
|--------|------|
| **1** | Ingest & clean Play Store reviews; dedupe / spam / language filters; JSON artifacts |
| **2** | LLM-assisted theming (Groq, etc.) |
| **3** | Clustering / theme consolidation |
| **4** | Insights + one-page pulse (e.g. Gemini); strict structure (themes, quotes, actions) |
| **4.5** | Optional MF fee scrape → bullets + source links |
| **5** | **Delivery:** merge pulse + fees → Doc upsert (MCP) + **HTML email** (MCP stdio) |
| **6** | QA / run summary over artifact paths |
| **7** | **Ops UI:** static web app + **FastAPI** (`/api/*`); production target **Vercel** |

Deeper contracts, diagrams, and tool links live in **[Architecture.md](./Architecture.md)**.

---

## Repository layout (high level)

- `phase1_pipeline/` … `phase6_ops/` — backend jobs and outputs under each phase’s `outputs/` (where committed samples exist).
- `phase7_ui/` — FastAPI routes, optional local **Streamlit** dev UI, shared **`send_service`**.
- `api/` — **Vercel** serverless entry (`Mangum`) mounting the same API under `/api`.
- `public/` — production **send console** (HTML/JS) served at `/` on Vercel.

---

## Quick start (local)

```bash
git clone https://github.com/sonal-dks/weeklypulsemcp.git
cd weeklypulsemcp
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
```

Copy each phase’s **`.env.example`** → **`.env`** and fill secrets (never commit `.env`). Typical run order:

```bash
# From repo root with PYTHONPATH set
export PYTHONPATH=.
python phase1_pipeline/scripts/run_phase1.py
python phase2_theming/scripts/run_phase2.py
python phase3_clustering/scripts/run_phase3.py
python phase4_insights/scripts/run_phase4.py
# optional fee data:
python phase4_5_fee_scraper/scripts/run_phase4_5.py
python phase5_delivery/scripts/run_phase5.py
python phase6_ops/scripts/run_phase6.py
```

Phase scripts and READMEs under each `phase*/README.md` have details.

---

## Phase 7 on Vercel (production UI)

1. Import this repo in [Vercel](https://vercel.com) with **root directory = repository root**.
2. Add **environment variables** matching `phase5_delivery/.env.example` (and any paths your deployment needs). Serverless **cannot rely on local `npx` + OAuth token dirs** the way a laptop can—use a runtime that supports Gmail MCP stdio for actual sends; for Docs only, optional `GDOCS_MCP_TRANSPORT=http` can point to a custom endpoint.
3. Deploy. Open the site: **`/`** = send console, **`/api/health`** = API check.

**Live example:** [weeklypulsemcp.vercel.app](https://weeklypulsemcp.vercel.app) (set your own env vars in the Vercel project for doc/email delivery).

Local API (no Vercel): `PYTHONPATH=. uvicorn phase7_ui.api:app --reload --port 8010`  
Optional local Streamlit: see [phase7_ui/README.md](./phase7_ui/README.md).

---

## Security & secrets

- **Do not commit** real OAuth client secrets, API keys, or `gcp-oauth.keys.json`. Use **`.env.example`** only as a template; keep **`.env`** local or in your host’s secret store (Vercel env, etc.).
- If credentials were ever pasted into a tracked file, **rotate them** in Google Cloud / provider consoles.

---

## Links

- **Repo:** [github.com/sonal-dks/weeklypulsemcp](https://github.com/sonal-dks/weeklypulsemcp)  
- **Design & MCP details:** [Architecture.md](./Architecture.md)
