"""Thin wrappers around ffmpeg / ffprobe / yt-dlp."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


class MediaError(RuntimeError):
    pass


def require_ffmpeg() -> None:
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise MediaError(f"{tool} not found on PATH - install ffmpeg first")


def run(cmd: list[str], cwd: Path | None = None) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise MediaError(f"command failed: {' '.join(cmd[:3])} ...\n{tail}")


def probe(path: Path) -> dict:
    """Return duration (s), width, height and whether the file has audio."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json",
         "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise MediaError(f"ffprobe could not read {path}: {out.stderr.strip()}")
    data = json.loads(out.stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video"), None)
    has_audio = any(s["codec_type"] == "audio" for s in data["streams"])
    width = height = 0
    if video:
        width, height = int(video["width"]), int(video["height"])
        # Phone footage often stores portrait video as landscape + rotation.
        rotation = abs(int(video.get("tags", {}).get("rotate", 0) or 0))
        for side in video.get("side_data_list", []):
            rotation = abs(int(side.get("rotation", rotation) or 0))
        if rotation in (90, 270):
            width, height = height, width
    return {
        "duration": float(data["format"].get("duration", 0.0)),
        "width": width,
        "height": height,
        "has_audio": has_audio,
    }


def extract_audio(src: Path, dst: Path) -> Path:
    """16 kHz mono WAV - what Whisper wants."""
    run(["ffmpeg", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000", str(dst)])
    return dst


def download(url: str, dest_dir: Path) -> Path:
    """Download a video from YouTube/TikTok/etc. with yt-dlp."""
    try:
        import yt_dlp
    except ImportError as e:
        raise MediaError("yt-dlp is not installed (pip install yt-dlp)") from e
    dest_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "quiet": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
    if not path.exists():
        matches = sorted(dest_dir.glob(f"{info['id']}.*"))
        if not matches:
            raise MediaError(f"download finished but no file found for {url}")
        path = matches[0]
    return path
