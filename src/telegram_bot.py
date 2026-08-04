"""Thin wrapper around Telegram's official Bot API (free, no ToS risk, no
CAPTCHA to fight) — used to send the daily Suno prompt to your team's group
and to receive the finished MP3 back, then deliver the final video.
"""
from .settings import OUTPUT_DIR, env

import requests


def _url(method: str) -> str:
    return f"https://api.telegram.org/bot{env('TELEGRAM_BOT_TOKEN')}/{method}"


def _chat_id() -> str:
    return env("TELEGRAM_CHAT_ID")


def send_message(text: str) -> None:
    r = requests.post(_url("sendMessage"), data={"chat_id": _chat_id(), "text": text}, timeout=30)
    r.raise_for_status()


def send_photo(photo_path: str, caption: str = "") -> None:
    with open(photo_path, "rb") as f:
        r = requests.post(_url("sendPhoto"), data={"chat_id": _chat_id(), "caption": caption[:1024]},
                           files={"photo": f}, timeout=60)
    r.raise_for_status()


def send_video(video_path: str, caption: str = "") -> None:
    with open(video_path, "rb") as f:
        r = requests.post(_url("sendVideo"), data={"chat_id": _chat_id(), "caption": caption[:1024]},
                           files={"video": f}, timeout=300)
    r.raise_for_status()


def get_updates(offset=None, timeout: int = 25) -> list:
    params = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    r = requests.get(_url("getUpdates"), params=params, timeout=timeout + 10)
    r.raise_for_status()
    return r.json()["result"]


def download_file(file_id: str, out_name: str) -> str:
    """Bot API caps file downloads at 20MB — fine for an MP3, which is typically 2-6MB."""
    r = requests.get(_url("getFile"), params={"file_id": file_id}, timeout=30)
    r.raise_for_status()
    file_path = r.json()["result"]["file_path"]
    file_url = f"https://api.telegram.org/file/bot{env('TELEGRAM_BOT_TOKEN')}/{file_path}"
    out_path = str(OUTPUT_DIR / out_name)
    with requests.get(file_url, stream=True, timeout=120) as resp:
        resp.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
    return out_path
