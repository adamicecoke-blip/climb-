"""Thin wrappers around ffmpeg / ffprobe / yt-dlp."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _use_bundled_ffmpeg() -> None:
    """The installer ships ffmpeg/ffprobe in a folder next to the app; prefer them."""
    if not getattr(sys, "frozen", False):
        return
    for root in (Path(getattr(sys, "_MEIPASS", sys.executable)), Path(sys.executable).parent):
        bundled = root / "ffmpeg"
        if bundled.is_dir():
            os.environ["PATH"] = str(bundled) + os.pathsep + os.environ.get("PATH", "")
            return


_use_bundled_ffmpeg()


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


# YouTube often blocks data-centre servers ("confirm you're not a bot"). Retrying as
# other YouTube apps sometimes gets through; a cookies file from a signed-in
# browser (CLIPFORGE_COOKIES) reliably does.
_YT_CLIENTS = [None, "tv", "web_safari,mweb", "android_vr", "ios"]


def download(url: str, dest_dir: Path) -> Path:
    """Download a video from YouTube/TikTok/etc. with yt-dlp."""
    try:
        import yt_dlp
    except ImportError as e:
        raise MediaError("yt-dlp is not installed (pip install yt-dlp)") from e
    dest_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "outtmpl": str(dest_dir / "%(id)s.%(ext)s"),
        "format": "bv*[height<=1080]+ba/b[height<=1080]/b",
        "merge_output_format": "mp4",
        "quiet": True,
        "noprogress": True,
    }
    cookies = os.environ.get("CLIPFORGE_COOKIES")
    if cookies and Path(cookies).is_file():
        base["cookiefile"] = cookies
    is_youtube = "youtu" in url
    last_error: Exception | None = None
    for client in (_YT_CLIENTS if is_youtube else [None]):
        opts = dict(base)
        if client:
            opts["extractor_args"] = {"youtube": {"player_client": client.split(",")}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                path = Path(ydl.prepare_filename(info)).with_suffix(".mp4")
            break
        except yt_dlp.utils.DownloadError as e:
            last_error = e
            if not is_youtube or "not a bot" not in str(e) and "Sign in" not in str(e):
                raise MediaError(f"Couldn't download {url}: {e}") from e
    else:
        raise MediaError(
            "YouTube blocked the download from this server (it asks to confirm you're not a bot). "
            "Add your YouTube cookies (see the README), or download the video yourself and upload the file."
        ) from last_error
    if not path.exists():
        matches = sorted(dest_dir.glob(f"{info['id']}.*"))
        if not matches:
            raise MediaError(f"download finished but no file found for {url}")
        path = matches[0]
    return path
