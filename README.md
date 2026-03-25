# weeklypulsemcp — Weekly Pulse

Monorepo for the Groww Play Store → weekly product pulse pipeline (ingestion → insights → Google Docs MCP upsert + HTML email). Google MCP usage details: [Architecture.md](./Architecture.md).

## Phase 7 on Vercel

Production UI: [`public/`](./public/) at `/`, API under `/api/*` (see [`vercel.json`](./vercel.json)).

1. Import [github.com/sonal-dks/weeklypulsemcp](https://github.com/sonal-dks/weeklypulsemcp) in [Vercel](https://vercel.com). **Root directory:** repo root.
2. Set **environment variables** from `phase5_delivery/.env.example`. On Vercel, prefer **`GMAIL_MCP_TRANSPORT=http`** / **`GDOCS_MCP_TRANSPORT=http`** with a deployed [`mcp_bridge`](./mcp_bridge) (stdio `npx` OAuth is not suited to serverless).
3. Deploy and open the project URL.

Local API: `PYTHONPATH=. uvicorn phase7_ui.api:app --reload --port 8010`  
Optional local Streamlit: [`phase7_ui/README.md`](./phase7_ui/README.md)

## Clone

```bash
git clone https://github.com/sonal-dks/weeklypulsemcp.git
cd weeklypulsemcp
```
