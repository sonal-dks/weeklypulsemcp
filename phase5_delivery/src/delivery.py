import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from phase5_delivery.src.config import Phase5Config
from phase5_delivery.src.gdocs_google_mcp_stdio import append_weekly_via_google_docs_mcp_sync
from phase5_delivery.src.gmail_gongrzhe_mcp_stdio import deliver_via_gmail_mcp_stdio_sync
from phase5_delivery.src.mcp_client import (
    DeliveryHardError,
    DeliveryTransientError,
    append_doc_via_mcp,
)


def week_tag_now() -> str:
    from shared.week_utils import current_week_tag
    return current_week_tag()


def load_validated_pulse(pulse_path: str, insights_path: str) -> str:
    insights = json.loads(Path(insights_path).read_text(encoding="utf-8"))
    status = str(insights.get("status", "")).lower()
    expected_pulse_path = str(insights.get("pulse_path", ""))
    if status != "pass":
        raise ValueError("Insights status is not pass; pulse cannot be delivered")
    if expected_pulse_path and expected_pulse_path != pulse_path:
        raise ValueError("PULSE_PATH does not match pulse_path in insights artifact")
    body = Path(pulse_path).read_text(encoding="utf-8").strip()
    if not body:
        raise ValueError("Pulse body is empty")
    return body


def build_subject(week_or_date: str) -> str:
    return f"Groww Weekly Product Pulse - {week_or_date}"


def validate_subject(subject: str) -> bool:
    return re.match(r"^Groww Weekly Product Pulse - .+$", subject) is not None


def extract_date_from_pulse_path(pulse_path: str) -> str:
    m = re.search(r"pulse_(.+)\.md$", pulse_path)
    return m.group(1) if m else week_tag_now()


def deliver_with_retries(
    cfg: Phase5Config,
    mode: str,
    recipient: str,
    subject: str,
    body: str,
    max_retries: int,
    retry_backoff_seconds: float,
    body_mime_type: str = "text/plain",
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []

    for attempt in range(1, max_retries + 1):
        try:
            result = deliver_via_gmail_mcp_stdio_sync(
                command=cfg.google_gmail_mcp_command.strip() or "npx",
                args=cfg.google_gmail_mcp_args_list(),
                extra_env=cfg.google_gmail_mcp_extra_env(),
                mode=mode,
                recipient=recipient,
                subject=subject,
                body=body,
                mime_type=body_mime_type,
            )
            attempts.append({"attempt": attempt, "status": "success", "result": result})
            return result, attempts
        except DeliveryTransientError as exc:
            attempts.append({"attempt": attempt, "status": "transient_error", "error": str(exc)})
            if attempt < max_retries:
                time.sleep(retry_backoff_seconds * attempt)
            else:
                raise
        except DeliveryHardError as exc:
            attempts.append({"attempt": attempt, "status": "hard_error", "error": str(exc)})
            raise
        except Exception as exc:  # noqa: BLE001
            attempts.append({"attempt": attempt, "status": "error", "error": str(exc)})
            if attempt < max_retries:
                time.sleep(retry_backoff_seconds * attempt)
                continue
            raise DeliveryHardError(f"Gmail MCP (stdio) failed: {exc}") from exc
    raise RuntimeError("Unreachable delivery retry state")


def ensure_pulse_sections(pulse_text: str) -> list[str]:
    errors: list[str] = []
    required_headers = [
        "Weekly Groww Product Pulse -",
        "Top Themes",
        "User Voice",
        "Action Ideas",
    ]
    for header in required_headers:
        if header not in pulse_text:
            errors.append(f"Missing required pulse section: {header}")
    return errors


def append_doc_with_retries(
    cfg: Phase5Config,
    week: str,
    pulse_body: str,
    max_retries: int,
    retry_backoff_seconds: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    attempts: list[dict[str, Any]] = []
    # `pulse_body` already starts with "Weekly Groww Product Pulse - {date}".
    # If we also add a section title here, Google Docs ends up with a duplicated
    # header line. Keep the week block header markers only.
    section_title = ""
    transport = (cfg.gdocs_mcp_transport or "http").strip().lower()

    for attempt in range(1, max_retries + 1):
        try:
            if transport == "stdio":
                result = append_weekly_via_google_docs_mcp_sync(
                    command=cfg.google_docs_mcp_command.strip() or "npx",
                    args=cfg.google_docs_mcp_args_list(),
                    extra_env=cfg.google_docs_mcp_extra_env(),
                    doc_id=cfg.google_doc_id,
                    doc_title=cfg.google_doc_title,
                    section_title=section_title,
                    pulse_body=pulse_body,
                    report_date=week,
                    insert_page_break=True,
                )
            else:
                result = append_doc_via_mcp(
                    endpoint=cfg.gdocs_mcp_endpoint,
                    api_key=cfg.gdocs_mcp_api_key,
                    doc_id=cfg.google_doc_id,
                    doc_title=cfg.google_doc_title,
                    section_title=section_title,
                    pulse_body=pulse_body,
                )
            attempts.append({"attempt": attempt, "status": "success", "result": result})
            return result, attempts
        except DeliveryTransientError as exc:
            attempts.append({"attempt": attempt, "status": "transient_error", "error": str(exc)})
            if attempt < max_retries:
                time.sleep(retry_backoff_seconds * attempt)
            else:
                raise
        except DeliveryHardError as exc:
            attempts.append({"attempt": attempt, "status": "hard_error", "error": str(exc)})
            raise
        except Exception as exc:  # noqa: BLE001
            if transport != "stdio":
                raise
            attempts.append({"attempt": attempt, "status": "error", "error": str(exc)})
            if attempt < max_retries:
                time.sleep(retry_backoff_seconds * attempt)
                continue
            raise DeliveryHardError(f"Google Docs MCP (stdio) failed: {exc}") from exc
    raise RuntimeError("Unreachable docs append retry state")
