#!/bin/bash
# Double-click to open ClipForge. First run installs everything (a few minutes).
cd "$(dirname "$0")"
command -v python3 >/dev/null || { echo "Python 3 is not installed: https://www.python.org/downloads/"; read -r; exit 1; }
command -v ffmpeg >/dev/null || echo "ffmpeg is missing - install it with: brew install ffmpeg"
if [ ! -d .venv ]; then
  echo "Setting up ClipForge for the first time..."
  python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip \
    && .venv/bin/pip install -q -r requirements.txt pywebview || { read -r; exit 1; }
fi
exec .venv/bin/python -m clipforge app
