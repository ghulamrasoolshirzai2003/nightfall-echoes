"""Generates a Suno-ready prompt (style tags + full structured lyrics) via
Gemini (free).

Targets REAL vocal songs — original German rap (Deutschrap) — using ORIGINAL
lyrics and melody ideas — never a specific existing song, artist name, or
"sounds like X" prompt. That distinction matters right now: Suno is in active,
unsettled litigation with major labels and independent artists over outputs
that resemble specific existing copyrighted work (Sony's case heads to a
summary-judgment hearing in mid-2026). Genre/mood-inspired originals sidestep
that risk; imitating an identifiable song or artist does not.
"""
import json
import random

import requests

from .settings import CONFIG, env

GEMINI_MODEL = "gemini-flash-latest"  # alias that always points to the current model
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

PROMPT = """You are a German rap ("Deutschrap") songwriter for a music channel
called "{channel}". Today's style is "{style_name}": {style_tags}. Theme
inspiration: {lyric_theme}.

Write ONE original German rap song for Suno (an AI music generator). It must
be 100% original — never reuse lyrics, hooks, melodies, or titles from any
real existing song, and never reference a real German rapper's name or flow
by name (describe genre/style/production only, e.g. "Deutschrap trap" not an
artist's name).

CRITICAL: The lyrics must be written entirely in natural, authentic German —
real Deutschrap slang, flow, and street vocabulary, not a stiff textbook
translation from English. The title should be in German (or a natural
German/English mix, which is common in real Deutschrap song titles).

Also write the full metadata package needed to publish this song once it's
made — a real YouTube-ready description and a real tag list, not placeholders.

Return ONLY valid JSON (no markdown fences) with exactly these keys:
- "title": a catchy original German (or German/English mix) song title.
- "style_tags": a comma-separated string of Suno "Style of Music" tags IN
  ENGLISH (genre, mood, vocal type, production), always explicitly including
  "German rap" / "Deutschrap", refined from "{style_tags}".
- "lyrics": full original German lyrics using [Verse 1], [Chorus],
  [Verse 2], [Chorus], [Bridge], [Chorus] section tags, ready to paste into
  Suno's custom lyrics box. Written entirely in German.
- "description": a 3-5 sentence YouTube video description IN GERMAN, written
  for discovery (natural, searchable phrasing, not a keyword dump), mentioning
  it's an original song, ending with a short line inviting the listener to
  follow/subscribe.
- "tags": an array of 12-18 relevant lowercase search tags (mix of German and
  English), e.g. genre, mood, and topical terms someone would search for this
  kind of song.
"""


def pick_style() -> dict:
    styles = CONFIG["suno"]["styles"]
    weights = [s.get("weight", 1) for s in styles]
    return random.choices(styles, weights=weights, k=1)[0]


def _fallback(style: dict) -> dict:
    theme = style["lyric_theme"].split(",")[0].strip()
    title = f"{style['name'].title()} Heute Nacht"
    return {
        "title": title,
        "style_tags": style["style_tags"],
        "lyrics": (
            f"[Verse 1]\nIch geh durch die {theme}, spür die Straße unter mir\n"
            "Jedes Licht ruft meinen Namen, ich weiß genau, wer ich bin\n\n"
            "[Chorus]\nDas ist unser Moment, wir brechen durch\n"
            "Nichts hält uns auf, wir geben nicht auf\n\n"
            f"[Verse 2]\nJeder Schritt durch die {theme}, heute Nacht\n"
            "Wir jagen was echt ist, halten fest, was uns trägt\n\n"
            "[Chorus]\nDas ist unser Moment, wir brechen durch\n"
            "Nichts hält uns auf, wir geben nicht auf\n\n"
            "[Bridge]\nAuch wenn's dunkel wird, wir finden das Licht\n\n"
            "[Chorus]\nDas ist unser Moment, wir brechen durch\n"
            "Nichts hält uns auf, wir geben nicht auf\n"
        ),
        "description": (
            f"{title} — ein originaler Deutschrap-Song. 100% Original, "
            "Text und Musik. Folge dem Kanal für mehr.\n\n"
            f"#deutschrap #{style['name'].lower().replace(' ', '')} #newmusic"
        ),
        "tags": [style["name"].lower(), "deutschrap", "german rap", "original song",
                 "new music", "rap deutsch"] + [w.strip() for w in style["lyric_theme"].split(",")],
    }


def generate(style: dict) -> dict:
    prompt = PROMPT.format(
        channel=CONFIG["channel"]["name"],
        style_name=style["name"],
        style_tags=style["style_tags"],
        lyric_theme=style["lyric_theme"],
    )
    try:
        resp = requests.post(
            GEMINI_URL, params={"key": env("GEMINI_API_KEY")},
            json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        print(f"[suno_prompt] Generated: {data['title']}")
        return data
    except Exception as e:  # noqa: BLE001 — never let this crash the daily run.
        print(f"[suno_prompt] Gemini failed ({e}); using fallback template.")
        return _fallback(style)


METADATA_FROM_LYRICS_PROMPT = """A song was uploaded to a German rap
("Deutschrap") channel called "{channel}" without a matching prompt on file —
here is what was actually transcribed from the real audio:

\"\"\"{lyrics}\"\"\"

Based on these ACTUAL lyrics, write the metadata needed to publish it.

Return ONLY valid JSON (no markdown fences) with exactly these keys:
- "title": a catchy title in German (or German/English mix) matching the song's real content.
- "description": a 3-5 sentence YouTube description IN GERMAN, written for
  discovery (natural, searchable phrasing), mentioning it's an original song,
  ending with a short line inviting the listener to follow/subscribe.
- "tags": an array of 12-18 relevant lowercase search tags (mix of German and
  English) matching the song's actual content and mood.
"""


def generate_metadata_from_lyrics(lyrics_text: str) -> dict:
    """For an "orphan" upload with no matching daily-prompt context (see
    poll_telegram.py) — derives title/description/tags AFTER the fact from
    what was actually transcribed, instead of the pre-written prompt lyrics."""
    prompt = METADATA_FROM_LYRICS_PROMPT.format(
        channel=CONFIG["channel"]["name"], lyrics=lyrics_text[:3000],
    )
    try:
        resp = requests.post(
            GEMINI_URL, params={"key": env("GEMINI_API_KEY")},
            json={"contents": [{"parts": [{"text": prompt}]}]}, timeout=60,
        )
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(text)
        print(f"[suno_prompt] Derived metadata from lyrics: {data['title']}")
        return data
    except Exception as e:  # noqa: BLE001
        print(f"[suno_prompt] Metadata-from-lyrics failed ({e}); using generic fallback.")
        return {
            "title": "Neuer Track",
            "description": "Ein originaler Deutschrap-Song. 100% Original, Text und Musik.",
            "tags": ["deutschrap", "german rap", "original song", "new music"],
        }
