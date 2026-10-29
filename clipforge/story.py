"""Crayo-style story shorts: script -> AI voiceover -> captions over gameplay."""

from __future__ import annotations

import asyncio
import logging
import os
import random
from pathlib import Path

from .transcribe import Word

log = logging.getLogger(__name__)

MODEL = os.environ.get("CLIPFORGE_MODEL", "claude-opus-5-5")

VOICES = {
    "Andrew (US, male)": "en-US-AndrewMultilingualNeural",
    "Emma (US, female)": "en-US-EmmaMultilingualNeural",
    "Brian (US, male)": "en-US-BrianMultilingualNeural",
    "Ava (US, female)": "en-US-AvaMultilingualNeural",
    "Christopher (US, deep)": "en-US-ChristopherNeural",
    "Ryan (UK, male)": "en-GB-RyanNeural",
    "Sonia (UK, female)": "en-GB-SoniaNeural",
}

SCRIPT_PROMPT = """Write the voiceover script for a {seconds}-second vertical short video.

Style: {style}
Topic: {topic}

Requirements:
- The first sentence is a scroll-stopping hook.
- Short punchy sentences, conversational, easy to read aloud.
- About {words} words in total.
- End with a payoff or twist, not a call to subscribe.
- Output ONLY the words to be spoken: no title, stage directions, emojis, hashtags or quotes."""

STYLES = {
    "reddit": "a dramatic first-person Reddit story (AITA / relationship / revenge), told like the poster",
    "facts": "rapid-fire mind-blowing facts about the topic",
    "motivation": "an intense motivational monologue",
    "scary": "a creepy short horror story with a chilling ending",
    "explainer": "a clear, fast explainer that teaches one surprising idea",
}


def write_script(topic: str, style: str = "reddit", seconds: int = 60) -> str:
    """Have Claude write a narration script for `topic`."""
    import anthropic

    if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
        raise RuntimeError("AI script writing needs an Anthropic API key (set ANTHROPIC_API_KEY). "
                           "Or paste your own script instead of a topic.")
    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium"},
        messages=[{"role": "user", "content": SCRIPT_PROMPT.format(
            seconds=seconds, style=STYLES.get(style, style), topic=topic,
            words=int(seconds * 2.6))}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("The model declined to write this script - try a different topic.")
    return "".join(b.text for b in response.content if b.type == "text").strip()


async def _tts(text: str, voice: str, rate: str, out: Path) -> list[Word]:
    import edge_tts

    comm = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    words: list[Word] = []
    with out.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                start = chunk["offset"] / 1e7  # 100ns ticks
                words.append(Word(start, start + chunk["duration"] / 1e7, chunk["text"]))
    return words


def synthesize(text: str, out: Path, voice: str = "en-US-AndrewMultilingualNeural",
               rate: str = "+10%") -> list[Word]:
    """Text -> MP3 at `out`, returning per-word timings for captions."""
    try:
        words = asyncio.run(_tts(text, voice, rate, out))
    except OSError as e:  # aiohttp connection errors subclass OSError
        raise RuntimeError("Couldn't reach the AI voice service. Check your internet connection "
                           "and try again.") from e
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("Text-to-speech produced no audio (is the machine online?)")
    if not words:
        # Older voices may not emit word boundaries; recover timings with Whisper.
        from .transcribe import transcribe
        words = transcribe(out).words
    return words


def pick_background(folder: Path) -> Path | None:
    vids = [p for p in folder.glob("*") if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}]
    return random.choice(vids) if vids else None
