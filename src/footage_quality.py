"""Screens a candidate stock clip's preview image with Gemini vision before
committing to it — catches unusual/disorienting camera angles (like an
extreme top-down "dutch angle" shot) that read badly as music-video
background footage, especially once text captions are overlaid on top.

Uses Pexels' lightweight preview JPEG (the `image` field on a search result)
rather than downloading the full clip, so a rejected candidate costs one
small image fetch, not a multi-MB video download.
"""
import base64
import time

import requests

from .settings import env

GEMINI_MODEL = "gemini-flash-latest"  # alias that always points to the current model
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

PROMPT = (
    "Look at this image, a candidate background clip for a music video. Is "
    "the camera framing normal and stable enough to use as background "
    "footage with text captions overlaid on it? Reject only if it's an "
    "extreme/disorienting tilted (dutch angle) or upside-down shot, or "
    "otherwise hard to read with text on top. Minor artistic angles are "
    "fine — only reject clearly disorienting ones. Answer with exactly one "
    "word: YES or NO."
)


def is_usable_framing(preview_image_url: str) -> bool:
    """Returns True if usable. Fails open (returns True) if the check itself
    errors — a broken quality gate should never block the whole pipeline.

    A single video build makes many of these calls in quick succession (up to
    a few per shot group), which can trip Gemini's free-tier per-minute rate
    limit — retries once with a short backoff on a 429 specifically, since
    that's a transient "try again shortly" condition, not a real failure.
    """
    try:
        img_resp = requests.get(preview_image_url, timeout=20)
        img_resp.raise_for_status()
        b64 = base64.b64encode(img_resp.content).decode("ascii")
    except Exception as e:  # noqa: BLE001
        print(f"[footage_quality] Preview fetch failed ({e}); allowing clip through.")
        return True

    for attempt in range(2):
        try:
            resp = requests.post(
                GEMINI_URL, params={"key": env("GEMINI_API_KEY")},
                json={"contents": [{"parts": [
                    {"text": PROMPT},
                    {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                ]}]},
                timeout=60,  # vision calls are slower than text-only; 30s was too tight and mostly just timed out
            )
            resp.raise_for_status()
            answer = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip().upper()
            return answer.startswith("Y")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429 and attempt == 0:
                print("[footage_quality] Rate limited, retrying in 5s...")
                time.sleep(5)
                continue
            print(f"[footage_quality] Check failed ({e}); allowing clip through.")
            return True
        except Exception as e:  # noqa: BLE001
            print(f"[footage_quality] Check failed ({e}); allowing clip through.")
            return True
