from __future__ import annotations

import traceback
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from phase5_delivery.src.config import Phase5Config
from phase5_delivery.src.path_resolver import (
    find_latest_fee_data_path_for_week,
    list_available_weeks,
    resolve_latest_phase4_paths,
)
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


@app.get("/meta/week")
def meta_week() -> dict[str, str]:
    cfg = Phase5Config()
    _pulse_path, _insights_path, week = resolve_latest_phase4_paths(
        configured_pulse_path=cfg.pulse_path,
        configured_insights_path=cfg.insights_path,
    )
    return {"week": week}


@app.get("/weeks")
def available_weeks() -> dict[str, Any]:
    """All weeks that have both insights + pulse artifacts, newest first."""
    weeks = list_available_weeks()
    return {"weeks": weeks, "count": len(weeks)}


@app.get("/pulse/{week}")
def pulse_for_week(week: str) -> dict:
    """Return pulse markdown for a specific week tag."""
    from phase5_delivery.src.path_resolver import resolve_phase4_for_week
    from pathlib import Path

    try:
        pulse_path, _ = resolve_phase4_for_week(week)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"No pulse artifact for week {week}")
    return {"week": week, "markdown": Path(pulse_path).read_text(encoding="utf-8")}


@app.get("/funds")
def list_funds(week: str = "") -> dict[str, Any]:
    """Mutual fund names from fee artifact (optionally for a specific week)."""
    fee_path = None
    if week.strip():
        fee_path = find_latest_fee_data_path_for_week(week.strip())
    lookup = load_funds_lookup(fee_path)
    names = sorted(lookup.keys())
    return {"fund_names": names, "count": len(names)}


class DeliverRequest(BaseModel):
    recipients: str | list[str] = Field(
        ...,
        description="Comma/newline-separated string or list of email addresses",
    )
    fund_names: list[str] = Field(default_factory=list)
    delivery_token: str = Field(..., description="Admin-issued token required to trigger send")
    week: str | None = Field(default=None, description="Report week YYYY-Www; default = latest")


class DeliverResponse(BaseModel):
    ok: bool
    week: str
    recipients: list[str]
    doc_url: str
    message: str = ""


@app.post("/deliver", response_model=DeliverResponse)
def deliver(req: DeliverRequest) -> DeliverResponse:
    cfg = Phase5Config()
    if not (req.week or "").strip():
        _pulse_path, _insights_path, resolved_week = resolve_latest_phase4_paths(
            configured_pulse_path=cfg.pulse_path,
            configured_insights_path=cfg.insights_path,
        )
        week = resolved_week
    else:
        week = req.week.strip()

    if isinstance(req.recipients, str):
        recipients = parse_recipients(req.recipients)
    else:
        recipients = list(dict.fromkeys([r.strip() for r in req.recipients if str(r).strip()]))
    bad = [r for r in recipients if not is_valid_email(r)]
    if bad:
        raise HTTPException(status_code=400, detail=f"Invalid email(s): {', '.join(bad)}")
    if not recipients:
        raise HTTPException(status_code=400, detail="At least one recipient is required")

    try:
        fee_path = find_latest_fee_data_path_for_week(week)
        lookup = load_funds_lookup(fee_path)
        fee_blocks = fee_blocks_for_selected(req.fund_names, lookup)
        report = run_console_delivery(
            recipients=recipients,
            fee_funds=fee_blocks,
            week=week,
            delivery_token=req.delivery_token,
        )
    except Exception as exc:  # noqa: BLE001
        tb = traceback.format_exc()
        # Temporary diagnostics: write detailed traces for Vercel troubleshooting.
        log_load_error(f"/api/deliver failed: {exc}\n{tb}")
        print(f"[phase7][deliver_error] week={week} recipients={len(recipients)} err={exc}\n{tb}", flush=True)
        msg = str(exc)
        if "token" in msg.lower():
            raise HTTPException(status_code=403, detail=msg) from exc
        raise HTTPException(status_code=502, detail=msg) from exc

    doc_url = str(report.get("doc_url", "")).strip()
    return DeliverResponse(
        ok=True,
        week=week,
        recipients=recipients,
        doc_url=doc_url,
        message="Sent email to each recipient.",
    )


@app.get("/preview/fee")
def preview_fee(fund_names: str = "", week: str = "") -> dict[str, str]:
    """Plain-text fee preview for selected fund names (comma-separated)."""
    names = [x.strip() for x in fund_names.split(",") if x.strip()]
    fee_path = None
    if week.strip():
        fee_path = find_latest_fee_data_path_for_week(week.strip())
    lookup = load_funds_lookup(fee_path)
    blocks = fee_blocks_for_selected(names, lookup)
    return {"text": fee_preview_text(blocks)}
