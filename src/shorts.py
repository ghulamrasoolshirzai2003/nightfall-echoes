"""Stage 8 — build a YouTube Short: vertical 9:16 clip with a slow "Ken Burns"
zoom on the background (so it feels alive, not a static slide) plus the
freshest ~30s of original audio.

Shorts are the real discovery engine for a niche instrumental channel — the
algorithm feeds them to new viewers far more readily than long-form videos,
and a satisfying, aesthetic loop is what earns replays/shares even without
vocals. This is the free, sustainable growth lever (vs. one video "going
viral").
"""
from PIL import ImageFilter

from .ffmpeg_utils import probe_duration, render_zoom_video
from .settings import CONFIG, OUTPUT_DIR
from .thumbnail import draw_text, fetch_background


def make_shorts_thumbnail(mood: dict, text: str) -> tuple[str, str]:
    """Returns (background_path, thumbnail_path) — see thumbnail.make_thumbnail
    for why the video needs the plain (no-text) version."""
    cfg = CONFIG["shorts"]
    bg = fetch_background(mood["visual"], cfg["width"], cfg["height"], aspect="9:16 vertical portrait")
    bg = bg.filter(ImageFilter.GaussianBlur(1))
    bg_path = str(OUTPUT_DIR / "shorts_background.png")
    bg.save(bg_path, "PNG")

    img = draw_text(bg.copy(), text or mood["name"], cfg["width"], cfg["height"])
    thumb_path = str(OUTPUT_DIR / "shorts_thumbnail.png")
    img.save(thumb_path, "PNG")
    print(f"[shorts] Thumbnail saved: {thumb_path}")
    return bg_path, thumb_path


def make_shorts_video(image_path: str, audio_path: str) -> str:
    """Still image -> slow zoom-in video (zoompan), muxed with the seed audio."""
    cfg = CONFIG["shorts"]
    duration = min(probe_duration(audio_path), cfg["duration_seconds"])
    out_path = str(OUTPUT_DIR / "shorts_video.mp4")
    print(f"[shorts] Rendering vertical short ({duration:.1f}s)...")
    render_zoom_video(
        image_path, audio_path, out_path,
        width=cfg["width"], height=cfg["height"], duration=duration, fps=cfg["fps"],
        zoom_speed=cfg["zoom_speed"], zoom_max=cfg["zoom_max"],
    )
    print(f"[shorts] Done: {out_path}")
    return out_path


def make_shorts_metadata(meta: dict, mood: dict) -> dict:
    """Derives Shorts-specific title/description from the main video's metadata."""
    base_title = meta["title"]
    # Keep it short — Shorts titles get truncated hard in the UI.
    short_title = (base_title[:80] + "…") if len(base_title) > 80 else base_title
    if "#shorts" not in short_title.lower():
        short_title = f"{short_title} #Shorts"

    description = (
        f"{mood['name'].title()} — a short original clip. Full track on the channel. "
        "100% original, royalty-free, copyright-free.\n\n"
        "#Shorts #" + " #".join(k.replace(" ", "") for k in mood["keywords"][:6])
    )
    return {
        "title": short_title,
        "description": description,
        "tags": meta["tags"],
    }


def make_shorts(mood: dict, meta: dict, seed_audio_path: str) -> tuple[str, str, dict]:
    """Runs the full Shorts sub-pipeline. Returns (video_path, thumb_path, shorts_meta)."""
    bg, thumb = make_shorts_thumbnail(mood, meta.get("thumbnail_text", ""))
    video = make_shorts_video(bg, seed_audio_path)
    shorts_meta = make_shorts_metadata(meta, mood)
    return video, thumb, shorts_meta
