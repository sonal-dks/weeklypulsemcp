from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from phase5_delivery.src.config import Phase5Config
from phase5_delivery.src.path_resolver import (
    list_available_weeks,
    resolve_latest_phase4_paths,
    resolve_phase4_for_week,
    find_latest_fee_data_path_for_week,
)
from phase7_ui.send_service import (
    fee_blocks_for_selected,
    fee_preview_text,
    is_valid_email,
    load_funds_lookup,
    log_load_error,
    parse_recipients,
    run_console_delivery,
)


def _inject_theme() -> None:
    st.markdown(
        """
        <style>
        .main { background: #f7f7f8 !important; }
        .block-container { padding-top: 2rem; max-width: 960px; }
        h1 { color: #0d0d0d !important; font-weight: 600; letter-spacing: -0.025em; }

        [data-testid="column"] .stMarkdown { opacity: 1 !important; }

        .preview-wrap { margin-bottom: 0.5rem; }
        .preview-title {
          color: #0d0d0d !important;
          font-size: 14px;
          font-weight: 600;
          margin: 0 0 10px 0;
          letter-spacing: -0.01em;
        }
        .preview-card {
          background: #ffffff !important;
          border: 1px solid #e5e5e5;
          border-radius: 14px;
          padding: 16px 18px;
          box-shadow: 0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04);
        }
        .preview-scroll {
          max-height: 440px;
          overflow-y: auto;
          overflow-x: auto;
          white-space: pre-wrap;
          word-wrap: break-word;
          line-height: 1.65;
          color: #0d0d0d !important;
          opacity: 1 !important;
          font-size: 13.5px;
          -webkit-font-smoothing: antialiased;
          font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }
        .preview-scroll::-webkit-scrollbar {
          width: 6px;
        }
        .preview-scroll::-webkit-scrollbar-thumb {
          background: #d1d5db;
          border-radius: 3px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _preview_block(title: str, body_text: str) -> str:
    safe = html.escape(body_text)
    return (
        f'<div class="preview-wrap">'
        f'<h3 class="preview-title">{html.escape(title)}</h3>'
        f'<div class="preview-card"><div class="preview-scroll">{safe}</div></div>'
        f"</div>"
    )


def _load_pulse_text(path: str) -> str:
    p = Path(path)
    if not p.exists():
        return "Pulse file not found."
    return p.read_text(encoding="utf-8").strip() or "Pulse file is empty."


def main() -> None:
    st.set_page_config(page_title="Groww Pulse Send", layout="wide")
    _inject_theme()
    st.title("Weekly Pulse Delivery")

    cfg = Phase5Config()
    weeks = list_available_weeks()
    if not weeks:
        _pulse_path, _insights_path, latest = resolve_latest_phase4_paths(
            configured_pulse_path=cfg.pulse_path,
            configured_insights_path=cfg.insights_path,
        )
        weeks = [latest]

    selected_week = st.selectbox("Report week", weeks, index=0)
    week = selected_week or weeks[0]

    try:
        pulse_path, _insights_path = resolve_phase4_for_week(week)
    except FileNotFoundError:
        pulse_path, _insights_path, _w = resolve_latest_phase4_paths(
            configured_pulse_path=cfg.pulse_path,
            configured_insights_path=cfg.insights_path,
        )
    pulse_text = _load_pulse_text(pulse_path)

    fee_path = find_latest_fee_data_path_for_week(week)
    funds_lookup = load_funds_lookup(fee_path)
    fund_names = sorted(funds_lookup.keys())

    if "mf_multiselect_pick" not in st.session_state:
        st.session_state["mf_multiselect_pick"] = []

    recipients_input = st.text_area(
        "Email IDs (multiple)",
        placeholder="one@example.com, two@example.com",
        height=90,
    )
    delivery_token_input = st.text_input(
        "Delivery token",
        type="password",
        placeholder="Enter admin token to enable send",
    )

    st.markdown("**Mutual funds (fee explainer — email only, not in Google Doc)**")
    st.caption("Pick any number of funds. Fee data is included in the email body only.")
    ba, bb = st.columns(2)
    with ba:
        if st.button("Select all funds", use_container_width=True) and fund_names:
            st.session_state["mf_multiselect_pick"] = list(fund_names)
            st.rerun()
    with bb:
        if st.button("Clear selection", use_container_width=True):
            st.session_state["mf_multiselect_pick"] = []
            st.rerun()

    selected_funds = st.multiselect(
        "Choose fund(s)",
        options=fund_names,
        key="mf_multiselect_pick",
        placeholder="Select one or more mutual funds…",
        label_visibility="collapsed",
    )

    fee_blocks = fee_blocks_for_selected(selected_funds, funds_lookup)
    recipients = parse_recipients(recipients_input)
    invalid = [r for r in recipients if not is_valid_email(r)]
    send_disabled = (not recipients) or bool(invalid) or (not delivery_token_input.strip())

    if invalid:
        st.error("Invalid email IDs found. Please fix and retry.")
    if not fund_names:
        st.warning("No mutual fund data found. Run Phase 4.5 first.")
    elif selected_funds and not fee_blocks:
        st.warning("None of the selected funds have successful fee data. Adjust your selection.")

    if st.button("Send email", type="primary", use_container_width=True, disabled=send_disabled):
        try:
            run_console_delivery(
                recipients=recipients,
                fee_funds=fee_blocks,
                week=week,
                delivery_token=delivery_token_input,
            )
            st.success("Email sent.")
        except Exception as exc:  # noqa: BLE001
            log_load_error(str(exc))
            st.error(str(exc))

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(_preview_block("Weekly Pulse Preview", pulse_text), unsafe_allow_html=True)
    with col2:
        fee_preview = fee_preview_text(fee_blocks)
        st.markdown(_preview_block("Fee Explainer Preview (email only)", fee_preview), unsafe_allow_html=True)


if __name__ == "__main__":
    main()
