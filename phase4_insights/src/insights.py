import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from phase4_insights.src.gemini_client import generate_json, generate_text


PII_PATTERNS = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    re.compile(r"\b\d{10}\b"),
    re.compile(r"\b(ticket|acct|account|id)\s*[:#-]?\s*[A-Za-z0-9-]{4,}\b", flags=re.IGNORECASE),
]


def _sanitize_text(text: str) -> str:
    out = text
    for pattern in PII_PATTERNS:
        out = pattern.sub("[REDACTED]", out)
    return out


def load_inputs(
    themes_path: str,
    review_theme_map_path: str,
    processed_reviews_path: str,
    cluster_distribution_path: str,
) -> tuple[list[str], list[dict[str, Any]], dict[str, int], dict[str, dict[str, Any]]]:
    themes_payload = json.loads(Path(themes_path).read_text(encoding="utf-8"))
    themes = themes_payload.get("themes", [])
    if not isinstance(themes, list) or len(themes) != 5:
        raise ValueError("themes payload must contain exactly 5 themes")

    map_payload = json.loads(Path(review_theme_map_path).read_text(encoding="utf-8"))
    mapping = map_payload.get("mapping", [])
    if not isinstance(mapping, list):
        raise ValueError("review_theme_map missing mapping list")

    processed_payload = json.loads(Path(processed_reviews_path).read_text(encoding="utf-8"))
    processed_rows = processed_payload if isinstance(processed_payload, list) else []
    processed_lookup = {
        str(r.get("review_id")): r
        for r in processed_rows
        if isinstance(r, dict) and r.get("review_id")
    }

    dist_payload = json.loads(Path(cluster_distribution_path).read_text(encoding="utf-8"))
    dist = dist_payload.get("theme_distribution", {})
    if not isinstance(dist, dict):
        raise ValueError("cluster_distribution missing theme_distribution")
    return (
        [str(t) for t in themes],
        [m for m in mapping if isinstance(m, dict)],
        {str(k): int(v) for k, v in dist.items()},
        processed_lookup,
    )


def rank_top_themes(themes: list[str], mapping: list[dict[str, Any]], distribution: dict[str, int], top_n: int = 3) -> list[dict[str, Any]]:
    analyzer = SentimentIntensityAnalyzer()
    theme_texts: dict[str, list[str]] = defaultdict(list)
    for row in mapping:
        t = str(row.get("primary_theme", ""))
        txt = str(row.get("text", ""))
        if t in themes and txt:
            theme_texts[t].append(txt)

    ranked: list[dict[str, Any]] = []
    for t in themes:
        texts = theme_texts.get(t, [])
        if texts:
            sentiments = [analyzer.polarity_scores(x)["compound"] for x in texts]
            avg_sent = sum(sentiments) / len(sentiments)
            neg_share = sum(1 for s in sentiments if s < 0) / len(sentiments)
        else:
            avg_sent = 0.0
            neg_share = 0.0

        freq = distribution.get(t, 0)
        # deterministic proxy score as described in architecture.
        score = (0.6 * freq) + (0.4 * (neg_share * 100))
        ranked.append(
            {
                "theme": t,
                "frequency": freq,
                "avg_sentiment": round(avg_sent, 4),
                "negative_share": round(neg_share, 4),
                "score": round(score, 4),
            }
        )

    ranked.sort(key=lambda x: x["score"], reverse=True)
    return ranked[:top_n]


def select_quotes(
    mapping: list[dict[str, Any]],
    top_themes: list[dict[str, Any]],
    processed_lookup: dict[str, dict[str, Any]],
    quote_count: int = 3,
) -> list[dict[str, Any]]:
    analyzer = SentimentIntensityAnalyzer()
    selected: list[dict[str, Any]] = []
    top_theme_names = [t["theme"] for t in top_themes]
    negative_pool: list[dict[str, Any]] = []
    for theme in top_theme_names:
        candidates = [
            r
            for r in mapping
            if str(r.get("primary_theme", "")) == theme and str(r.get("text", "")).strip()
        ]
        # representative by medium length
        candidates = sorted(candidates, key=lambda x: abs(len(str(x.get("text", ""))) - 140))
        if candidates:
            c = candidates[0]
            rid = str(c.get("review_id", ""))
            meta = processed_lookup.get(rid, {})
            q = {
                "review_id": rid,
                "theme": theme,
                "text": _sanitize_text(str(c.get("text", "")).strip()),
                "date": str(meta.get("date", "unknown")),
                "rating": int(meta.get("rating", 0) or 0),
            }
            if analyzer.polarity_scores(q["text"])["compound"] < 0:
                negative_pool.append(q)
            selected.append(q)
        if len(selected) >= quote_count:
            break
    # Ensure not only positive quotes: inject one negative if available.
    if selected and all(analyzer.polarity_scores(q["text"])["compound"] >= 0 for q in selected) and negative_pool:
        selected[-1] = negative_pool[0]
    return selected[:quote_count]


