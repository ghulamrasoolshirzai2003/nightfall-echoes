"""Entrypoint: checks Telegram for a newly uploaded MP3 reply, and if found,
builds the thumbnail + video for it and sends the finished video back to the
group. Telegram has no push-to-GitHub webhook, so polling on a schedule is
the free, reliable option.

    python -m src.poll_telegram

Called every ~10-15 min by .github/workflows/poll_telegram.yml.
"""
from . import state, stock_video, story_video, telegram_bot, thumbnail, video
from .ffmpeg_utils import probe_duration, render_video_with_clip
from .settings import CONFIG, OUTPUT_DIR


def _build_video(style_tags: str, stock_query: str | None, background_path: str, audio_path: str) -> str:
    """Tries the full story-video build first (transcribed scenes matched to
    real footage + synced subtitles). Falls back to a single looped stock
    clip, then to the AI-image + zoom — never breaks the run either way."""
    v = CONFIG["video"]
    out_path = str(OUTPUT_DIR / "video.mp4")

    if stock_query:
        story_path = story_video.build_story_video(
            audio_path, style_tags, stock_query, v["width"], v["height"], out_path
        )
        if story_path:
            return story_path

    if stock_query:
        clip_path = stock_video.fetch_background_clip(stock_query, v["width"], v["height"])
        if clip_path:
            duration = probe_duration(audio_path)
            render_video_with_clip(clip_path, audio_path, out_path,
                                    width=v["width"], height=v["height"], duration=duration)
            print("[poll_telegram] Story build unavailable; used a single looped stock clip.")
            return out_path

    print("[poll_telegram] No stock footage available; using AI image + zoom instead.")
    return video.make_video(background_path, audio_path)


def _extract_audio(update: dict):
    msg = update.get("message") or update.get("channel_post")
    if not msg:
        return None
    for key in ("audio", "voice"):
        if key in msg:
            return msg[key]["file_id"], msg[key].get("file_name", "song.mp3")
    if "document" in msg:
        doc = msg["document"]
        mime = doc.get("mime_type", "")
        name = doc.get("file_name", "")
        if mime.startswith("audio/") or name.lower().endswith((".mp3", ".wav", ".m4a")):
            return doc["file_id"], name
    return None


def _description(song: dict, style_name: str) -> str:
    return (
        f"{song['title']} — an original {style_name} song.\n\n"
        "100% original lyrics and music, made for this channel.\n\n"
        f"#{style_name.replace(' ', '')} #originalsong #newmusic"
    )


def run():
    st = state.load()
    pending = st.get("pending")

    updates = telegram_bot.get_updates(offset=st.get("telegram_offset"))
    if not updates:
        print("[poll_telegram] No new updates.")
        return

    for update in updates:
        st["telegram_offset"] = update["update_id"] + 1

        if not pending:
            continue  # nothing waiting on an MP3 right now

        found = _extract_audio(update)
        if not found:
            continue
        file_id, file_name = found

        print(f"[poll_telegram] Received {file_name}, building final video...")
        audio_path = telegram_bot.download_file(file_id, "suno_song.mp3")

        song = pending["song"]
        mood_like = {"visual": pending["visual"]}
        title = song["title"]
        caption = f"{title}\n\n{_description(song, pending['style_name'])}"[:1024]

        background_path, thumb_path = thumbnail.make_thumbnail(mood_like, title)
        video_path = _build_video(song.get("style_tags", pending["style_name"]),
                                   pending.get("stock_query"), background_path, audio_path)

        telegram_bot.send_photo(thumb_path, caption=f"Thumbnail: {title}")
        telegram_bot.send_video(video_path, caption=caption)

        pending = None
        st["pending"] = None
        print("[poll_telegram] Sent finished video to Telegram.")

    state.save(st)


if __name__ == "__main__":
    run()
