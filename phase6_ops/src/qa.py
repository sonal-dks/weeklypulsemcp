import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\d{10}\b"),
    re.compile(r"\b(ticket|acct|account|id)\s*[:#-]?\s*[A-Za-z0-9-]{4,}\b", flags=re.IGNORECASE),
]


@dataclass
class GateResult:
    gate: str
    status: str  # pass/fail/warn
    details: dict[str, Any]


def _read_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def detect_latest_week_tag() -> str:
    # Prefer the phase5 combined payload (it’s what gets appended/sent).
    candidates: list[Path] = []
    for p in Path("phase5_delivery/outputs").glob("combined_payload_*.json"):
        candidates.append(p)
    for p in Path("phase4_insights/outputs").glob("pulse_*.md"):
        candidates.append(p)
    if not candidates:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    m = re.search(r"_(\d{4}-\d{2}-\d{2})\.", candidates[0].name)
    return m.group(1) if m else datetime.now(timezone.utc).strftime("%Y-%m-%d")


def check_theme_count(themes_payload: dict[str, Any]) -> GateResult:
    themes = themes_payload.get("themes", [])
    unique = list(dict.fromkeys([str(t).strip() for t in themes if str(t).strip()]))
    ok = len(unique) == 5
    return GateResult(
        gate="themes_exactly_5",
        status="pass" if ok else "fail",
        details={"theme_count": len(unique), "themes": unique},
    )


def check_insights_quotes_actions(insights_payload: dict[str, Any]) -> GateResult:
    quotes = insights_payload.get("quotes", [])
    actions = insights_payload.get("action_ideas", [])
    qn = len(quotes) if isinstance(quotes, list) else 0
    an = len(actions) if isinstance(actions, list) else 0
    ok = qn == 3 and an == 3
    return GateResult(
        gate="insights_3_quotes_3_actions",
        status="pass" if ok else "fail",
        details={"quotes_count": qn, "action_ideas_count": an},
    )


def check_pulse_wordcount_and_pii(pulse_text: str) -> GateResult:
    words = re.findall(r"\S+", pulse_text)
    wc_ok = len(words) <= 250
    pii_hits = 0
    for p in PII_PATTERNS:
        if p.search(pulse_text):
            pii_hits += 1
    ok = wc_ok and pii_hits == 0
    return GateResult(
        gate="pulse_wordcount_and_pii",
        status="pass" if ok else "fail",
        details={"word_count": len(words), "pii_pattern_matches": pii_hits},
    )


def check_delivery(email_report: dict[str, Any], doc_report: dict[str, Any]) -> GateResult:
    email_status = str(email_report.get("status", "")).lower()
    delivery_status = str(email_report.get("delivery_status", "")).lower()
    doc_status = str(doc_report.get("status", "")).lower()
    ok = email_status == "pass" and doc_status == "pass" and delivery_status in {"sent", "drafted", "draft_only_local", "sent_local"}
    return GateResult(
        gate="delivery_status",
        status="pass" if ok else "fail",
        details={
            "email_report_status": email_status,
            "delivery_status": delivery_status,
            "doc_report_status": doc_status,
            "doc_id": doc_report.get("doc_id"),
            "message_id": email_report.get("message_id"),
        },
    )


def check_run_completeness(paths: dict[str, str]) -> GateResult:
    missing: list[str] = []
    for k, p in paths.items():
        if p and not Path(p).exists():
            missing.append(k)
    ok = len(missing) == 0
    return GateResult(
        gate="run_completeness",
        status="pass" if ok else "fail",
        details={"missing": missing},
    )


def build_run_summary(*, week: str, paths: dict[str, str]) -> dict[str, Any]:
    config_check = _read_json(paths["phase1_config_check"])
    themes_payload = _read_json(paths["phase2_themes"])
    insights_payload = _read_json(paths["phase4_insights"])
    pulse_text = _read_text(paths["phase4_pulse"])
    combined_payload = _read_json(paths["phase5_combined_payload"])
    email_report = _read_json(paths["phase5_email_report"])
    doc_report = _read_json(paths["phase5_doc_report"])

    gates: list[GateResult] = []
    gates.append(check_run_completeness(paths))
    gates.append(check_theme_count(themes_payload))
    gates.append(check_insights_quotes_actions(insights_payload))
    gates.append(check_pulse_wordcount_and_pii(pulse_text))
    gates.append(check_delivery(email_report, doc_report))

    overall = "pass" if all(g.status == "pass" for g in gates) else "fail"

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 6 (Backend): Orchestration, Observability, and QA",
        "week": week,
        "status": overall,
        "inputs": {
            "config_check": paths["phase1_config_check"],
            "themes": paths["phase2_themes"],
            "insights": paths["phase4_insights"],
            "pulse": paths["phase4_pulse"],
            "combined_payload": paths["phase5_combined_payload"],
            "doc_append_report": paths["phase5_doc_report"],
            "email_delivery_report": paths["phase5_email_report"],
        },
        "high_level_metrics": {
            "theme_summary_counts": themes_payload.get("theme_summary_counts", {}),
            "word_count": len(re.findall(r"\S+", pulse_text)),
            "email_delivery_status": email_report.get("delivery_status"),
        },
        "combined_payload_snapshot": {
            "fee_scenario": combined_payload.get("fee_scenario"),
            "last_checked": combined_payload.get("last_checked"),
            "source_links": combined_payload.get("source_links", [])[:3],
        },
        "gates": [asdict(g) for g in gates],
        "upstream_status": {
            "phase1": config_check.get("status"),
            "phase4": insights_payload.get("status"),
            "phase5": email_report.get("status"),
        },
    }