def generate_action_ideas(
    api_key: str,
    model: str,
    top_themes: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
) -> list[str]:
    system_prompt = (
        "You are a product strategist. Return JSON only with key action_ideas as an array of exactly 3 concise actionable bullets."
    )
    user_prompt = (
        "Generate exactly 3 action ideas from top themes and user voice.\n"
        "Top themes:\n"
        + "\n".join([f"- {t['theme']} (freq={t['frequency']}, neg_share={t['negative_share']})" for t in top_themes])
        + "\nUser voice quotes:\n"
        + "\n".join([f'- "{q["text"]}" [date: {q["date"]}, rating: {q["rating"]}]' for q in quotes])
        + "\nConstraints: no PII, no generic advice, each bullet max 20 words."
    )
    payload = generate_json(api_key=api_key, model=model, system_prompt=system_prompt, user_prompt=user_prompt)
    ideas = payload.get("action_ideas", [])
    if not isinstance(ideas, list) or len(ideas) != 3:
        raise ValueError("Gemini action ideas output must contain exactly 3 items")
    return [_sanitize_text(str(x).strip()) for x in ideas]


def compose_pulse_markdown(
    api_key: str,
    model: str,
    top_themes: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    action_ideas: list[str],
    report_date: str,
) -> str:
    system_prompt = """You are a senior product analyst writing a weekly internal product pulse.
Hard constraints:
1) Output <= 250 words.
2) Sections in exact order:
   Weekly Groww Product Pulse - <YYYY-MM-DD>
   Top Themes
   User Voice
   Action Ideas
3) Exactly 3 bullets in each section (Top Themes/User Voice/Action Ideas).
4) No PII.
5) Decision-oriented, concise style.
"""
    user_prompt = (
        "Use the provided structured inputs only.\n"
        f"Report date: {report_date}\n"
        "Top themes and context:\n"
        + "\n".join(
            [
                f"- {t['theme']}: count={t['frequency']}, negative_share={t['negative_share']}, explain what this theme means in one short clause."
                for t in top_themes
            ]
        )
        + "\nUser voice:\n"
        + "\n".join([f'- "{q["text"]}" [date: {q["date"]}, rating: {q["rating"]}]' for q in quotes])
        + "\nAction ideas:\n"
        + "\n".join([f"- {a}" for a in action_ideas])
        + "\nFormatting requirement for Top Themes bullets: each bullet MUST include count in this style '(count: N)'."
    )
    text = generate_text(api_key=api_key, model=model, system_prompt=system_prompt, user_prompt=user_prompt)
    return _sanitize_text(text)


def compose_pulse_markdown_strict(
    api_key: str,
    model: str,
    top_themes: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    action_ideas: list[str],
    report_date: str,
) -> str:
    system_prompt = (
        "Return markdown only. Follow exact section headers and exactly 3 bullets under each section."
    )
    user_prompt = (
        "Generate output in this exact template:\n"
        f"Weekly Groww Product Pulse - {report_date}\n\n"
        "Top Themes\n"
        "- <theme 1> (count: N): <what this theme means>\n- <theme 2> (count: N): <what this theme means>\n- <theme 3> (count: N): <what this theme means>\n\n"
        "User Voice\n"
        "- \"<quote 1>\" [date: YYYY-MM-DD, rating: N]\n- \"<quote 2>\" [date: YYYY-MM-DD, rating: N]\n- \"<quote 3>\" [date: YYYY-MM-DD, rating: N]\n\n"
        "Action Ideas\n"
        "- <action 1>\n- <action 2>\n- <action 3>\n\n"
        "Keep total <=250 words and no PII.\n"
        "Inputs:\n"
        + "\n".join([f"- theme: {t['theme']} (freq={t['frequency']}, neg={t['negative_share']})" for t in top_themes])
        + "\nQuotes:\n"
        + "\n".join([f'- "{q["text"]}" [date: {q["date"]}, rating: {q["rating"]}]' for q in quotes])
        + "\nAction ideas seed:\n"
        + "\n".join([f"- {a}" for a in action_ideas])
    )
    text = generate_text(api_key=api_key, model=model, system_prompt=system_prompt, user_prompt=user_prompt)
    return _sanitize_text(text)


