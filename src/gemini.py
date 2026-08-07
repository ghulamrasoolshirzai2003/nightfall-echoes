"""One shared, resilient way to call Gemini's free API — every call site in
this project (concept.py, suno_prompt.py, scenes.py, footage_quality.py) used
to duplicate its own requests.post(...) with no rate-limit handling. In
production, a single video build fires enough Gemini calls across these
files in quick succession to trip the free-tier per-minute limit — confirmed
for real (scene-grouping fell back to "one group for the whole song" after a
429). Centralizing the retry-with-backoff here means every call site gets
the same resilience instead of needing the fix copy-pasted four times.
"""
import time

import requests

from .settings import env

GEMINI_MODEL = "gemini-flash-latest"  # alias that always points to the current model
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)


def generate_text(prompt: str, *, timeout: int = 60, max_retries: int = 2) -> str:
    """Text-only prompt -> raw response text. Retries on 429 with backoff;
    raises on any other failure or if retries are exhausted — callers already
    wrap this in their own try/except with a template fallback."""
    return _call({"contents": [{"parts": [{"text": prompt}]}]}, timeout, max_retries)


def generate_vision(prompt: str, image_bytes: bytes, mime_type: str, *,
                     timeout: int = 60, max_retries: int = 1) -> str:
    """Text + image prompt -> raw response text. Same retry behavior as
    generate_text; kept as a separate function since vision calls are
    slower/more expensive and callers may want a smaller retry budget."""
    import base64
    b64 = base64.b64encode(image_bytes).decode("ascii")
    body = {"contents": [{"parts": [
        {"text": prompt},
        {"inline_data": {"mime_type": mime_type, "data": b64}},
    ]}]}
    return _call(body, timeout, max_retries)


def _call(body: dict, timeout: int, max_retries: int) -> str:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            resp = requests.post(GEMINI_URL, params={"key": env("GEMINI_API_KEY")},
                                  json=body, timeout=timeout)
            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        except requests.HTTPError as e:
            last_error = e
            if e.response is not None and e.response.status_code == 429 and attempt < max_retries:
                wait = 5 * (attempt + 1)  # 5s, then 10s, ...
                print(f"[gemini] Rate limited, retrying in {wait}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait)
                continue
            raise
        except Exception as e:  # noqa: BLE001
            last_error = e
            raise
    raise last_error  # pragma: no cover — loop always returns or raises above


def strip_json_fences(text: str) -> str:
    """Gemini sometimes wraps JSON in ```json ... ``` despite being told not
    to — every call site was doing this exact strip, now shared too."""
    return text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
