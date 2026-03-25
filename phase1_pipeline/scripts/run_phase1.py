import json
from datetime import datetime, timezone
from pathlib import Path

from phase1_pipeline.src.cleaning import run_cleaning
from phase1_pipeline.src.config import Phase1Config
from phase1_pipeline.src.ingestion import fetch_reviews, write_raw_json


def _write_json(path: str, payload: dict) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    cfg = Phase1Config()
    errors = cfg.validate_foundation_rules()

    config_check = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 1 (Backend): Foundation + Ingestion + Cleaning (Combined)",
        "status": "pass" if not errors else "fail",
        "config": cfg.model_dump(),
        "errors": errors,
    }
    _write_json("phase1_pipeline/outputs/config_check.json", config_check)

    if errors:
        print("Config validation failed. See phase1_pipeline/outputs/config_check.json")
        return

    fetched = fetch_reviews(
        app_id=cfg.app_id,
        lookback_weeks=cfg.lookback_weeks,
        lang=cfg.playstore_lang,
        country=cfg.playstore_country,
        batch_size=cfg.batch_size,
        max_fetch=cfg.max_fetch,
    )
    ingestion_stats = write_raw_json(cfg.raw_json_path, fetched)

    dates = [r.get("date") for r in fetched if r.get("date")]
    dropped_between_fetch_and_insert = len(fetched) - ingestion_stats["inserted_raw_reviews"]
    ingestion_report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 1.1: Data Ingestion",
        "status": "pass",
        "raw_json_path": cfg.raw_json_path,
        "fetched_count": len(fetched),
        "inserted_raw_reviews": ingestion_stats["inserted_raw_reviews"],
        "dropped_between_fetch_and_insert": dropped_between_fetch_and_insert,
        "drop_reasons": {
            "skipped_existing_review_id": ingestion_stats["skipped_existing_review_id"],
            "skipped_duplicate_in_batch": ingestion_stats["skipped_duplicate_in_batch"],
        },
        "min_review_date": min(dates) if dates else None,
        "max_review_date": max(dates) if dates else None,
        "sample_records": fetched[:5],
    }
    _write_json("phase1_pipeline/outputs/ingestion_report.json", ingestion_report)

    cleaning_summary = run_cleaning(
        raw_json_path=cfg.raw_json_path,
        processed_json_path=cfg.processed_json_path,
        omitted_json_path=cfg.omitted_json_path,
    )
    cleaning_report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "phase": "Phase 1.2: Cleaning, Deduplication, and Spam Filtering",
        "status": "pass",
        **cleaning_summary,
        "processed_json_path": cfg.processed_json_path,
        "omitted_json_path": cfg.omitted_json_path,
    }
    _write_json("phase1_pipeline/outputs/cleaning_report.json", cleaning_report)

    omitted_rows = json.loads(Path(cfg.omitted_json_path).read_text(encoding="utf-8"))
    sample = omitted_rows[:30] if isinstance(omitted_rows, list) else []
    _write_json("phase1_pipeline/outputs/omitted_reviews_sample.json", {"sample": sample})

    print("Phase 1 complete. See phase1_pipeline/outputs/")


if __name__ == "__main__":
    main()
