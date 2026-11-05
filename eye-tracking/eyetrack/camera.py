"""Camera capture with per-frame timestamps.

Why a background thread? `cap.read()` blocks until the next frame arrives
(~33 ms at 30 fps). If the display/stimulus loop also waited on it, the
stimulus would stutter. The thread grabs frames as fast as the camera
delivers them and stamps each with `time.monotonic()` the moment it arrives.

Caveat: the timestamp is when the frame reached Python, not when the sensor
exposed it. Webcams add a roughly constant 30-100 ms pipeline delay. That
shifts absolute saccade latency by a constant; comparisons made on the
SAME hardware are still meaningful. See docs/EYE_TRACKING.md.
"""

from __future__ import annotations

import platform
import queue
import threading
import time
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Frame:
    t: float            # time.monotonic() seconds
    image: np.ndarray   # BGR


class Camera:
    def __init__(self, index: int = 0, width: int = 1280, height: int = 720, fps: int = 60):
        backend = cv2.CAP_AVFOUNDATION if platform.system() == "Darwin" else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(index, backend)
        if not self.cap.isOpened():
            raise RuntimeError(
                f"Could not open camera {index}. On macOS, allow camera access for your "
                "terminal app in System Settings > Privacy & Security > Camera."
            )
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.cap.set(cv2.CAP_PROP_FPS, fps)  # a request; the camera may ignore it
        self.queue: queue.Queue[Frame] = queue.Queue(maxsize=600)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self.dropped = 0

    @property
    def info(self) -> dict:
        return {
            "width": int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            "height": int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            "fps_reported": float(self.cap.get(cv2.CAP_PROP_FPS)),
        }

    def start(self) -> "Camera":
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            ok, img = self.cap.read()
            t = time.monotonic()
            if not ok:
                time.sleep(0.005)
                continue
            try:
                self.queue.put_nowait(Frame(t, img))
            except queue.Full:
                self.dropped += 1  # processing fell behind; counted as a quality issue

    def frames(self) -> list[Frame]:
        """Return every frame captured since the last call (oldest first)."""
        out = []
        while True:
            try:
                out.append(self.queue.get_nowait())
            except queue.Empty:
                return out

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=1.0)
        self.cap.release()


def video_frames(path: str):
    """Yield Frames from a video file, timestamped from its frame rate."""
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    i = 0
    while True:
        ok, img = cap.read()
        if not ok:
            break
        # Prefer the container timestamp; fall back to frame index / fps.
        pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
        t = pos_ms / 1000.0 if pos_ms > 0 or i == 0 else i / fps
        yield Frame(t, img)
        i += 1
    cap.release()
