@echo off
REM Double-click to open ClipForge. First run installs everything (a few minutes).
cd /d "%~dp0"
where python >nul 2>nul || (echo Python is not installed. Get it from https://www.python.org/downloads/ & pause & exit /b 1)
if not exist .venv (
  echo Setting up ClipForge for the first time...
  python -m venv .venv || (pause & exit /b 1)
  .venv\Scripts\python -m pip install --upgrade pip -q
  .venv\Scripts\python -m pip install -r requirements.txt pywebview -q || (pause & exit /b 1)
)
.venv\Scripts\python -m clipforge app
if errorlevel 1 pause
