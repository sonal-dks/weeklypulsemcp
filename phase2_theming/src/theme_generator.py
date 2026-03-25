import json
import re
import time
from pathlib import Path
from typing import Any

from phase2_theming.src.groq_client import GroqError, generate_themes_json


def load_processed_reviews(path: str) -> list[dict[str, Any]]:
    rows = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("Processed reviews file must be a JSON list")
    return [r for r in rows if isinstance(r, dict)]


def _truncate_reviews(rows: list[dict[str, Any]], max_items: int = 220, max_chars_per_review: int = 220) -> list[str]:
    texts: list[str] = []
    for row in rows[:max_items]:
        txt = str(row.get("text", "")).strip()
        if txt:
            texts.append(txt[:max_chars_per_review])
    return texts


def _chunk_texts(texts: list[str], batch_size: int) -> list[list[str]]:
    return [texts[i : i + batch_size] for i in range(0, len(texts), batch_size)]


def _build_prompt(review_texts: list[str], theme_count: int) -> str:
    sample = "\n".join(f"- {t}" for t in review_texts)
    return (
        f"From the following user reviews, generate exactly {theme_count} high-level product themes.\n"
        "Constraints:\n"
        "- exactly 5 themes\n"
        "- each theme must be 1 to 3 words\n"
        "- avoid overlap and synonyms\n"
        "- no punctuation-heavy labels\n"
        'Return JSON only in this format: {"themes":["Theme A","Theme B","Theme C","Theme D","Theme E"]}\n'
        "Reviews:\n"
        f"{sample}"
    )


def _build_consolidation_prompt(candidate_themes: list[str], theme_count: int) -> str:
    pool = "\n".join(f"- {t}" for t in candidate_themes)
    return (
        "Consolidate the following candidate review themes into a final non-overlapping set.\n"
        f"Return exactly {theme_count} themes.\n"
        "Constraints:\n"
        "- exactly 5 themes\n"
        "- each theme must be 1 to 3 words\n"
        "- remove synonyms/overlaps and keep broad product-facing labels\n"
        'Return JSON only in this format: {"themes":["Theme A","Theme B","Theme C","Theme D","Theme E"]}\n'
        "Candidate themes:\n"
        f"{pool}"
    )


def _normalize_theme(theme: str) -> str:
    t = re.sub(r"\s+", " ", theme.strip())
    t = t.strip(" -:;,.")
    return t


def _rate_limit_wait_seconds(error_text: str) -> float:
    m = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", error_text, flags=re.IGNORECASE)
    if m:
        return float(m.group(1)) + 0.5
    return 2.5


def _validate_themes(payload: dict[str, Any], theme_count: int) -> list[str]:
    themes = payload.get("themes")
    if not isinstance(themes, list):
        raise ValueError("Payload must contain list key 'themes'")
    normalized = [_normalize_theme(str(t)) for t in themes if str(t).strip()]
    if len(normalized) != theme_count:
        raise ValueError(f"Expected exactly {theme_count} themes, got {len(normalized)}")
    for t in normalized:
        wc = len(t.split(" "))
        if wc < 1 or wc > 3:
            raise ValueError(f"Theme must be 1-3 words: {t}")
    # basic uniqueness check
    lower = [t.lower() for t in normalized]
    if len(set(lower)) != len(lower):
        raise ValueError("Themes must be unique")
    return normalized


def _coerce_from_non_schema_payload(payload: dict[str, Any], theme_count: int) -> dict[str, Any]:
    if "themes" in payload:
        return payload

    # Common fallback: model returns {"Theme A":"...", ...} or {"items":[...]}
    if "items" in payload and isinstance(payload["items"], list):
        items = [str(x).strip() for x in payload["items"] if str(x).strip()]
        return {"themes": items[:theme_count]}

    values = [str(v).strip() for v in payload.values() if isinstance(v, str) and str(v).strip()]
    if values:
        return {"themes": values[:theme_count]}
    return payload


