"""Command line: python -m clipforge {clip,story,serve} ..."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from . import captions, pipeline, story


def _progress(frac: float, msg: str) -> None:
    print(f"[{frac * 100:5.1f}%] {msg}", file=sys.stderr, flush=True)


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="clipforge", description="AI short-form video generator")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("clip", help="Long video -> viral vertical clips (Opus Clip mode)")
    c.add_argument("source", help="Video file or URL (YouTube, etc.)")
    c.add_argument("-o", "--out", default="output/clips")
    c.add_argument("-n", "--num-clips", type=int, default=5)
    c.add_argument("--min", type=float, default=20, help="Min clip length (s)")
    c.add_argument("--max", type=float, default=60, help="Max clip length (s)")
    c.add_argument("--layout", choices=["crop", "fit"], default="crop")
    c.add_argument("--captions", choices=list(captions.PRESETS), default="bold")
    c.add_argument("--no-captions", action="store_true")
    c.add_argument("--no-hook", action="store_true", help="Skip the hook title card")
    c.add_argument("--prompt", default="", help='e.g. "only the funny moments"')
    c.add_argument("--no-ai", action="store_true", help="Use the offline heuristic")
    c.add_argument("--whisper", default=None, help="Whisper model: tiny/base/small/medium/large-v3")

    s = sub.add_parser("story", help="Script/topic -> narrated gameplay short (Crayo mode)")
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--script", help="Narration text, or @file.txt")
    g.add_argument("--topic", help="Let AI write the script about this")
    s.add_argument("-o", "--out", default="output/story")
    s.add_argument("--style", default="reddit", help=f"one of {list(story.STYLES)} or free text")
    s.add_argument("--seconds", type=int, default=60)
    s.add_argument("--voice", default="en-US-AndrewMultilingualNeural")
    s.add_argument("--rate", default="+10%")
    s.add_argument("--captions", choices=list(captions.PRESETS), default="bold")
    s.add_argument("--title", default="", help="Title card shown for the first 3 seconds")
    s.add_argument("--background", type=Path, help="Gameplay video (default: random from backgrounds/)")
    s.add_argument("--music", type=Path)

    v = sub.add_parser("serve", help="Run the web app")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8000)

    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if args.cmd == "clip":
        opts = pipeline.ClipOptions(
            num_clips=args.num_clips, min_len=args.min, max_len=args.max, layout=args.layout,
            caption_preset=args.captions, captions=not args.no_captions,
            hook_title=not args.no_hook, prompt=args.prompt, use_ai=not args.no_ai,
            whisper_model=args.whisper)
        result = pipeline.auto_clip(args.source, Path(args.out), opts, _progress)
        print(f"\nHighlight engine: {result['engine']}")
        for clip in result["clips"]:
            print(f"  [{clip['score']:3d}] {clip['title']}  ({clip['duration']:.0f}s) -> "
                  f"{Path(args.out) / clip['video']}")
    elif args.cmd == "story":
        script = args.script or ""
        if script.startswith("@"):
            script = Path(script[1:]).read_text()
        opts = pipeline.StoryOptions(
            script=script, topic=args.topic or "", style=args.style, seconds=args.seconds,
            voice=args.voice, rate=args.rate, caption_preset=args.captions, title=args.title,
            background=args.background, music=args.music)
        result = pipeline.make_story(Path(args.out), opts, _progress)
        print(f"\nSaved {Path(args.out) / result['video']} ({result['duration']:.0f}s)")
    else:
        import uvicorn
        print(f"ClipForge running at http://{args.host}:{args.port}")
        uvicorn.run("clipforge.server:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
