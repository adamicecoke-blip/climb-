"""Find where the speaker is so a 16:9 frame can be cropped to 9:16 around them."""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)


def speaker_center_x(video: Path, start: float, end: float, samples: int = 12) -> float | None:
    """Return the median horizontal face centre (0..1) in [start, end], or None.

    Samples a handful of frames and runs OpenCV's face detector; good enough for
    podcasts / talking-head content, which is what this mode is for.
    """
    try:
        import cv2
    except ImportError:
        log.info("opencv not installed - using centre crop")
        return None

    if not hasattr(cv2, "CascadeClassifier"):  # removed from core in OpenCV 5
        log.info("this OpenCV build has no face detector - using centre crop")
        return None
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        return None
    centres: list[float] = []
    try:
        span = max(end - start, 0.1)
        for i in range(samples):
            t = start + span * (i + 0.5) / samples
            cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
            ok, frame = cap.read()
            if not ok:
                continue
            h, w = frame.shape[:2]
            scale = 480 / w if w > 480 else 1.0
            small = cv2.resize(frame, None, fx=scale, fy=scale) if scale != 1.0 else frame
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            faces = cascade.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=6,
                                             minSize=(24, 24))
            if len(faces):
                # Biggest face is most likely the active speaker.
                x, _, fw, _ = max(faces, key=lambda f: f[2] * f[3])
                centres.append((x + fw / 2) / small.shape[1])
    finally:
        cap.release()
    if not centres:
        return None
    centres.sort()
    return centres[len(centres) // 2]
