import json
from datetime import datetime, timezone
from pathlib import Path

from phase2_theming.src.config import Phase2Config
from phase2_theming.src.theme_generator import (
    generate_themes_batched,
    load_processed_reviews,
    map_reviews_to_themes,
)


def _week_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    cfg = Phase2Config()
    errors = cfg.validate_rules()

    output_dir = Path(cfg.output_dir)
    tag = _week_tag()
    theme_run_path = output_dir / f"theme_runs_{tag}.json"
    themes_path = output_dir / f"themes_{tag}.json"
    review_theme_map_path = output_dir / f"review_theme_map_{tag}.json"

    if errors:
        _write_json(
            theme_run_path,
            {
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "phase": "Phase 2 (Backend): Theme Generation (LLM)",
                "status": "fail",
                "errors": errors,
            },
        )
        print(f"Wrote {theme_run_path}")
        print("Status: fail")
        return

    try:
        reviews = load_processed_reviews(cfg.input_processed_reviews_path)
        result = generate_themes_batched(
            api_key=cfg.groq_api_key,
            model=cfg.groq_model,
            reviews=reviews,
            theme_count=cfg.theme_count,
            max_retries=cfg.max_retries,
            batch_size_reviews=cfg.batch_size_reviews,
        )
        run_payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "phase": "Phase 2 (Backend): Theme Generation (LLM)",
            "status": "pass",
            "input_processed_reviews_path": cfg.input_processed_reviews_path,
            "theme_count": cfg.theme_count,
            "model": cfg.groq_model,
            "review_count_input": len(reviews),
            "review_count_used": result["review_count_used"],
            "batch_count": result["batch_count"],
            "candidate_theme_count": result["candidate_theme_count"],
            "batch_results": result["batch_results"],
            "final_attempts": result["final_attempts"],
            "themes_path": str(themes_path),
        }
        themes_payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "themes": result["themes"],
            "theme_count": len(result["themes"]),
        }
        review_theme_map_payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "input_processed_reviews_path": cfg.input_processed_reviews_path,
            "theme_count": len(result["themes"]),
            "review_count": len(reviews),
            "mapping": map_reviews_to_themes(reviews, result["themes"]),
        }
        theme_summary_counts: dict[str, int] = {theme: 0 for theme in result["themes"]}
        for row in review_theme_map_payload["mapping"]:
            t = str(row.get("primary_theme", ""))
            if t not in theme_summary_counts:
                theme_summary_counts[t] = 0
            theme_summary_counts[t] += 1
        themes_payload["theme_summary_counts"] = theme_summary_counts
        run_payload["review_theme_map_path"] = str(review_theme_map_path)
        _write_json(theme_run_path, run_payload)
        _write_json(themes_path, themes_payload)
        _write_json(review_theme_map_path, review_theme_map_payload)
        print(f"Wrote {theme_run_path}")
        print(f"Wrote {themes_path}")
        print(f"Wrote {review_theme_map_path}")
        print("Status: pass")
    except Exception as exc:  # noqa: BLE001
        run_payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "phase": "Phase 2 (Backend): Theme Generation (LLM)",
            "status": "fail",
            "input_processed_reviews_path": cfg.input_processed_reviews_path,
            "theme_count": cfg.theme_count,
            "model": cfg.groq_model,
            "error": str(exc),
        }
        _write_json(theme_run_path, run_payload)
        print(f"Wrote {theme_run_path}")
        print("Status: fail")


if __name__ == "__main__":
    main()
