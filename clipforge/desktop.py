"""Desktop app: runs the server in the background and opens ClipForge in its own window.

Window, in order of preference:
  1. a native window (pywebview, if installed)
  2. Chrome / Edge / Chromium in "app mode" - its own window, no tabs or address bar
  3. the default web browser
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path


def _free_port(preferred: int = 8765) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise RuntimeError("no free port")


def _start_server(port: int) -> None:
    import uvicorn

    config = uvicorn.Config("clipforge.server:app", host="127.0.0.1", port=port, log_level="warning")
    threading.Thread(target=uvicorn.Server(config).run, daemon=True).start()


def _wait_until_up(url: str, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url + "api/options", timeout=1)
            return
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("ClipForge server did not start")


def _chromium() -> str | None:
    names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "msedge", "chrome"]
    for name in names:
        if path := shutil.which(name):
            return path
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        if base := os.environ.get(env):
            candidates += [rf"{base}\Google\Chrome\Application\chrome.exe",
                           rf"{base}\Microsoft\Edge\Application\msedge.exe"]
    return next((c for c in candidates if Path(c).exists()), None)


def _open_window(url: str) -> None:
    """Open the UI and block until the window is closed."""
    try:
        import webview

        webview.create_window("ClipForge", url, width=1280, height=860, min_size=(380, 600))
        webview.start()
        return
    except ImportError:
        pass

    if browser := _chromium():
        # A separate profile makes it a separate process we can wait on.
        profile = Path(tempfile.gettempdir()) / "clipforge-window"
        proc = subprocess.Popen([browser, f"--app={url}", f"--user-data-dir={profile}",
                                 "--window-size=1280,860", "--no-first-run", "--no-default-browser-check"])
        proc.wait()
        return

    webbrowser.open(url)
    print(f"ClipForge is open in your browser at {url}\nKeep this window open; press Ctrl+C to quit.")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass


def main() -> None:
    from .media import MediaError, require_ffmpeg

    try:
        require_ffmpeg()
    except MediaError as e:
        print(f"⚠ {e}\n  Windows: winget install ffmpeg   Mac: brew install ffmpeg   Linux: sudo apt install ffmpeg")
        sys.exit(1)
    port = _free_port()
    url = f"http://127.0.0.1:{port}/"
    print("Starting ClipForge…")
    _start_server(port)
    _wait_until_up(url)
    _open_window(url)


if __name__ == "__main__":
    main()
