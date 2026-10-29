"""End-to-end tests that run offline: Whisper and TTS are stubbed, ffmpeg is real."""

import json
import subprocess
from pathlib import Path

import pytest

from clipforge import captions, highlights, pipeline, story
from clipforge.media import probe
from clipforge.transcribe import Segment, Transcript, Word, words_in_range

SENTENCES = [
    "Here's the secret nobody tells you about money.",
    "Most people save first and invest later.",
    "That is actually the biggest mistake you can make.",
    "Why? Because time in the market beats everything!",
    "I realized this when I was twenty two and broke.",
    "So I started investing ten dollars a week.",
    "Ten years later it changed my life completely.",
    "Now here is how you can do the same thing today.",
]


def fake_transcript(seconds_per_sentence: float = 6.0) -> Transcript:
    segs, t = [], 0.0
    for s in SENTENCES:
        toks = s.split()
        step = seconds_per_sentence / len(toks)
        words = [Word(t + i * step, t + (i + 0.8) * step, w) for i, w in enumerate(toks)]
        segs.append(Segment(t, t + seconds_per_sentence, s, words))
        t += seconds_per_sentence
    return Transcript("en", segs)


@pytest.fixture(scope="module")
def landscape_video(tmp_path_factory) -> Path:
    path = tmp_path_factory.mktemp("src") / "talk.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:d=50:r=30",
         "-f", "lavfi", "-i", "sine=f=220:d=50", "-shortest",
         "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", str(path)],
        check=True, capture_output=True)
    return path


def test_ass_highlights_active_word():
    words = [Word(0, 0.4, "hello"), Word(0.5, 0.9, "world"), Word(1.0, 1.4, "again.")]
    doc = captions.build_ass(words, captions.PRESETS["bold"], title="Big hook")
    dialogue = [line for line in doc.splitlines() if line.startswith("Dialogue")]
    assert len(dialogue) == 4  # title + one event per word
    assert "Big hook" in dialogue[0]
    assert r"{\c&H0000E6FF" in dialogue[1] and "HELLO" in dialogue[1]


def test_group_words_breaks_on_punctuation_and_pause():
    words = [Word(0, .2, "a"), Word(.3, .5, "b."), Word(.6, .8, "c"), Word(3, 3.2, "d")]
    pages = captions.group_words(words, max_words=3)
    assert [[w.text for w in p] for p in pages] == [["a", "b."], ["c"], ["d"]]


def test_words_in_range_is_relative():
    t = fake_transcript()
    ws = words_in_range(t, 6.0, 12.0)
    assert ws[0].text == "Most" and ws[0].start == pytest.approx(0.0)
    assert all(0 <= w.start < 6 for w in ws)


def test_heuristic_highlights_non_overlapping():
    picks, engine = highlights.find_highlights(fake_transcript(), n=2, min_len=10, max_len=20, use_ai=False)
    assert engine == "heuristic" and len(picks) == 2
    a, b = sorted(picks, key=lambda h: h.start)
    assert a.end <= b.start + 0.5
    assert all(9 <= h.duration <= 21 for h in picks)


@pytest.mark.parametrize("layout", ["crop", "fit"])
def test_auto_clip_end_to_end(tmp_path, monkeypatch, landscape_video, layout):
    monkeypatch.setattr(pipeline, "transcribe", lambda wav, model=None: fake_transcript())
    opts = pipeline.ClipOptions(num_clips=2, min_len=10, max_len=20, layout=layout, use_ai=False)
    result = pipeline.auto_clip(landscape_video, tmp_path, opts)
    assert len(result["clips"]) == 2
    for clip in result["clips"]:
        info = probe(tmp_path / clip["video"])
        assert (info["width"], info["height"]) == (1080, 1920)
        assert info["has_audio"]
        assert abs(info["duration"] - clip["duration"]) < 0.6
    assert json.loads((tmp_path / "clips.json").read_text())["engine"] == "heuristic"


def test_story_end_to_end(tmp_path, monkeypatch, landscape_video):
    def fake_tts(text, out, voice, rate):
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=330:d=6", str(out)],
                       check=True, capture_output=True)
        return [Word(i * 0.5, i * 0.5 + 0.4, w) for i, w in enumerate(text.split())]

    monkeypatch.setattr(story, "synthesize", fake_tts)
    for bg in (None, landscape_video):
        out = tmp_path / ("bg" if bg else "gradient")
        opts = pipeline.StoryOptions(script="So my roommate did something wild yesterday.",
                                     title="AITA?", background=bg, backgrounds_dir=tmp_path)
        result = pipeline.make_story(out, opts)
        info = probe(out / result["video"])
        assert (info["width"], info["height"]) == (1080, 1920)
        assert 6 <= info["duration"] <= 7


def test_web_app_library(tmp_path, monkeypatch, landscape_video):
    import importlib
    import time
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CLIPFORGE_HOME", str(tmp_path))
    monkeypatch.setattr(pipeline, "transcribe", lambda wav, model=None: fake_transcript())
    from clipforge import server
    server = importlib.reload(server)
    c = TestClient(server.app)

    assert c.get("/").status_code == 200
    assert c.get("/sw.js").headers["content-type"].startswith("text/javascript")
    assert c.get("/static/manifest.webmanifest").json()["display"] == "standalone"
    assert c.get("/api/library").json() == []

    with landscape_video.open("rb") as f:
        job = c.post("/api/clip", files={"file": ("talk.mp4", f, "video/mp4")},
                     data={"num_clips": "1", "min_len": "10", "max_len": "20"}).json()
    while (s := c.get(f"/api/jobs/{job['id']}").json())["status"] in ("queued", "running"):
        time.sleep(0.5)
    assert s["status"] == "done", s["error"]

    lib = c.get("/api/library").json()
    assert [p["id"] for p in lib] == [job["id"]] and lib[0]["count"] == 1
    proj = c.get(f"/api/library/{job['id']}").json()
    assert c.get(f"/files/{job['id']}/{proj['result']['clips'][0]['video']}").status_code == 200

    assert c.get("/api/library/..%2F..").status_code == 404
    assert c.delete(f"/api/library/{job['id']}").status_code == 200
    assert c.get("/api/library").json() == []
