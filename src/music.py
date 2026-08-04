"""Stage 3 — generate ORIGINAL music with MusicGen, then extend it with ffmpeg.

To stay fast and free on CPU-only GitHub runners we generate two short seed
clips (config: music.seed_seconds each) from the same prompt and crossfade them
into one ~2x-length "base" clip, then loop THAT to the full track length. Looping
a single seed sounds obviously repetitive within a 3-minute track; alternating
two distinct takes roughly doubles the time before a listener notices the
pattern repeat. The audio is 100% original either way (no copyright).
"""
import subprocess

import scipy.io.wavfile

from .ffmpeg_utils import probe_duration
from .settings import CONFIG, OUTPUT_DIR


def _load_model(model_name: str):
    import torch  # imported lazily so the rest of the pipeline loads fast
    from transformers import AutoProcessor, MusicgenForConditionalGeneration

    print(f"[music] Loading {model_name} (first run downloads ~2GB)...")
    processor = AutoProcessor.from_pretrained(model_name)
    model = MusicgenForConditionalGeneration.from_pretrained(model_name)
    return torch, processor, model


def _generate_clip(prompt: str, seconds: int, torch, processor, model, out_name: str) -> str:
    """Run MusicGen once and write a wav clip. Returns its path."""
    inputs = processor(text=[prompt], padding=True, return_tensors="pt")
    # MusicGen makes ~50 tokens per second of audio. Its decoder has a hard
    # position-embedding ceiling (~2048 tokens, ~41s for musicgen-small) —
    # requesting more than that crashes with "index out of range in self".
    # Clamp with a safety margin so a config change can never break this.
    max_position_tokens = getattr(
        getattr(model.config, "decoder", model.config), "max_position_embeddings", 2048
    )
    safe_max_tokens = max_position_tokens - 48  # margin for the prompt's own tokens
    max_new_tokens = min(int(seconds * 50), safe_max_tokens)
    if max_new_tokens < int(seconds * 50):
        print(f"[music] Requested {seconds}s exceeds model limit; "
              f"capping to ~{max_new_tokens // 50}s.")
    print(f"[music] Generating ~{max_new_tokens // 50}s clip '{out_name}' "
          "(this is the slow part on CPU)...")
    with torch.no_grad():
        audio = model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=True)

    sr = model.config.audio_encoder.sampling_rate
    wav = audio[0, 0].cpu().numpy()
    path = str(OUTPUT_DIR / out_name)
    scipy.io.wavfile.write(path, rate=sr, data=wav)
    print(f"[music] Clip written: {path} ({sr} Hz)")
    return path


def _crossfade_join(clip_a: str, clip_b: str, crossfade_seconds: float = 2.0) -> str:
    """Crossfades two clips into one continuous clip (roughly duration_a + duration_b - overlap)."""
    out_path = str(OUTPUT_DIR / "base.wav")
    cmd = [
        "ffmpeg", "-y",
        "-i", clip_a, "-i", clip_b,
        "-filter_complex", f"acrossfade=d={crossfade_seconds}:c1=tri:c2=tri",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[music] Crossfaded base clip: {out_path}")
    return out_path


def _mastering_chain(duration_seconds: float) -> str:
    """Gentle compression (evens dynamics) -> subtle echo (sense of space) ->
    loudness normalization (YouTube's -14 LUFS target) -> edge fades. This is
    what takes a raw MusicGen clip from "flat AI sample" to something that
    sounds intentionally mixed."""
    fade_out_start = max(duration_seconds - 3, 0)
    return (
        "acompressor=threshold=0.1:ratio=3:attack=200:release=1000,"
        "aecho=0.8:0.9:60|40:0.25|0.15,"
        "loudnorm=I=-14:TP=-1.5:LRA=11,"
        f"afade=t=in:st=0:d=2,afade=t=out:st={fade_out_start}:d=3"
    )


def _extend_and_master(base_path: str, target_seconds: int) -> str:
    """Loop the base clip up to target length, then apply the mastering chain."""
    out_path = str(OUTPUT_DIR / "track.wav")
    cmd = [
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", base_path,
        "-t", str(target_seconds),
        "-af", _mastering_chain(target_seconds),
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[music] Full {target_seconds}s mastered track: {out_path}")
    return out_path


def _master_seed(seed_path: str) -> str:
    """Master a clip as-is (no looping) — used for the Shorts clip, which
    wants a single freshest take rather than the crossfaded/looped base."""
    out_path = str(OUTPUT_DIR / "seed_mastered.wav")
    actual_seconds = probe_duration(seed_path)
    cmd = ["ffmpeg", "-y", "-i", seed_path, "-af", _mastering_chain(actual_seconds), out_path]
    subprocess.run(cmd, check=True, capture_output=True)
    print(f"[music] Mastered seed clip: {out_path}")
    return out_path


def make_track(mood: dict) -> tuple[str, str]:
    """Returns (mastered_seed_path, full_track_path).

    The mastered seed (clip A, the freshest single take) is reused as-is for
    Shorts. The full track loops a crossfade of clip A + clip B, so its
    repeating pattern is ~2x longer than a single-clip loop would be.
    """
    cfg = CONFIG["music"]
    torch, processor, model = _load_model(cfg["model"])
    clip_a = _generate_clip(mood["music_prompt"], cfg["seed_seconds"], torch, processor, model, "seed_a.wav")
    clip_b = _generate_clip(mood["music_prompt"], cfg["seed_seconds"], torch, processor, model, "seed_b.wav")

    base = _crossfade_join(clip_a, clip_b)
    track = _extend_and_master(base, cfg["target_seconds"])
    mastered_seed = _master_seed(clip_a)
    return mastered_seed, track
