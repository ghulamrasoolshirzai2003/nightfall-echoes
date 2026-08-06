"""Entrypoint: checks Telegram for a newly uploaded MP3 reply, and if found,
builds the thumbnail + video for it and sends the finished video back to the
group. Also guarantees the daily prompt goes out (see ensure_sent below) —
called from a self-chaining loop that runs near-continuously, so neither of
these depends on GitHub's own `schedule:` trigger, which has been observed
to silently fail to fire reliably.

Works for TWO upload cases:
1. A reply to today's prompt (the normal flow) — uses the pre-generated
   title/description/tags/style from send_daily_prompt.py.
2. An "orphan" upload with no matching prompt (uploaded any time, standalone)
   — transcribes it, derives title/description/tags from what was actually
   sung, and picks a generic visual style. Either way, any audio upload gets
   a finished video back — nothing is silently ignored.

    python -m src.poll_telegram

Called every ~45s by the inner loop in .github/workflows/poll_telegram.yml.
"""
from . import send_daily_prompt, state, stock_video, story_video, suno_prompt, telegram_bot, thumbnail, video
from .ffmpeg_utils import probe_duration, render_video_with_clip
from .settings import CONFIG, OUTPUT_DIR


def _progress_notifier():
    """Returns an on_progress(percent, message) callback that relays each
    checkpoint to Telegram as a short "X% - message" update, so there's
    visible movement during the several minutes a build takes instead of
    total silence."""
    def notify(percent: int, message: str) -> None:
        telegram_bot.send_message(f"⏳ {percent}% — {message}")
    return notify


def _build_video(style_tags: str, stock_query: str | None, background_path: str,
                  audio_path: str, on_progress) -> tuple[str, str | None]:
    """Tries the full story-video build first (transcribed scenes matched to
    real footage + synced captions) — returns (video_path, transcribed_lyrics).
    Falls back to a single looped stock clip, then to the AI-image + zoom —
    never breaks the run either way, though the fallbacks don't transcribe,
    so lyrics come back as None in that case."""
    v = CONFIG["video"]
    out_path = str(OUTPUT_DIR / "video.mp4")

    if stock_query:
        result = story_video.build_story_video(
            audio_path, style_tags, stock_query, v["width"], v["height"], out_path,
            on_progress=on_progress,
        )
        if result:
            return result

    if stock_query:
        clip_path = stock_video.fetch_background_clip(stock_query, v["width"], v["height"])
        if clip_path:
            duration = probe_duration(audio_path)
            render_video_with_clip(clip_path, audio_path, out_path,
                                    width=v["width"], height=v["height"], duration=duration)
            print("[poll_telegram] Story build unavailable; used a single looped stock clip.")
            return out_path, None

    print("[poll_telegram] No stock footage available; using AI image + zoom instead.")
    return video.make_video(background_path, audio_path), None


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


def _details_message(song: dict) -> str:
    """Full copy-paste-ready package for whoever uploads this — title,
    YouTube-ready description, and the full tag list, not just a caption
    snippet (Telegram video captions cap at 1024 chars, too short for this)."""
    tags = song.get("tags", [])
    tags_line = ", ".join(tags) if tags else "(none generated)"
    message = (
        f"📋 Full details for: {song['title']}\n\n"
        f"TITLE:\n{song['title']}\n\n"
        f"DESCRIPTION:\n{song.get('description', '(none generated)')}\n\n"
        f"TAGS:\n{tags_line}"
    )
    return message[:4096]  # Telegram's hard message-length limit


def _process_pending(audio_path: str, pending: dict) -> None:
    """Normal flow: this upload is a reply to today's prompt, so we already
    have rich title/description/tags/style generated ahead of time."""
    song = pending["song"]
    mood_like = {"visual": pending["visual"]}
    title = song["title"]

    background_path, thumb_path = thumbnail.make_thumbnail(mood_like, title)
    video_path, _lyrics = _build_video(song.get("style_tags", pending["style_name"]),
                                        pending.get("stock_query"), background_path, audio_path,
                                        _progress_notifier())

    telegram_bot.send_photo(thumb_path, caption=f"Thumbnail: {title}")
    telegram_bot.send_video(video_path, caption=title)
    telegram_bot.send_message(_details_message(song))


def _process_orphan(audio_path: str) -> None:
    """No matching prompt on file — someone uploaded a song standalone. Still
    builds a full video: picks a generic style for the visual fallback, lets
    the real transcription drive scene-matching as usual, then derives
    title/description/tags from what was ACTUALLY sung afterward."""
    print("[poll_telegram] No pending prompt for this upload — treating as standalone.")
    style = suno_prompt.pick_style()
    mood_like = {"visual": style["visual"]}

    background_path, thumb_path = thumbnail.make_thumbnail(mood_like, style["name"])
    video_path, lyrics = _build_video(style["style_tags"], style.get("stock_query"),
                                       background_path, audio_path, _progress_notifier())

    song = suno_prompt.generate_metadata_from_lyrics(lyrics) if lyrics else {
        "title": "Neuer Track", "description": "Ein originaler Song.", "tags": ["original song"],
    }
    title = song["title"]

    telegram_bot.send_photo(thumb_path, caption=f"Thumbnail: {title}")
    telegram_bot.send_video(video_path, caption=title)
    telegram_bot.send_message(_details_message(song))


def run():
    # Guarantees a prompt goes out every day without depending on GitHub's
    # separate (unreliable) once-a-day schedule trigger — this function gets
    # called every ~45s via the self-chaining loop, so "hasn't today's prompt
    # been sent yet" gets checked constantly rather than once. Isolated in
    # its own try/except — a hiccup here (e.g. a transient Telegram/Gemini
    # error) must never block this cycle from still processing a waiting
    # audio upload.
    try:
        send_daily_prompt.ensure_sent()
    except Exception as e:  # noqa: BLE001
        print(f"[poll_telegram] ensure_sent failed ({e}); continuing anyway.")

    st = state.load()
    pending = st.get("pending")

    updates = telegram_bot.get_updates(offset=st.get("telegram_offset"))
    if not updates:
        print("[poll_telegram] No new updates.")
        return

    for update in updates:
        st["telegram_offset"] = update["update_id"] + 1

        found = _extract_audio(update)
        if not found:
            continue
        file_id, file_name = found

        print(f"[poll_telegram] Received {file_name}, building final video...")
        # Immediate feedback — otherwise there's total silence for the ~5-10
        # min it takes to build the video, and no way to tell it was even
        # received vs. still waiting on the next poll cycle.
        telegram_bot.send_message(
            f"🎧 Got \"{file_name}\" — generating your video now. "
            "This usually takes about 5-10 minutes, I'll send progress updates here."
        )
        audio_path = telegram_bot.download_file(file_id, "suno_song.mp3")

        if pending:
            _process_pending(audio_path, pending)
            pending = None
            st["pending"] = None
        else:
            _process_orphan(audio_path)

        print("[poll_telegram] Sent finished video + full details to Telegram.")

    state.save(st)


if __name__ == "__main__":
    run()
