"""Web app: upload a video or paste a link, get shorts back."""

from __future__ import annotations

import json
import logging
import os
import re
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

ROOT = Path(os.environ.get("CLIPFORGE_HOME") or Path.cwd())
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


@app.get("/sw.js")
def service_worker() -> FileResponse:
    # Served from the root so its scope covers the whole app.
    return FileResponse(STATIC / "sw.js", media_type="text/javascript",
                        headers={"Cache-Control": "no-cache"})


def _project_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{6,32}", job_id):
        raise HTTPException(404, "No such project")
    path = OUTPUT / job_id
    if not path.is_dir():
        raise HTTPException(404, "No such project")
    return path


def _load_project(path: Path) -> dict | None:
    for kind, name in (("clip", "clips.json"), ("story", "story.json")):
        manifest = path / name
        if manifest.exists():
            result = json.loads(manifest.read_text())
            return {"id": path.name, "kind": kind, "created": manifest.stat().st_mtime, "result": result}
    return None


@app.get("/api/library")
def library() -> list[dict]:
    """Finished projects on disk, newest first (survives app restarts)."""
    out = []
    for path in OUTPUT.iterdir():
        if not path.is_dir() or not (p := _load_project(path)):
            continue
        r = p.pop("result")
        if p["kind"] == "clip":
            first = r["clips"][0] if r["clips"] else {}
            p |= {"title": first.get("title", "Clips"), "thumbnail": first.get("thumbnail"),
                  "count": len(r["clips"])}
        else:
            p |= {"title": " ".join(r["script"].split()[:8]), "thumbnail": r["thumbnail"], "count": 1}
        out.append(p)
    return sorted(out, key=lambda p: p["created"], reverse=True)


@app.get("/api/library/{job_id}")
def project(job_id: str) -> dict:
    p = _load_project(_project_dir(job_id))
    if p is None:
        raise HTTPException(404, "Project is not finished")
    return p


@app.delete("/api/library/{job_id}")
def delete_project(job_id: str) -> dict:
    path = _project_dir(job_id)
    with _lock:
        if _jobs.get(job_id, {}).get("status") in ("queued", "running"):
            raise HTTPException(409, "This job is still running")
        _jobs.pop(job_id, None)
    shutil.rmtree(path)
    return {"deleted": job_id}


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
