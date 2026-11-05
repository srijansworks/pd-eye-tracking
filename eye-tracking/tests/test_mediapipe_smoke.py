"""Smoke test of the real MediaPipe model (skipped if the model isn't downloaded).

We can't commit face images, so this checks that the model loads, that a
frame without a face is reported as a tracking failure (not a crash or a
fake measurement), and that timestamps are forced to increase.
"""

import numpy as np
import pytest

from eyetrack.landmarks import DEFAULT_MODEL, EyeLandmarker

pytestmark = pytest.mark.skipif(not DEFAULT_MODEL.exists(), reason="model not downloaded")


def test_no_face_is_a_flagged_failure():
    lm = EyeLandmarker()
    try:
        blank = np.full((480, 640, 3), 90, np.uint8)
        for i in range(3):
            ef = lm.process(blank, 1.0)  # same timestamp on purpose
            assert ef.ok is False and np.isnan(ef.h)
    finally:
        lm.close()
