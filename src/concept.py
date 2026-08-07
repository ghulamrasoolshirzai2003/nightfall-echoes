"""Stage 2 + 6 — the creative brain (Google Gemini free API).

Given today's mood, Gemini writes: a track title, a viral-optimized YouTube
description, and a list of tags. Prompts are engineered for the YouTube algorithm
(searchable keywords, emotional hooks, clear CTAs).

Falls back to a safe template if the API ever hiccups, so the daily run never dies.
"""
import json
import random

from . import gemini
from .settings import CONFIG

PROMPT = """You are a YouTube growth expert running an aesthetic instrumental music
channel called "{channel} {emoji}". Today's track mood is "{mood}" ({keywords}).

Write metadata for ONE new original instrumental track. Optimize for the YouTube
algorithm: emotional, searchable, click-worthy, but NOT clickbait-spammy.

Return ONLY valid JSON (no markdown fences) with exactly these keys:
- "title": <=90 chars, catchy, includes 1-2 searchable keywords and an emoji.
- "description": 3-5 short paragraphs. First line is a hook with keywords.
  Mention it's original / royalty-free / copyright-free. Include a soft call to
  subscribe. End with 5-8 hashtags on one line.
- "tags": array of 12-18 short lowercase search tags (strings).
- "thumbnail_text": 2-4 punchy words to overlay on the thumbnail (e.g. "Midnight Lofi").
"""


def _fallback(mood: dict) -> dict:
    kw = mood["keywords"]
    return {
        "title": f"{mood['name'].title()} {CONFIG['channel']['emoji']} | {kw[0]} music to relax",
        "description": (
            f"Original {mood['name']} music to help you {random.choice(['relax','study','sleep','focus'])}. "
            "100% royalty-free and copyright-free — made for this channel.\n\n"
            "Subscribe for a new track every day. 🌙\n\n"
            "#" + " #".join(k.replace(' ', '') for k in kw[:5])
        ),
        "tags": mood["keywords"] + CONFIG["upload"]["base_tags"],
        "thumbnail_text": mood["name"].title(),
    }


def generate(mood: dict) -> dict:
    prompt = PROMPT.format(
        channel=CONFIG["channel"]["name"],
        emoji=CONFIG["channel"]["emoji"],
        mood=mood["name"],
        keywords=", ".join(mood["keywords"]),
    )
    try:
        text = gemini.generate_text(prompt, timeout=60, max_retries=2)
        data = json.loads(gemini.strip_json_fences(text))
        # Merge in base tags and de-dupe.
        data["tags"] = list(dict.fromkeys(list(data.get("tags", [])) + CONFIG["upload"]["base_tags"]))
        print(f"[concept] Gemini title: {data['title']}")
        return data
    except Exception as e:  # noqa: BLE001 — never let creativity crash the run.
        print(f"[concept] Gemini failed ({e}); using fallback template.")
        return _fallback(mood)
