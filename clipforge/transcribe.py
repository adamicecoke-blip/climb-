"""Speech-to-text with word-level timestamps (faster-whisper)."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)


@dataclass
class Transcript:
    language: str
    segments: list[Segment]

    @property
    def words(self) -> list[Word]:
        return [w for s in self.segments for w in s.words]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Transcript":
        return cls(
            language=d["language"],
            segments=[
                Segment(s["start"], s["end"], s["text"], [Word(**w) for w in s["words"]])
                for s in d["segments"]
            ],
        )


@lru_cache(maxsize=2)
def _load_model(size: str):
    from faster_whisper import WhisperModel

    device = os.environ.get("CLIPFORGE_DEVICE", "auto")
    compute = "int8" if device in ("cpu", "auto") else "float16"
    return WhisperModel(size, device=device, compute_type=compute)


def transcribe(audio: Path, model_size: str | None = None) -> Transcript:
    model = _load_model(model_size or os.environ.get("CLIPFORGE_WHISPER", "small"))
    segments, info = model.transcribe(str(audio), word_timestamps=True, vad_filter=True)
    out = []
    for s in segments:
        words = [Word(w.start, w.end, w.word.strip()) for w in (s.words or []) if w.word.strip()]
        out.append(Segment(s.start, s.end, s.text.strip(), words))
    return Transcript(language=info.language, segments=out)


def words_in_range(transcript: Transcript, start: float, end: float) -> list[Word]:
    """Words overlapping [start, end], re-timed relative to `start`."""
    out = []
    for w in transcript.words:
        if w.end <= start or w.start >= end:
            continue
        out.append(Word(max(w.start, start) - start, min(w.end, end) - start, w.text))
    return out
