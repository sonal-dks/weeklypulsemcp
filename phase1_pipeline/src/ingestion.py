import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from google_play_scraper import Sort, reviews


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _to_iso_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


def _review_hash(rating: int, text: str, date_iso: str) -> str:
    return hashlib.sha256(f"{rating}|{text}|{date_iso}".encode("utf-8")).hexdigest()


def fetch_reviews(app_id: str, lookback_weeks: int, lang: str, country: str, batch_size: int, max_fetch: int) -> list[dict[str, Any]]:
    cutoff = datetime.now(timezone.utc) - timedelta(weeks=lookback_weeks)
    all_reviews: list[dict[str, Any]] = []
    token = None

    while len(all_reviews) < max_fetch:
        count = min(batch_size, max_fetch - len(all_reviews))
        page, token = reviews(
            app_id,
            lang=lang,
            country=country,
            sort=Sort.NEWEST,
            count=count,
            continuation_token=token,
        )
        if not page:
            break
        stop = False
        for item in page:
            at = item.get("at")
            if at is None:
                continue
            if at.tzinfo is None:
                at = at.replace(tzinfo=timezone.utc)
            if at < cutoff:
                stop = True
                break
            all_reviews.append(item)
        if stop or token is None:
            break

    mapped: list[dict[str, Any]] = []
    for raw in all_reviews:
        text = _clean_text(str(raw.get("content", "")))
        rating = int(raw.get("score", 0))
        date_iso = _to_iso_date(raw.get("at"))
        playstore_review_id = str(raw.get("reviewId", "")).strip()
        review_id = playstore_review_id if playstore_review_id else _review_hash(rating=rating, text=text, date_iso=date_iso)
        mapped.append(
            {
                "review_id": review_id,
                "rating": rating,
                "text": text,
                "date": date_iso,
                "helpful_count": int(raw.get("thumbsUpCount", 0) or 0),
                "ingested_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return mapped


def write_raw_json(path: str, rows: list[dict[str, Any]]) -> dict[str, int]:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    inserted = 0
    skipped_existing_review_id = 0
    skipped_duplicate_in_batch = 0
    batch_seen: set[str] = set()
    final_rows: list[dict[str, Any]] = []

    for row in rows:
        if row["review_id"] in batch_seen:
            skipped_duplicate_in_batch += 1
            continue
        batch_seen.add(row["review_id"])
        final_rows.append(row)
        inserted += 1

    # Full rewrite per run: do not append historical raw reviews.
    final_rows = sorted(final_rows, key=lambda x: (x.get("date", ""), x.get("ingested_at", "")), reverse=True)
    target.write_text(json.dumps(final_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "inserted_raw_reviews": inserted,
        "skipped_existing_review_id": skipped_existing_review_id,
        "skipped_duplicate_in_batch": skipped_duplicate_in_batch,
    }
