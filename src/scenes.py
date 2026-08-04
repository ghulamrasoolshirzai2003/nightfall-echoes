"""Turns a word-level transcription into a scene + shot-group plan:

1. Chunks words into natural phrase-level scenes — a new scene starts at
   each real pause in the vocal (not evenly-spaced time slices), and each
   scene's cut point is snapped to the nearest detected beat so cuts feel
   rhythm-aligned. This also fixes captions "appearing before the singer" —
   a scene/caption's start is the actual first word's start, not a loose
   Whisper segment boundary that can bundle several bars together.
2. Asks Gemini to cluster CONSECUTIVE scenes that share the same visual
   setting/characters into "shot groups" (e.g. all the celebration scenes
   share one group), each with one stock-footage search query.

Grouping is what enables character consistency: src/story_video.py fetches
ONE longer clip per group and slices different moments of it across that
group's scenes — same real people throughout, because it's the same shot.
"""
import json

import requests

from . import beats as beats_mod
from .settings import CONFIG, env

GEMINI_MODEL = "gemini-flash-latest"  # alias that always points to the current model
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

COLOR_MOODS = ["warm_romantic", "cool_melancholic", "vibrant_energetic", "moody_dark"]

PROMPT = """You are directing a music video for an original song. Style: {style_tags}.

Here are the song's scenes in order, with the actual sung lyrics in each:
{scene_list}

Group CONSECUTIVE scenes that would naturally show the SAME setting/characters
into "shot groups" — like a movie keeps the same actors for a continuous
sequence before cutting to a new one. Only start a new group when the content
genuinely changes (new subject, new mood, new setting). A group can be just
one scene if nothing else fits with it. Every scene must belong to exactly one
group, groups must be in order, and together they must cover all {n} scenes
with no gaps or overlaps.

For each group, give ONE short, concrete stock-footage search query (3-6
words, literal and visual) matching what's being sung across that whole
group. Examples: a group about racing -> "car racing highway night"; a group
about heartbreak/goodbye -> "couple separation sad breakup"; a group about
romance -> "couple sunset romantic walk"; a group about ambition/hustle ->
"city skyline night neon".

Also pick ONE overall color_mood for the whole video from exactly this list:
{color_moods}

Return ONLY valid JSON (no markdown fences):
{{
  "color_mood": "<one of the list above>",
  "groups": [
    {{"scene_indices": [0, 1], "query": "..."}},
    {{"scene_indices": [2], "query": "..."}}
  ]
}}
scene_indices are 0-based, in order, covering 0 through {max_index} exactly once total.
"""


def chunk_into_scenes(words: list[dict], total_duration: float, audio_path: str, *,
                       pause_threshold: float = 0.45, max_chunk_duration: float = 7.0,
                       min_chunk_duration: float = 1.2, beat_tolerance: float = 0.35) -> list[dict]:
    """Groups words into natural phrase-level scenes instead of fixed
    even-time slices: a new scene starts wherever there's a real pause in the
    vocal (gap >= pause_threshold) or a run of words gets too long
    (>= max_chunk_duration) to stay as one caption/shot. Very short chunks
    get merged into a neighbor. Every scene's start/end is then snapped to
    the nearest beat (see src/beats.py) so cuts land on the rhythm.

    Deliberately spans the whole song (0 -> total_duration), with empty-text
    "instrumental" scenes filling any silent gaps — the video must never run
    shorter than the audio.
    """
    if total_duration <= 0:
        return []
    if not words:
        return [{"start": 0.0, "end": total_duration, "text": ""}]

    raw_chunks: list[list[dict]] = [[words[0]]]
    for w in words[1:]:
        last = raw_chunks[-1]
        gap = w["start"] - last[-1]["end"]
        span = last[-1]["end"] - last[0]["start"]
        if gap >= pause_threshold or span >= max_chunk_duration:
            raw_chunks.append([w])
        else:
            last.append(w)

    # Merge any chunk that's too short into the previous one, unless the gap
    # before it is itself a real pause (in which case it's a deliberate short
    # phrase, not a fragment).
    merged: list[list[dict]] = []
    for c in raw_chunks:
        span = c[-1]["end"] - c[0]["start"]
        gap_before = c[0]["start"] - merged[-1][-1]["end"] if merged else 999
        if merged and span < min_chunk_duration and gap_before < pause_threshold:
            merged[-1].extend(c)
        else:
            merged.append(c)

    scenes = []
    prev_end = 0.0
    for c in merged:
        start, end = c[0]["start"], c[-1]["end"]
        if start - prev_end > 0.5:
            scenes.append({"start": prev_end, "end": start, "text": ""})  # instrumental gap
        scenes.append({"start": start, "end": end, "text": " ".join(w["text"] for w in c)})
        prev_end = end
    if total_duration - prev_end > 0.5:
        scenes.append({"start": prev_end, "end": total_duration, "text": ""})

    beat_times = beats_mod.detect_beats(audio_path)
    for i in range(1, len(scenes)):
        snapped = beats_mod.snap_to_beat(scenes[i]["start"], beat_times, beat_tolerance)
        scenes[i - 1]["end"] = snapped
        scenes[i]["start"] = snapped

    print(f"[scenes] Chunked into {len(scenes)} phrase-level scenes "
          f"(avg {total_duration / max(len(scenes), 1):.1f}s each).")
    return scenes


