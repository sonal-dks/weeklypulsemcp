"""
Gmail draft/send via stdio MCP using the GongRzhe Gmail MCP server (npm: @gongrzhe/server-gmail-autoauth-mcp).

Upstream: https://github.com/GongRzhe/Gmail-MCP-Server (archived; package still published for npx).

Tools used (per upstream README):
  - draft_email  — DELIVERY_MODE=draft_only
  - send_email   — DELIVERY_MODE=send
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import timedelta
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _tool_text(result: Any) -> str:
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        t = getattr(block, "text", None)
        if t:
            parts.append(t)
    return "\n".join(parts)


def _child_env(extra_env: dict[str, str] | None) -> dict[str, str]:
    import os

    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    if extra_env:
        for key, val in extra_env.items():
            if val:
                env[key] = val
    return env


def _guess_message_id(text: str) -> str:
    # Try Gmail message id patterns in tool output
    for pat in (r"\b([a-zA-Z0-9_-]{10,})\b", r"message[:\s]+([a-zA-Z0-9_-]+)", r"id[:\s]+([a-zA-Z0-9_-]+)"):
        m = re.search(pat, text, re.I)
        if m:
            return m.group(1)
    return f"gmail-mcp-{uuid.uuid4()}"


async def deliver_via_gmail_mcp_stdio(
    *,
    command: str,
    args: list[str],
    extra_env: dict[str, str] | None,
    mode: str,
    recipient: str,
    subject: str,
    body: str,
    mime_type: str = "text/plain",
    session_timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    if mode == "draft_only":
        tool_name = "draft_email"
    elif mode == "send":
        tool_name = "send_email"
    else:
        raise ValueError("mode must be draft_only or send")

    arguments: dict[str, Any] = {
        "to": [recipient],
        "subject": subject,
        "body": body,
        "mimeType": mime_type,
    }

    params = StdioServerParameters(
        command=command,
        args=args,
        env=_child_env(extra_env),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(
            read,
            write,
            read_timeout_seconds=timedelta(seconds=session_timeout_seconds),
        ) as session:
            await session.initialize()
            out = await session.call_tool(tool_name, arguments)
            if getattr(out, "isError", False):
                msg = _tool_text(out) or "MCP tool error"
                raise RuntimeError(f"{tool_name} failed: {msg}")
            text = _tool_text(out)
            mid = _guess_message_id(text)
            status = "drafted" if mode == "draft_only" else "sent"
            return {
                "status": status,
                "message_id": mid,
                "provider": "gongrzhe-gmail-mcp-stdio",
                "raw_response_preview": text[:500],
            }


def deliver_via_gmail_mcp_stdio_sync(**kwargs: Any) -> dict[str, Any]:
    return asyncio.run(deliver_via_gmail_mcp_stdio(**kwargs))
