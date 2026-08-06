"""Orchestrates the full "story video" build:

    transcribe real audio (word-level) -> chunk into natural phrase scenes,
    cut points snapped to the beat -> Gemini clusters consecutive scenes into
    shot groups (same setting/characters) -> fetch ONE longer clip per group
    and slice different moments of it across that group's scenes -> render +
    color-grade each slice -> concatenate -> mux with the real audio +
    burned-in synced captions.

Slicing one clip per group (instead of a fresh random clip per scene) is what
gives real character consistency: consecutive scenes in the same group show
the same actual people, because it's literally the same shot.
"""
from . import scenes as scenes_mod
from . import stock_video, transcribe
from .ffmpeg_utils import concat_clips, mux_with_audio_and_captions, probe_duration, render_scene_clip
from .settings import CONFIG, OUTPUT_DIR


def _noop(percent: int, message: str) -> None:
    pass


def build_story_video(audio_path: str, style_tags: str, default_query: str,
                       width: int, height: int, out_path: str,
                       on_progress=_noop) -> tuple[str, str] | None:
    """Returns (video_path, full_lyrics_text), or None if there wasn't enough
    to work with — the caller should fall back to the simpler single-clip
    build. The lyrics text is the actual transcribed words (not the original
    Suno prompt) — useful for callers that need to generate title/description
    metadata for a song with no pre-existing prompt context (see
    poll_telegram.py's handling of "orphan" uploads).

    `on_progress(percent, message)` is called at a handful of major
    checkpoints (not per-scene — that would spam whoever's watching), so a
    caller can relay real progress updates (e.g. to Telegram) instead of
    total silence for the several minutes this takes.
    """
    total_duration = probe_duration(audio_path)

    on_progress(10, "Transcribing your song...")
    words = transcribe.transcribe_words(audio_path)
    if not words:
        print("[story_video] No speech detected; caller should fall back.")
        return None
    full_lyrics_text = " ".join(w["text"] for w in words)

    lv_cfg = CONFIG.get("lyric_video", {})
    scene_windows = scenes_mod.chunk_into_scenes(
        words, total_duration, audio_path,
        pause_threshold=lv_cfg.get("pause_threshold", 0.45),
        max_chunk_duration=lv_cfg.get("max_scene_seconds", 7.0),
        min_chunk_duration=lv_cfg.get("min_scene_seconds", 1.2),
        beat_tolerance=lv_cfg.get("beat_tolerance", 0.35),
    )
    if not scene_windows:
        return None

    on_progress(25, f"Found the beat, planned {len(scene_windows)} scenes — matching footage to your lyrics...")
    plan = scenes_mod.plan_visuals(scene_windows, style_tags, default_query)
    color_mood = plan["color_mood"]

    clip_paths = []
    used_ids: set = set()
    scene_counter = 0
    n_groups = len(plan["groups"])
    for g, group in enumerate(plan["groups"]):
        indices = group["scene_indices"]
        query = group["query"]
        group_windows = [scene_windows[i] for i in indices]
        group_duration = sum(max(w["end"] - w["start"], 1.0) for w in group_windows)
        raw_name = f"stock_group_{g:02d}.mp4"

        found = (stock_video.fetch_unique_clip(query, width, height, used_ids, raw_name, group_duration)
                 or stock_video.fetch_unique_clip(default_query, width, height, used_ids, raw_name, group_duration))
        if not found:
            print(f"[story_video] No unused footage found for group {g} ('{query}'); aborting story build.")
            return None
        video_id, clip, _reported_duration = found
        used_ids.add(video_id)
        # Probe the actual downloaded file rather than trust Pexels' reported
        # duration — they can differ by a fraction of a second, and that gap
        # matters for deciding whether a scene's slice needs to loop.
        source_duration = probe_duration(clip)
        print(f"[story_video] Group {g+1}/{n_groups} clip ready "
              f"('{query}', source {source_duration:.1f}s, covers {len(indices)} scene(s)).")
        # Spread 30-75% across the group loop — a handful of updates for a
        # typical 8-10 group video, not a message per group.
        on_progress(30 + int(45 * (g + 1) / max(n_groups, 1)),
                    f"Building scene {g+1}/{n_groups}...")

        # Slice a DIFFERENT moment of this same clip for each scene in the
        # group — same people throughout, but not a literal repeated frame.
        cursor = 0.0
        for window in group_windows:
            scene_duration = max(window["end"] - window["start"], 1.0)
            scene_out = str(OUTPUT_DIR / f"scene_{scene_counter:02d}.mp4")
            render_scene_clip(clip, scene_out, duration=scene_duration, width=width, height=height,
                               color_mood=color_mood, source_offset=cursor,
                               source_duration=source_duration)
            clip_paths.append(scene_out)
            cursor += scene_duration
            scene_counter += 1

    on_progress(80, "Assembling the final video...")
    concat_path = str(OUTPUT_DIR / "story_concat.mp4")
    concat_clips(clip_paths, concat_path)

    # Captions are chunked SEPARATELY from the visual scene cuts, much finer
    # grained — a shot can hold for ~5s while the caption underneath changes
    # every 1-2s in short bursts, matching how real short-form lyric videos
    # display text (a few words at a time), not one long sentence sitting on
    # screen for the whole shot.
    caption_chunks = scenes_mod.chunk_words_into_captions(
        words,
        max_words=lv_cfg.get("caption_max_words", 4),
        max_duration=lv_cfg.get("caption_max_seconds", 2.2),
        pause_threshold=lv_cfg.get("caption_pause_threshold", 0.25),
    )
    on_progress(92, "Syncing captions and finalizing...")
    mux_with_audio_and_captions(concat_path, audio_path, caption_chunks, out_path,
                                 duration=total_duration, width=width, height=height)

    print(f"[story_video] Built: {out_path}")
    return out_path, full_lyrics_text
