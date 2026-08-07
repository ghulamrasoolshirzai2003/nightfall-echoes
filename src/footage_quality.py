"""Screens a candidate stock clip's preview image with Gemini vision before
committing to it — catches unusual/disorienting camera angles (like an
extreme top-down "dutch angle" shot) that read badly as music-video
background footage, especially once text captions are overlaid on top.

Uses Pexels' lightweight preview JPEG (the `image` field on a search result)
rather than downloading the full clip, so a rejected candidate costs one
small image fetch, not a multi-MB video download.
"""
import requests

from . import gemini

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
    Retries once on a rate limit via the shared gemini helper (see
    src/gemini.py) — a single video build can make many of these calls in
    quick succession, which trips Gemini's free-tier per-minute limit."""
    try:
        img_resp = requests.get(preview_image_url, timeout=20)
        img_resp.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print(f"[footage_quality] Preview fetch failed ({e}); allowing clip through.")
        return True

    try:
        answer = gemini.generate_vision(PROMPT, img_resp.content, "image/jpeg",
                                         timeout=60, max_retries=1)
        return answer.strip().upper().startswith("Y")
    except Exception as e:  # noqa: BLE001
        print(f"[footage_quality] Check failed ({e}); allowing clip through.")
        return True