def generate_themes_with_retry(
    *,
    api_key: str,
    model: str,
    reviews: list[dict[str, Any]],
    theme_count: int,
    max_retries: int,
) -> dict[str, Any]:
    review_texts = _truncate_reviews(reviews)
    if not review_texts:
        raise ValueError("No review text available in processed reviews input")

    last_error = None
    attempts: list[dict[str, Any]] = []
    current_texts = list(review_texts)
    for attempt in range(1, max_retries + 1):
        prompt = _build_prompt(current_texts, theme_count)
        try:
            payload = generate_themes_json(api_key=api_key, model=model, prompt=prompt)
            payload = _coerce_from_non_schema_payload(payload, theme_count)
            themes = _validate_themes(payload, theme_count)
            return {
                "status": "pass",
                "attempts": attempts + [{"attempt": attempt, "status": "pass"}],
                "themes": themes,
                "review_count_used": len(current_texts),
            }
        except (GroqError, ValueError) as exc:
            last_error = str(exc)
            attempts.append({"attempt": attempt, "status": "fail", "error": str(exc)})
            # Truncate only when payload is too large (413 style), not on generic TPM rate limits.
            if "Request too large" in str(exc):
                # adaptive fallback to meet token limits on smaller tiers
                next_count = max(40, len(current_texts) // 2)
                current_texts = current_texts[:next_count]
            if "rate_limit_exceeded" in str(exc).lower() or "rate limit reached" in str(exc).lower():
                time.sleep(_rate_limit_wait_seconds(str(exc)))

    raise RuntimeError(f"Theme generation failed after {max_retries} attempts: {last_error}")


def generate_themes_batched(
    *,
    api_key: str,
    model: str,
    reviews: list[dict[str, Any]],
    theme_count: int,
    max_retries: int,
    batch_size_reviews: int,
) -> dict[str, Any]:
    review_texts = _truncate_reviews(reviews, max_items=len(reviews))
    if not review_texts:
        raise ValueError("No review text available in processed reviews input")

    batches = _chunk_texts(review_texts, batch_size_reviews)
    batch_results: list[dict[str, Any]] = []
    candidate_themes: list[str] = []
    total_reviews_used = 0

    for idx, batch in enumerate(batches, start=1):
        # Reuse existing retry path per batch with bounded payload.
        pseudo_reviews = [{"text": t} for t in batch]
        result = generate_themes_with_retry(
            api_key=api_key,
            model=model,
            reviews=pseudo_reviews,
            theme_count=theme_count,
            max_retries=max_retries,
        )
        if result["review_count_used"] != len(batch):
            raise RuntimeError(
                "Batch theme generation used fewer reviews than provided. "
                "Reduce BATCH_SIZE_REVIEWS to process all reviews without truncation."
            )
        total_reviews_used += result["review_count_used"]
        candidate_themes.extend(result["themes"])
        batch_results.append(
            {
                "batch_index": idx,
                "batch_size": len(batch),
                "review_count_used": result["review_count_used"],
                "attempts": result["attempts"],
                "themes": result["themes"],
            }
        )

    # Consolidate candidates into final exactly-5 themes.
    consolidation_attempts: list[dict[str, Any]] = []
    last_error = None
    consolidated_themes: list[str] | None = None
    for attempt in range(1, max_retries + 1):
        try:
            payload = generate_themes_json(
                api_key=api_key,
                model=model,
                prompt=_build_consolidation_prompt(candidate_themes, theme_count),
            )
            payload = _coerce_from_non_schema_payload(payload, theme_count)
            consolidated_themes = _validate_themes(payload, theme_count)
            consolidation_attempts.append({"attempt": attempt, "status": "pass"})
            break
        except (GroqError, ValueError) as exc:
            last_error = str(exc)
            consolidation_attempts.append({"attempt": attempt, "status": "fail", "error": str(exc)})
            if "rate_limit_exceeded" in str(exc).lower() or "rate limit reached" in str(exc).lower():
                time.sleep(_rate_limit_wait_seconds(str(exc)))
    if consolidated_themes is None:
        raise RuntimeError(f"Consolidation failed after {max_retries} attempts: {last_error}")

    return {
        "status": "pass",
        "batch_count": len(batches),
        "review_count_used": total_reviews_used,
        "batch_results": batch_results,
        "candidate_theme_count": len(candidate_themes),
        "final_attempts": consolidation_attempts,
        "themes": consolidated_themes,
    }


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z]+", text.lower()) if t}


def map_reviews_to_themes(
    reviews: list[dict[str, Any]],
    themes: list[str],
) -> list[dict[str, Any]]:
    theme_tokens = {theme: _tokenize(theme) for theme in themes}
    mapping: list[dict[str, Any]] = []

    for row in reviews:
        text = str(row.get("text", "")).strip()
        review_tokens = _tokenize(text)

        # Primary matching rule: max token overlap with tie-break on theme order.
        best_theme = themes[0] if themes else "Unknown"
        best_score = -1
        for theme in themes:
            overlap = len(review_tokens.intersection(theme_tokens[theme]))
            if overlap > best_score:
                best_score = overlap
                best_theme = theme

        mapping.append(
            {
                "review_id": row.get("review_id"),
                "text": text,
                "primary_theme": best_theme,
            }
        )
    return mapping
