import json
from datetime import datetime, timezone
from pathlib import Path

from phase4_insights.src.config import Phase4Config
from phase4_insights.src.insights import (
    compose_pulse_markdown_strict,
    compose_pulse_markdown,
    deterministic_pulse_fallback,
    generate_action_ideas,
    load_inputs,
    rank_top_themes,
    select_quotes,
    validate_pulse,
)


def _week_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    cfg = Phase4Config()
    errors = cfg.validate_rules()

    out_dir = Path(cfg.output_dir)
    tag = _week_tag()
    insights_path = out_dir / f"insights_{tag}.json"
    pulse_path = out_dir / f"pulse_{tag}.md"

    if errors:
        _write_json(
            insights_path,
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "phase": "Phase 4 (Backend): Insights + One-Page Composition (Integrated)",
                "status": "fail",
                "errors": errors,
            },
        )
        print(f"Wrote {insights_path}")
        print("Status: fail")
        return

    try:
        themes, mapping, distribution, processed_lookup = load_inputs(
            cfg.themes_path,
            cfg.review_theme_map_path,
            cfg.processed_reviews_path,
            cfg.cluster_distribution_path,
        )
        top_themes = rank_top_themes(themes, mapping, distribution, top_n=cfg.top_themes_count)
        quotes = select_quotes(mapping, top_themes, processed_lookup=processed_lookup, quote_count=3)
        report_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        action_ideas = generate_action_ideas(
            api_key=cfg.gemini_api_key,
            model=cfg.gemini_model,
            top_themes=top_themes,
            quotes=quotes,
        )
        pulse = compose_pulse_markdown(
            api_key=cfg.gemini_api_key,
            model=cfg.gemini_model,
            top_themes=top_themes,
            quotes=quotes,
            action_ideas=action_ideas,
            report_date=report_date,
        )
        pulse_errors = validate_pulse(pulse)
        if pulse_errors:
            pulse = compose_pulse_markdown_strict(
                api_key=cfg.gemini_api_key,
                model=cfg.gemini_model,
                top_themes=top_themes,
                quotes=quotes,
                action_ideas=action_ideas,
                report_date=report_date,
            )
            pulse_errors = validate_pulse(pulse)
        if pulse_errors:
            pulse = deterministic_pulse_fallback(top_themes, quotes, action_ideas, report_date=report_date)
            pulse_errors = validate_pulse(pulse)
        if pulse_errors:
            raise RuntimeError(f"Pulse validation failed: {pulse_errors}")

        insights_payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "phase": "Phase 4 (Backend): Insights + One-Page Composition (Integrated)",
            "status": "pass",
            "input_themes_path": cfg.themes_path,
            "input_review_theme_map_path": cfg.review_theme_map_path,
            "input_cluster_distribution_path": cfg.cluster_distribution_path,
            "top_themes": top_themes,
            "quotes": quotes,
            "action_ideas": action_ideas,
            "pulse_path": str(pulse_path),
        }
        _write_json(insights_path, insights_payload)
        pulse_path.parent.mkdir(parents=True, exist_ok=True)
        pulse_path.write_text(pulse, encoding="utf-8")
        print(f"Wrote {insights_path}")
        print(f"Wrote {pulse_path}")
        print("Status: pass")
    except Exception as exc:  # noqa: BLE001
        _write_json(
            insights_path,
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "phase": "Phase 4 (Backend): Insights + One-Page Composition (Integrated)",
                "status": "fail",
                "input_themes_path": cfg.themes_path,
                "input_review_theme_map_path": cfg.review_theme_map_path,
                "input_cluster_distribution_path": cfg.cluster_distribution_path,
                "error": str(exc),
            },
        )
        print(f"Wrote {insights_path}")
        print("Status: fail")


if __name__ == "__main__":
    main()
