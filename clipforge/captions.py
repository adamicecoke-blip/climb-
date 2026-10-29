"""Animated word-by-word captions as an ASS subtitle file.

The look matches the big, bold "TikTok captions" style: a few words on screen
at a time, the word being spoken highlighted and slightly enlarged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .transcribe import Word

WIDTH, HEIGHT = 1080, 1920
FONTS_DIR = Path(__file__).parent / "fonts"  # bundled so captions look the same everywhere


@dataclass
class CaptionStyle:
    font: str = "Inter Black"
    size: int = 92
    color: str = "#FFFFFF"
    highlight: str = "#FFE600"
    outline: str = "#000000"
    outline_width: int = 7
    shadow: int = 3
    position: float = 0.68  # vertical centre of captions as a fraction of height
    words_per_line: int = 3
    uppercase: bool = True
    pop: bool = True  # scale-up the active word


PRESETS = {
    "bold": CaptionStyle(),
    "clean": CaptionStyle(font="Inter", size=78, highlight="#4ADE80", uppercase=False,
                          outline_width=5, words_per_line=4, pop=False),
    "hormozi": CaptionStyle(size=104, highlight="#22C55E", words_per_line=2),
    "beast": CaptionStyle(size=100, highlight="#FF3B3B", outline_width=9, words_per_line=2),
}


def _ass_color(hex_color: str, alpha: int = 0) -> str:
    """#RRGGBB -> &HAABBGGRR (ASS is little-endian BGR)."""
    h = hex_color.lstrip("#")
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H{alpha:02X}{b}{g}{r}".upper()


def _ts(t: float) -> str:
    t = max(t, 0.0)
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def group_words(words: list[Word], max_words: int, max_gap: float = 0.6) -> list[list[Word]]:
    """Split words into short on-screen pages, breaking at pauses and punctuation."""
    pages: list[list[Word]] = []
    cur: list[Word] = []
    for w in words:
        if cur and (len(cur) >= max_words or w.start - cur[-1].end > max_gap
                    or re.search(r"[.!?,;:]$", cur[-1].text)):
            pages.append(cur)
            cur = []
        cur.append(w)
    if cur:
        pages.append(cur)
    return pages


def _header(style: CaptionStyle, extra_styles: str = "") -> str:
    margin_v = int(HEIGHT * (1 - style.position)) - style.size // 2
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,{style.font},{style.size},{_ass_color(style.color)},{_ass_color(style.highlight)},{_ass_color(style.outline)},{_ass_color('#000000', 0x60)},-1,0,0,0,100,100,0,0,1,{style.outline_width},{style.shadow},2,60,60,{margin_v},1
{extra_styles}
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def _caption_events(words: list[Word], style: CaptionStyle) -> list[str]:
    hl = _ass_color(style.highlight)
    base = _ass_color(style.color)
    pop = r"\fscx112\fscy112" if style.pop else ""
    events = []
    for page in group_words(words, style.words_per_line):
        texts = [_escape(w.text.upper() if style.uppercase else w.text) for w in page]
        for i, w in enumerate(page):
            start = w.start
            # Hold each highlight until the next word starts so text never flickers.
            end = page[i + 1].start if i + 1 < len(page) else w.end
            if end - start < 0.05:
                end = start + 0.05
            parts = []
            for j, t in enumerate(texts):
                if j == i:
                    parts.append(rf"{{\c{hl}{pop}}}{t}{{\c{base}\fscx100\fscy100}}")
                else:
                    parts.append(t)
            events.append(f"Dialogue: 0,{_ts(start)},{_ts(end)},Caption,,0,0,0,,{' '.join(parts)}")
    return events


def build_ass(words: list[Word], style: CaptionStyle, title: str | None = None,
              title_duration: float = 3.0) -> str:
    """Return a full ASS document. `title` adds a boxed hook/title card at the top."""
    extra = ""
    events = _caption_events(words, style)
    if title:
        extra = (
            f"Style: Title,{style.font},64,{_ass_color('#111111')},{_ass_color('#111111')},"
            f"{_ass_color('#FFFFFF')},{_ass_color('#FFFFFF')},-1,0,0,0,100,100,0,0,3,24,0,8,90,90,260,1\n"
        )
        events.insert(0, f"Dialogue: 1,{_ts(0)},{_ts(title_duration)},Title,,0,0,0,,"
                         rf"{{\fad(150,250)}}{_escape(title)}")
    return _header(style, extra) + "\n".join(events) + "\n"


def write_ass(path: Path, words: list[Word], style: CaptionStyle, title: str | None = None) -> Path:
    path.write_text(build_ass(words, style, title), encoding="utf-8")
    return path
