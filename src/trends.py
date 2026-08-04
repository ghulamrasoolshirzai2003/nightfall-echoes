"""Stage 1 — pick today's mood.

Weighted-random selection over the moods in config.yaml. This keeps the channel
varied while leaning into the styles you mark as higher-weight. It's intentionally
simple and dependency-free so it can never break the daily run.

(Hook for later: you can enrich the chosen mood with live YouTube/Google-Trends
keywords here without touching the rest of the pipeline.)
"""
import random

from .settings import CONFIG


def pick_mood() -> dict:
    moods = CONFIG["moods"]
    weights = [m.get("weight", 1) for m in moods]
    mood = random.choices(moods, weights=weights, k=1)[0]
    print(f"[trends] Today's mood: {mood['name']}")
    return mood
