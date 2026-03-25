import json
import re
import time
from collections import Counter
from pathlib import Path
from typing import Any

from phase3_clustering.src.groq_reclassify import GroqClassifyError, classify_batch


def _tokenize(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-zA-Z]+", text.lower()) if t}


def load_inputs(themes_path: str, review_theme_map_path: str) -> tuple[list[str], list[dict[str, Any]]]:
    themes_payload = json.loads(Path(themes_path).read_text(encoding="utf-8"))
    themes = themes_payload.get("themes", [])
    if not isinstance(themes, list) or not themes:
        raise ValueError("themes file missing valid 'themes' list")

    mapping_payload = json.loads(Path(review_theme_map_path).read_text(encoding="utf-8"))
    mapping = mapping_payload.get("mapping", [])
    if not isinstance(mapping, list):
        raise ValueError("review_theme_map file missing valid 'mapping' list")
    return [str(t) for t in themes], [m for m in mapping if isinstance(m, dict)]


def add_confidence(rows: list[dict[str, Any]], themes: list[str]) -> list[dict[str, Any]]:
    theme_tokens = {t: _tokenize(t) for t in themes}
    enriched: list[dict[str, Any]] = []
    for row in rows:
        text = str(row.get("text", ""))
        assigned = str(row.get("primary_theme", themes[0]))
        tokens = _tokenize(text)
        scores = {t: len(tokens.intersection(theme_tokens[t])) for t in themes}
        max_score = max(scores.values()) if scores else 0
        assigned_score = scores.get(assigned, 0)
        # low confidence when assigned score is weak or tied
        top_themes = [t for t, s in scores.items() if s == max_score]
        low_conf = assigned_score <= 0 or len(top_themes) > 1
        enriched.append(
            {
                "review_id": row.get("review_id"),
                "text": text,
                "primary_theme": assigned if assigned in themes else themes[0],
                "confidence_band": "low" if low_conf else "high",
                "scores": scores,
            }
        )
    return enriched


def reclassify_ambiguous(
    rows: list[dict[str, Any]],
    themes: list[str],
    api_key: str,
    model: str,
    max_ambiguous_reclassify: int,
) -> tuple[list[dict[str, Any]], int]:
    ambiguous = [r for r in rows if r["confidence_band"] == "low"][:max_ambiguous_reclassify]
    if not ambiguous:
        return rows, 0

    reassigned = 0
    chunk_size = 25
    for i in range(0, len(ambiguous), chunk_size):
        chunk = ambiguous[i : i + chunk_size]
        request_rows = [{"review_id": str(r["review_id"]), "text": str(r["text"])} for r in chunk]
        assignments: dict[str, str] = {}
        last_err = None
        for attempt in range(1, 4):
            try:
                assignments = classify_batch(api_key=api_key, model=model, themes=themes, rows=request_rows)
                break
            except GroqClassifyError as exc:
                last_err = str(exc)
                if "rate_limit_exceeded" in last_err.lower() or "rate limit reached" in last_err.lower():
                    m = re.search(r"try again in\s+([0-9]+(?:\.[0-9]+)?)s", last_err, flags=re.IGNORECASE)
                    wait_s = float(m.group(1)) + 0.5 if m else 2.5
                    time.sleep(wait_s)
                    continue
                raise
        if last_err and not assignments:
            raise RuntimeError(f"Ambiguous reclassification failed after retries: {last_err}")
        for row in rows:
            rid = str(row["review_id"])
            if rid in assignments and assignments[rid] != row["primary_theme"]:
                row["primary_theme"] = assignments[rid]
                reassigned += 1
    return rows, reassigned


def rebalance_dominant(rows: list[dict[str, Any]], themes: list[str], dominance_threshold: float) -> tuple[list[dict[str, Any]], int]:
    counts = Counter([r["primary_theme"] for r in rows])
    total = len(rows) if rows else 1
    dominant_theme, dominant_count = (counts.most_common(1)[0] if counts else (None, 0))
    if not dominant_theme:
        return rows, 0
    if dominant_count / total <= dominance_threshold:
        return rows, 0

    # Reassign low-confidence reviews from dominant theme to second-best score theme.
    target = int(total * dominance_threshold)
    need_to_move = dominant_count - target
    moved = 0
    for row in rows:
        if moved >= need_to_move:
            break
        if row["primary_theme"] != dominant_theme or row["confidence_band"] != "low":
            continue
        scores = row.get("scores", {})
        ordered = sorted(themes, key=lambda t: scores.get(t, 0), reverse=True)
        for cand in ordered:
            if cand != dominant_theme:
                row["primary_theme"] = cand
                moved += 1
                break
    return rows, moved


def finalize_mapping(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "review_id": r["review_id"],
            "text": r["text"],
            "primary_theme": r["primary_theme"],
        }
        for r in rows
    ]


def distribution_payload(rows: list[dict[str, Any]], themes: list[str], reassigned: int, rebalanced: int) -> dict[str, Any]:
    counts = Counter([r["primary_theme"] for r in rows])
    total = len(rows)
    return {
        "review_count": total,
        "theme_distribution": {t: counts.get(t, 0) for t in themes},
        "reassigned_low_confidence_count": reassigned,
        "rebalanced_count": rebalanced,
    }
