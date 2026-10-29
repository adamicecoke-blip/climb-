# ClipForge

An open-source AI short-form video generator, in the spirit of **Opus Clip** and **Crayo**.

| Mode | What it does |
|---|---|
| **Auto-Clip** (Opus Clip) | Long video or YouTube link → transcribed → AI picks the most viral moments → each one cut, reframed to 9:16 around the speaker, with animated word-by-word captions and a hook title card. Ranked by virality score. |
| **Story Video** (Crayo) | A topic (AI writes the script) or your own script → AI voiceover → bold centred captions over gameplay footage (Minecraft parkour, Subway Surfers, etc.), with an optional title card and music. |

Everything runs on your machine. Claude picks the highlights and writes the scripts. Without an API key, the tool falls back to a built-in heuristic for picking highlights.

## Setup

Requires Python 3.10+ and [ffmpeg](https://ffmpeg.org/download.html).

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...   # optional, enables AI highlight picking + script writing
```

For Story mode, drop a few gameplay videos into `backgrounds/`. One is picked at random, starting at a random point.

## Web app

```bash
python -m clipforge serve
# open http://127.0.0.1:8000
```

Upload a video or paste a link, set how many clips and how long, and download the results. There's a tab for each mode.

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
| `clipforge/server.py`, `static/index.html` | Web app |

## Tests

```bash
pip install pytest httpx
python -m pytest tests
```

The tests stub out Whisper and TTS, which need model downloads and network access. They run the real ffmpeg renders and check the output is 1080×1920 with audio.

## Ideas for next steps

- Track the speaker continuously (a moving crop) instead of one crop position per clip
- Emoji and keyword styling in captions, plus B-roll
- Fake text-message and Reddit-card templates (more Crayo features)
- Auto-posting to TikTok, YouTube and Instagram
- A GPU queue and user accounts to run it as a hosted SaaS
