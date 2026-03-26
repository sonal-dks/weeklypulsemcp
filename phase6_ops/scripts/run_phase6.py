import json
from pathlib import Path

from phase6_ops.src.config import Phase6Config
from phase6_ops.src.qa import build_run_summary, detect_latest_week_tag


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    cfg = Phase6Config()
    week = cfg.week_tag.strip() or detect_latest_week_tag()

    paths = {
        "phase1_config_check": cfg.phase1_config_check_path,
        "phase2_themes": cfg.phase2_themes_path.format(week=week),
        "phase4_insights": cfg.phase4_insights_path.format(week=week),
        "phase4_pulse": cfg.phase4_pulse_path.format(week=week),
        "phase5_doc_report": cfg.phase5_doc_report_path.format(week=week),
        "phase5_combined_payload": cfg.phase5_combined_payload_path.format(week=week),
    }

    summary = build_run_summary(week=week, paths=paths)
    out_path = cfg.out_path(week)
    _write_json(out_path, summary)
    print(f"Wrote {out_path}")
    print(f"Status: {summary.get('status')}")


if __name__ == "__main__":
    main()
