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
    def __init__(self, cfg: PupilDetectorConfig | None = None):
        self.det = PupilDetector(cfg)

    def process(self, image: np.ndarray, t_seconds: float) -> EyeFrame:
        gray = image if image.ndim == 2 else cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        h_img, w_img = gray.shape
        p = self.det.detect(gray)
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
