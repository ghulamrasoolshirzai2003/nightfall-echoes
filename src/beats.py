"""Beat detection (librosa, free, runs locally on CPU) — used to snap scene
cut points to the song's actual rhythm, which is what makes professionally
edited music videos feel "produced" instead of arbitrarily timed.
"""


def detect_beats(audio_path: str) -> list[float]:
    import librosa  # imported lazily so the rest of the pipeline loads fast

    y, sr = librosa.load(audio_path, sr=None)
    _tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beats = librosa.frames_to_time(beat_frames, sr=sr).tolist()
    print(f"[beats] Detected {len(beats)} beats.")
    return beats


def snap_to_beat(time: float, beats: list[float], tolerance: float = 0.35) -> float:
    """Returns the nearest beat to `time` if within `tolerance` seconds,
    otherwise `time` unchanged (a cut driven by a lyric change shouldn't jump
    far from its natural point just to land on a beat)."""
    if not beats:
        return time
    nearest = min(beats, key=lambda b: abs(b - time))
    return nearest if abs(nearest - time) <= tolerance else time
