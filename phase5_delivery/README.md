# Phase 5 Google Doc Append + Email Delivery

Implements Phase 5 from `Architecture.md`.

## Google Docs (default): [a-bonus/google-docs-mcp](https://github.com/a-bonus/google-docs-mcp)

Phase 5 runs **`npx -y @a-bonus/google-docs-mcp`** as a stdio MCP subprocess and calls tools: `createDocument`, `readDocument`, `insertPageBreak`, `appendText` (see `src/gdocs_google_mcp_stdio.py`). This matches the same server you can wire in Cursor/Claude.

1. Install [Node.js](https://nodejs.org/) so `npx` is available.
2. OAuth (personal / test users): create a Desktop OAuth client in Google Cloud, then run once from your machine:
   ```bash
   GOOGLE_CLIENT_ID="..." GOOGLE_CLIENT_SECRET="..." npx -y @a-bonus/google-docs-mcp auth
   ```
   Refresh token is stored under `~/.config/google-docs-mcp/` (see upstream README).
3. Workspace: alternatively use **service account** env vars as in that repo (`SERVICE_ACCOUNT_PATH`, `GOOGLE_IMPERSONATE_USER`).

Set in `phase5_delivery/.env`: `GDOCS_MCP_TRANSPORT=stdio`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` (and/or service account paths).

## Gmail: [GongRzhe/Gmail-MCP-Server](https://github.com/GongRzhe/Gmail-MCP-Server)

Phase 5 runs **`npx -y @gongrzhe/server-gmail-autoauth-mcp`** over stdio and calls MCP tools **`draft_email`** (`DELIVERY_MODE=draft_only`) or **`send_email`** (`DELIVERY_MODE=send`). See `src/gmail_gongrzhe_mcp_stdio.py`.

1. Create Gmail API OAuth credentials in Google Cloud (Desktop or Web app per upstream README).
2. Run once: `npx -y @gongrzhe/server-gmail-autoauth-mcp auth` — tokens are stored under `~/.gmail-mcp/` (or set `GMAIL_CREDENTIALS_PATH`).
3. Set `GMAIL_MCP_TRANSPORT=stdio` in `.env`.

The GitHub repo is **archived**; the npm workflow remains the common integration path. For CI without Node, use **`GMAIL_MCP_TRANSPORT=http`** and `mcp_bridge` `POST /gmail/deliver` (see `mcp_bridge/README.md`).

## HTTP fallback (Docs only)

For CI or hosts without Node: `GDOCS_MCP_TRANSPORT=http` and `GDOCS_MCP_ENDPOINT` pointing at `mcp_bridge` `POST /docs/append`.

## Inputs

- `phase4_insights/outputs/pulse_<week>.md`
- `phase4_insights/outputs/insights_<week>.json`

## Outputs

- `phase5_delivery/outputs/email_delivery_report.json`
- `phase5_delivery/outputs/email_runs_<week>.json`
- `phase5_delivery/outputs/doc_append_report_<week>.json`

## Run

```bash
cd /path/to/Milestone2
source .venv/bin/activate
pip install -r phase5_delivery/requirements.txt
set -a && source phase5_delivery/.env && set +a
export PYTHONPATH=.
python3 phase5_delivery/scripts/run_phase5.py
```

## Google Docs HTTP client (mcp_bridge / custom)

Use `phase5_delivery/scripts/gdocs_mcp_client.py` when `GDOCS_MCP_TRANSPORT=http`.

```bash
PYTHONPATH=. python3 phase5_delivery/scripts/gdocs_mcp_client.py append \
  --section-title "Groww Weekly Product Pulse - 2026-03-24" \
  --content-file phase4_insights/outputs/pulse_2026-03-24.md
```
