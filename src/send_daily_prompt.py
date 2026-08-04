"""Entrypoint: picks today's style, generates the Suno prompt, saves it to
state (so the poller can match it to the MP3 that comes back later), and
sends it to the team's Telegram group.

    python -m src.send_daily_prompt

Called daily by .github/workflows/daily_prompt.yml.
"""
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
    st["pending"] = {
        "style_name": style["name"],
        "visual": style["visual"],
        "stock_query": style.get("stock_query"),
        "song": song,
    }
    state.save(st)
    print("[send_daily_prompt] Sent prompt to Telegram, saved pending state.")


if __name__ == "__main__":
    run()
