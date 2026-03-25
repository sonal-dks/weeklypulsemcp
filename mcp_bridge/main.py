from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from mcp_bridge.config import BridgeConfig
from mcp_bridge.doc_ops import append_weekly_section, create_document, doc_url
from mcp_bridge.gmail_ops import send_or_draft
from mcp_bridge.google_services import docs_service, gmail_service

_cfg = BridgeConfig()

app = FastAPI(title="Groww Pulse MCP Bridge", version="1.0.0")


def verify_bearer(authorization: Annotated[str | None, Header()] = None) -> None:
    expected = _cfg.mcp_bridge_api_key.strip()
    if not expected:
        raise HTTPException(500, "MCP_BRIDGE_API_KEY is not configured on server")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(403, "Invalid API key")


class DocsAppendBody(BaseModel):
    action: str = Field(default="append_weekly_pulse")
    doc_id: str | None = None
    doc_title: str = "Groww Weekly Product Pulse"
    section_title: str
    insert_page_break: bool = True
    content_markdown: str


class GmailDeliverBody(BaseModel):
    mode: str
    to: str
    subject: str
    body: str
    mimeType: str = "text/plain"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/docs/append")
def docs_append(payload: DocsAppendBody, _: Annotated[None, Depends(verify_bearer)]):
    sa_path = _cfg.google_application_credentials or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not sa_path or not os.path.isfile(sa_path):
        raise HTTPException(500, "GOOGLE_APPLICATION_CREDENTIALS is not set or file missing")

    docs_delegate = (_cfg.docs_impersonate_user or "").strip() or None
    docs = docs_service(sa_path, docs_delegate)

    doc_id = (payload.doc_id or "").strip() or ""
    if not doc_id:
        doc_id = create_document(docs, payload.doc_title)

    append_weekly_section(
        docs,
        doc_id=doc_id,
        section_title=payload.section_title,
        content_markdown=payload.content_markdown,
        insert_page_break=payload.insert_page_break,
    )

    return {
        "status": "doc_appended",
        "doc_id": doc_id,
        "document_id": doc_id,
        "doc_url": doc_url(doc_id),
        "section_title": payload.section_title,
        "section_ref": "",
    }


@app.post("/gmail/deliver")
def gmail_deliver(payload: GmailDeliverBody, _: Annotated[None, Depends(verify_bearer)]):
    sa_path = _cfg.google_application_credentials or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if not sa_path or not os.path.isfile(sa_path):
        raise HTTPException(500, "GOOGLE_APPLICATION_CREDENTIALS is not set or file missing")
    if payload.mode not in {"draft_only", "send"}:
        raise HTTPException(400, "mode must be draft_only or send")
    if _cfg.gmail_use_impersonation and not (_cfg.gmail_impersonate_user or "").strip():
        raise HTTPException(
            500,
            "GMAIL_IMPERSONATE_USER is required for Gmail when using service account delegation",
        )
    delegate = (_cfg.gmail_impersonate_user or "").strip() if _cfg.gmail_use_impersonation else None
    try:
        gmail = gmail_service(sa_path, delegate)
    except ValueError as exc:
        raise HTTPException(500, str(exc)) from exc

    try:
        out = send_or_draft(
            gmail,
            mode=payload.mode,
            to_addr=payload.to,
            subject=payload.subject,
            body=payload.body,
            mime_type=payload.mimeType,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Gmail API error: {exc}") from exc

    return {
        "status": out.get("status", payload.mode),
        "message_id": out.get("message_id", ""),
        "id": out.get("message_id", ""),
    }
