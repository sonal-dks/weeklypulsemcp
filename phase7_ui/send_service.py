"""Shared delivery logic for Phase 7 (Streamlit locally, FastAPI on Vercel).

Google Doc append: pulse-only text (same for everyone, static per week).
Email: pulse + selected fee explainer (varies per send).
"""

from __future__ import annotations

import base64
import binascii
import json
import os
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
    build_subject,
    deliver_with_retries,
    ensure_pulse_sections,
)
from phase5_delivery.src.path_resolver import (
    find_latest_fee_data_path_for_week,
    resolve_latest_phase4_paths,
    resolve_phase4_for_week,
)

UI_DELIVERY_LOG = Path("phase7_ui/outputs/ui_delivery_runs.jsonl")
UI_ERRORS_LOG = Path("phase7_ui/outputs/ui_load_errors.log")


def _ensure_gmail_credentials_file_from_env() -> None:
    """
    Materialize Gmail MCP credentials from env for serverless runtimes (e.g., Vercel).

    Priority:
    1) Existing GMAIL_CREDENTIALS_PATH file (do nothing)
    2) GMAIL_CREDENTIALS_JSON_B64 (base64 JSON) -> write /tmp/gmail-credentials.json
    3) GMAIL_CREDENTIALS_JSON (raw JSON) -> write /tmp/gmail-credentials.json
    """
    existing = os.environ.get("GMAIL_CREDENTIALS_PATH", "").strip()
    if existing and Path(existing).is_file():
        return

    target = "/tmp/gmail-credentials.json"
    raw_b64 = os.environ.get("GMAIL_CREDENTIALS_JSON_B64", "").strip()
    raw_json = os.environ.get("GMAIL_CREDENTIALS_JSON", "").strip()
    payload = ""

    if raw_b64:
        try:
            payload = base64.b64decode(raw_b64).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise ValueError("Invalid GMAIL_CREDENTIALS_JSON_B64. Must be valid base64-encoded JSON.") from exc
    elif raw_json:
        payload = raw_json
    else:
        return

    try:
        parsed = json.loads(payload)
        if not isinstance(parsed, dict):
            raise ValueError("Gmail credentials JSON must be an object.")
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid Gmail credentials JSON in environment.") from exc

    Path(target).write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
    os.environ["GMAIL_CREDENTIALS_PATH"] = target


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


def assert_valid_delivery_token(provided_token: str, cfg: Phase5Config) -> None:
    expected = cfg.delivery_trigger_token.strip()
    if not expected:
        raise ValueError("Delivery token is not configured. Please contact admin.")
    if provided_token.strip() != expected:
        raise ValueError("Token wrong. Please get token from admin.")


def load_funds_lookup(fee_path: str | None = None) -> dict[str, dict[str, Any]]:
    if not fee_path:
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


def run_console_delivery(
    *,
    recipients: list[str],
    fee_funds: list[dict[str, Any]],
    week: str,
    delivery_token: str,
) -> dict[str, Any]:
    """Send email only (no Doc append here — Doc is handled by the scheduler)."""
    _ensure_gmail_credentials_file_from_env()
    cfg = Phase5Config()
    if not recipients:
        raise ValueError("At least one recipient is required")
    assert_valid_delivery_token(delivery_token, cfg)

    try:
        pulse_path, insights_path = resolve_phase4_for_week(week)
    except FileNotFoundError:
        _pulse_path, insights_path, _resolved_week = resolve_latest_phase4_paths(
            configured_pulse_path=cfg.pulse_path,
            configured_insights_path=cfg.insights_path,
        )

    insights_payload = load_phase4_insights(insights_path)
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

    doc_url = ""
    if cfg.google_doc_id:
        doc_url = f"https://docs.google.com/document/d/{cfg.google_doc_id}/edit"

    subject = build_subject(week)
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
        "doc_url": doc_url,
        "email_attempts": email_attempts,
    }
    UI_DELIVERY_LOG.parent.mkdir(parents=True, exist_ok=True)
    with UI_DELIVERY_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(run_report, ensure_ascii=False) + "\n")
    return run_report
