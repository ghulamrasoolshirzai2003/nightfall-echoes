# 🌙 Nightfall Echoes — Automated AI Music Channel

A fully automated pipeline that produces **original instrumental music** (lo-fi / sad piano /
ambient / sleep & study) and uploads it to YouTube **every single day, hands-off, for $0**.

Everything runs in the cloud on **GitHub Actions** — your PC does not need to be on.

---

## How it works (the daily pipeline)

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│ 1. TRENDS   │──▶│ 2. CONCEPT  │──▶│ 3. MUSIC    │──▶│ 4. THUMBNAIL│
│ pick a mood │   │ Gemini      │   │ MusicGen    │   │ Pollinations│
│ + keywords  │   │ title/desc  │   │ + ffmpeg    │   │ + text      │
└─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘
                                                              │
        ┌─────────────┐   ┌─────────────┐   ┌─────────────┐  │
        │ 7. UPLOAD   │◀──│ 6. METADATA │◀──│ 5. VIDEO    │◀─┘
        │ YouTube API │   │ tags/desc   │   │ ffmpeg mp4  │
        └─────────────┘   └─────────────┘   └─────────────┘
```

| Stage | File | Tool | Cost |
|-------|------|------|------|
| 1. Trend research | `src/trends.py` | keyword bank + YouTube API | $0 |
| 2. Concept + copy | `src/concept.py` | Google Gemini (free API) | $0 |
| 3. Music | `src/music.py` | MusicGen + ffmpeg loop | $0 |
| 4. Thumbnail | `src/thumbnail.py` | Pollinations.ai + Pillow | $0 |
| 5. Video | `src/video.py` | ffmpeg | $0 |
| 6. Metadata | `src/metadata.py` | (bundled with concept) | $0 |
| 7. Upload | `src/upload.py` | YouTube Data API v3 | $0 |
| 8. Scheduler | `.github/workflows/daily.yml` | GitHub Actions cron | $0 |

Orchestrated by `src/pipeline.py`.

---

## ⚠️ Rules baked into this system (why it won't get you banned)

- **Only original music.** MusicGen generates brand-new audio; we never upload copyrighted
  songs, remixes, or covers. This avoids Content ID claims and copyright strikes.
- **Full commercial rights** on everything (MusicGen output, Pollinations images) → monetizable.

---

## 🔑 One-time setup (do this once, then never again)

See **`SETUP.md`** for click-by-click instructions. Short version:

1. Create a **GitHub account** and a repo; upload this folder.
2. In **Google Cloud**: enable *YouTube Data API v3*, create OAuth credentials, run
   `python -m src.auth` locally once to get a **refresh token**, and grab a **YouTube API key**.
3. In **Google AI Studio**: create a free **Gemini API key**.
4. Paste these into **GitHub → Settings → Secrets → Actions**:
   - `GEMINI_API_KEY`
   - `YOUTUBE_API_KEY`
   - `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`
5. Done. The channel now posts itself daily.

---

## Run it locally (to test)

```bash
pip install -r requirements.txt
cp .env.example .env        # fill in your keys
python -m src.pipeline      # runs the whole thing once
```

Add `--dry-run` to build the video but skip the actual upload.

---

## Build status

- [x] Project scaffold, config, orchestrator
- [x] Concept + metadata (Gemini)
- [x] Thumbnail (Pollinations + Pillow)
- [x] Video assembly (ffmpeg)
- [x] Music generation (MusicGen)
- [x] YouTube upload + auth
- [x] GitHub Actions daily workflow
- [ ] **First live test run** (needs your API keys — see SETUP.md)
