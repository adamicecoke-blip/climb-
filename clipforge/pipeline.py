"""End-to-end jobs, shared by the CLI and the web server."""

from __future__ import annotations

import json
import random
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import captions, highlights, media, reframe, render, story
from .transcribe import Transcript, transcribe, words_in_range

Progress = Callable[[float, str], None]


def _noop(_: float, __: str) -> None:
    pass


def _slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n] or "clip"


@dataclass
class ClipOptions:
    num_clips: int = 5
    min_len: float = 20
    max_len: float = 60
    layout: str = "crop"  # crop | fit
    caption_preset: str = "bold"
    captions: bool = True
    hook_title: bool = True
    prompt: str = ""
    use_ai: bool = True
    whisper_model: str | None = None


def auto_clip(source: str | Path, out_dir: Path, opts: ClipOptions,
              progress: Progress = _noop) -> dict:
    """Long video (path or URL) -> ranked vertical shorts with captions. Opus Clip mode."""
    media.require_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)

    src = Path(str(source))
    is_url = bool(re.match(r"^https?://", str(source)))
    if is_url:
        progress(0.02, "Downloading video")
        src = media.download(str(source), out_dir / "source")
    if not src.exists():
        raise FileNotFoundError(src)
    info = media.probe(src)
    if not info["has_audio"]:
        raise media.MediaError("This video has no audio track, so there is nothing to transcribe.")

    cache = out_dir / "transcript.json"
    if cache.exists():
        transcript = Transcript.from_dict(json.loads(cache.read_text()))
    else:
        progress(0.08, "Extracting audio")
        wav = media.extract_audio(src, out_dir / "audio.wav")
        progress(0.12, "Transcribing (this is the slow part)")
        transcript = transcribe(wav, opts.whisper_model)
        cache.write_text(json.dumps(transcript.to_dict()))
        wav.unlink(missing_ok=True)
    if not transcript.segments:
        raise RuntimeError("No speech found in the video.")

    progress(0.45, "Finding the most viral moments")
    picks, engine = highlights.find_highlights(
        transcript, opts.num_clips, opts.min_len, opts.max_len, opts.prompt, opts.use_ai)

    style = captions.PRESETS.get(opts.caption_preset, captions.PRESETS["bold"])
    results = []
    for i, h in enumerate(picks):
        frac = 0.5 + 0.5 * i / max(len(picks), 1)
        progress(frac, f"Rendering clip {i + 1}/{len(picks)}: {h.title}")
        name = f"{i + 1:02d}-{_slug(h.title)}"
        words = words_in_range(transcript, h.start, h.end)
        ass = None
        if opts.captions:
            ass = captions.write_ass(out_dir / f"{name}.ass", words, style,
                                     title=h.hook if opts.hook_title else None)
        cx = None
        if opts.layout == "crop":
            cx = reframe.speaker_center_x(src, h.start, h.end)
        video = render.render_clip(src, h.start, h.end, out_dir / f"{name}.mp4", ass,
                                   opts.layout, info["width"], info["height"], cx)
        thumb = render.thumbnail(video, out_dir / f"{name}.jpg")
        results.append(h.to_dict() | {"video": video.name, "thumbnail": thumb.name,
                                      "transcript": " ".join(w.text for w in words)})

    if src.parent == out_dir / "source":
        shutil.rmtree(src.parent, ignore_errors=True)  # downloaded original, no longer needed
    manifest = {"source": str(source) if is_url else src.name, "engine": engine, "clips": results}
    (out_dir / "clips.json").write_text(json.dumps(manifest, indent=2))
    progress(1.0, f"Done - {len(results)} clips")
    return manifest


@dataclass
class StoryOptions:
    script: str = ""
    topic: str = ""
    style: str = "reddit"
    seconds: int = 60
    voice: str = "en-US-AndrewMultilingualNeural"
    rate: str = "+10%"
    caption_preset: str = "bold"
    title: str = ""
    background: Path | None = None
    backgrounds_dir: Path = Path("backgrounds")
    music: Path | None = None


def make_story(out_dir: Path, opts: StoryOptions, progress: Progress = _noop) -> dict:
    """Script/topic -> narrated short over gameplay with captions. Crayo mode."""
    media.require_ffmpeg()
    out_dir.mkdir(parents=True, exist_ok=True)

    script = opts.script.strip()
    if not script:
        if not opts.topic.strip():
            raise ValueError("Provide either a script or a topic.")
        progress(0.05, "Writing script with AI")
        script = story.write_script(opts.topic, opts.style, opts.seconds)
    (out_dir / "script.txt").write_text(script)

    progress(0.3, "Generating voiceover")
    voice = out_dir / "voice.mp3"
    words = story.synthesize(script, voice, opts.voice, opts.rate)
    duration = media.probe(voice)["duration"] + 0.4

    progress(0.55, "Building captions")
    style = captions.PRESETS.get(opts.caption_preset, captions.PRESETS["bold"])
    style = captions.CaptionStyle(**{**style.__dict__, "position": 0.5})  # centred like Crayo
    ass = captions.write_ass(out_dir / "captions.ass", words, style, title=opts.title or None)

    bg = opts.background or story.pick_background(opts.backgrounds_dir)
    offset = 0.0
    if bg is not None:
        bg_len = media.probe(bg)["duration"]
        if bg_len > duration + 5:
            offset = random.uniform(0, bg_len - duration - 1)

    progress(0.65, "Rendering video")
    name = _slug(opts.title or script.split(".")[0])
    video = render.render_story(bg, voice, duration, out_dir / f"{name}.mp4", ass, offset, opts.music)
    thumb = render.thumbnail(video, out_dir / f"{name}.jpg")
    manifest = {"video": video.name, "thumbnail": thumb.name, "script": script,
                "duration": round(duration, 2), "background": bg.name if bg else None}
    (out_dir / "story.json").write_text(json.dumps(manifest, indent=2))
    progress(1.0, "Done")
    return manifest
