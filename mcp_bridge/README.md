# HTTP bridge (Gmail + optional Docs fallback)

**Gmail:** Phase 5 can use stdio [**GongRzhe/Gmail-MCP-Server**](https://github.com/GongRzhe/Gmail-MCP-Server) (`@gongrzhe/server-gmail-autoauth-mcp`). Run this service when you want **`GMAIL_MCP_TRANSPORT=http`** (e.g. Cloud Run, no `npx` on the runner) — `GMAIL_MCP_ENDPOINT` → `POST /gmail/deliver`.

**Google Docs:** Phase 5 can use stdio [google-docs-mcp](https://github.com/a-bonus/google-docs-mcp). Use this service for Docs when `GDOCS_MCP_TRANSPORT=http`.

Small FastAPI service that matches the JSON contracts used by `phase5_delivery/src/mcp_client.py`:

| Client env | HTTP route | Purpose |
|------------|------------|---------|
| `GDOCS_MCP_ENDPOINT` | `POST /docs/append` | Optional: append weekly pulse (page break + section) |
| `GMAIL_MCP_ENDPOINT` | `POST /gmail/deliver` | Gmail draft or send |

Authenticate every request with:

`Authorization: Bearer <MCP_BRIDGE_API_KEY>`

Use the **same** secret in the client as `GDOCS_MCP_API_KEY` and `GMAIL_MCP_API_KEY` (simplest).

## Google Cloud setup (summary)

1. Create a GCP project; enable **Google Docs API** and **Gmail API**.
2. Create a **service account**; download a JSON key (used as `GOOGLE_APPLICATION_CREDENTIALS`).
3. **Google Workspace only (required for Gmail via service account):**
   - In Admin console, add **domain-wide delegation** for the service account client ID.
   - OAuth scopes:
     - `https://www.googleapis.com/auth/documents`
     - `https://www.googleapis.com/auth/gmail.compose`
     - `https://www.googleapis.com/auth/gmail.send`
   - Set `GMAIL_IMPERSONATE_USER` to the mailbox that should send mail (e.g. `pulse@yourdomain.com`).
4. **Google Docs access:**
   - Either set `DOCS_IMPERSONATE_USER` to the same delegated user, **or** leave it empty and **share the target Doc** with the service account email (`something@project-id.iam.gserviceaccount.com`) with Editor access.
   - Put the doc id in Phase 5 `GOOGLE_DOC_ID`, or leave empty to create a new doc on first append (doc is created in the caller’s / service account Drive).

## Local run

From the **repository root** (`Milestone2`):

```bash
cp mcp_bridge/.env.example mcp_bridge/.env
# Edit mcp_bridge/.env: MCP_BRIDGE_API_KEY, GOOGLE_APPLICATION_CREDENTIALS, GMAIL_IMPERSONATE_USER, optional DOCS_IMPERSONATE_USER

source .venv/bin/activate
pip install -r mcp_bridge/requirements.txt
set -a && source mcp_bridge/.env && set +a
export PYTHONPATH=.
uvicorn mcp_bridge.main:app --reload --port 8080
```

Health: `curl http://127.0.0.1:8080/health`

## Phase 5 client URLs

After deploy (or locally):

```env
GDOCS_MCP_ENDPOINT=http://127.0.0.1:8080/docs/append
GMAIL_MCP_ENDPOINT=http://127.0.0.1:8080/gmail/deliver
GDOCS_MCP_API_KEY=<same as MCP_BRIDGE_API_KEY>
GMAIL_MCP_API_KEY=<same as MCP_BRIDGE_API_KEY>
```

## Cloud Run (outline)

Build from this folder (context = `mcp_bridge`):

```bash
cd mcp_bridge
gcloud builds submit --tag REGION-docker.pkg.dev/PROJECT/pulse/bridge:latest .
gcloud run deploy pulse-bridge \
  --image REGION-docker.pkg.dev/PROJECT/pulse/bridge:latest \
  --region REGION \
  --set-secrets=GOOGLE_APPLICATION_CREDENTIALS=sa-json:latest \
  --set-env-vars MCP_BRIDGE_API_KEY=...,GMAIL_IMPERSONATE_USER=...,PORT=8080
```

Mount the service account JSON as a secret file and set `GOOGLE_APPLICATION_CREDENTIALS` to its path inside the container (match your secret mount path).

---

**Note:** Content is appended as plain text (Markdown is not rendered to rich formatting). For rich text you would extend the bridge to use structured Docs requests.
