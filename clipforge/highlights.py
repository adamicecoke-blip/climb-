"""Pick the most viral-worthy moments from a transcript.

Uses Claude when ANTHROPIC_API_KEY (or another Anthropic credential) is set,
otherwise falls back to a keyword/pace heuristic so the tool still works offline.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass

from .transcribe import Transcript

log = logging.getLogger(__name__)

MODEL = os.environ.get("CLIPFORGE_MODEL", "claude-opus-5-5")


@dataclass
class Highlight:
    start: float
    end: float
    title: str
    hook: str
    score: int
    reason: str

    @property
    def duration(self) -> float:
        return self.end - self.start

    def to_dict(self) -> dict:
        return asdict(self) | {"duration": round(self.duration, 2)}


SCHEMA = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "number", "description": "Start time in seconds"},
                    "end": {"type": "number", "description": "End time in seconds"},
                    "title": {"type": "string", "description": "Short catchy title, max 8 words"},
                    "hook": {"type": "string", "description": "On-screen hook text for the first 3 seconds, max 8 words"},
                    "score": {"type": "integer", "description": "Virality score 0-100"},
                    "reason": {"type": "string", "description": "One sentence on why this will perform"},
                },
                "required": ["start", "end", "title", "hook", "score", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}

PROMPT = """You are an expert short-form video editor who has cut thousands of viral TikToks, Reels and YouTube Shorts.

Below is a timestamped transcript of a long video. Find the {n} best moments to post as standalone vertical shorts.

Rules:
- Each clip must be between {min_len} and {max_len} seconds long.
- Each clip must make sense on its own with no prior context: start at the beginning of a thought and end on a payoff, punchline or conclusion - never mid-sentence.
- Prefer moments with a strong hook in the first 3 seconds: a bold claim, a surprising fact, a question, conflict, emotion, a story, or useful actionable advice.
- Clips must not overlap.
- Use the transcript timestamps for start and end.
- Rank by virality score, highest first.
{extra}
Transcript:
{transcript}"""


def _format_transcript(t: Transcript) -> str:
    return "\n".join(f"[{s.start:.1f}-{s.end:.1f}] {s.text}" for s in t.segments)


def _snap(t: Transcript, start: float, end: float, min_len: float, max_len: float) -> tuple[float, float]:
    """Snap clip edges to word boundaries so captions/audio don't start mid-word."""
    words = t.words
    if not words:
        return start, end
    starts = [w.start for w in words if w.start >= start - 1.0]
    s = min(starts, key=lambda x: abs(x - start)) if starts else start
    ends = [w.end for w in words if w.end <= end + 1.0 and w.end > s]
    e = min(ends, key=lambda x: abs(x - end)) if ends else end
    if e - s > max_len:
        e = max((w.end for w in words if s < w.end <= s + max_len), default=s + max_len)
    if e - s < min_len:
        e = min(s + min_len, words[-1].end)
    return max(0.0, s - 0.15), e + 0.25


def _with_claude(t: Transcript, n: int, min_len: float, max_len: float, prompt_extra: str) -> list[Highlight]:
    import anthropic

    client = anthropic.Anthropic()
    extra = f"- Extra instructions from the creator: {prompt_extra}\n" if prompt_extra else ""
    response = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{
            "role": "user",
            "content": PROMPT.format(n=n, min_len=int(min_len), max_len=int(max_len),
                                     extra=extra, transcript=_format_transcript(t)),
        }],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("model declined the request")
    text = next(b.text for b in response.content if b.type == "text")
    clips = json.loads(text)["clips"]
    return [Highlight(**c) for c in clips]


HOOK_WORDS = re.compile(
    r"\b(secret|never|always|nobody|everyone|biggest|worst|best|mistake|crazy|insane|"
    r"actually|truth|why|how|what if|imagine|money|million|stop|need to|you should|"
    r"the reason|here's|problem|realized|changed my life)\b",
    re.I,
)


def _heuristic(t: Transcript, n: int, min_len: float, max_len: float) -> list[Highlight]:
    segs = t.segments
    target = (min_len + max_len) / 2
    candidates = []
    for i in range(len(segs)):
        j, text = i, []
        while j < len(segs) and segs[j].end - segs[i].start < target:
            text.append(segs[j].text)
            j += 1
        if j >= len(segs) and segs[-1].end - segs[i].start < min_len:
            break
        end = segs[min(j, len(segs) - 1)].end
        body = " ".join(text)
        dur = max(end - segs[i].start, 1.0)
        pace = len(body.split()) / dur  # words/sec - energy proxy
        hooks = len(HOOK_WORDS.findall(body))
        opener = 15 if HOOK_WORDS.search(segs[i].text) or segs[i].text.rstrip().endswith("?") else 0
        punct = body.count("?") * 3 + body.count("!") * 4
        score = min(99, int(pace * 12 + hooks * 6 + opener + punct))
        candidates.append((score, segs[i].start, end, segs[i].text))
    candidates.sort(reverse=True)
    picked: list[Highlight] = []
    for score, s, e, first in candidates:
        if any(s < h.end and e > h.start for h in picked):
            continue
        hook = " ".join(first.split()[:8])
        picked.append(Highlight(s, e, hook, hook, score, "High pace and hook keywords"))
        if len(picked) == n:
            break
    return picked


def find_highlights(t: Transcript, n: int = 5, min_len: float = 20, max_len: float = 60,
                    prompt_extra: str = "", use_ai: bool = True) -> tuple[list[Highlight], str]:
    """Return (highlights sorted by score, engine used)."""
    engine = "heuristic"
    clips: list[Highlight] = []
    if use_ai and (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
                   or os.environ.get("CLIPFORGE_FORCE_AI")):
        try:
            clips = _with_claude(t, n, min_len, max_len, prompt_extra)
            engine = MODEL
        except Exception as e:  # network, auth, refusal: fall back rather than fail the job
            log.warning("AI highlight detection failed, using heuristic: %s", e)
    if not clips:
        clips = _heuristic(t, n, min_len, max_len)
    duration = t.segments[-1].end if t.segments else 0
    out = []
    for c in clips:
        if c.end <= c.start or c.start >= duration:
            continue
        c.start, c.end = _snap(t, c.start, min(c.end, duration), min_len, max_len)
        out.append(c)
    out.sort(key=lambda h: h.score, reverse=True)
    return out[:n], engine
