"""
Google Docs delivery via stdio MCP using @a-bonus/google-docs-mcp.

See: https://github.com/a-bonus/google-docs-mcp

Tools used:
  - createDocument (only if GOOGLE_DOC_ID empty and GDOCS_AUTO_CREATE=1)
  - readDocument (format=json) — plain text + API index mapping for week blocks
  - deleteRange — replace existing week section in place
  - insertText — insert replacement week block after delete
  - insertPageBreak — only when appending a *new* ISO week block
  - appendText — new week when markers not present
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import timedelta
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from phase5_delivery.src.gdocs_weekly_idempotent import (
    api_span_for_plain_span,
    build_week_block,
    doc_json_to_plain_with_index_map,
    estimated_plain_len_after,
    find_week_span_in_plain,
    is_well_formed_week_id,
    week_id_from_report_date,
    write_last_week_cache,
)


def _tool_text(result: Any) -> str:
    parts: list[str] = []
    for block in getattr(result, "content", None) or []:
        t = getattr(block, "text", None)
        if t:
            parts.append(t)
    return "\n".join(parts)


def _child_env(extra_env: dict[str, str] | None) -> dict[str, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUNBUFFERED", "1")
    if extra_env:
        for key, val in extra_env.items():
            if val:
                env[key] = val
    gac = env.get("GOOGLE_APPLICATION_CREDENTIALS", "")
    if gac and not env.get("SERVICE_ACCOUNT_PATH") and os.path.isfile(gac):
        env["SERVICE_ACCOUNT_PATH"] = gac
    return env


def _last_end_index_from_doc_json(doc: dict[str, Any]) -> int:
    content = doc.get("body", {}).get("content", [])
    if not content:
        return 1
    return int(content[-1].get("endIndex", 1))


async def _call(session: ClientSession, name: str, arguments: dict[str, Any]) -> Any:
    out = await session.call_tool(name, arguments)
    if getattr(out, "isError", False):
        msg = _tool_text(out) or "MCP tool error"
        raise RuntimeError(f"{name} failed: {msg}")
    return out


async def append_weekly_via_google_docs_mcp(
    *,
    command: str,
    args: list[str],
    extra_env: dict[str, str] | None = None,
    doc_id: str,
    doc_title: str,
    section_title: str,
    pulse_body: str,
    report_date: str,
    insert_page_break: bool = True,
    session_timeout_seconds: float = 120.0,
) -> dict[str, Any]:
    """
    Upsert one delimited week block per ISO week (``YYYY-Www``), derived from ``report_date`` (YYYY-MM-DD).

    Same week + re-run → ``deleteRange`` + ``insertText`` at the same span (idempotent).
    New week → optional ``insertPageBreak`` then ``appendText``.
    """
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

            resolved_id = (doc_id or "").strip()
            if not resolved_id:
                allow_create = os.environ.get("GDOCS_AUTO_CREATE", "").strip().lower() in {
                    "1",
                    "true",
                    "yes",
                }
                if not allow_create:
                    raise ValueError(
                        "GOOGLE_DOC_ID is missing or empty, so the Google Docs MCP would call createDocument — "
                        "that often fails with Permission denied (OAuth/service account cannot create in My Drive, "
                        "restricted Workspace, or wrong account). "
                        "Fix: (1) Create or open a Google Doc in Drive. "
                        "(2) Copy the ID from the URL …/document/d/<DOC_ID>/edit "
                        "(3) Set GOOGLE_DOC_ID=<DOC_ID> in phase5_delivery/.env. "
                        "(4) If DOC_ID is already in .env, your shell may export GOOGLE_DOC_ID= (empty), which "
                        "overrides .env — run `unset GOOGLE_DOC_ID` or remove the empty export. "
                        "(5) Share the doc with the same Google account used for `google-docs-mcp` auth. "
                        "Optional: set env GDOCS_AUTO_CREATE=1 to retry automatic doc creation."
                    )
                created = await _call(session, "createDocument", {"title": doc_title})
                raw = _tool_text(created).strip()
                data = json.loads(raw)
                resolved_id = str(data["id"])

            week_id = week_id_from_report_date(report_date)
            if not is_well_formed_week_id(week_id):
                raise ValueError(f"Bad week id {week_id!r} from report_date {report_date!r}")
            block = build_week_block(week_id, pulse_body, section_title=section_title)

            rdoc = await _call(
                session,
                "readDocument",
                {"documentId": resolved_id, "format": "json"},
            )
            jtxt = _tool_text(rdoc).strip()
            doc_json = json.loads(jtxt)
            plain, index_map = doc_json_to_plain_with_index_map(doc_json)
            len_before = len(plain)
            span = find_week_span_in_plain(plain, week_id)
            action: str
            appended: bool

            if span:
                api_span = api_span_for_plain_span(index_map, span[0], span[1])
                if not api_span:
                    raise RuntimeError(
                        "Week markers found in plain text but API index mapping failed "
                        "(non-paragraph content?). Fix document or remove stray markers."
                    )
                d_start, d_end = api_span
                await _call(
                    session,
                    "deleteRange",
                    {"documentId": resolved_id, "startIndex": d_start, "endIndex": d_end},
                )
                await _call(
                    session,
                    "insertText",
                    {"documentId": resolved_id, "index": d_start, "text": block},
                )
                action = "update"
                appended = False
            else:
                action = "append"
                appended = True
                if insert_page_break:
                    end_idx = _last_end_index_from_doc_json(doc_json)
                    if end_idx > 2:
                        await _call(
                            session,
                            "insertPageBreak",
                            {"documentId": resolved_id, "index": end_idx - 1},
                        )
                await _call(
                    session,
                    "appendText",
                    {
                        "documentId": resolved_id,
                        "text": block,
                        "addNewlineIfNeeded": True,
                    },
                )

            len_after = estimated_plain_len_after(plain, span, block, appended=appended)
            print(
                f"[gdocs-weekly] week_id={week_id} action={action} doc_id={resolved_id} "
                f"plain_len_before={len_before} plain_len_after={len_after}",
                flush=True,
            )

            cache_path = os.environ.get("GDOCS_LAST_WEEK_CACHE", "").strip()
            if cache_path:
                write_last_week_cache(cache_path, resolved_id, week_id)

            url = f"https://docs.google.com/document/d/{resolved_id}/edit"
            return {
                "status": "doc_appended" if action == "append" else "doc_updated",
                "gdocs_action": action,
                "week_id": week_id,
                "plain_len_before": len_before,
                "plain_len_after": len_after,
                "doc_id": resolved_id,
                "document_id": resolved_id,
                "doc_url": url,
                "section_title": section_title,
                "section_ref": week_id,
                "provider": "google-docs-mcp-stdio",
            }


def append_weekly_via_google_docs_mcp_sync(**kwargs: Any) -> dict[str, Any]:
    try:
        return asyncio.run(append_weekly_via_google_docs_mcp(**kwargs))
    except BaseExceptionGroup as eg:  # Python 3.11+
        msgs: list[str] = []
        for e in eg.exceptions:
            msgs.append(repr(e))
            if isinstance(e, BaseExceptionGroup):
                for sub in e.exceptions:
                    msgs.append(str(sub))
            else:
                msgs.append(str(e))
        raise RuntimeError("Google Docs MCP stdio failed: " + " | ".join([m for m in msgs if m])) from eg
