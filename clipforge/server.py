"""Web app: upload a video or paste a link, get shorts back."""

from __future__ import annotations

import logging
import shutil
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import captions, pipeline, story

log = logging.getLogger(__name__)

ROOT = Path.cwd()
OUTPUT = ROOT / "output"
UPLOADS = ROOT / "uploads"
BACKGROUNDS = ROOT / "backgrounds"
STATIC = Path(__file__).parent / "static"
for d in (OUTPUT, UPLOADS, BACKGROUNDS):
    d.mkdir(exist_ok=True)

app = FastAPI(title="ClipForge")
app.mount("/files", StaticFiles(directory=OUTPUT), name="files")

# Rendering is CPU-heavy, so jobs run one at a time.
_executor = ThreadPoolExecutor(max_workers=1)
_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _update(job_id: str, **kw) -> None:
    with _lock:
        _jobs[job_id].update(kw)


def _submit(kind: str, fn, *args) -> dict:
    job_id = uuid.uuid4().hex[:10]
    out_dir = OUTPUT / job_id
    with _lock:
        _jobs[job_id] = {"id": job_id, "kind": kind, "status": "queued", "progress": 0.0,
                         "message": "Waiting in queue", "result": None, "error": None}

    def progress(frac: float, msg: str) -> None:
        _update(job_id, progress=round(frac, 3), message=msg)

    def work() -> None:
        _update(job_id, status="running")
        try:
            result = fn(out_dir, *args, progress)
            _update(job_id, status="done", progress=1.0, result=result)
        except Exception as e:
            log.error("job %s failed\n%s", job_id, traceback.format_exc())
            _update(job_id, status="error", error=str(e), message="Failed")

    _executor.submit(work)
    return _jobs[job_id]


async def _save_upload(upload: UploadFile | None) -> Path | None:
    if upload is None or not upload.filename:
        return None
    dest = UPLOADS / f"{uuid.uuid4().hex[:8]}-{Path(upload.filename).name}"
    with dest.open("wb") as f:
        shutil.copyfileobj(upload.file, f)
    return dest


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/options")
def options() -> dict:
    return {
        "voices": story.VOICES,
        "styles": list(story.STYLES),
        "caption_presets": list(captions.PRESETS),
        "backgrounds": sorted(p.name for p in BACKGROUNDS.iterdir()
                              if p.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm"}),
    }


@app.post("/api/clip")
async def create_clips(
    file: UploadFile | None = File(None),
    url: str = Form(""),
    num_clips: int = Form(5),
    min_len: float = Form(20),
    max_len: float = Form(60),
    layout: str = Form("crop"),
    caption_preset: str = Form("bold"),
    captions_on: bool = Form(True),
    hook_title: bool = Form(True),
    prompt: str = Form(""),
) -> dict:
    src = await _save_upload(file)
    source = src or url.strip()
    if not source:
        raise HTTPException(400, "Upload a video or paste a URL")
    if min_len >= max_len:
        raise HTTPException(400, "Min length must be less than max length")
    opts = pipeline.ClipOptions(num_clips=max(1, min(num_clips, 20)), min_len=min_len,
                                max_len=max_len, layout=layout, caption_preset=caption_preset,
                                captions=captions_on, hook_title=hook_title, prompt=prompt)
    return _submit("clip", lambda out, p: pipeline.auto_clip(source, out, opts, p))


@app.post("/api/story")
async def create_story(
    script: str = Form(""),
    topic: str = Form(""),
    style: str = Form("reddit"),
    seconds: int = Form(60),
    voice: str = Form("en-US-AndrewMultilingualNeural"),
    caption_preset: str = Form("bold"),
    title: str = Form(""),
    background_name: str = Form(""),
    background: UploadFile | None = File(None),
    music: UploadFile | None = File(None),
) -> dict:
    if not script.strip() and not topic.strip():
        raise HTTPException(400, "Write a script or give a topic")
    bg = await _save_upload(background)
    if bg is None and background_name:
        candidate = (BACKGROUNDS / background_name).resolve()
        if candidate.parent != BACKGROUNDS.resolve() or not candidate.exists():
            raise HTTPException(400, "Unknown background")
        bg = candidate
    opts = pipeline.StoryOptions(script=script, topic=topic, style=style,
                                 seconds=max(15, min(seconds, 180)), voice=voice,
                                 caption_preset=caption_preset, title=title, background=bg,
                                 backgrounds_dir=BACKGROUNDS, music=await _save_upload(music))
    return _submit("story", lambda out, p: pipeline.make_story(out, opts, p))


@app.get("/api/jobs/{job_id}")
def job(job_id: str) -> dict:
    with _lock:
        if job_id not in _jobs:
            raise HTTPException(404, "No such job")
        return dict(_jobs[job_id])


@app.get("/api/jobs")
def jobs() -> list[dict]:
    with _lock:
        return [dict(j) for j in reversed(_jobs.values())]


app.mount("/static", StaticFiles(directory=STATIC), name="static")
