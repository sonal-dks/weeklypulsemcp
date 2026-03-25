"""
Fetch a Groww mutual fund page HTML.

Primary:  requests  — fast; works when Next.js SSR embeds data in the initial HTML.
Fallback: playwright — headless Chromium for fully JS-rendered sections.
"""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)

# Mimic a real browser so Groww doesn't serve a bot-block page.
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
}


def fetch_with_requests(url: str, timeout: int = 30) -> str | None:
    """
    GET the page and return raw HTML, or None if Groww served a
    rate-limited / bot-detection stub (identified by missing __NEXT_DATA__
    or response size < 100 KB).
    Raises requests.HTTPError on 4xx/5xx.
    """
    log.debug("requests GET  url=%s", url)
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    html = resp.text
    log.debug("requests response  status=%d  bytes=%d", resp.status_code, len(resp.content))

    # Groww SSR pages are ~400-500 KB and always contain __NEXT_DATA__.
    # A smaller page means we hit a bot-detection / pre-render stub — not useful.
    if "__NEXT_DATA__" not in html or len(html) < 100_000:
        log.info(
            "requests returned a stub page (size=%d, has_next_data=%s) — will use playwright",
            len(html),
            "__NEXT_DATA__" in html,
        )
        return None

    return html


def fetch_with_playwright(url: str, timeout_ms: int = 30000) -> str:
    """
    Launch a headless Chromium browser, navigate to the page, wait for
    network idle, then return the fully-rendered HTML.

    Requires:
        pip install playwright
        playwright install chromium
    """
    log.debug("playwright GET  url=%s", url)
    try:
        from playwright.sync_api import sync_playwright  # lazy import — optional dep
    except ImportError as exc:
        raise ImportError(
            "playwright is not installed. Run: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(extra_http_headers={"Accept-Language": "en-US,en;q=0.9"})
            page.goto(url, timeout=timeout_ms, wait_until="networkidle")
            # Scroll halfway down to trigger any lazy-loaded sections
            page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
            page.wait_for_timeout(2000)
            html = page.content()
        finally:
            browser.close()

    log.debug("playwright response  bytes=%d", len(html))
    return html
