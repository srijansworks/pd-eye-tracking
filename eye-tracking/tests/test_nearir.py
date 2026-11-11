"""Near-eye IR (glasses camera) pipeline: pupil detector accuracy and end-to-end
measurements on synthetic IR video with exact ground truth."""

import json

import numpy as np
import pytest

from eyetrack import calibration, features
from eyetrack.export import build_batch
from eyetrack.nearir.pupil import PupilDetector
from eyetrack.nearir.render import EyeCamera, EyeState, render


def test_pupil_detector_subpixel_on_open_eyes():
    cam, rng, det = EyeCamera(), np.random.default_rng(7), PupilDetector()
    errs, derrs = [], []
    for _ in range(120):
        st = EyeState(rng.uniform(-18, 18), rng.uniform(-10, 10), rng.uniform(2.5, 6.5))
        img, tr = render(cam, st, rng)
        det.reset()
        p = det.detect(img)
        assert p.ok and p.confidence > 0.6
        errs.append(np.hypot(p.cx - tr["cx"], p.cy - tr["cy"]))
        derrs.append(abs(p.major - tr["major"]))
    assert np.median(errs) < 0.3 and np.max(errs) < 1.0     # pixels
    assert np.median(derrs) < 0.5


def test_closed_eye_is_not_a_pupil():
    cam, rng, det = EyeCamera(), np.random.default_rng(8), PupilDetector()
    accepted = 0
    for _ in range(40):
        img, tr = render(cam, EyeState(rng.uniform(-10, 10), 0, 4.0, lid_open=0.02), rng)
        det.reset()
        accepted += det.detect(img).ok
    assert accepted <= 2


def test_size_jump_is_rejected_in_video():
    cam, rng, det = EyeCamera(), np.random.default_rng(9), PupilDetector()
    for _ in range(10):
        det.detect(render(cam, EyeState(0, 0, 4.0), rng)[0])
    p = det.detect(render(cam, EyeState(0, 0, 7.0), rng)[0])  # +75% in one frame: impossible
    assert not p.ok


@pytest.mark.slow
def test_glasses_pipeline_end_to_end_60fps():
    from eyetrack.nearir.simulate import simulate_ir
    rec, stim, truth = simulate_ir(fps=60, seed=2)
    c = calibration.fit(rec, stim)
    assert c["rmse_x_deg"] < 0.3
    calibration.apply(rec, c)
    ms, q = features.compute(rec, stim)
    d = {m["name"]: m["value"] for m in ms}
    assert d["saccade_gain_median"] == pytest.approx(truth["saccade_gain"], abs=0.04)
    assert d["saccade_latency_median"] == pytest.approx(truth["latency_median_ms"], abs=20)
    assert d["pursuit_velocity_gain"] == pytest.approx(truth["pursuit_gain"], abs=0.08)
    assert d["pupil_diameter_median"] == pytest.approx(truth["pupil_mm_median"], abs=0.1)   # mm
    assert d["pupil_found_fraction"] > 0.95
    assert "nearir" in q["flags"]
    batch = build_batch(rec, ms, q, stim, session_id="00000000-0000-4000-8000-000000000002")
    json.dumps(batch, allow_nan=False)                          # API-safe JSON
