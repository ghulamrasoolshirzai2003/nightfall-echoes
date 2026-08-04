# 🛠️ One-Time Setup — Nightfall Echoes

There are now **two systems** in this project — pick the one you actually want live
(or set up both):

| | System A: Fully-automatic instrumental | System B: Suno + Telegram (vocal songs) |
|---|---|---|
| Vocals | ❌ Instrumental only | ✅ Real sung songs |
| Manual step | None | ~2 min/day: paste prompt into Suno, upload MP3 back |
| Posts to | YouTube directly | Your Telegram group (your team posts everywhere) |
| Setup needed | Parts A + B + C + D | Parts A + E + D |

If you only want System B (which is what we've been building most recently), you can
**skip Part B and Part C entirely** — those are YouTube-upload credentials, not needed
when Telegram is the only destination.

---

## Part A — Get your free Gemini key (2 min) — needed by both systems

1. Go to **https://aistudio.google.com/apikey**
2. Sign in with the Google account you want.
3. Click **Create API key** → copy it. This is your `GEMINI_API_KEY`.

---

## Part B — Google Cloud: YouTube upload access (~10 min) — System A only

Skip this if you're only running the Telegram system.

1. Go to **https://console.cloud.google.com/** and create a new project (top bar → "New Project"). Name it `nightfall`.
2. **Enable the API:** search "YouTube Data API v3" → **Enable**.
3. **API key:** left menu → *APIs & Services → Credentials → Create Credentials → API key*. Copy it → this is your `YOUTUBE_API_KEY`.
4. **OAuth consent screen:** menu → *APIs & Services → OAuth consent screen*.
   - User type: **External** → Create.
   - Fill app name (`Nightfall`), your email. Save through the steps.
   - **IMPORTANT:** on the consent-screen overview, set **Publishing status → "In production"** (click *Publish app*). This stops your upload token from expiring every 7 days.
   - Add yourself under *Test users* as well (belt and suspenders).
5. **OAuth client:** *Credentials → Create Credentials → OAuth client ID → Desktop app*. Create, then **Download JSON**.
6. Rename that downloaded file to **`client_secret.json`** and put it in this project folder (`D:\YOUTUBE AUTOMATED SONGS\`).

---

## Part C — Mint your upload token (2 min, on your PC) — System A only

Skip this if you're only running the Telegram system.

```bash
pip install -r requirements.txt
python -m src.auth
```

A browser opens → pick your **channel's Google account** → **Allow**.
The terminal prints three lines:

```
YT_CLIENT_ID=...
YT_CLIENT_SECRET=...
YT_REFRESH_TOKEN=...
```

Copy all three. (Tell me if you'd rather I guide this live.)

---

## Part E — Telegram bot (5 min) — System B only

1. Open Telegram, search for **@BotFather**, start a chat.
2. Send `/newbot`, give it a name and a username (must end in `bot`, e.g. `nightfall_songs_bot`).
3. BotFather replies with a token like `123456789:AAExxxxxxxxxxxxxxxxxxxxxx` — this is your `TELEGRAM_BOT_TOKEN`.
4. Add the bot to your team's Telegram **group** (Group Info → Add Member → search its username).
5. **Get your group's chat ID:**
   - Send any message in the group.
   - In a browser, open: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` (replace `<YOUR_TOKEN>`).
   - Find `"chat":{"id":-1001234567890,...}` in the response — that negative number is your `TELEGRAM_CHAT_ID`.

You'll also need your own **Suno account subscription** (suno.com) — that's separate,
just sign up/subscribe there directly; nothing to configure here for it.

---

## Part F — Pexels key for real stock-footage videos (2 min) — System B only

Gives the video real human-shot background footage instead of a zoomed AI image.

1. Go to **https://www.pexels.com/api/** and click **Get Started** (free).
2. Sign up / log in, then copy the API key shown on your account page.
3. This is your `PEXELS_API_KEY`.

If this key is ever missing or a search comes up empty, the system automatically
falls back to the AI-image approach — never breaks the run either way.

---

## Part D — Put it on GitHub so it runs in the cloud (~10 min) — needed by both systems

1. Create a free account at **https://github.com** if you don't have one.
2. Create a **new repository** (name it `nightfall-echoes`). Make it **Public**
   (public = unlimited free Actions minutes). *Do not upload `client_secret.json`,
   `.env`, or `token.json`* — `.gitignore` already blocks them.
3. Upload this whole folder to the repo (drag-and-drop works on github.com, or use
   GitHub Desktop). I can give you the exact commands if you prefer.
4. **Enable write access for Actions** (needed for System B's state file commits):
   *Settings → Actions → General → Workflow permissions* → select **"Read and write
   permissions"** → Save.
5. In the repo: **Settings → Secrets and variables → Actions → New repository secret**.
   Add whichever of these apply to the system(s) you're running:

   | Secret name | Value | Needed for |
   |---|---|---|
   | `GEMINI_API_KEY` | from Part A | Both |
   | `YOUTUBE_API_KEY` | from Part B step 3 | System A |
   | `YT_CLIENT_ID` | from Part C | System A |
   | `YT_CLIENT_SECRET` | from Part C | System A |
   | `YT_REFRESH_TOKEN` | from Part C | System A |
   | `TELEGRAM_BOT_TOKEN` | from Part E step 3 | System B |
   | `TELEGRAM_CHAT_ID` | from Part E step 5 | System B |
   | `PEXELS_API_KEY` | from Part F | System B (strongly recommended — without it, falls back to a plain AI image instead of the real-footage story video) |

6. Go to the **Actions** tab → enable workflows. For System A, run **"Daily song"**
   once manually to test. For System B, run **"Daily Suno prompt"** once manually —
   you should see the prompt land in your Telegram group within a minute or two.

That's it. From now on:
- System A posts to YouTube automatically every day at 06:00 UTC.
- System B sends your team a prompt every day at 06:00 UTC, and checks every 15 min
  for a finished MP3 reply to turn into a video.

---

## Changing the channel's style later
Everything creative lives in **`config.yaml`** — moods (System A), Suno styles
(System B), track length, thumbnails, tags. Edit that file, commit, done. No coding
needed.
