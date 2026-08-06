"""Small JSON state file, committed back to the repo by the workflows.

Two jobs: (1) remember which Telegram messages were already processed
(telegram_offset), and (2) carry today's song details from the "send the
prompt" step to the later "an MP3 came back" step — they run as separate,
stateless GitHub Actions runs, so this file is the handoff between them.
"""
import json

from .settings import ROOT

STATE_PATH = ROOT / "state" / "state.json"


def load() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"telegram_offset": None, "pending": None, "pending_date": None, "last_prompt_date": None}


def save(state: dict) -> None:
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
