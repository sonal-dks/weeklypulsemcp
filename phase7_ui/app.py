from __future__ import annotations

import html
from pathlib import Path

import streamlit as st

from phase5_delivery.src.config import Phase5Config
from phase5_delivery.src.delivery import extract_date_from_pulse_path
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
        .main { background: linear-gradient(180deg, #0b1020 0%, #10172a 100%); }
        .block-container { padding-top: 1.5rem; max-width: 1200px; }
        h1 { color: #f8fafc !important; font-weight: 600; letter-spacing: -0.02em; }

        /* Streamlit sometimes mutes markdown; keep preview columns crisp */
        [data-testid="column"] .stMarkdown { opacity: 1 !important; }

        .preview-wrap { margin-bottom: 0.5rem; }
        .preview-title {
          color: #f8fafc !important;
          font-size: 1.125rem;
          font-weight: 650;
          margin: 0 0 12px 0;
          letter-spacing: -0.02em;
        }
        .preview-card {
          background: #162039 !important;
          border: 1px solid rgba(255,255,255,0.22);
          border-radius: 14px;
          padding: 16px 18px;
          box-shadow: 0 4px 20px rgba(0,0,0,0.35);
        }
        .preview-scroll {
          max-height: 440px;
          overflow-y: auto;
          overflow-x: auto;
          white-space: pre-wrap;
          word-wrap: break-word;
          line-height: 1.58;
          color: #f8fafc !important;
          opacity: 1 !important;
          font-size: 15px;
          font-weight: 500;
          -webkit-font-smoothing: antialiased;
          font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        }
        .preview-scroll::-webkit-scrollbar {
          width: 8px;
        }
        .preview-scroll::-webkit-scrollbar-thumb {
          background: rgba(255,255,255,0.28);
          border-radius: 6px;
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
    week = extract_date_from_pulse_path(cfg.pulse_path)
    pulse_text = _load_pulse_text(cfg.pulse_path)

    funds_lookup = load_funds_lookup()
    fund_names = sorted(funds_lookup.keys())

    if "mf_multiselect_pick" not in st.session_state:
        st.session_state["mf_multiselect_pick"] = []

    recipients_input = st.text_area(
        "Email IDs (multiple)",
        placeholder="one@example.com, two@example.com",
        height=90,
    )

    st.markdown("**Mutual funds (fee explainer)**")
    st.caption("Pick any number of funds — 1, 2, 3, … — or use **Select all** / **Clear**.")
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
    send_disabled = (not recipients) or bool(invalid)

    if invalid:
        st.error("Invalid email IDs found. Please fix and retry.")
    if not fund_names:
        st.warning("No mutual fund data found. Run Phase 4.5 first.")
    elif selected_funds and not fee_blocks:
        st.warning("None of the selected funds have successful fee data. Adjust your selection.")

    if st.button("Append to doc and send email", type="primary", use_container_width=True, disabled=send_disabled):
        try:
            run_console_delivery(recipients=recipients, fee_funds=fee_blocks, week=week)
            st.success("Appended and sent.")
        except Exception as exc:  # noqa: BLE001
            log_load_error(str(exc))
            st.error(str(exc))

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(_preview_block("Weekly Pulse Preview", pulse_text), unsafe_allow_html=True)
    with col2:
        fee_preview = fee_preview_text(fee_blocks)
        st.markdown(_preview_block("Fee Explainer Preview", fee_preview), unsafe_allow_html=True)


if __name__ == "__main__":
    main()
