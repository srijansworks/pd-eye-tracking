"""Near-eye IR tracker with the same interface as the webcam EyeLandmarker.

`process(image, t) -> EyeFrame`, so live recording, analysis, upload and the
dashboard work unchanged whether the eye camera is a laptop webcam or the
glasses' infrared camera.

Signal conventions (head-mounted camera, so no head pose is needed):
  h, v        pupil centre relative to the image centre, divided by image width
  pupil_px    pupil diameter (long ellipse axis) in pixels
  pupil_conf  detector confidence
  blink_score 1 when no trustworthy pupil is visible (lid closed or tracking lost)
"""

from __future__ import annotations

import math

import cv2
import numpy as np

from ..landmarks import EyeFrame
from .pupil import PupilDetector, PupilDetectorConfig


class NearIRTracker:
    """method:
      'classic' - hand-built dark-pupil detector (no extra dependencies)
      'hybrid'  - neural network finds the pupil, classic ellipse fit refines it (needs torch
                  + models/pupilnet.pt); falls back to the network's centre if the fit fails
      'nn'      - neural network centre only (no pupil size)
      'fast'    - hybrid accuracy at real-time cost: the network runs only every `nn_every` frames
                  (and whenever tracking is lost); in between the ellipse fit tracks the pupil inside a
                  small crop around its last position. Same output as 'hybrid'.
    """

    def __init__(self, cfg: PupilDetectorConfig | None = None, method: str = "classic",
                 nn_min_conf: float = 0.3, nn_every: int = 30, track_radius_frac: float = 0.05,
                 track_min_conf: float = 0.5):
        self.det = PupilDetector(cfg)
        self.method = method
        self.nn_min_conf = nn_min_conf
        self.nn_every, self.track_radius_frac, self.track_min_conf = nn_every, track_radius_frac, track_min_conf
        self._n = 0
        self._last = None          # last good pupil (fast mode)
        self.net = None
        if method in ("nn", "hybrid", "fast"):
            from .nn_model import PupilNet
            self.net = PupilNet()

    def _detect(self, gray: np.ndarray):
        from .pupil import Pupil
        if self.net is None:
            return self.det.detect(gray)
        if self.method == "fast":
            return self._detect_fast(gray)
        nx, ny, nconf = self.net.predict(gray)
        if nconf < self.nn_min_conf:
            return Pupil(False, confidence=nconf)
        if self.method == "hybrid":
            r = self.det.refine_near(gray, nx, ny, radius=0.025 * gray.shape[1])
            if r.ok:
                return r
        return Pupil(True, cx=nx, cy=ny, confidence=nconf)   # centre only; size unknown

    def _detect_fast(self, gray: np.ndarray):
        from .pupil import Pupil
        self._n += 1
        last = self._last
        if last is not None and self._n % self.nn_every:
            rad = self.track_radius_frac * gray.shape[1]
            # crop = search radius + pupil + a ring of iris for the contrast check
            r = self.det.refine_near(gray, last.cx, last.cy, radius=rad, crop_half=int(rad + 1.5 * last.major + 10))
            # A real pupil changes size slowly; a sudden jump is a bad fit, so ask the network instead.
            if r.ok and r.confidence >= self.track_min_conf and abs(r.major / last.major - 1) < 0.3:
                self._last = r
                return r
        nx, ny, nconf = self.net.predict(gray)
        if nconf < self.nn_min_conf:
            self._last = None
            return Pupil(False, confidence=nconf)
        r = self.det.refine_near(gray, nx, ny, radius=0.025 * gray.shape[1])
        if not r.ok:
            r = Pupil(True, cx=nx, cy=ny, confidence=nconf)
        self._last = r if r.ok and not math.isnan(r.major) else None
        return r

    def process(self, image: np.ndarray, t_seconds: float) -> EyeFrame:
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h_img, w_img = gray.shape
        p = self._detect(gray)
        bright = float(gray.mean())
        if not p.ok:
            # The camera frame itself is fine (frame_ok) but no pupil is visible.
            return EyeFrame(ok=True, blink_score=1.0, brightness=bright, pupil_conf=p.confidence,
                            points={"iris": [], "corners": []})
        return EyeFrame(
            ok=True,
            h=(p.cx - w_img / 2) / w_img,
            v=(p.cy - h_img / 2) / w_img,
            blink_score=0.0,
            brightness=bright,
            pupil_px=p.major,
            pupil_conf=p.confidence,
            points={"iris": [np.array([p.cx, p.cy])], "corners": []},
        )

    def close(self) -> None:
        pass

    def reset(self) -> None:
        self.det.reset()
        self._n, self._last = 0, None
