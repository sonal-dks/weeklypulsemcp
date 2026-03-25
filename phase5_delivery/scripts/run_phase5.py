import json
from datetime import datetime, timezone
from pathlib import Path

from phase5_delivery.src.config import Phase5Config
from phase5_delivery.src.combined_payload import (
    build_combined_payload,
    combined_payload_to_doc_text,
    combined_payload_to_html_email,
    find_latest_fee_data_path,
    load_fee_data,
    load_phase4_insights,
)
from phase5_delivery.src.delivery import (
    append_doc_with_retries,
    build_subject,
    deliver_with_retries,
    ensure_pulse_sections,
    extract_date_from_pulse_path,
    validate_subject,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    cfg = Phase5Config()
    output_dir = Path(cfg.output_dir)
    week = extract_date_from_pulse_path(cfg.pulse_path)
    runs_path = output_dir / f"email_runs_{week}.json"
    report_path = output_dir / "email_delivery_report.json"
    doc_report_path = output_dir / f"doc_append_report_{week}.json"

    rule_errors = cfg.validate_rules()
    if rule_errors:
        payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "phase": "Phase 5 (Backend): Email Draft and MCP Delivery",
            "status": "fail",
            "mode": cfg.delivery_mode,
            "errors": rule_errors,
        }
        _write_json(report_path, payload)
        _write_json(runs_path, payload)
        _write_json(doc_report_path, payload)
        print(f"Wrote {report_path}")
        print(f"Wrote {runs_path}")
        print(f"Wrote {doc_report_path}")
        print("Status: fail")
        return

    try:
        insights_payload = load_phase4_insights(cfg.insights_path)

        # Fee data is optional; prefer explicit FEE_DATA_PATH, else latest in phase4_5 outputs.
        fee_payload = None
        fee_path = cfg.fee_data_path.strip() or (find_latest_fee_data_path() or "")
        if fee_path:
            fee_payload = load_fee_data(fee_path)

        subject = build_subject(week)
        if not validate_subject(subject):
            raise ValueError("Subject does not match required format")

        combined = build_combined_payload(
            report_date=week,
            insights_payload=insights_payload,
            fee_scenario=cfg.fee_scenario,
            fee_payload=fee_payload,
        )
        combined_path = output_dir / f"combined_payload_{week}.json"
        _write_json(combined_path, combined)

        doc_text = combined_payload_to_doc_text(combined)
        body_errors = ensure_pulse_sections(doc_text)
        if body_errors:
            raise ValueError(f"Combined payload formatting validation failed: {body_errors}")

        doc_result, doc_attempts = append_doc_with_retries(
            cfg,
            week=week,
            pulse_body=doc_text,
            max_retries=cfg.max_retries,
            retry_backoff_seconds=cfg.retry_backoff_seconds,
        )
        doc_payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "phase": "Phase 5 (Backend): Email Draft and MCP Delivery",
            "status": "pass",
            "week": week,
            "doc_id": doc_result.get("doc_id"),
            "doc_url": doc_result.get("doc_url", ""),
            "section_title": doc_result.get("section_title", ""),
            "section_ref": doc_result.get("section_ref", ""),
            "provider": doc_result.get("provider"),
            "attempts": doc_attempts,
        }
        _write_json(doc_report_path, doc_payload)

        doc_url = str(doc_result.get("doc_url", "")).strip()
        email_body = combined_payload_to_html_email(combined, doc_url=doc_url)

        result, attempts = deliver_with_retries(
            cfg,
            mode=cfg.delivery_mode,
            recipient=cfg.email_recipient.strip(),
            subject=subject,
            body=email_body,
            max_retries=cfg.max_retries,
            retry_backoff_seconds=cfg.retry_backoff_seconds,
            body_mime_type="text/html",
        )

        payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "phase": "Phase 5 (Backend): Email Draft and MCP Delivery",
            "status": "pass",
            "mode": cfg.delivery_mode,
            "recipient": cfg.email_recipient.strip(),
            "subject": subject,
            "source_insights_path": cfg.insights_path,
            "fee_data_path_used": fee_path,
            "combined_payload_path": str(combined_path),
            "doc_id": doc_result.get("doc_id"),
            "doc_url": doc_result.get("doc_url", ""),
            "doc_section_title": doc_result.get("section_title", ""),
            "doc_section_ref": doc_result.get("section_ref", ""),
            "message_id": result.get("message_id"),
            "delivery_status": result.get("status"),
            "provider": result.get("provider"),
            "doc_append_attempts": doc_attempts,
            "attempts": attempts,
        }
        _write_json(report_path, payload)
        _write_json(runs_path, payload)
        print(f"Wrote {report_path}")
        print(f"Wrote {runs_path}")
        print(f"Wrote {doc_report_path}")
        print("Status: pass")
    except Exception as exc:  # noqa: BLE001
        if "Docs MCP" in str(exc) or "doc" in str(exc).lower():
            status = "doc_append_failed"
        else:
            status = "delivery_failed"
        payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "phase": "Phase 5 (Backend): Email Draft and MCP Delivery",
            "status": status,
            "mode": cfg.delivery_mode,
            "recipient": cfg.email_recipient.strip(),
            "source_pulse_path": cfg.pulse_path,
            "source_insights_path": cfg.insights_path,
            "error": str(exc),
        }
        _write_json(report_path, payload)
        _write_json(runs_path, payload)
        if status == "doc_append_failed":
            _write_json(doc_report_path, payload)
        print(f"Wrote {report_path}")
        print(f"Wrote {runs_path}")
        if status == "doc_append_failed":
            print(f"Wrote {doc_report_path}")
        print(f"Status: {status}")


if __name__ == "__main__":
    main()
