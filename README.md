# ClipForge

An open-source AI short-form video generator, in the spirit of **Opus Clip** and **Crayo**.

| Mode | What it does |
|---|---|
| **Auto-Clip** (Opus Clip) | Long video or YouTube link → transcribed → AI picks the most viral moments → each one cut, reframed to 9:16 around the speaker, with animated word-by-word captions and a hook title card. Ranked by virality score. |
| **Story Video** (Crayo) | A topic (AI writes the script) or your own script → AI voiceover → bold centred captions over gameplay footage (Minecraft parkour, Subway Surfers, etc.), with an optional title card and music. |

Everything runs on your machine. Claude picks the highlights and writes the scripts. Without an API key, the tool falls back to a built-in heuristic for picking highlights.

## Three ways to use it

| | What you get | Needs |
|---|---|---|
| **Desktop app** (installer) | Everything: automatic transcripts, face tracking, AI voices, full 1080×1920 | Just the download |
| **Online** (your own website) | The same app from any phone or computer, with a password | A hosting account, such as Render |
| **ClipForge Studio** (inside Claude) | Claude-picked clips and AI scripts, rendered in your browser at 720×1280 | You paste the transcript; voice comes from an uploaded recording |

## Download the desktop app

Installers are built automatically by GitHub (see `.github/workflows/build-apps.yml`):

1. Open the repository on GitHub, go to **Actions**, then **Build apps**, then **Run workflow**. Or push a tag such as `v0.3.0`, which also creates a Release with the files attached.
2. When it finishes, about 15 minutes later, download your file from the run's **Artifacts** section:
   - **Windows:** `ClipForge-Windows-Setup.exe`. Run it; it adds Start-menu and desktop shortcuts.
   - **Mac:** `ClipForge-Mac.dmg`. Drag ClipForge into Applications. The app isn't signed, so the first time, right-click it and choose **Open**. ffmpeg inside is an Intel build, which Macs with Apple chips run through Rosetta; macOS offers to install Rosetta if it's missing.
   - **Linux:** `ClipForge-Linux.tar.gz`. Unpack it and run `ClipForge/ClipForge`.

The installed app keeps your videos in a `ClipForge` folder in your home folder. Put gameplay clips for story videos in `ClipForge/backgrounds`. The first transcription downloads the speech-to-text model (about 500 MB) once.

## Put it online

The repository includes a `Dockerfile` and a `render.yaml`:

- **Render:** choose New, then Blueprint, then pick this repo. It creates the service, a disk for your videos, and a random password, which you'll find in the dashboard. Paste your `ANTHROPIC_API_KEY` in the dashboard. Pick at least the Standard plan, because video rendering needs RAM.
- **Anywhere else:** `docker build -t clipforge . && docker run -p 8000:8000 -v clipforge-data:/data -e CLIPFORGE_PASSWORD=choose-one -e ANTHROPIC_API_KEY=sk-ant-... clipforge`

Always set `CLIPFORGE_PASSWORD` when it's online. Otherwise anyone who finds the address can use your server and API credits. Over HTTPS, phones get the full **Install app** prompt.

## ClipForge Studio (inside Claude)

`studio/clipforge-studio.html` is a browser-only version that runs as a Claude artifact. Claude picks the highlights and writes scripts, and the video is recorded in your browser and saved through Claude. Because it can't run speech-to-text or face tracking in a browser, you paste the transcript (YouTube's "Show transcript", or an .srt/.vtt file) and set the crop position with a slider.

## Run from source


For developers, or if you'd rather not use an installer. You need [Python 3.10+](https://www.python.org/downloads/) and [ffmpeg](https://ffmpeg.org/download.html)
(Windows: `winget install ffmpeg`, Mac: `brew install ffmpeg`, Linux: `sudo apt install ffmpeg`).

Then double-click the launcher for your computer:

| Computer | Double-click |
|---|---|
| Windows | `start-windows.bat` |
| Mac | `start-mac.command` (the first time, right-click it and choose **Open**) |
| Linux | `./start-linux.sh` |

The first launch installs everything, which takes a few minutes. After that ClipForge opens straight away in its own window.

The app has three screens: **Auto-Clip**, **Story Video** and **Library**. Library keeps every video you've made, even after you close the app. Each finished video has **Save** and **Share** buttons. On a phone, Share opens the share sheet, so you can send a clip straight to TikTok or Instagram.

To turn on AI highlight picking and script writing, set your Anthropic API key before launching:
`export ANTHROPIC_API_KEY=sk-ant-...` (Mac/Linux) or `setx ANTHROPIC_API_KEY sk-ant-...` (Windows, then reopen).

