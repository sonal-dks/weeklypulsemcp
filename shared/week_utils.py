"""
Shared week-tag utility for all phases.

Format: ``Month-WN-Year``  (e.g. ``March-W4-2026``)

The tag is derived from the **Monday** of the current ISO week.
Week-of-month N is computed as ``((monday.day - 1) // 7) + 1``.

Re-runs within the same week always produce the same tag,
so output files are overwritten (idempotent).
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def _monday_of_week(d: date) -> date:
    """Return the Monday of the ISO week containing ``d``."""
    return d - timedelta(days=d.weekday())


def week_tag_from_date(d: date) -> str:
    """Return ``Month-WN-Year`` for the week containing ``d``."""
    monday = _monday_of_week(d)
    week_of_month = ((monday.day - 1) // 7) + 1
    return f"{monday.strftime('%B')}-W{week_of_month}-{monday.year}"


def current_week_tag() -> str:
    """Return the week tag for the current UTC date."""
    return week_tag_from_date(datetime.now(timezone.utc).date())
