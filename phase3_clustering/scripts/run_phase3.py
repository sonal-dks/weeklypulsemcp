import json
from datetime import datetime, timezone
from pathlib import Path

from phase3_clustering.src.clustering import (
    add_confidence,
    distribution_payload,
    finalize_mapping,
    load_inputs,
    rebalance_dominant,
    reclassify_ambiguous,
)
from phase3_clustering.src.config import Phase3Config
from shared.week_utils import current_week_tag


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _resolve_phase2_inputs(cfg: Phase3Config) -> tuple[str, str]:
    theme_path = cfg.themes_path.strip()
    map_path = cfg.review_theme_map_path.strip()
    if theme_path and map_path and Path(theme_path).exists() and Path(map_path).exists():
        return theme_path, map_path
    tag = current_week_tag()
    cand_theme = Path(f"phase2_theming/outputs/themes_{tag}.json")
    cand_map = Path(f"phase2_theming/outputs/review_theme_map_{tag}.json")
    if cand_theme.exists() and cand_map.exists():
        return str(cand_theme), str(cand_map)
    themes = sorted(Path("phase2_theming/outputs").glob("themes_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    maps = sorted(
        Path("phase2_theming/outputs").glob("review_theme_map_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not themes or not maps:
        raise FileNotFoundError("Missing phase2 theming outputs (themes/review_theme_map)")
    return str(themes[0]), str(maps[0])


def main() -> None:
    cfg = Phase3Config()
    errors = cfg.validate_rules()
    themes_path, review_theme_map_path = _resolve_phase2_inputs(cfg)

    out_dir = Path(cfg.output_dir)
    map_path = out_dir / "review_theme_map.json"
    dist_path = out_dir / "cluster_distribution.json"

    if errors:
        _write_json(
            dist_path,
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "phase": "Phase 3 (Backend): Review Clustering (Primary Theme Assignment)",
                "status": "fail",
                "errors": errors,
            },
        )
        print(f"Wrote {dist_path}")
        print("Status: fail")
        return

    try:
        themes, input_map = load_inputs(themes_path, review_theme_map_path)
        rows = add_confidence(input_map, themes)
        rows, reassigned = reclassify_ambiguous(
            rows,
            themes,
            api_key=cfg.groq_api_key,
            model=cfg.groq_model,
            max_ambiguous_reclassify=cfg.max_ambiguous_reclassify,
        )
        rows, rebalanced = rebalance_dominant(rows, themes, cfg.dominance_threshold)
        final_map = finalize_mapping(rows)
        dist = distribution_payload(final_map, themes, reassigned, rebalanced)

        _write_json(
            map_path,
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "input_review_theme_map_path": review_theme_map_path,
                "themes_path": themes_path,
                "mapping": final_map,
            },
        )
        _write_json(
            dist_path,
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "phase": "Phase 3 (Backend): Review Clustering (Primary Theme Assignment)",
                "status": "pass",
                "input_review_theme_map_path": review_theme_map_path,
                "themes_path": themes_path,
                "dominance_threshold": cfg.dominance_threshold,
                **dist,
            },
        )
        print(f"Wrote {map_path}")
        print(f"Wrote {dist_path}")
        print("Status: pass")
    except Exception as exc:  # noqa: BLE001
        _write_json(
            dist_path,
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "phase": "Phase 3 (Backend): Review Clustering (Primary Theme Assignment)",
                "status": "fail",
                "input_review_theme_map_path": review_theme_map_path,
                "themes_path": themes_path,
                "error": str(exc),
            },
        )
        print(f"Wrote {dist_path}")
        print("Status: fail")


if __name__ == "__main__":
    main()
