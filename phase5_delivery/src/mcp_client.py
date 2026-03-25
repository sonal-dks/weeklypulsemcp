import uuid
from typing import Any

import requests


class DeliveryTransientError(Exception):
    pass


class DeliveryHardError(Exception):
    pass


def deliver_via_mcp(
    endpoint: str,
    api_key: str,
    mode: str,
    recipient: str,
    subject: str,
    body: str,
    mime_type: str = "text/plain",
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    if not endpoint.strip():
        if mode == "draft_only":
            return {
                "status": "draft_only_local",
                "message_id": f"local-{uuid.uuid4()}",
                "provider": "local_fallback",
                "details": "No GMAIL_MCP_ENDPOINT configured; created local draft artifact only.",
            }
        raise DeliveryHardError("Missing GMAIL_MCP_ENDPOINT for send mode")

    payload = {
        "mode": mode,
        "to": recipient,
        "subject": subject,
        "body": body,
        "mimeType": mime_type,
    }
    headers = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout_seconds)
    except requests.RequestException as exc:
        raise DeliveryTransientError(f"MCP request failed: {exc}") from exc

    if response.status_code >= 500:
        raise DeliveryTransientError(f"MCP server error: {response.status_code}")
    if response.status_code >= 400:
        raise DeliveryHardError(f"MCP client error: {response.status_code} {response.text}")

    try:
        body_json = response.json()
    except ValueError:
        body_json = {}

    message_id = str(body_json.get("message_id") or body_json.get("id") or f"mcp-{uuid.uuid4()}")
    status = str(body_json.get("status") or ("drafted" if mode == "draft_only" else "sent"))
    return {
        "status": status,
        "message_id": message_id,
        "provider": "gmail_mcp",
        "http_status": response.status_code,
    }


def append_doc_via_mcp(
    endpoint: str,
    api_key: str,
    doc_id: str,
    doc_title: str,
    section_title: str,
    pulse_body: str,
    timeout_seconds: int = 20,
) -> dict[str, Any]:
    if not endpoint.strip():
        # Local fallback for draft/testing when Docs MCP isn't configured.
        resolved_doc_id = doc_id.strip() or f"local-doc-{uuid.uuid4()}"
        return {
            "status": "doc_appended_local",
            "doc_id": resolved_doc_id,
            "provider": "local_fallback",
            "section_title": section_title,
            "details": "No GDOCS_MCP_ENDPOINT configured; local append simulation only.",
        }

    payload = {
        "action": "append_weekly_pulse",
        "doc_id": doc_id.strip() or None,
        "doc_title": doc_title,
        "section_title": section_title,
        "insert_page_break": True,
        "content_markdown": pulse_body,
    }
    headers = {"Content-Type": "application/json"}
    if api_key.strip():
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout_seconds)
    except requests.RequestException as exc:
        raise DeliveryTransientError(f"Docs MCP request failed: {exc}") from exc

    if response.status_code >= 500:
        raise DeliveryTransientError(f"Docs MCP server error: {response.status_code}")
    if response.status_code >= 400:
        raise DeliveryHardError(f"Docs MCP client error: {response.status_code} {response.text}")

    try:
        body_json = response.json()
    except ValueError:
        body_json = {}

    resolved_doc_id = str(body_json.get("doc_id") or body_json.get("document_id") or doc_id or f"doc-{uuid.uuid4()}")
    section_ref = str(body_json.get("section_ref") or body_json.get("range") or "")
    status = str(body_json.get("status") or "doc_appended")
    doc_url = str(body_json.get("doc_url") or body_json.get("url") or "")
    return {
        "status": status,
        "doc_id": resolved_doc_id,
        "doc_url": doc_url,
        "section_ref": section_ref,
        "provider": "gdocs_mcp",
        "http_status": response.status_code,
        "section_title": section_title,
    }
