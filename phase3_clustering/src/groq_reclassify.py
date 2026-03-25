import json
from typing import Any

import requests


class GroqClassifyError(RuntimeError):
    pass


def _build_prompt(themes: list[str], rows: list[dict[str, str]]) -> str:
    lines = "\n".join([f"- {t}" for t in themes])
    review_lines = "\n".join(
        [f'{idx+1}. review_id={r["review_id"]} | text={r["text"][:280]}' for idx, r in enumerate(rows)]
    )
    return (
        "Assign each review to exactly one primary theme from the provided theme list.\n"
        "Return JSON only in this format:\n"
        '{"assignments":[{"review_id":"...","primary_theme":"..."}]}\n'
        "Rules:\n"
        "- primary_theme must be one of the provided themes exactly\n"
        "- one assignment for each review_id\n"
        "Themes:\n"
        f"{lines}\n"
        "Reviews:\n"
        f"{review_lines}\n"
    )


def classify_batch(api_key: str, model: str, themes: list[str], rows: list[dict[str, str]]) -> dict[str, str]:
    if not api_key:
        raise GroqClassifyError("Missing GROQ_API_KEY")
    if not rows:
        return {}

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = {
        "model": model,
        "temperature": 0.0,
        "messages": [
            {"role": "system", "content": "Return valid JSON only."},
            {"role": "user", "content": _build_prompt(themes, rows)},
        ],
    }
    resp = requests.post(url, headers=headers, json=body, timeout=60)
    if resp.status_code >= 300:
        raise GroqClassifyError(f"Groq API error {resp.status_code}: {resp.text}")

    payload = resp.json()
    try:
        content = payload["choices"][0]["message"]["content"]
        cleaned = str(content).strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()
        parsed = json.loads(cleaned)
        assignments = parsed["assignments"]
    except Exception as exc:  # noqa: BLE001
        raise GroqClassifyError(f"Invalid Groq assignment response: {payload}") from exc

    result: dict[str, str] = {}
    for item in assignments:
        rid = str(item.get("review_id", "")).strip()
        theme = str(item.get("primary_theme", "")).strip()
        if rid and theme in themes:
            result[rid] = theme
    return result
