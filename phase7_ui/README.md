# Phase 7 — Send console

## Production (Vercel)

The deployed product is:

- **Static UI:** `public/index.html` (repo root) → served at `/`
- **API:** FastAPI app in `api.py`, mounted under `/api` via `api/index.py` (Mangum) and `vercel.json` rewrites

Configure Vercel env vars from `phase5_delivery/.env.example`. On Vercel, **stdio MCP (`npx` + OAuth dirs) is not practical**; use **`GMAIL_MCP_TRANSPORT=http`** / **`GDOCS_MCP_TRANSPORT=http`** with a reachable `mcp_bridge` (or equivalent).

## Local — Streamlit (optional)

```bash
pip install -r phase7_ui/requirements.txt
PYTHONPATH=. streamlit run phase7_ui/app.py --server.port 8507
```

## Local — API only

```bash
PYTHONPATH=. uvicorn phase7_ui.api:app --port 8010
```

Open `public/index.html` in a browser **from a local static server** and set API base to `http://127.0.0.1:8010` if you extend the page; the production build uses relative `/api`.

Logs: `phase7_ui/outputs/ui_delivery_runs.jsonl`, `phase7_ui/outputs/ui_load_errors.log`