For Story mode, drop a few gameplay videos into `backgrounds/`. One is picked at random, starting at a random point.

### On your phone

The video processing runs on your computer. Your phone just uses the app.

```bash
python -m clipforge serve --lan
```

The command prints an address such as `http://192.168.1.20:8000`. Open it on your phone while it's on the same Wi-Fi.
- **iPhone:** tap Share, then **Add to Home Screen**.
- **Android:** tap the ⋮ menu, then **Add to Home screen**.

ClipForge then opens full-screen from its own icon. On a desktop browser at `http://127.0.0.1:8000`, an **Install app** button appears in the sidebar.

### Manual install

```bash
pip install -e ".[desktop]"     # adds the `clipforge` and `clipforge-app` commands
clipforge-app                   # desktop window
clipforge serve                 # browser version at http://127.0.0.1:8000
```

## Command line

```bash
# Opus Clip mode
python -m clipforge clip podcast.mp4 -n 5 --min 20 --max 60
python -m clipforge clip "https://youtube.com/watch?v=..." --prompt "only the funniest moments"
python -m clipforge clip talk.mp4 --layout fit --captions hormozi

# Crayo mode
python -m clipforge story --topic "my roommate secretly sold my PS5" --style reddit --title "AITA?"
python -m clipforge story --script @script.txt --voice en-US-AvaMultilingualNeural --background parkour.mp4
```

Options:

- `--layout crop` fills the frame and centres the crop on the detected face. `--layout fit` shows the whole frame over a blurred copy of itself, which suits screen recordings and gameplay.
- `--captions`: `bold` (yellow highlight), `hormozi` (green, 2 words), `beast` (red), `clean` (sentence case).
- `--style` for stories: `reddit`, `facts`, `motivation`, `scary`, `explainer`, or any free-text description.
- `--whisper tiny|base|small|medium|large-v3`: bigger models are more accurate but slower (default `small`).

Environment variables: `CLIPFORGE_MODEL` (Claude model, default `claude-opus-5-5`), `CLIPFORGE_WHISPER` (default Whisper size), `CLIPFORGE_DEVICE` (`cpu`/`cuda`).

## How it works

```
Auto-Clip:  video ─ffmpeg→ audio ─faster-whisper→ word timestamps ─Claude→ ranked moments
                 └→ per clip: OpenCV face position → ffmpeg crop 9:16 + ASS captions → mp4

Story:      topic ─Claude→ script ─edge-tts→ voice + word timings → ASS captions
                 └→ ffmpeg: looped gameplay (cropped 9:16) + voice + captions → mp4
```

| File | Role |
|---|---|
| `clipforge/transcribe.py` | Whisper transcription with word timestamps |
| `clipforge/highlights.py` | Claude highlight picking (structured JSON output) and the offline heuristic |
| `clipforge/captions.py` | Animated caption presets, written as ASS subtitles |
| `clipforge/reframe.py` | Speaker tracking for the 9:16 crop |
| `clipforge/render.py` | ffmpeg filter graphs |
| `clipforge/story.py` | Script writing, TTS voices |
| `clipforge/pipeline.py` | The two end-to-end jobs |
| `clipforge/server.py`, `static/` | App UI, Library, installable-app files (manifest, service worker, icons) |
| `clipforge/desktop.py` | Desktop window launcher |

## Tests

```bash
pip install pytest httpx
python -m pytest tests
```

The tests stub out Whisper and TTS, which need model downloads and network access. They run the real ffmpeg renders and check the output is 1080×1920 with audio.

## Settings

| Variable | What it does |
|---|---|
| `ANTHROPIC_API_KEY` | Enables Claude highlight picking and script writing |
| `CLIPFORGE_PASSWORD` | Requires a password for the web app (use it when hosting online) |
| `CLIPFORGE_HOME` | Folder for output, uploads and backgrounds (default: current folder, or `~/ClipForge` for the installed app) |
| `CLIPFORGE_MODEL` | Claude model (default `claude-opus-5-5`) |
| `CLIPFORGE_WHISPER` | Speech-to-text size: `tiny`, `base`, `small` (default), `medium`, `large-v3` |
| `CLIPFORGE_DEVICE` | `cpu` or `cuda` |

## Ideas for next steps

- Track the speaker continuously (a moving crop) instead of one crop position per clip
- Emoji and keyword styling in captions, plus B-roll
- Fake text-message and Reddit-card templates (more Crayo features)
- Auto-posting to TikTok, YouTube and Instagram
- A GPU queue and user accounts to run it as a hosted SaaS
