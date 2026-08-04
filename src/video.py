"""Stage 5 — assemble the final MP4 (still image + audio) with ffmpeg.

Applies the same subtle "Ken Burns" zoom as the Shorts clip (see
src/ffmpeg_utils.py) so a 3-minute video isn't a fully static slide — it reads
as intentional production and helps retention, which YouTube's algorithm
rewards for long-form watch time.
"""
from .ffmpeg_utils import probe_duration, render_zoom_video
from .settings import CONFIG, OUTPUT_DIR


def make_video(image_path: str, audio_path: str) -> str:
    out_path = str(OUTPUT_DIR / "video.mp4")
    v = CONFIG["video"]
    duration = probe_duration(audio_path)
    print(f"[video] Rendering MP4 ({duration:.1f}s)...")
    render_zoom_video(
        image_path, audio_path, out_path,
        width=v["width"], height=v["height"], duration=duration, fps=v["fps"],
        zoom_speed=v["zoom_speed"], zoom_max=v["zoom_max"],
    )
    print(f"[video] Done: {out_path}")
    return out_path