def chunk_words_into_captions(words: list[dict], *, max_words: int = 4,
                               max_duration: float = 2.2, pause_threshold: float = 0.25) -> list[dict]:
    """Groups words into SHORT caption bursts (a few words at a time) that
    track the vocal tightly — deliberately much finer-grained than the visual
    scene cuts (chunk_into_scenes). A visual shot can hold for ~5s while the
    caption underneath changes every 1-2s in short phrases, same as real
    short-form lyric videos, rather than one long sentence sitting on screen."""
    if not words:
        return []

    chunks: list[list[dict]] = [[words[0]]]
    for w in words[1:]:
        last = chunks[-1]
        gap = w["start"] - last[-1]["end"]
        span = w["end"] - last[0]["start"]
        if gap >= pause_threshold or span > max_duration or len(last) >= max_words:
            chunks.append([w])
        else:
            last.append(w)

    captions = [
        {"start": c[0]["start"], "end": c[-1]["end"], "text": " ".join(w["text"] for w in c)}
        for c in chunks
    ]
    avg = sum(c["end"] - c["start"] for c in captions) / max(len(captions), 1)
    print(f"[scenes] Chunked into {len(captions)} short caption bursts (avg {avg:.1f}s each).")
    return captions


def _fallback(scenes: list[dict], default_query: str) -> dict:
    """One group covering every scene — ironically gives full-song character
    consistency for free even when Gemini is unavailable, since it's all one
    sliced clip rather than a query repeated across independent searches."""
    return {"color_mood": "cool_melancholic",
            "groups": [{"scene_indices": list(range(len(scenes))), "query": default_query}]}


def _validate(data: dict, n: int) -> bool:
    if data.get("color_mood") not in COLOR_MOODS:
        return False
    groups = data.get("groups")
    if not isinstance(groups, list) or not groups:
        return False
    seen = []
    for g in groups:
        indices = g.get("scene_indices")
        if not isinstance(indices, list) or not g.get("query"):
            return False
        seen.extend(indices)
    return sorted(seen) == list(range(n))


def plan_visuals(scenes: list[dict], style_tags: str, default_query: str) -> dict:
    """Returns {"color_mood": str, "groups": [{"scene_indices": [...], "query": str}, ...]}."""
    if not scenes:
        return {"color_mood": "cool_melancholic", "groups": []}

    scene_list = "\n".join(
        f"{i}. \"{s['text']}\"" if s["text"] else f"{i}. (instrumental, no lyrics)"
        for i, s in enumerate(scenes)
    )
    prompt = PROMPT.format(
        style_tags=style_tags, scene_list=scene_list,
        color_moods=", ".join(COLOR_MOODS), n=len(scenes), max_index=len(scenes) - 1,
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
        if not _validate(data, len(scenes)):
            raise ValueError(f"Gemini returned malformed/incomplete group plan: {data}")
        print(f"[scenes] Planned {len(data['groups'])} shot groups over {len(scenes)} scenes, "
              f"color_mood={data['color_mood']}")
        return data
    except Exception as e:  # noqa: BLE001 — never let this crash the run.
        print(f"[scenes] Gemini scene planning failed ({e}); using fallback (one group, all scenes).")
        return _fallback(scenes, default_query)
