"""Entrypoint: picks today's style, generates the Suno prompt, saves it to
state (so the poller can match it to the MP3 that comes back later), and
sends it to the team's Telegram group.

    python -m src.send_daily_prompt

Called daily by .github/workflows/daily_prompt.yml — but ALSO self-checked
from within poll_telegram.py's reliable ~45s loop (see ensure_sent below),
since GitHub's once-a-day `schedule:` trigger has been observed to silently
fail to fire at all on some days. The loop already runs near-continuously,
so it doubles as a much more reliable guarantee that a prompt goes out every
day than depending on a second, separate schedule trigger.
"""
import datetime

from . import state, suno_prompt, telegram_bot
from .settings import CONFIG


def build_message(style: dict, song: dict) -> str:
    return (
        f"New Suno prompt — {CONFIG['channel']['name']}\n"
        f"Title: {song['title']}\n"
        f"Style: {style['name']}\n\n"
        "--- STYLE OF MUSIC (paste into Suno) ---\n"
        f"{song['style_tags']}\n\n"
        "--- LYRICS (paste into Suno's custom lyrics box) ---\n"
        f"{song['lyrics']}\n\n"
        "Reply in this chat with the finished MP3 once Suno generates it 🎵"
    )


def run():
    style = suno_prompt.pick_style()
    song = suno_prompt.generate(style)

    telegram_bot.send_message(build_message(style, song))

    st = state.load()
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
    st["pending"] = {
        "style_name": style["name"],
        "visual": style["visual"],
        "stock_query": style.get("stock_query"),
        "song": song,
    }
    st["pending_date"] = today
    st["last_prompt_date"] = today
    state.save(st)
    print("[send_daily_prompt] Sent prompt to Telegram, saved pending state.")


def ensure_sent() -> bool:
    """Sends today's prompt if it hasn't gone out yet today. Returns True if
    a prompt was sent, False if one was already sent today (no-op).

    A pending prompt from a PRIOR day (still unfulfilled — nobody uploaded a
    reply) is treated as abandoned and replaced with a fresh one, so a missed
    day never blocks daily delivery going forward. A pending prompt from
    TODAY is left alone (don't clobber one that might already be in
    progress in Suno).
    """
    st = state.load()
    today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()

    if st.get("last_prompt_date") == today:
        return False  # already sent today

    if st.get("pending") and st.get("pending_date") == today:
        return False  # today's prompt exists but hasn't been marked sent yet (race-safe no-op)

    print("[send_daily_prompt] No prompt sent yet today — sending now.")
    run()
    return True


if __name__ == "__main__":
    run()
