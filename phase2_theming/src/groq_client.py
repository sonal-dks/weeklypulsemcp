import json
from typing import Any

import requests


class GroqError(RuntimeError):
    pass


def generate_themes_json(
    *,
    api_key: str,
    model: str,
    prompt: str,
    temperature: float = 0.1,
) -> dict[str, Any]:
    if not api_key:
        raise GroqError("Missing GROQ_API_KEY")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": "Return valid minified JSON only."},
            {"role": "user", "content": prompt},
        ],
    }
    resp = requests.post(url, headers=headers, json=body, timeout=60)
    if resp.status_code >= 300:
        raise GroqError(f"Groq API error {resp.status_code}: {resp.text}")

    payload = resp.json()
    try:
        content = payload["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        raise GroqError(f"Unexpected Groq response format: {payload}") from exc

    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise GroqError(f"Model did not return JSON: {content}") from exc