def deterministic_pulse_fallback(
    top_themes: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    action_ideas: list[str],
    report_date: str,
) -> str:
    theme_lines = [
        f"- {t['theme']} (count: {t['frequency']}): frequent user concern observed this week (negative_share={t['negative_share']})."
        for t in top_themes[:3]
    ]
    quote_lines = [f'- "{q["text"]}" [date: {q["date"]}, rating: {q["rating"]}]' for q in quotes[:3]]
    action_lines = [f"- {a}" for a in action_ideas[:3]]
    return (
        f"Weekly Groww Product Pulse - {report_date}\n\n"
        "Top Themes\n"
        + "\n".join(theme_lines)
        + "\n\nUser Voice\n"
        + "\n".join(quote_lines)
        + "\n\nAction Ideas\n"
        + "\n".join(action_lines)
    )


def validate_pulse(text: str) -> list[str]:
    errors: list[str] = []
    words = re.findall(r"\S+", text)
    if len(words) > 250:
        errors.append("Pulse exceeds 250 words")

    required_headers = ["Weekly Groww Product Pulse", "Top Themes", "User Voice", "Action Ideas"]
    for h in required_headers:
        if h not in text:
            errors.append(f"Missing section header: {h}")

    lines = text.splitlines()

    def count_bullets(section_title: str) -> int:
        start_idx = None
        for i, ln in enumerate(lines):
            if ln.strip().lower() == section_title.lower() or ln.strip().lower() == f"**{section_title.lower()}**":
                start_idx = i
                break
        if start_idx is None:
            return 0
        count = 0
        for ln in lines[start_idx + 1 :]:
            s = ln.strip()
            # stop when next section/header starts
            if not s:
                continue
            if s.lower() in {"weekly groww product pulse", "top themes", "user voice", "action ideas"}:
                break
            if s.startswith("**") and s.endswith("**"):
                break
            if s.startswith("#"):
                break
            if s.startswith("- "):
                count += 1
        return count

    if count_bullets("Top Themes") != 3:
        errors.append("Top Themes section must have 3 bullets")
    if count_bullets("User Voice") != 3:
        errors.append("User Voice section must have 3 bullets")
    if count_bullets("Action Ideas") != 3:
        errors.append("Action Ideas section must have 3 bullets")

    # Top themes bullets must include "(count: N)".
    in_top_themes = False
    top_theme_bullets: list[str] = []
    for ln in lines:
        s = ln.strip()
        if s.lower() == "top themes":
            in_top_themes = True
            continue
        if in_top_themes and s.lower() in {"user voice", "action ideas", "weekly groww product pulse"}:
            in_top_themes = False
        if in_top_themes and s.startswith("- "):
            top_theme_bullets.append(s)
    if top_theme_bullets and any(re.search(r"\(count:\s*\d+\)", b, flags=re.IGNORECASE) is None for b in top_theme_bullets):
        errors.append("Top Themes bullets must include count as '(count: N)'")

    # User voice bullets must include [date: ..., rating: ...]
    for ln in lines:
        s = ln.strip()
        if s.startswith('- "') and "[date:" in s.lower() and "rating:" in s.lower():
            continue
        if s.startswith('- "') and ("date:" not in s.lower() or "rating:" not in s.lower()):
            errors.append("User Voice bullets must include [date: ..., rating: ...]")
            break

    for p in PII_PATTERNS:
        if p.search(text):
            errors.append("PII detected in pulse output")
            break
    return errors
