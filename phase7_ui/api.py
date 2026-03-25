from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from phase5_delivery.src.config import Phase5Config
from phase5_delivery.src.delivery import extract_date_from_pulse_path
from phase7_ui.data_access import load_dashboard_bundle
from phase7_ui.send_service import (
    fee_blocks_for_selected,
    fee_preview_text,
    is_valid_email,
    load_funds_lookup,
    log_load_error,
    parse_recipients,
    run_console_delivery,
)


app = FastAPI(title="Groww Pulse API", version="1.0.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/latest/summary")
def latest_summary() -> dict:
    bundle = load_dashboard_bundle()
    if not bundle["summary"]:
        raise HTTPException(status_code=404, detail="No run summary artifact found")
    return {"path": bundle["summary_path"], "data": bundle["summary"]}


@app.get("/latest/pulse")
def latest_pulse() -> dict:
    bundle = load_dashboard_bundle()
    if not bundle["pulse"]:
        raise HTTPException(status_code=404, detail="No pulse artifact found")
    return {"path": bundle["pulse_path"], "markdown": bundle["pulse"]}


@app.get("/latest/delivery")
def latest_delivery() -> dict:
    bundle = load_dashboard_bundle()
    if not bundle["email_report"]:
        raise HTTPException(status_code=404, detail="No email delivery report found")
    return {"path": bundle["email_report_path"], "data": bundle["email_report"]}


@app.get("/meta/week")
def meta_week() -> dict[str, str]:
    cfg = Phase5Config()
    return {"week": extract_date_from_pulse_path(cfg.pulse_path)}


@app.get("/funds")
def list_funds() -> dict[str, Any]:
    """Mutual fund names from latest Phase 4.5 fee artifact (for multi-select UI)."""
    lookup = load_funds_lookup()
    names = sorted(lookup.keys())
    return {"fund_names": names, "count": len(names)}


class DeliverRequest(BaseModel):
    recipients: str | list[str] = Field(
        ...,
        description="Comma/newline-separated string or list of email addresses",
    )
    fund_names: list[str] = Field(default_factory=list)
    week: str | None = Field(default=None, description="Report date YYYY-MM-DD; default from pulse path in .env")


class DeliverResponse(BaseModel):
    ok: bool
    week: str
    recipients: list[str]
    doc_url: str
    message: str = ""


@app.post("/deliver", response_model=DeliverResponse)
def deliver(req: DeliverRequest) -> DeliverResponse:
    cfg = Phase5Config()
    week = (req.week or "").strip() or extract_date_from_pulse_path(cfg.pulse_path)
    if isinstance(req.recipients, str):
        recipients = parse_recipients(req.recipients)
    else:
        recipients = list(dict.fromkeys([r.strip() for r in req.recipients if str(r).strip()]))
    bad = [r for r in recipients if not is_valid_email(r)]
    if bad:
        raise HTTPException(status_code=400, detail=f"Invalid email(s): {', '.join(bad)}")
    if not recipients:
        raise HTTPException(status_code=400, detail="At least one recipient is required")

    lookup = load_funds_lookup()
    fee_blocks = fee_blocks_for_selected(req.fund_names, lookup)
    try:
        report = run_console_delivery(recipients=recipients, fee_funds=fee_blocks, week=week)
    except Exception as exc:  # noqa: BLE001
        log_load_error(str(exc))
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    doc_url = str((report.get("doc_result") or {}).get("doc_url", "")).strip()
    return DeliverResponse(
        ok=True,
        week=week,
        recipients=recipients,
        doc_url=doc_url,
        message="Appended to doc and sent email to each recipient.",
    )


@app.get("/preview/fee")
def preview_fee(fund_names: str = "") -> dict[str, str]:
    """Plain-text fee preview for selected fund names (comma-separated)."""
    names = [x.strip() for x in fund_names.split(",") if x.strip()]
    lookup = load_funds_lookup()
    blocks = fee_blocks_for_selected(names, lookup)
    return {"text": fee_preview_text(blocks)}
