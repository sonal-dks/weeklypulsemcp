from __future__ import annotations

import re
from pathlib import Path

from shared.week_utils import current_week_tag


def _extract_tag(name: str) -> str | None:
    """Extract week tag from a filename like ``insights_March-W4-2026.json``."""
    m = re.search(r"(?:insights|pulse|combined_payload|doc_append_report|mf_fee_data|themes|review_theme_map|theme_runs|run_summary|email_runs)_(.+)\.\w+$", name)
    return m.group(1) if m else None


def resolve_latest_phase4_paths(
    *,
    configured_pulse_path: str,
    configured_insights_path: str,
    outputs_dir: str = "phase4_insights/outputs",
) -> tuple[str, str, str]:
    """
    Pick the latest matching insights/pulse pair by week tag from outputs dir.
    Configured paths are used only when both exist.
    """
    c_pulse = configured_pulse_path.strip()
    c_ins = configured_insights_path.strip()
    if c_pulse and c_ins and Path(c_pulse).exists() and Path(c_ins).exists():
        cpd = _extract_tag(Path(c_pulse).name)
        cid = _extract_tag(Path(c_ins).name)
        if cpd and cid and cpd == cid:
            return c_pulse, c_ins, cpd

    out = Path(outputs_dir)
    if not out.exists():
        raise FileNotFoundError(f"Missing outputs directory: {outputs_dir}")

    insights_files = sorted(out.glob("insights_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    pulse_files = sorted(out.glob("pulse_*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not insights_files or not pulse_files:
        raise FileNotFoundError("Missing phase4 insights/pulse artifacts in phase4_insights/outputs")

    pulse_by_tag = {_extract_tag(p.name): str(p) for p in pulse_files if _extract_tag(p.name)}
    for p in insights_files:
        tag = _extract_tag(p.name)
        if tag and tag in pulse_by_tag:
            return pulse_by_tag[tag], str(p), tag

    raise FileNotFoundError("No matching insights + pulse pair found")


def list_available_weeks(outputs_dir: str = "phase4_insights/outputs") -> list[str]:
    """Return sorted list of week tags that have both insights + pulse artifacts (newest first by mtime)."""
    out = Path(outputs_dir)
    if not out.exists():
        return []

    insight_map: dict[str, float] = {}
    for p in out.glob("insights_*.json"):
        tag = _extract_tag(p.name)
        if tag:
            insight_map[tag] = p.stat().st_mtime

    pulse_tags = {_extract_tag(p.name) for p in out.glob("pulse_*.md") if _extract_tag(p.name)}
    common = insight_map.keys() & pulse_tags
    return sorted(common, key=lambda t: insight_map.get(t, 0), reverse=True)


def resolve_phase4_for_week(
    week: str,
    outputs_dir: str = "phase4_insights/outputs",
) -> tuple[str, str]:
    """Return (pulse_path, insights_path) for a specific week tag."""
    out = Path(outputs_dir)
    pulses = list(out.glob(f"pulse_{week}.md"))
    insights = list(out.glob(f"insights_{week}.json"))
    if not pulses or not insights:
        raise FileNotFoundError(f"No phase4 artifacts for week {week}")
    return str(pulses[0]), str(insights[0])


def find_latest_fee_data_path_for_week(
    week: str,
    default_dir: str = "phase4_5_fee_scraper/outputs",
) -> str | None:
    """Find fee data JSON for a specific week tag."""
    out = Path(default_dir)
    if not out.exists():
        return None
    exact = list(out.glob(f"mf_fee_data_{week}.json"))
    if exact:
        return str(exact[0])
    files = sorted(out.glob("mf_fee_data_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(files[0]) if files else None
