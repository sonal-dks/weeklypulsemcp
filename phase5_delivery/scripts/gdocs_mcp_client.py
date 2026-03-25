#!/usr/bin/env python3
"""
CLI client for an HTTP Google Docs MCP (or MCP bridge) server.

This matches the JSON contract used by phase5_delivery/src/mcp_client.py:
  POST with JSON body containing action, doc_id, doc_title, section_title,
  insert_page_break, content_markdown.

Native MCP over stdio (JSON-RPC) is a different protocol; use this when your
server exposes a single HTTP URL that accepts the Phase 5 payload shape.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import requests


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


def _headers(api_key: str) -> dict[str, str]:
    h = {"Content-Type": "application/json", "Accept": "application/json"}
    if api_key.strip():
        h["Authorization"] = f"Bearer {api_key.strip()}"
    return h


def append_weekly_pulse(
    endpoint: str,
    api_key: str,
    *,
    doc_id: str,
    doc_title: str,
    section_title: str,
    content_markdown: str,
    insert_page_break: bool = True,
    timeout: float = 30.0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "action": "append_weekly_pulse",
        "doc_id": doc_id.strip() or None,
        "doc_title": doc_title,
        "section_title": section_title,
        "insert_page_break": insert_page_break,
        "content_markdown": content_markdown,
    }
    r = requests.post(endpoint, json=payload, headers=_headers(api_key), timeout=timeout)
    out: dict[str, Any] = {
        "http_status": r.status_code,
        "request": payload,
    }
    try:
        out["response"] = r.json()
    except ValueError:
        out["response_text"] = r.text[:8000]
    return out


def raw_post(
    endpoint: str,
    api_key: str,
    body: dict[str, Any],
    timeout: float = 30.0,
) -> dict[str, Any]:
    r = requests.post(endpoint, json=body, headers=_headers(api_key), timeout=timeout)
    out: dict[str, Any] = {"http_status": r.status_code, "request": body}
    try:
        out["response"] = r.json()
    except ValueError:
        out["response_text"] = r.text[:8000]
    return out


def main() -> None:
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--env-file", type=Path, default=None)
    pre_args, argv_rest = pre.parse_known_args()
    if pre_args.env_file:
        _load_env_file(pre_args.env_file)
    else:
        _default = Path(__file__).resolve().parent.parent / ".env"
        _load_env_file(_default)

    parser = argparse.ArgumentParser(
        description=(
            "HTTP client for Google Docs MCP bridge (Phase 5 contract). "
            "Loads phase5_delivery/.env when present (setdefault). Use --env-file to load another file first."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_append = sub.add_parser("append", help="append_weekly_pulse — same payload as Phase 5 delivery")
    p_append.add_argument("--endpoint", default=os.environ.get("GDOCS_MCP_ENDPOINT", ""))
    p_append.add_argument("--api-key", default=os.environ.get("GDOCS_MCP_API_KEY", ""))
    p_append.add_argument("--doc-id", default=os.environ.get("GOOGLE_DOC_ID", ""))
    p_append.add_argument("--doc-title", default=os.environ.get("GOOGLE_DOC_TITLE", "Groww Weekly Product Pulse"))
    p_append.add_argument("--section-title", required=True)
    p_append.add_argument("--content-file", type=Path, help="Markdown/plain text file to append")
    p_append.add_argument("--content", help="Inline body (use --content-file for long text)")
    p_append.add_argument("--no-page-break", action="store_true")
    p_append.add_argument("--timeout", type=float, default=30.0)

    p_raw = sub.add_parser("raw", help="POST arbitrary JSON (for custom server shapes)")
    p_raw.add_argument("--endpoint", required=True)
    p_raw.add_argument("--api-key", default=os.environ.get("GDOCS_MCP_API_KEY", ""))
    p_raw.add_argument("--json-file", type=Path, required=True)
    p_raw.add_argument("--timeout", type=float, default=30.0)

    args = parser.parse_args(argv_rest)

    if args.cmd == "append":
        endpoint = args.endpoint or os.environ.get("GDOCS_MCP_ENDPOINT", "")
        if not endpoint.strip():
            print("Missing --endpoint or GDOCS_MCP_ENDPOINT", file=sys.stderr)
            sys.exit(2)
        if args.content_file and args.content:
            print("Use either --content-file or --content, not both", file=sys.stderr)
            sys.exit(2)
        if args.content_file:
            content = args.content_file.read_text(encoding="utf-8")
        elif args.content:
            content = args.content
        else:
            print("Provide --content-file or --content", file=sys.stderr)
            sys.exit(2)

        doc_id = args.doc_id or os.environ.get("GOOGLE_DOC_ID", "")
        api_key = args.api_key or os.environ.get("GDOCS_MCP_API_KEY", "")
        result = append_weekly_pulse(
            endpoint,
            api_key,
            doc_id=doc_id,
            doc_title=args.doc_title,
            section_title=args.section_title,
            content_markdown=content,
            insert_page_break=not args.no_page_break,
            timeout=args.timeout,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        status = result.get("http_status", 0)
        if status >= 400:
            sys.exit(1)

    elif args.cmd == "raw":
        body = json.loads(args.json_file.read_text(encoding="utf-8"))
        result = raw_post(args.endpoint, args.api_key, body, timeout=args.timeout)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        status = result.get("http_status", 0)
        if status >= 400:
            sys.exit(1)


if __name__ == "__main__":
    main()
