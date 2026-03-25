"""
Phase 4.5 entry point: Mutual Fund Fee Scraper.

Scrapes exit load details for all 10 configured Quant funds from their
public Groww pages and writes a structured JSON artifact.

Execution (from Milestone2/):
    python -m phase4_5_fee_scraper.scripts.run_phase4_5

Parse strategy per fund (first success wins):
    1. requests  → parse __NEXT_DATA__ JSON
    2. requests  → parse HTML table / visible text
    3. playwright → same parse strategies on fully-rendered HTML  (if USE_PLAYWRIGHT_FALLBACK=true)

Output:
    phase4_5_fee_scraper/outputs/mf_fee_data_<week>.json
"""

from __future__ import annotations

import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow running as a script from any working directory
_ROOT = Path(__file__).resolve().parent.parent.parent  # Milestone2/
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from phase4_5_fee_scraper.src.config import FUND_SOURCES, Phase45Config  # noqa: E402
from phase4_5_fee_scraper.src.parser import extract_exit_load  # noqa: E402
from phase4_5_fee_scraper.src.scraper import fetch_with_playwright, fetch_with_requests  # noqa: E402


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.getLogger(__name__).info("Wrote %s", path)


def scrape_fund(
    fund: dict[str, str],
    cfg: Phase45Config,
    now_utc: str,
) -> dict:
    """
    Scrape one fund with retry/backoff.  Returns a fund result dict.
    """
    log = logging.getLogger(__name__)
    name = fund["name"]
    url = fund["url"]

    last_error = ""
    html: str | None = None
    fetch_method = "requests"

    # ── try requests first (fast; works when Groww serves full SSR HTML) ──
    try:
        html = fetch_with_requests(url, timeout=cfg.request_timeout_seconds)
        if html is not None:
            fetch_method = "requests"
            log.info("Fetched  fund=%r  method=requests", name)
    except Exception as exc:  # noqa: BLE001
        last_error = str(exc)
        log.warning("requests fetch failed  fund=%r  error=%s", name, exc)

    # ── playwright fallback: used when requests returns a stub page ───────
    # Groww rate-limits rapid requests and serves a ~37 KB JS-only shell
    # without __NEXT_DATA__. Playwright renders the full page reliably.
    if html is None and cfg.use_playwright_fallback:
        log.info("Falling back to playwright  fund=%r", name)
        for attempt in range(1, cfg.max_retries + 1):
            try:
                html = fetch_with_playwright(url, timeout_ms=cfg.playwright_timeout_ms)
                fetch_method = "playwright"
                log.info("Fetched  fund=%r  method=playwright  attempt=%d", name, attempt)
                break
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                log.warning(
                    "playwright fetch failed  fund=%r  attempt=%d  error=%s", name, attempt, exc
                )
                if attempt < cfg.max_retries:
                    time.sleep(cfg.retry_backoff_seconds * attempt)

    if html is None:
        log.error("All fetch attempts failed  fund=%r  last_error=%s", name, last_error)
        return {
            "fund_name": name,
            "status": "scrape_failed",
            "exit_load_bullets": [],
            "parse_method": None,
            "fetch_method": None,
            "source_url": url,
            "last_scraped": now_utc,
            "error": f"fetch failed: {last_error}",
        }

    # ── parse exit load ───────────────────────────────────────────────────
    try:
        bullets, parse_method = extract_exit_load(html, name)
        log.info(
            "Parsed  fund=%r  fetch=%s  parse=%s  bullets=%d",
            name,
            fetch_method,
            parse_method,
            len(bullets),
        )
        return {
            "fund_name": name,
            "status": "success",
            "exit_load_bullets": bullets,
            "parse_method": parse_method,
            "fetch_method": fetch_method,
            "source_url": url,
            "last_scraped": now_utc,
            "error": None,
        }
    except ValueError as exc:
        last_error = str(exc)
        log.error("Parse failed  fund=%r  fetch=%s  error=%s", name, fetch_method, exc)
        return {
            "fund_name": name,
            "status": "parse_failed",
            "exit_load_bullets": [],
            "parse_method": None,
            "fetch_method": fetch_method,
            "source_url": url,
            "last_scraped": now_utc,
            "error": last_error,
        }


def main() -> None:
    _setup_logging()
    log = logging.getLogger(__name__)

    cfg = Phase45Config()
    now_utc = datetime.now(timezone.utc).isoformat()
    week = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    output_path = Path(cfg.output_dir) / f"mf_fee_data_{week}.json"

    log.info(
        "=== Phase 4.5 start  week=%s  funds=%d  playwright=%s ===",
        week,
        len(FUND_SOURCES),
        cfg.use_playwright_fallback,
    )

    fund_results: list[dict] = []
    for fund in FUND_SOURCES:
        log.info("--- Scraping: %s ---", fund["name"])
        result = scrape_fund(fund, cfg, now_utc)
        fund_results.append(result)
        # Small polite delay between requests
        time.sleep(1.5)

    scraped = sum(1 for r in fund_results if r["status"] == "success")
    failed = sum(1 for r in fund_results if r["status"] != "success")

    if scraped == 0:
        overall_status = "fail"
    elif failed > 0:
        overall_status = "partial"
    else:
        overall_status = "pass"

    payload = {
        "generated_at_utc": now_utc,
        "phase": "Phase 4.5 (Backend): Mutual Fund Fee Scraper",
        "week": week,
        "status": overall_status,
        "total_funds": len(FUND_SOURCES),
        "scraped_count": scraped,
        "failed_count": failed,
        "funds": fund_results,
    }

    _write_json(output_path, payload)
    log.info(
        "=== Phase 4.5 complete  status=%s  scraped=%d/%d ===",
        overall_status,
        scraped,
        len(FUND_SOURCES),
    )
    print(f"Status: {overall_status}  ({scraped}/{len(FUND_SOURCES)} funds scraped)")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
