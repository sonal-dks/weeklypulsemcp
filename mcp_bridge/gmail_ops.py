from __future__ import annotations

import base64
from email.mime.text import MIMEText
from typing import Any

from googleapiclient.discovery import Resource


def send_or_draft(
    gmail: Resource,
    *,
    mode: str,
    to_addr: str,
    subject: str,
    body: str,
    mime_type: str = "text/plain",
) -> dict[str, Any]:
    subtype = "html" if mime_type.strip().lower() in {"text/html", "html"} else "plain"
    mime = MIMEText(body, subtype, "utf-8")
    mime["to"] = to_addr
    mime["subject"] = subject
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("utf-8")

    if mode == "draft_only":
        out = gmail.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
        draft_id = str(out.get("id", ""))
        mid = str(out.get("message", {}).get("id", draft_id))
        return {"status": "drafted", "message_id": mid, "draft_id": draft_id}

    if mode == "send":
        out = gmail.users().messages().send(userId="me", body={"raw": raw}).execute()
        return {"status": "sent", "message_id": str(out.get("id", ""))}

    raise ValueError("mode must be draft_only or send")
