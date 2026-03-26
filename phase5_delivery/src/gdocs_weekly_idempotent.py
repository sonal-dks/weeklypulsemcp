"""
Idempotent weekly blocks for Google Docs: one logical entry per week.

Markers:
  ===== WEEK: Month-WN-Year =====
  ... content ...
  ===== END WEEK: Month-WN-Year =====

Same week re-run → replaces block in place (overwrite).
New week → append with page break.

Pure helpers are unit-testable; MCP I/O stays in gdocs_google_mcp_stdio.py.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from typing import Any

from shared.week_utils import current_week_tag, week_tag_from_date


def get_current_week_id() -> str:
    """Ledger id for 'now' in UTC (``Month-WN-Year``)."""
    return current_week_tag()


def week_id_from_report_date(report_date: str) -> str:
    """Derive ledger id from artifact tag.

    Accepts ``Month-WN-Year`` directly, ``YYYY-Www``, or ``YYYY-MM-DD``.
    """
    s = report_date.strip()
    if re.match(r"^[A-Z][a-z]+-W\d+-\d{4}$", s):
        return s
    if re.match(r"^\d{4}-W\d{2}$", s):
        return s
    try:
        d = date.fromisoformat(s[:10])
        return week_tag_from_date(d)
    except ValueError:
        return s


def week_id_from_datetime(dt: datetime) -> str:
    return week_tag_from_date(dt.date())


def week_markers(week_id: str) -> tuple[str, str]:
    return (f"===== WEEK: {week_id} =====", f"===== END WEEK: {week_id} =====")


def build_week_block(week_id: str, pulse_content: str, *, section_title: str = "") -> str:
    """Build a single delimited week section (plain text for Google Docs)."""
    inner = pulse_content.strip()
    parts: list[str] = [f"===== WEEK: {week_id} =====\n"]
    st = section_title.strip()
    if st:
        parts.append(st + "\n\n")
    parts.append(inner + "\n")
    parts.append(f"===== END WEEK: {week_id} =====\n")
    return "".join(parts)


def extract_week_section(content: str, week_id: str) -> str | None:
    """Return the full marked block (including markers), or None if missing."""
    span = find_week_span_in_plain(content, week_id)
    if not span:
        return None
    return content[span[0] : span[1]]


def replace_week_section(content: str, week_id: str, new_block: str) -> str:
    """Replace an existing week block or append if missing (string model)."""
    span = find_week_span_in_plain(content, week_id)
    if not span:
        return append_new_week(content, week_id, new_block)
    start, end = span
    return content[:start] + new_block + content[end:]


def append_new_week(content: str, _week_id: str, new_block: str) -> str:
    """Append a week block to plain-text document body (string model)."""
    base = content.rstrip()
    sep = "\n\n" if base else ""
    return base + sep + new_block


def find_week_span_in_plain(plain: str, week_id: str) -> tuple[int, int] | None:
    """
    Find [start, end) slice indices in ``plain`` for the full week block including markers.
    Returns None if not found or if only a corrupted partial match (no end marker).
    """
    start_marker, end_marker = week_markers(week_id)
    i = plain.find(start_marker)
    if i < 0:
        return None
    j = plain.find(end_marker, i + len(start_marker))
    if j < 0:
        return None
    j_end = j + len(end_marker)
    if j_end < len(plain) and plain[j_end] == "\r":
        j_end += 1
    if j_end < len(plain) and plain[j_end] == "\n":
        j_end += 1
    return i, j_end


def doc_json_to_plain_with_index_map(doc: dict[str, Any]) -> tuple[str, list[int]]:
    """
    Walk Google Docs API JSON body paragraphs and map each body character to API index.

    Indices follow the Docs API (1-based). Used with ``deleteRange`` / ``insertText``.
    """
    chars: list[str] = []
    indices: list[int] = []
    body = doc.get("body") or {}
    content = body.get("content") or []
    for el in content:
        para = el.get("paragraph")
        if not para:
            continue
        for pe in para.get("elements") or []:
            tr = pe.get("textRun")
            if not tr:
                continue
            text = tr.get("content") or ""
            si = pe.get("startIndex")
            if si is None:
                continue
            base = int(si)
            for k, _ch in enumerate(text):
                chars.append(_ch)
                indices.append(base + k)
    return "".join(chars), indices


def api_span_for_plain_span(
    index_map: list[int],
    plain_start: int,
    plain_end_exclusive: int,
) -> tuple[int, int] | None:
    """
    Map plain-text [plain_start, plain_end_exclusive) to API [startIndex, endIndex)
    for deleteContentRange (end exclusive).
    """
    if not index_map or plain_start < 0 or plain_end_exclusive > len(index_map):
        return None
    if plain_start >= plain_end_exclusive:
        return None
    api_start = index_map[plain_start]
    api_end = index_map[plain_end_exclusive - 1] + 1
    if api_end <= api_start:
        return None
    return api_start, api_end


def fetch_existing_doc(doc_json_text: str) -> dict[str, Any]:
    """Parse MCP ``readDocument`` JSON string into a dict (for testing / callers)."""
    return json.loads(doc_json_text)


def estimated_plain_len_after(
    plain_before: str,
    span: tuple[int, int] | None,
    new_block: str,
    *,
    appended: bool,
) -> int:
    if span and not appended:
        a, b = span
        return len(plain_before[:a] + new_block + plain_before[b:])
    pb = plain_before.rstrip()
    if not pb:
        return len(new_block)
    return len(pb + "\n\n" + new_block)


def main() -> None:
    print(get_current_week_id())


_WEEK_ID_RE = re.compile(r"^[A-Z][a-z]+-W\d+-\d{4}$")


def is_well_formed_week_id(week_id: str) -> bool:
    safe = week_id.strip()
    return bool(_WEEK_ID_RE.match(safe))


def write_last_week_cache(path: str, doc_id: str, week_id: str) -> None:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {"doc_id": doc_id, "week_id": week_id, "updated_at_utc": datetime.now(timezone.utc).isoformat()},
            indent=2,
        ),
        encoding="utf-8",
    )


__all__ = [
    "append_new_week",
    "api_span_for_plain_span",
    "build_week_block",
    "doc_json_to_plain_with_index_map",
    "estimated_plain_len_after",
    "extract_week_section",
    "fetch_existing_doc",
    "find_week_span_in_plain",
    "get_current_week_id",
    "main",
    "replace_week_section",
    "week_id_from_datetime",
    "week_id_from_report_date",
    "week_markers",
    "write_last_week_cache",
    "is_well_formed_week_id",
]
