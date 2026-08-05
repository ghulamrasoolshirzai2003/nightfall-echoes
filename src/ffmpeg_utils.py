"""Small shared ffmpeg/ffprobe helpers used by more than one pipeline stage."""
import subprocess
from pathlib import Path


def _run(cmd: list[str]) -> None:
    """Runs an ffmpeg/ffprobe command, raising with the REAL stderr message on
    failure instead of an opaque CalledProcessError exit code."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\n\n{result.stderr[-3000:]}"
        )

# One consistent color grade per song (see src/scenes.py) so clips pulled from
# different stock-footage sources still feel like the same visual world.
COLOR_GRADES = {
    "warm_romantic": "eq=saturation=1.15:contrast=1.05:brightness=0.02,colorbalance=rs=0.08:gs=0.02:bs=-0.06",
    "cool_melancholic": "eq=saturation=0.85:contrast=1.08:brightness=-0.02,colorbalance=rs=-0.06:gs=0.0:bs=0.1",
    "vibrant_energetic": "eq=saturation=1.3:contrast=1.12:brightness=0.03",
    "moody_dark": "eq=saturation=0.8:contrast=1.15:brightness=-0.06,colorbalance=rs=-0.04:bs=0.06",
}


FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"


def _contains_devanagari(text: str) -> bool:
    """Hindi and several other Indian languages use the Devanagari script
    (U+0900-U+097F). Latin-only caption fonts render it as empty boxes."""
    return any("ऀ" <= ch <= "ॿ" for ch in text)


def _find_font_for_text(text: str) -> str:
    """Picks a font file that can actually render `text`'s script — a single
    Latin font silently renders Devanagari (Hindi) as empty tofu boxes, which
    is exactly what happened before this was script-aware. The Devanagari
    font is bundled in the repo so it's available in CI too, not just
    wherever it happens to be installed as a system font."""
    if _contains_devanagari(text):
        candidates = [FONTS_DIR / "NotoSansDevanagari-Bold.ttf"]
    else:
        candidates = [
            FONTS_DIR / "DejaVuSans-Bold.ttf",
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
            Path("C:/Windows/Fonts/arialbd.ttf"),
        ]
    for c in candidates:
        if c.exists():
            return c.as_posix()
    raise FileNotFoundError(
        f"No font file found for {'Devanagari' if _contains_devanagari(text) else 'Latin'} "
        "captions. On Linux, `apt-get install fonts-dejavu-core`; on Windows, "
        "arialbd.ttf should already exist."
    )


def _wrap_caption_lines(text: str, font_path: str, font_size: int, max_width: int) -> list[str]:
    """Wraps caption text to fit `max_width` pixels, measured against the
    ACTUAL font/size used to render it — a long Whisper segment rendered
    unwrapped just runs off both edges of the frame, since drawtext has no
    built-in auto-wrap. Returns separate line strings (never joined with an
    embedded "\\n") — ffmpeg's drawtext renders a literal newline byte as a
    visible "tofu" box glyph even while still using it as a line break, so
    each line is rendered as its own drawtext filter instance instead."""
    from PIL import ImageFont

    font = ImageFont.truetype(font_path, font_size)
    words = text.split()
    if not words:
        return [text]

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if font.getlength(candidate) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _escape_path_for_filter(path: str) -> str:
    """ffmpeg's filtergraph parser treats ':' as special — escape a Windows
    drive letter like C:/foo/bar.ttf into C\\:/foo/bar.ttf. Used for file
    paths (font files, caption text files), which never contain quotes."""
    return Path(path).as_posix().replace(":", "\\:")


def probe_duration(media_path: str) -> float:
    """Returns a media file's real duration in seconds via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", media_path],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout.strip())


