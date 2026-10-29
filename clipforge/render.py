"""ffmpeg filter graphs for vertical 1080x1920 output."""

from __future__ import annotations

from pathlib import Path

from .captions import HEIGHT, WIDTH
from .media import run

ENCODE = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart"]


def _vertical_filter(layout: str, src_w: int, src_h: int, center_x: float | None) -> str:
    """Filter chain [0:v] -> [v] producing a 1080x1920 frame.

    layout:
      crop - fill the frame, cropping the sides around the speaker (Opus Clip "AI reframe")
      fit  - whole frame centred over a blurred, zoomed copy of itself
    """
    if src_w and src_h and src_w / src_h <= WIDTH / HEIGHT + 0.01:
        # Already vertical (or narrower): just scale and pad.
        return (f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
                f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black,setsar=1[v]")
    if layout == "fit":
        return (f"[0:v]split=2[a][b];"
                f"[a]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},"
                f"boxblur=24:2,eq=brightness=-0.08[bg];"
                f"[b]scale={WIDTH}:-2[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v]")
    cx = 0.5 if center_x is None else center_x
    crop_w = f"ih*{WIDTH}/{HEIGHT}"
    x = f"max(0\\,min(iw-{crop_w}\\,iw*{cx:.4f}-{crop_w}/2))"
    return f"[0:v]crop={crop_w}:ih:{x}:0,scale={WIDTH}:{HEIGHT},setsar=1[v]"


def render_clip(src: Path, start: float, end: float, out: Path, ass: Path | None,
                layout: str, src_w: int, src_h: int, center_x: float | None,
                has_audio: bool = True) -> Path:
    graph = _vertical_filter(layout, src_w, src_h, center_x)
    if ass is not None:
        # Run from the subtitle's directory so its path needs no filter escaping.
        graph = graph[:-3] + f"[pre];[pre]ass={ass.name}[v]"
    cmd = ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-to", f"{end:.3f}", "-i", str(src.resolve()),
           "-filter_complex", graph, "-map", "[v]"]
    if has_audio:
        cmd += ["-map", "0:a:0"]
    cmd += ENCODE + [str(out.resolve())]
    run(cmd, cwd=ass.parent if ass else None)
    return out


def render_story(background: Path | None, voice: Path, duration: float, out: Path, ass: Path,
                 bg_offset: float = 0.0, music: Path | None = None, music_volume: float = 0.12) -> Path:
    """Narration + captions over looping background footage (Crayo style)."""
    cmd = ["ffmpeg", "-y"]
    if background is None:
        # No gameplay supplied: animated gradient so the output still looks intentional.
        cmd += ["-f", "lavfi", "-i",
                f"gradients=s={WIDTH}x{HEIGHT}:c0=0x1e1b4b:c1=0x7c3aed:c2=0xdb2777:nb_colors=3:speed=0.02:d={duration:.2f}"]
        vf = "[0:v]setsar=1"
    else:
        cmd += ["-stream_loop", "-1", "-ss", f"{bg_offset:.2f}", "-i", str(background.resolve())]
        vf = (f"[0:v]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
              f"crop={WIDTH}:{HEIGHT},setsar=1")
    cmd += ["-i", str(voice.resolve())]
    graph = f"{vf},ass={ass.name}[v]"
    audio_map = "1:a"
    if music is not None:
        cmd += ["-stream_loop", "-1", "-i", str(music.resolve())]
        graph += (f";[2:a]volume={music_volume}[m];[1:a][m]amix=inputs=2:duration=first:"
                  f"dropout_transition=0[a]")
        audio_map = "[a]"
    cmd += ["-filter_complex", graph, "-map", "[v]", "-map", audio_map,
            "-t", f"{duration:.2f}", "-r", "30"] + ENCODE + [str(out.resolve())]
    run(cmd, cwd=ass.parent)
    return out


def thumbnail(video: Path, out: Path, at: float = 0.8) -> Path:
    run(["ffmpeg", "-y", "-ss", f"{at:.2f}", "-i", str(video), "-frames:v", "1",
         "-vf", "scale=360:-2", str(out)])
    return out
