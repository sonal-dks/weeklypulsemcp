"""
Phase 5 scheduler script: Google Doc append only (pulse text, no fee data, no email).

Email delivery is triggered exclusively from the Phase 7 UI.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from phase5_delivery.src.config import Phase5Config
from phase5_delivery.src.combined_payload import (
    build_combined_payload,
    combined_payload_to_doc_text,
    load_phase4_insights,
)
from phase5_delivery.src.delivery import (
    append_doc_with_retries,
    ensure_pulse_sections,
)
from phase5_delivery.src.path_resolver import resolve_latest_phase4_paths


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    cfg = Phase5Config()
    output_dir = Path(cfg.output_dir)
    pulse_path, insights_path, week = resolve_latest_phase4_paths(
        configured_pulse_path=cfg.pulse_path,
        configured_insights_path=cfg.insights_path,
    )
    doc_report_path = output_dir / f"doc_append_report_{week}.json"

    rule_errors = cfg.validate_rules()
    if rule_errors:
        payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "phase": "Phase 5 (Backend): Google Doc Append",
            "status": "fail",
            "errors": rule_errors,
        }
        _write_json(doc_report_path, payload)
        print(f"Wrote {doc_report_path}")
        print("Status: fail")
        return

    try:
        insights_payload = load_phase4_insights(insights_path)

        combined = build_combined_payload(
            report_date=week,
            insights_payload=insights_payload,
            fee_scenario="",
            fee_payload=None,
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

        payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "phase": "Phase 5 (Backend): Google Doc Append",
            "status": "pass",
            "week": week,
            "source_pulse_path": pulse_path,
            "source_insights_path": insights_path,
            "combined_payload_path": str(combined_path),
            "doc_id": doc_result.get("doc_id"),
            "doc_url": doc_result.get("doc_url", ""),
            "section_title": doc_result.get("section_title", ""),
            "section_ref": doc_result.get("section_ref", ""),
            "provider": doc_result.get("provider"),
            "attempts": doc_attempts,
        }
        _write_json(doc_report_path, payload)
        print(f"Wrote {doc_report_path}")
        print("Status: pass")
    except Exception as exc:  # noqa: BLE001
        payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "phase": "Phase 5 (Backend): Google Doc Append",
            "status": "doc_append_failed",
            "source_pulse_path": pulse_path,
            "source_insights_path": insights_path,
            "error": str(exc),
        }
        _write_json(doc_report_path, payload)
        print(f"Wrote {doc_report_path}")
        print(f"Status: doc_append_failed")


if __name__ == "__main__":
    main()
