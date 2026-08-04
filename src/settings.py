"""Loads config.yaml + environment variables. One source of truth."""
import os
import sys
from pathlib import Path

import yaml

# Windows terminals default to a legacy codepage that can't print emoji; force
# UTF-8 so our log lines (🌙 etc.) never crash the run. No-op on Linux/macOS.
if sys.platform == "win32":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv is only needed for local runs; GitHub Actions injects env directly.

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"
ASSETS_DIR = ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"

OUTPUT_DIR.mkdir(exist_ok=True)


def load_config() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


CONFIG = load_config()


def env(key: str, required: bool = True) -> str:
    val = os.environ.get(key, "").strip()
    if required and not val:
        raise RuntimeError(
            f"Missing environment variable {key}. "
            f"Add it to your .env file (local) or GitHub Secrets (cloud)."
        )
    return val