def render_zoom_video(image_path: str, audio_path: str, out_path: str, *,
                       width: int, height: int, duration: float, fps: int,
                       zoom_speed: float, zoom_max: float) -> None:
    """Still image -> slow continuous zoom ("Ken Burns") video, muxed with audio.

    Used for both the long-form video and Shorts so neither is a fully static
    frame — the subtle motion reads as intentional production, not a slideshow.
    """
    total_frames = max(int(duration * fps), 1)
    vf = (
        "scale=8000:-1,"
        f"zoompan=z='min(zoom+{zoom_speed},{zoom_max})':d={total_frames}:s={width}x{height}:fps={fps}"
    )
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-filter_complex", f"[0:v]{vf}[v]",
        "-map", "[v]", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration),
        out_path,
    ]
    _run(cmd)


def render_video_with_clip(clip_path: str, audio_path: str, out_path: str, *,
                            width: int, height: int, duration: float) -> None:
    """Loops/trims a real (stock) video clip to match the audio's exact
    length, crops to fill the target frame, and muxes with the audio."""
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"fade=t=in:st=0:d=1,fade=t=out:st={max(duration - 1, 0)}:d=1"
    )
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", clip_path,
        "-i", audio_path,
        "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(duration),
        out_path,
    ]
    _run(cmd)


def render_scene_clip(clip_path: str, out_path: str, *, duration: float,
                       width: int, height: int, color_mood: str, fps: int = 30,
                       source_offset: float = 0, source_duration: float | None = None) -> None:
    """One silent scene clip: trimmed to its slice of the song, cropped to
    fill the frame, color-graded to match the rest of the song's scenes,
    with a short internal fade so cuts between scenes feel intentional.

    `source_offset` lets several scenes in the same "shot group" (see
    src/story_video.py) each pull a DIFFERENT moment from the SAME downloaded
    clip rather than all starting at its beginning — same people throughout
    the group, but not a literal repeated frame-for-frame loop.

    Uses an INPUT-side seek (`-ss` before `-i`) when the source clip is long
    enough to cover [offset, offset+duration] outright — this is the
    reliable, well-tested seek method. `-stream_loop` is only added when we
    actually need to wrap past the end of a too-short source clip; combining
    `-stream_loop` with an output-side seek (i.e. `-ss` placed after `-i`)
    was tried first and silently produced a frozen/black clip after the first
    few frames — that combination is unreliable and deliberately avoided here.

    Forces a consistent `fps` on every scene — stock clips arrive with
    different native frame rates (24/25/30fps etc.), and leaving them
    mismatched breaks reliable concatenation later.
    """
    grade = COLOR_GRADES.get(color_mood, COLOR_GRADES["cool_melancholic"])
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},fps={fps},{grade},"
        f"fade=t=in:st=0:d=0.4,fade=t=out:st={max(duration - 0.4, 0)}:d=0.4"
    )

    needs_loop = source_duration is not None and (source_offset + duration) > source_duration
    effective_offset = (source_offset % source_duration) if source_duration else source_offset

    cmd = ["ffmpeg", "-y"]
    if needs_loop:
        cmd += ["-stream_loop", "-1"]
    cmd += ["-ss", str(effective_offset), "-i", clip_path]
    cmd += [
        "-vf", vf,
        "-an",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-t", str(duration),
        out_path,
    ]
    _run(cmd)


def concat_clips(clip_paths: list[str], out_path: str) -> None:
    """Joins silent scene clips end-to-end into one continuous silent video.

    Uses the concat FILTER (decodes and re-encodes every frame), not the
    concat DEMUXER's stream-copy mode. Stream-copy concat requires every
    input to share identical codec parameters — with clips originally pulled
    from different stock sources, even a single mismatched timebase silently
    produces broken output (typically only the first segment plays right).
    The filter is immune to that because it works on decoded frames.
    """
    inputs = []
    filter_parts = []
    for i, p in enumerate(clip_paths):
        inputs += ["-i", p]
        filter_parts.append(f"[{i}:v]")
    filter_complex = "".join(filter_parts) + f"concat=n={len(clip_paths)}:v=1:a=0[outv]"
    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        out_path,
    ]
    _run(cmd)


