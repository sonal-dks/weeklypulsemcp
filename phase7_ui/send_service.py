"""Shared delivery logic for Phase 7 (Streamlit locally, FastAPI on Vercel)."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase5_delivery.src.combined_payload import (
    build_combined_payload,
    combined_payload_to_doc_text,
    combined_payload_to_html_email,
    find_latest_fee_data_path,
    load_fee_data,
    load_phase4_insights,
)
from phase5_delivery.src.config import Phase5Config
from phase5_delivery.src.delivery import (
    append_doc_with_retries,
    build_subject,
    deliver_with_retries,
    ensure_pulse_sections,
)

UI_DELIVERY_LOG = Path("phase7_ui/outputs/ui_delivery_runs.jsonl")
UI_ERRORS_LOG = Path("phase7_ui/outputs/ui_load_errors.log")


def log_load_error(error: str) -> None:
    UI_ERRORS_LOG.parent.mkdir(parents=True, exist_ok=True)
    payload = {"timestamp_utc": datetime.now(timezone.utc).isoformat(), "error": error}
    with UI_ERRORS_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def parse_recipients(raw_text: str) -> list[str]:
    parts = [x.strip() for x in re.split(r"[,\n;]+", raw_text) if x.strip()]
    unique: list[str] = []
    seen: set[str] = set()
    for p in parts:
        key = p.lower()
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique


def is_valid_email(email: str) -> bool:
    return re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email) is not None


def load_funds_lookup() -> dict[str, dict[str, Any]]:
    fee_path = find_latest_fee_data_path()
    if not fee_path:
        return {}
    try:
        fee_payload = load_fee_data(fee_path)
    except Exception as exc:  # noqa: BLE001
        log_load_error(str(exc))
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in fee_payload.get("funds", []):
        if not isinstance(row, dict):
            continue
        name = str(row.get("fund_name", "")).strip()
        if name:
            out[name] = row
    return out


def fee_blocks_for_selected(selected_names: list[str], funds_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for name in selected_names:
        row = funds_lookup.get(name)
        if not row or row.get("status") != "success":
            continue
        bullets = [str(b).strip() for b in (row.get("exit_load_bullets") or []) if str(b).strip()][:3]
        blocks.append(
            {
                "fund_name": name,
                "bullets": bullets,
                "source_url": str(row.get("source_url", "")).strip(),
            }
        )
    return blocks


def fee_preview_text(blocks: list[dict[str, Any]]) -> str:
    if not blocks:
        return "Fee Explainer\n\nNone selected."
    lines: list[str] = ["Fee Explainer", ""]
    for b in blocks:
        lines.append(b["fund_name"])
        for bullet in b.get("bullets", []):
            lines.append(f"- {bullet}")
        if b.get("source_url"):
            lines.append(f"Links: {b['source_url']}")
        lines.append("")
    return "\n".join(lines).strip()


def run_console_delivery(*, recipients: list[str], fee_funds: list[dict[str, Any]], week: str) -> dict[str, Any]:
    cfg = Phase5Config()
    if not recipients:
        raise ValueError("At least one recipient is required")

    insights_payload = load_phase4_insights(cfg.insights_path)
    flat_bullets: list[str] = []
    flat_links: list[str] = []
    for block in fee_funds:
        for b in block.get("bullets", []) or []:
            if b not in flat_bullets:
                flat_bullets.append(b)
        u = str(block.get("source_url", "")).strip()
        if u and u not in flat_links:
            flat_links.append(u)

    fee_scenario = "Mutual Fund Fee Explainer" if fee_funds else ""
    combined = build_combined_payload(
        report_date=week,
        insights_payload=insights_payload,
        fee_scenario=fee_scenario,
        fee_payload=None,
    )
    combined["fee_funds"] = fee_funds
    combined["fee_scenario"] = fee_scenario
    combined["explanation_bullets"] = flat_bullets
    combined["source_links"] = flat_links
    combined["last_checked"] = datetime.now(timezone.utc).date().isoformat()

    doc_text = combined_payload_to_doc_text(combined)
    body_errors = ensure_pulse_sections(doc_text)
    if body_errors:
        raise ValueError(f"Invalid composed body: {body_errors}")

    doc_result, doc_attempts = append_doc_with_retries(
        cfg,
        week=week,
        pulse_body=doc_text,
        max_retries=cfg.max_retries,
        retry_backoff_seconds=cfg.retry_backoff_seconds,
    )

    subject = build_subject(week)
    doc_url = str(doc_result.get("doc_url", "")).strip()
    email_body = combined_payload_to_html_email(combined, doc_url=doc_url)

    email_attempts: dict[str, Any] = {}
    for recipient in recipients:
        result, attempts = deliver_with_retries(
            cfg,
            mode="send",
            recipient=recipient,
            subject=subject,
            body=email_body,
            max_retries=cfg.max_retries,
            retry_backoff_seconds=cfg.retry_backoff_seconds,
            body_mime_type="text/html",
        )
        email_attempts[recipient] = {"result": result, "attempts": attempts}

    run_report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "week": week,
        "recipients": recipients,
        "fee_funds": fee_funds,
        "doc_result": doc_result,
        "doc_attempts": doc_attempts,
        "email_attempts": email_attempts,
    }
    UI_DELIVERY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with UI_DELIVERY_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(run_report, ensure_ascii=False) + "\n")
    return run_report
