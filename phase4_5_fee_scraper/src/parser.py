"""
Extract exit load bullets from a Groww MF page's HTML.

Strategy (tried in order, first success wins):
1. __NEXT_DATA__ JSON  — Next.js SSR embeds structured fund data here.
2. HTML table/row scan — look for rows labelled "Exit Load" in the page.
3. Visible-text search  — plain-text fallback using regex on stripped page text.

All three approaches use only BeautifulSoup + regex; no LLM required.
Exit load text is short, structured, and deterministic (e.g. "1% if redeemed
within 1 year of allotment. Nil thereafter.").
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# Matches "exit load" case-insensitively
_EXIT_RE = re.compile(r"exit\s*load", re.IGNORECASE)

# Matches percentage figures like "1%", "0.5%", "Nil", "NIL", "0%"
_LOAD_VALUE_RE = re.compile(
    r"(?:\d+(?:\.\d+)?\s*%|[Nn]il|[Zz]ero|no\s+exit\s+load)", re.IGNORECASE
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    """Collapse whitespace and strip."""
    return re.sub(r"\s+", " ", text).strip()


def _enrich_exit_load_sentence(sentence: str) -> list[str]:
    """
    Given a single exit load sentence (e.g. "Exit load of 1% if redeemed within 1 year"),
    generate 3 distinct factual bullets by extracting the charge and time period.

    Pattern:  <charge>% if redeemed within <period>
    Bullet 1: charge + period (the raw fact)
    Bullet 2: nil / no load condition (after the period)
    Bullet 3: application note (NAV-based deduction)
    """
    sentence = _clean(sentence)

    # Extract charge: "1%", "0.50%", "Nil", "0%"
    charge_match = re.search(r"(\d+(?:\.\d+)?)\s*%", sentence)
    charge = charge_match.group(0) if charge_match else "applicable"

    # Extract period: "1 year", "3 months", "15 days", "365 days"
    period_match = re.search(
        r"(\d+)\s*(year|years|month|months|day|days)", sentence, re.IGNORECASE
    )
    if period_match:
        period = f"{period_match.group(1)} {period_match.group(2).lower()}"
    else:
        period = "the specified period"

    # Check for NIL load (ELSS lock-in or zero-load funds)
    if re.search(r"\bnil\b|\bzero\b|0\s*%", sentence, re.IGNORECASE):
        return [
            f"No exit load (Nil) — redemption is free at any time.",
            f"ELSS funds have a mandatory 3-year statutory lock-in; units cannot be redeemed before lock-in ends.",
            f"After the lock-in period, redemption proceeds are credited at the prevailing NAV.",
        ]

    bullet1 = sentence if sentence.endswith(".") else sentence + "."
    bullet2 = f"Nil exit load if redeemed after {period} from the date of allotment."
    bullet3 = f"Exit load of {charge} is deducted from the redemption amount at the prevailing NAV."

    return [bullet1, bullet2, bullet3]


def _to_bullets(raw_lines: list[str]) -> list[str]:
    """
    Normalise raw lines into exactly 3 non-empty bullet strings.
    When only a single exit load sentence is available, enriches it into
    3 distinct factual bullets (charge, nil-condition, application note).
    """
    bullets = [_clean(l) for l in raw_lines if _clean(l)]
    bullets = [b for b in bullets if len(b) > 8]

    if len(bullets) == 1:
        return _enrich_exit_load_sentence(bullets[0])

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique = []
    for b in bullets:
        if b not in seen:
            seen.add(b)
            unique.append(b)
    bullets = unique

    while len(bullets) < 3:
        bullets.append(bullets[-1])
    return bullets[:3]


def _search_json(obj: Any, depth: int = 0) -> str | None:
    """
    Recursively walk a JSON-decoded object and return the first string
    value that looks like exit load information (>20 chars, contains the
    phrase "exit load").
    """
    if depth > 12:
        return None
    if isinstance(obj, str) and _EXIT_RE.search(obj) and len(obj) > 20:
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            hit = _search_json(v, depth + 1)
            if hit:
                return hit
    if isinstance(obj, list):
        for item in obj:
            hit = _search_json(item, depth + 1)
            if hit:
                return hit
    return None


# ── strategy 1: __NEXT_DATA__ ─────────────────────────────────────────────

def _get_direct_exit_load(data: dict[str, Any]) -> str | None:
    """
    Directly access the known Groww NEXT_DATA path:
      data.props.pageProps.mfServerSideData.exit_load
    Returns the string value (even if short like "Nil"), or None.
    """
    try:
        val = data["props"]["pageProps"]["mfServerSideData"]["exit_load"]
        if val and isinstance(val, str) and val.strip():
            return val.strip()
    except (KeyError, TypeError):
        pass
    return None


def parse_from_next_data(html: str) -> list[str] | None:
    """
    Groww is a Next.js app. The server-side rendered page includes a
    <script id="__NEXT_DATA__"> tag with the full page props as JSON.
    Fund details (including exit load) are inside this blob.

    Primary:  reads data.props.pageProps.mfServerSideData.exit_load directly.
    Fallback: generic recursive string search for any value containing "exit load".
    """
    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script or not script.string:
        log.debug("__NEXT_DATA__ script tag not found")
        return None

    try:
        data = json.loads(script.string)
    except json.JSONDecodeError as exc:
        log.debug("__NEXT_DATA__ JSON parse error: %s", exc)
        return None

    # Try the direct known key first (handles short values like "Nil")
    hit = _get_direct_exit_load(data)

    # Fall back to generic recursive search
    if not hit:
        hit = _search_json(data)

    if not hit:
        log.debug("exit load not found in __NEXT_DATA__")
        return None

    log.debug("exit load found in __NEXT_DATA__: %r", hit[:120])

    # Split on sentence boundaries and pick lines that contain load-value signals
    sentences = re.split(r"(?<=[.;])\s+", hit)
    bullets = []
    for s in sentences:
        s = _clean(s)
        if _EXIT_RE.search(s) or _LOAD_VALUE_RE.search(s) or s.lower() in ("nil", "0%", "zero"):
            bullets.append(s)
        if len(bullets) == 3:
            break

    if not bullets:
        bullets = [_clean(s) for s in sentences if len(_clean(s)) > 3]

    if not bullets:
        return None

    log.info("Parsed exit load via __NEXT_DATA__  bullets=%d", len(bullets))
    return _to_bullets(bullets)


# ── strategy 2: HTML table / definition-list scan ────────────────────────

def parse_from_html_table(html: str) -> list[str] | None:
    """
    Many fund detail pages render exit load in a table or key-value list:

        | Exit Load | 1% if redeemed within 1 year ... |

    This strategy scans <tr>, <li>, <dt>/<dd>, and <div> pairs for a cell
    labelled "Exit Load" and extracts its sibling/adjacent value cell.
    """
    soup = BeautifulSoup(html, "lxml")

    # --- table rows ---
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["th", "td"])
        for i, cell in enumerate(cells):
            if _EXIT_RE.search(cell.get_text()):
                # The value is in the next sibling cell(s)
                value_cells = cells[i + 1 :]
                value_text = " ".join(c.get_text(separator=" ") for c in value_cells)
                value_text = _clean(value_text)
                if value_text and len(value_text) > 5:
                    log.info("Parsed exit load via HTML table row")
                    sentences = re.split(r"(?<=[.;])\s+", value_text)
                    return _to_bullets(sentences)

    # --- definition lists (<dt>/<dd>) ---
    for dt in soup.find_all("dt"):
        if _EXIT_RE.search(dt.get_text()):
            dd = dt.find_next_sibling("dd")
            if dd:
                value_text = _clean(dd.get_text(separator=" "))
                if value_text:
                    log.info("Parsed exit load via <dt>/<dd>")
                    return _to_bullets(re.split(r"(?<=[.;])\s+", value_text))

    # --- adjacent <div> / <span> pairs with "exit load" label ---
    for elem in soup.find_all(string=_EXIT_RE):
        parent = elem.parent
        if parent is None:
            continue
        # Look at the next sibling element for the value
        sibling = parent.find_next_sibling()
        if sibling:
            value_text = _clean(sibling.get_text(separator=" "))
            if value_text and len(value_text) > 5:
                log.info("Parsed exit load via sibling element")
                return _to_bullets(re.split(r"(?<=[.;])\s+", value_text))

    log.debug("exit load not found in HTML tables/lists")
    return None


# ── strategy 3: visible-text fallback ────────────────────────────────────

def parse_from_visible_text(html: str) -> list[str] | None:
    """
    Last-resort: strip all tags to plain text, find the paragraph or block
    near "exit load", and extract load-value sentences via regex.
    """
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav"]):
        tag.decompose()

    text = soup.get_text(separator="\n")
    lines = [_clean(l) for l in text.splitlines() if _clean(l)]

    # Find the line index containing "exit load"
    anchor = None
    for i, line in enumerate(lines):
        if _EXIT_RE.search(line):
            anchor = i
            break

    if anchor is None:
        log.debug("exit load not found in visible text")
        return None

    # Gather a window of lines around the anchor (±5 lines)
    window = lines[max(0, anchor - 1) : anchor + 6]

    # Keep lines that have a load-value signal
    bullets = []
    for line in window:
        if (
            _EXIT_RE.search(line)
            or _LOAD_VALUE_RE.search(line)
            or any(
                kw in line.lower()
                for kw in ("if redeemed", "within", "year", "days", "allotment", "applicable", "lock")
            )
        ):
            if len(line) > 8:
                bullets.append(line)
        if len(bullets) == 3:
            break

    if not bullets:
        # Just take the anchor line and the two that follow
        bullets = [lines[anchor + j] for j in range(3) if anchor + j < len(lines)]

    if not bullets:
        return None

    log.info("Parsed exit load via visible-text fallback  bullets=%d", len(bullets))
    return _to_bullets(bullets)


# ── public API ────────────────────────────────────────────────────────────

def extract_exit_load(html: str, fund_name: str) -> tuple[list[str], str]:
    """
    Try each strategy in order; return (bullets, method_name).
    Raises ValueError if all strategies fail.
    """
    for strategy, method_name in [
        (parse_from_next_data, "next_data"),
        (parse_from_html_table, "html_table"),
        (parse_from_visible_text, "visible_text"),
    ]:
        try:
            result = strategy(html)
        except Exception as exc:  # noqa: BLE001
            log.warning("Strategy %s raised an error for %r: %s", method_name, fund_name, exc)
            result = None

        if result:
            log.info("exit load extracted  fund=%r  method=%s", fund_name, method_name)
            return result, method_name

    raise ValueError(f"Could not extract exit load for {fund_name!r} — all parse strategies failed")
