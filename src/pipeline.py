"""The orchestrator — runs the whole A-to-Z pipeline once.

    python -m src.pipeline            # full run: make + upload
    python -m src.pipeline --dry-run  # make everything, skip the upload

Called daily by .github/workflows/daily.yml.
"""
import argparse
import sys

from . import concept, music, shorts, thumbnail, trends, video
from .settings import CONFIG


def run(dry_run: bool = False) -> None:
    print("=" * 60)
    print("🌙  Nightfall Echoes — daily run starting")
    print("=" * 60)

    # 1. Pick today's mood.
    mood = trends.pick_mood()

    # 2 + 6. Concept, title, description, tags (Gemini).
    meta = concept.generate(mood)

    # 3. Original music. seed = freshest ~30s (reused for Shorts), track = full length.
    seed_audio_path, track_audio_path = music.make_track(mood)

    # 4. Thumbnail. background = plain (feeds the zoomed video), thumb = with
    # text (uploaded as YouTube's separate static custom thumbnail).
    background_path, thumb_path = thumbnail.make_thumbnail(mood, meta.get("thumbnail_text", ""))

    # 5. Long-form video.
    video_path = video.make_video(background_path, track_audio_path)

    # 8. Shorts — the main free growth lever (see src/shorts.py).
    shorts_video_path = shorts_thumb_path = None
    shorts_meta = None
    if CONFIG["shorts"]["enabled"]:
        shorts_video_path, shorts_thumb_path, shorts_meta = shorts.make_shorts(
            mood, meta, seed_audio_path
        )

    # 7. Upload.
    if dry_run:
        print("\n[pipeline] --dry-run: skipping upload.")
        print(f"  video:        {video_path}")
        print(f"  thumbnail:    {thumb_path}")
        print(f"  title:        {meta['title']}")
        if shorts_video_path:
            print(f"  short:        {shorts_video_path}")
            print(f"  short title:  {shorts_meta['title']}")
        return

    from . import upload
    video_id = upload.upload(video_path, thumb_path, meta)
    print(f"\n✅ Long-form live! https://youtu.be/{video_id}")

    if shorts_video_path:
        short_id = upload.upload(shorts_video_path, shorts_thumb_path, shorts_meta)
        print(f"✅ Short live! https://youtu.be/{short_id}")


def main():
    parser = argparse.ArgumentParser(description="Nightfall Echoes daily pipeline")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build the video but don't upload.")
    args = parser.parse_args()
    try:
        run(dry_run=args.dry_run)
    except Exception as e:  # noqa: BLE001
        print(f"\n❌ Pipeline failed: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
