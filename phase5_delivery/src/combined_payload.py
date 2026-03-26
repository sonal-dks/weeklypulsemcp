import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any


def _date_only(iso_ts: str) -> str:
    # Accept "YYYY-MM-DD" or ISO timestamp; return YYYY-MM-DD if parseable.
    s = (iso_ts or "").strip()
    if not s:
        return ""
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).date().isoformat()
    except Exception:  # noqa: BLE001
        return s[:10]


def load_phase4_insights(insights_path: str) -> dict[str, Any]:
    payload = json.loads(Path(insights_path).read_text(encoding="utf-8"))
    if str(payload.get("status", "")).lower() != "pass":
        raise ValueError("Phase 4 insights status is not pass")
    return payload


def find_latest_fee_data_path(default_dir: str = "phase4_5_fee_scraper/outputs") -> str | None:
    out_dir = Path(default_dir)
    if not out_dir.exists():
        return None
    files = sorted(out_dir.glob("mf_fee_data_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(files[0]) if files else None


def load_fee_data(fee_data_path: str) -> dict[str, Any]:
    payload = json.loads(Path(fee_data_path).read_text(encoding="utf-8"))
    # allow partial/pass; just require expected keys
    if "funds" not in payload or not isinstance(payload["funds"], list):
        raise ValueError("Fee data artifact missing funds list")
    return payload


def build_combined_payload(
    *,
    report_date: str,
    insights_payload: dict[str, Any],
    fee_scenario: str,
    fee_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    themes = [str(t.get("theme", "")).strip() for t in (insights_payload.get("top_themes") or [])][:3]
    themes = [t for t in themes if t]

    quotes = [str(q.get("text", "")).strip() for q in (insights_payload.get("quotes") or [])][:3]
    quotes = [q for q in quotes if q]

    action_ideas = [str(a).strip() for a in (insights_payload.get("action_ideas") or [])][:3]
    action_ideas = [a for a in action_ideas if a]

    explanation_bullets: list[str] = []
    source_links: list[str] = []
    last_checked = ""

    if fee_payload:
        last_checked = _date_only(str(fee_payload.get("generated_at_utc") or fee_payload.get("week") or ""))
        for row in fee_payload.get("funds", []):
            if not isinstance(row, dict):
                continue
            if row.get("status") != "success":
                continue
            for b in row.get("exit_load_bullets", []) or []:
                s = str(b).strip()
                if s and s not in explanation_bullets:
                    explanation_bullets.append(s)
                if len(explanation_bullets) >= 3:
                    break
            url = str(row.get("source_url", "")).strip()
            if url and url not in source_links:
                source_links.append(url)
            if len(explanation_bullets) >= 3 and len(source_links) >= 2:
                break
        source_links = source_links[:2]

    combined = {
        "date": report_date,
        "weekly_pulse": {
            "themes": themes,
            "quotes": quotes,
            "action_ideas": action_ideas,
        },
        "fee_scenario": fee_scenario,
        "explanation_bullets": explanation_bullets,
        "source_links": source_links,
        "last_checked": last_checked or report_date,
        "fee_funds": [],
    }

    # minimal structural checks
    required = [
        "date",
        "weekly_pulse",
        "fee_scenario",
        "explanation_bullets",
        "source_links",
        "last_checked",
        "fee_funds",
    ]
    for k in required:
        if k not in combined:
            raise ValueError(f"Combined payload missing key: {k}")
    return combined


def combined_payload_to_doc_text(combined: dict[str, Any]) -> str:
    """Pulse-only text for Google Docs (no fee explainer — that goes only in email)."""
    date = str(combined.get("date", "")).strip()
    weekly = combined.get("weekly_pulse", {}) or {}
    themes = weekly.get("themes", []) or []
    quotes = weekly.get("quotes", []) or []
    actions = weekly.get("action_ideas", []) or []

    lines: list[str] = []
    lines.append(f"Weekly Groww Product Pulse - {date}")
    lines.append("")
    lines.append("Top Themes")
    for t in themes[:3]:
        lines.append(f"- {t}")
    lines.append("")
    lines.append("User Voice")
    for q in quotes[:3]:
        lines.append(f'- "{q}"')
    lines.append("")
    lines.append("Action Ideas")
    for a in actions[:3]:
        lines.append(f"- {a}")
    return "\n".join(lines).strip()


def combined_payload_to_html_email(combined: dict[str, Any], *, doc_url: str = "") -> str:
    """Rich HTML for email clients (inline CSS). Plain-text ledger stays in `combined_payload_to_doc_text`."""

    def esc(s: str) -> str:
        return html.escape(s, quote=False)

    def esc_attr(s: str) -> str:
        return html.escape(s, quote=True)

    date = str(combined.get("date", "")).strip()
    weekly = combined.get("weekly_pulse", {}) or {}
    themes = [esc(str(t).strip()) for t in (weekly.get("themes", []) or []) if str(t).strip()][:3]
    quotes = [str(q).strip() for q in (weekly.get("quotes", []) or []) if str(q).strip()][:3]
    actions = [esc(str(a).strip()) for a in (weekly.get("action_ideas", []) or []) if str(a).strip()][:3]
    fee_scenario = str(combined.get("fee_scenario", "")).strip()
    fee_bullets = combined.get("explanation_bullets", []) or []
    links = [str(u).strip() for u in (combined.get("source_links", []) or []) if str(u).strip()]
    last_checked = str(combined.get("last_checked", "")).strip()
    fee_funds_raw = combined.get("fee_funds") or []

    fee_funds: list[dict[str, Any]] = []
    if isinstance(fee_funds_raw, list):
        for row in fee_funds_raw:
            if isinstance(row, dict) and str(row.get("fund_name", "")).strip():
                fee_funds.append(row)

    card = "background:#ffffff;border-radius:12px;padding:28px 32px;margin:0 auto;max-width:600px;border:1px solid #e2e8f0;"
    h2 = "margin:28px 0 12px 0;font-size:15px;font-weight:600;color:#0f172a;letter-spacing:0.02em;text-transform:uppercase;"
    ul = "margin:8px 0 0 0;padding-left:20px;color:#334155;font-size:15px;line-height:1.55;"
    li = "margin:6px 0;"
    quote_style = "margin:12px 0 0 0;padding:14px 16px;border-left:4px solid #059669;background:#f8fafc;border-radius:0 8px 8px 0;color:#334155;font-size:15px;line-height:1.55;font-style:italic;"

    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        "<title>Weekly Groww Product Pulse</title>",
        "</head>",
        '<body style="margin:0;padding:0;background:#f1f5f9;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif;">',
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f1f5f9;padding:24px 12px;">',
        "<tr><td align=\"center\">",
        f'<div style="{card}">',
        '<div style="border-bottom:1px solid #e2e8f0;padding-bottom:20px;margin-bottom:4px;">',
        '<p style="margin:0 0 6px 0;font-size:12px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:0.08em;">'
        "Weekly digest</p>",
        f'<h1 style="margin:0;font-size:22px;font-weight:700;color:#0f172a;line-height:1.3;">Groww Product Pulse</h1>',
        f'<p style="margin:10px 0 0 0;font-size:15px;color:#64748b;">Report date · <strong style="color:#334155;">{esc(date)}</strong></p>',
        "</div>",
    ]

    parts.append(f'<h2 style="{h2}">Top themes</h2>')
    parts.append(f'<ul style="{ul}">')
    for t in themes:
        parts.append(f'<li style="{li}">{t}</li>')
    parts.append("</ul>")

    parts.append(f'<h2 style="{h2}">User voice</h2>')
    for q in quotes:
        parts.append(f'<blockquote style="{quote_style}">&ldquo;{esc(q)}&rdquo;</blockquote>')

    parts.append(f'<h2 style="{h2}">Action ideas</h2>')
    parts.append(f'<ul style="{ul}">')
    for a in actions:
        parts.append(f'<li style="{li}">{a}</li>')
    parts.append("</ul>")

    if fee_funds:
        parts.append(f'<h2 style="{h2}">Fee explainer</h2>')
        for block in fee_funds:
            name = esc(str(block.get("fund_name", "")).strip())
            bullets = [str(b).strip() for b in (block.get("bullets") or []) if str(b).strip()][:3]
            url = str(block.get("source_url", "")).strip()
            parts.append(f'<div style="margin-top:16px;padding:16px;background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;">')
            parts.append(f'<p style="margin:0 0 8px 0;font-weight:600;color:#0f172a;font-size:15px;">{name}</p>')
            parts.append(f'<ul style="{ul}">')
            for b in bullets:
                parts.append(f'<li style="{li}">{esc(b)}</li>')
            parts.append("</ul>")
            if url:
                parts.append(
                    f'<p style="margin:12px 0 0 0;font-size:14px;"><a href="{esc_attr(url)}" '
                    f'style="color:#059669;font-weight:500;">View source</a></p>'
                )
            parts.append("</div>")
    elif fee_scenario and fee_bullets:
        parts.append(f'<h2 style="{h2}">Fee explainer</h2>')
        parts.append(f'<ul style="{ul}">')
        for b in fee_bullets[:3]:
            parts.append(f'<li style="{li}">{esc(str(b).strip())}</li>')
        parts.append("</ul>")
        if links:
            link_bits = []
            for u in links:
                link_bits.append(
                    f'<a href="{esc_attr(u)}" style="color:#059669;font-weight:500;">{esc(u)}</a>'
                )
            parts.append(
                '<p style="margin:16px 0 0 0;font-size:14px;color:#64748b;">Sources · '
                + " · ".join(link_bits)
                + "</p>"
            )
        if last_checked:
            parts.append(
                f'<p style="margin:8px 0 0 0;font-size:13px;color:#94a3b8;">Last checked: {esc(last_checked)}</p>'
            )

    doc_url = doc_url.strip()
    if doc_url:
        parts.append(
            '<div style="margin-top:28px;padding-top:20px;border-top:1px solid #e2e8f0;text-align:center;">'
            f'<a href="{esc_attr(doc_url)}" style="display:inline-block;background:#059669;color:#ffffff !important;'
            'text-decoration:none;font-weight:600;font-size:14px;padding:12px 22px;border-radius:8px;">'
            "Open full ledger in Google Docs</a>"
            "</div>"
        )

    parts.extend(
        [
            '<p style="margin:24px 0 0 0;font-size:12px;color:#94a3b8;text-align:center;line-height:1.5;">'
            "Internal product pulse · automated summary of Play Store themes and actions."
            "</p>",
            "</div>",
            "</td></tr></table>",
            "</body></html>",
        ]
    )
    return "\n".join(parts)

