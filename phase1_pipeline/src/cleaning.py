import json
import re
from pathlib import Path
from typing import Any

from langdetect import LangDetectException, detect
from rapidfuzz import fuzz


def _normalize_text(text: str) -> str:
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _word_count(text: str) -> int:
    return len([w for w in text.split(" ") if w.strip()])


def _is_spam(text: str) -> bool:
    t = text.lower()
    if re.fullmatch(r"[!@#$%^&*()_+\-=\[\]{};':\",.<>?/\\|`~\s]+", t):
        return True
    promo_patterns = ["use my code", "referral code", "promo code", "bonus code"]
    return any(p in t for p in promo_patterns)


def _safe_detect_lang(text: str) -> str:
    try:
        return detect(text)
    except LangDetectException:
        return "unknown"


def run_cleaning(
    raw_json_path: str,
    processed_json_path: str,
    omitted_json_path: str,
    similarity_threshold: float = 0.92,
) -> dict[str, Any]:
    raw_rows = json.loads(Path(raw_json_path).read_text(encoding="utf-8"))
    if not isinstance(raw_rows, list):
        raise ValueError("raw_reviews.json must be a JSON list")

    processed: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    seen_exact: dict[str, dict[str, Any]] = {}

    for row in raw_rows:
        text = _normalize_text(str(row.get("text", "")))
        row["text"] = text
        reason = None

        lang = _safe_detect_lang(text) if text else "unknown"
        if lang != "en":
            reason = "non_english"
        elif _word_count(text) < 5:
            reason = "short_text_lt_5_words"
        elif _is_spam(text):
            reason = "spam_or_promo"

        if reason is None:
            key = text.lower()
            if key in seen_exact:
                reason = "exact_duplicate"
            else:
                # near-duplicate check against a bounded recent window for performance
                recent = processed[-150:] if len(processed) > 150 else processed
                near_dup = False
                for prior in recent:
                    if fuzz.ratio(prior["text"].lower(), key) / 100.0 >= similarity_threshold:
                        near_dup = True
                        break
                if near_dup:
                    reason = "near_duplicate"

        if reason:
            omitted.append({"reason": reason, **row})
        else:
            seen_exact[text.lower()] = row
            processed.append(row)

    Path(processed_json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(processed_json_path).write_text(json.dumps(processed, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(omitted_json_path).parent.mkdir(parents=True, exist_ok=True)
    Path(omitted_json_path).write_text(json.dumps(omitted, ensure_ascii=False, indent=2), encoding="utf-8")

    reason_counts: dict[str, int] = {}
    for row in omitted:
        reason = str(row.get("reason", "unknown"))
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    return {
        "raw_count": len(raw_rows),
        "processed_count": len(processed),
        "omitted_count": len(omitted),
        "reasons": reason_counts,
    }
