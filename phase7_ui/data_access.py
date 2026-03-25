from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def latest_file(pattern: str) -> Path | None:
    files = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def load_dashboard_bundle() -> dict[str, Any]:
    bundle: dict[str, Any] = {
        "summary_path": None,
        "summary": None,
        "pulse_path": None,
        "pulse": None,
        "email_report_path": None,
        "email_report": None,
    }

    summary_path = latest_file("phase6_ops/outputs/run_summary_*.json")
    if summary_path and summary_path.exists():
        bundle["summary_path"] = str(summary_path)
        bundle["summary"] = read_json(summary_path)

    pulse_path = latest_file("phase4_insights/outputs/pulse_*.md")
    if pulse_path and pulse_path.exists():
        bundle["pulse_path"] = str(pulse_path)
        bundle["pulse"] = read_text(pulse_path)

    email_report_path = Path("phase5_delivery/outputs/email_delivery_report.json")
    if email_report_path.exists():
        bundle["email_report_path"] = str(email_report_path)
        bundle["email_report"] = read_json(email_report_path)

    return bundle

