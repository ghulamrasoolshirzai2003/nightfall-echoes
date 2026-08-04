"""Transcribes the actual sung audio with WORD-level timestamps
(faster-whisper, free, runs locally on CPU — no torch/GPU needed).

Word-level (not just segment-level) timing is what lets captions appear
exactly when a word is actually sung rather than at the start of a whole
merged Whisper segment, which can bundle several bars together and make
later lines appear to show up "early". It's also the foundation for
scenes.py's phrase-chunking (natural pauses become scene/caption breaks).
"""
from .settings import CONFIG

_model = None  # loaded once per process, reused across calls


def _get_model():
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        model_size = CONFIG.get("lyric_video", {}).get("whisper_model", "small")
        print(f"[transcribe] Loading Whisper model '{model_size}' (first run downloads it)...")
        _model = WhisperModel(model_size, device="cpu", compute_type="int8")
    return _model


def transcribe_words(audio_path: str) -> list[dict]:
    """Returns a flat list of {"start": float, "end": float, "text": str}
    per WORD, in order, across the whole song."""
    model = _get_model()
    segments, info = model.transcribe(audio_path, beam_size=5, word_timestamps=True)
    words = []
    for seg in segments:
        for w in seg.words:
            text = w.word.strip()
            if text:
                words.append({"start": w.start, "end": w.end, "text": text})
    print(f"[transcribe] {len(words)} words, language={info.language} "
          f"(p={info.language_probability:.2f})")
    return words
