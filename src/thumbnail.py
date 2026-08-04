"""Stage 4 — thumbnail: free AI background (Pollinations) + bold text overlay (Pillow).

Pollinations.ai serves AI images from a plain URL with no API key and no cost.
We then overlay big, high-contrast text (with a dark scrim + shadow) because
readable text is the single biggest driver of thumbnail click-through.

The same background+text logic is reused for the Shorts vertical clip (9:16)
by parameterizing width/height/aspect — the layout math scales proportionally.
"""
import textwrap
import urllib.parse
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from .settings import CONFIG, FONTS_DIR, OUTPUT_DIR

W, H = 1280, 720


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    # Prefer a bundled font (so Linux runners match local), else fall back.
    for candidate in [FONTS_DIR / "Montserrat-Bold.ttf", FONTS_DIR / "DejaVuSans-Bold.ttf"]:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    for sys_font in ["DejaVuSans-Bold.ttf", "arialbd.ttf", "Arial Bold.ttf"]:
        try:
            return ImageFont.truetype(sys_font, size)
        except OSError:
            continue
    return ImageFont.load_default()


def fetch_background(visual_prompt: str, width: int, height: int, aspect: str) -> Image.Image:
    prompt = urllib.parse.quote(f"{visual_prompt}, cinematic, high detail, moody, {aspect}")
    url = f"https://image.pollinations.ai/prompt/{prompt}?width={width}&height={height}&nologo=true"
    print(f"[thumbnail] Fetching {width}x{height} AI background from Pollinations...")
    try:
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        img = Image.open(BytesIO(r.content)).convert("RGB").resize((width, height))
        return img
    except Exception as e:  # noqa: BLE001
        print(f"[thumbnail] Pollinations failed ({e}); using solid dark background.")
        return Image.new("RGB", (width, height), (12, 14, 28))


def draw_text(img: Image.Image, text: str, width: int, height: int) -> Image.Image:
    draw = ImageDraw.Draw(img)
    # Dark gradient scrim at the bottom for legibility.
    scrim = Image.new("L", (width, height), 0)
    sdraw = ImageDraw.Draw(scrim)
    for y in range(height):
        sdraw.line([(0, y), (width, y)], fill=int(180 * (y / height) ** 2))
    img.paste(Image.new("RGB", (width, height), (0, 0, 0)), (0, 0), scrim)

    lines = textwrap.wrap(text.upper(), width=16) or [""]
    font = _load_font(int(width * 0.109) if len(lines) == 1 else int(width * 0.086))

    line_h = font.getbbox("Ag")[3] + 18
    total_h = line_h * len(lines)
    y = (height - total_h) // 2 + 40
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (width - (bbox[2] - bbox[0])) // 2
        # shadow
        draw.text((x + 5, y + 5), line, font=font, fill=(0, 0, 0))
        draw.text((x, y), line, font=font, fill=(255, 255, 255))
        y += line_h

    # Channel tag top-left. Standard TTF fonts have no emoji glyphs (renders as
    # a broken-box "tofu"), so keep the overlay text-only; the emoji still
    # appears fine in the video title/description, which YouTube itself renders.
    tag_font = _load_font(int(width * 0.036))
    tag = CONFIG["channel"]["name"]
    draw.text((int(width * 0.034), int(height * 0.055)), tag, font=tag_font, fill=(230, 230, 240))
    return img


def make_thumbnail(mood: dict, thumbnail_text: str) -> tuple[str, str]:
    """Returns (background_path, thumbnail_path).

    `background_path` has NO text — it's what the video itself zooms into,
    since baking text into an image that later gets Ken-Burns-zoomed makes the
    title drift/crop off-screen. `thumbnail_path` (with text) is only used for
    YouTube's separate, static custom-thumbnail upload.
    """
    bg = fetch_background(mood["visual"], W, H, aspect="16:9")
    bg = bg.filter(ImageFilter.GaussianBlur(1))
    bg_path = str(OUTPUT_DIR / "background.png")
    bg.save(bg_path, "PNG")

    img = draw_text(bg.copy(), thumbnail_text or mood["name"], W, H)
    thumb_path = str(OUTPUT_DIR / "thumbnail.png")
    img.save(thumb_path, "PNG")
    print(f"[thumbnail] Saved: {thumb_path}")
    return bg_path, thumb_path
