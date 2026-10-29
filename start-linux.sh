#!/bin/bash
# Run ./start-linux.sh to open ClipForge. First run installs everything (a few minutes).
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || echo "ffmpeg is missing - install it with: sudo apt install ffmpeg"
if [ ! -d .venv ]; then
  echo "Setting up ClipForge for the first time..."
  python3 -m venv .venv && .venv/bin/pip install -q --upgrade pip \
    && .venv/bin/pip install -q -r requirements.txt || exit 1
  .venv/bin/pip install -q pywebview || echo "(native window unavailable - will use Chrome app mode)"
fi
exec .venv/bin/python -m clipforge app
