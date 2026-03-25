import json
from typing import Any

import requests


class GeminiError(RuntimeError):
    pass


def generate_json(*, api_key: str, model: str, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    if not api_key:
        raise GeminiError("Missing GEMINI_API_KEY")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    resp = requests.post(url, json=body, timeout=60)
    if resp.status_code >= 300:
        raise GeminiError(f"Gemini API error {resp.status_code}: {resp.text}")
    payload = resp.json()
    try:
        text = payload["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)
    except Exception as exc:  # noqa: BLE001
        raise GeminiError(f"Invalid Gemini JSON response: {payload}") from exc


def generate_text(*, api_key: str, model: str, system_prompt: str, user_prompt: str) -> str:
    if not api_key:
        raise GeminiError("Missing GEMINI_API_KEY")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts": [{"text": user_prompt}]}],
        "generationConfig": {"temperature": 0.2},
    }
    resp = requests.post(url, json=body, timeout=60)
    if resp.status_code >= 300:
        raise GeminiError(f"Gemini API error {resp.status_code}: {resp.text}")
    payload = resp.json()
    try:
        return str(payload["candidates"][0]["content"]["parts"][0]["text"]).strip()
    except Exception as exc:  # noqa: BLE001
        raise GeminiError(f"Invalid Gemini text response: {payload}") from exc