def mux_with_audio_and_captions(silent_video_path: str, audio_path: str, segments: list[dict],
                                 out_path: str, *, duration: float, width: int, height: int) -> None:
    """Final pass: attaches the real song audio and burns in styled, synced
    lyric captions over the concatenated scene video.

    Uses `drawtext` (one call per caption line, each active only during its
    own [start, end] window) instead of the `subtitles` filter — drawtext
    coordinates are always real output pixels, so positioning is exact and
    doesn't depend on libass's internal script-resolution guessing (which is
    what put captions mid-screen instead of near the bottom before).

    Each caption's text is written to its own small .txt file and referenced
    via `textfile=`, not inlined as `text=`. Lyrics can contain apostrophes,
    colons, or other characters that are genuinely fragile to escape inside
    ffmpeg's filtergraph string syntax — reading raw bytes from a file
    sidesteps that whole class of bug entirely.
    """
    from .settings import OUTPUT_DIR  # local import avoids a circular import at module load

    font_size = max(int(height * 0.05), 18)
    y_from_bottom = int(height * 0.12)  # bottom-third, standard lyric-video proportion
    max_text_width = int(width * 0.92)  # leaves a small margin each side

    captions_dir = OUTPUT_DIR / "captions"
    captions_dir.mkdir(exist_ok=True)
    line_height = int(font_size * 1.3)

    parts = []
    for i, seg in enumerate(segments):
        # Picked per-caption, not once globally — a song can genuinely mix
        # scripts line to line (e.g. an English hook in an otherwise Hindi
        # song), and a Latin-only font renders Devanagari as empty boxes.
        font_file = _find_font_for_text(seg["text"])
        lines = _wrap_caption_lines(seg["text"], font_file, font_size, max_text_width)

        # One drawtext filter PER LINE (never a multi-line \n-joined string —
        # see _wrap_caption_lines for why), stacked upward from the bottom.
        for line_idx, line_text in enumerate(lines):
            cap_path = captions_dir / f"cap_{i:03d}_{line_idx}.txt"
            cap_path.write_bytes(line_text.encode("utf-8"))
            textfile = _escape_path_for_filter(str(cap_path))
            line_from_bottom = (len(lines) - 1) - line_idx
            y_expr = f"h-{y_from_bottom}-text_h-{line_from_bottom * line_height}"
            parts.append(
                f"drawtext=fontfile='{_escape_path_for_filter(font_file)}':textfile='{textfile}':"
                f"fontsize={font_size}:fontcolor=white:borderw=3:bordercolor=black:"
                f"box=1:boxcolor=black@0.40:boxborderw=10:"
                f"x=(w-text_w)/2:y={y_expr}:"
                f"enable='between(t,{seg['start']:.2f},{seg['end']:.2f})'"
            )
    vf = ",".join(parts) if parts else "null"

    # Cap bitrate so the file stays safely under Telegram's 50MB bot-upload
    # limit regardless of song length or how much motion/detail the footage
    # has — plain CRF alone hit 49.3MB on a real busy multi-scene test, too
    # close to the ceiling. Budgeted per-second so longer songs scale down
    # automatically instead of risking the same fixed bitrate blowing past it.
    target_max_mb = 40
    audio_kbps = 192
    video_kbps = max(400, int((target_max_mb * 8192) / max(duration, 1)) - audio_kbps)

    cmd = [
        "ffmpeg", "-y",
        "-i", silent_video_path,
        "-i", audio_path,
        "-vf", vf,
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-crf", "23", "-maxrate", f"{video_kbps}k", "-bufsize", f"{video_kbps * 2}k",
        "-c:a", "aac", "-b:a", f"{audio_kbps}k",
        "-t", str(duration),
        out_path,
    ]
    _run(cmd)
