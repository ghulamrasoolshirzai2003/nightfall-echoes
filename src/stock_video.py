"""Real licensed stock video footage (Pexels, free) as the video's visual —
actual human-shot motion instead of a zoomed still image, which is what
genuinely "looks real" since it is real. Falls back to the existing AI-image
approach if Pexels has no match or the key is missing/rate-limited, so this
can never break the daily run.
"""
import random

import requests

from . import footage_quality
from .settings import OUTPUT_DIR, env

SEARCH_URL = "https://api.pexels.com/videos/search"
MAX_QUALITY_CHECKS = 4  # cap Gemini-vision calls per search — bounds latency/cost


def _pick_best_file(video_files: list, width: int, height: int):
    """Picks the file closest to the target size — big enough to not look
    blurry, small enough to download quickly."""
    candidates = [f for f in video_files if (f.get("link") or "").endswith(".mp4")]
    if not candidates:
        return None
    return min(candidates, key=lambda f: abs((f.get("width") or 0) - width)
               + abs((f.get("height") or 0) - height))["link"]


def _pick_usable_candidate(shortlist: list) -> dict:
    """Checks candidates' preview images with Gemini vision (see
    src/footage_quality.py) and returns the first one with normal, usable
    camera framing — catches extreme tilted/disorienting angles that read
    badly with captions overlaid on top. Falls back to the first candidate
    unchecked if none pass within the check budget, so a clip is always
    returned rather than the search failing outright."""
    shuffled = shortlist[:]
    random.shuffle(shuffled)
    for video in shuffled[:MAX_QUALITY_CHECKS]:
        preview = video.get("image")
        if not preview or footage_quality.is_usable_framing(preview):
            return video
        print(f"[stock_video] Rejected clip {video.get('id')} — unusual camera framing.")
    return shuffled[0]


def find_clip(query: str, width: int, height: int, exclude_ids: set | None = None,
              min_duration: float = 0):
    """Returns (video_id, download_url, duration) or None.

    `exclude_ids` lets a caller building a multi-scene video avoid picking the
    same clip twice. `min_duration` prefers a clip long enough to be sliced
    into several consecutive scene segments (so the same people appear
    throughout that block) — falls back to the longest available candidate
    if nothing meets it, rather than failing outright.
    """
    exclude_ids = exclude_ids or set()
    orientation = "portrait" if height > width else "landscape"
    try:
        r = requests.get(
            SEARCH_URL,
            headers={"Authorization": env("PEXELS_API_KEY")},
            params={"query": query, "per_page": 15, "orientation": orientation},
            timeout=30,
        )
        r.raise_for_status()
        results = r.json().get("videos", [])
        candidates = [v for v in results if v.get("id") not in exclude_ids]
        if not candidates:
            print(f"[stock_video] No (new) Pexels results for '{query}'.")
            return None

        if min_duration > 0:
            long_enough = [v for v in candidates if (v.get("duration") or 0) >= min_duration]
            shortlist = long_enough[:5] if long_enough else (
                # Nothing is long enough — use the longest few we've got
                # rather than fail; the caller loops it to fill remaining time.
                sorted(candidates[:8], key=lambda v: v.get("duration") or 0, reverse=True)[:5]
            )
        else:
            shortlist = candidates[:5]

        video = _pick_usable_candidate(shortlist)
        file_url = _pick_best_file(video["video_files"], width, height)
        if not file_url:
            return None
        return video["id"], file_url, video.get("duration") or 0
    except Exception as e:  # noqa: BLE001
        print(f"[stock_video] Pexels search failed ({e}).")
        return None


def download_clip(url: str, out_name: str = "stock_clip.mp4") -> str:
    out_path = str(OUTPUT_DIR / out_name)
    with requests.get(url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    print(f"[stock_video] Downloaded: {out_path}")
    return out_path


def fetch_background_clip(query: str, width: int, height: int, out_name: str = "stock_clip.mp4"):
    """Simple single-clip fetch (no dedup) — used by the non-story fallback path.
    Returns a local file path, or None if unavailable."""
    found = find_clip(query, width, height)
    if not found:
        return None
    _video_id, url, _duration = found
    return download_clip(url, out_name)


def fetch_unique_clip(query: str, width: int, height: int, exclude_ids: set, out_name: str,
                       min_duration: float = 0):
    """Story-video variant: returns (video_id, local_path, source_duration) while
    avoiding any id already in `exclude_ids`, or None if nothing new is available."""
    found = find_clip(query, width, height, exclude_ids, min_duration)
    if not found:
        return None
    video_id, url, duration = found
    return video_id, download_clip(url, out_name), duration
