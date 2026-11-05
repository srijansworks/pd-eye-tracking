"""Tests: geometry, event detection, feature accuracy vs synthetic ground truth,
persistence, and the export contract.

The accuracy tests encode what each camera class can and cannot do:
at 30 fps we expect latency/gain/blinks to be roughly right but peak
velocity to be a large under-estimate; at 500 fps everything should match.
"""

import json
from pathlib import Path

import numpy as np
import pytest

from eyetrack import calibration, events, features
from eyetrack.export import build_batch
from eyetrack.landmarks import eye_in_head
from eyetrack.recording import Recording
from eyetrack.synthetic import simulate

SCHEMA = Path(__file__).resolve().parents[2] / "docs" / "schema" / "measurement-batch.v1.schema.json"


def run(fps, noise, seed=1, **kw):
    rec, stim, truth = simulate(fps=fps, noise_deg=noise, seed=seed, **kw)
    cal = calibration.fit(rec, stim)
    assert cal is not None
    calibration.apply(rec, cal)
    ms, q = features.compute(rec, stim)
    return {m["name"]: m for m in ms}, q, truth, cal


# ---------- geometry ------------------------------------------------------
def test_eye_in_head_cancels_head_translation_and_scale():
    a, b, iris = np.array([100.0, 200]), np.array([160.0, 200]), np.array([136.0, 203])
    h1, v1 = eye_in_head(iris, a, b)
    # Same eye, head moved and closer to camera (everything x2 + shifted)
    h2, v2 = eye_in_head(iris * 2 + 50, a * 2 + 50, b * 2 + 50)
    assert h1 == pytest.approx(h2) and v1 == pytest.approx(v2)
    assert h1 == pytest.approx(0.1)  # 6 px right of midpoint / 60 px width
    # Corner order must not matter
    assert eye_in_head(iris, b, a) == pytest.approx((h1, v1))


def test_eye_in_head_cancels_head_roll():
    a, b, iris = np.array([-30.0, 0]), np.array([30.0, 0]), np.array([6.0, 3])
    th = np.radians(15)
    R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
    assert eye_in_head(R @ iris, R @ a, R @ b) == pytest.approx(eye_in_head(iris, a, b))


# ---------- event primitives ---------------------------------------------
def test_blink_split_by_dropped_frame_is_merged():
    t = np.arange(0, 1, 1 / 100)
    closed = np.zeros(len(t), bool)
    closed[20:35] = True
    closed[27] = False  # one dropped frame mid-blink
    b = events.detect_blinks(t, closed)
    assert len(b) == 1 and b[0].duration == pytest.approx(0.15, abs=0.011)


def test_long_closure_is_not_a_blink():
    t = np.arange(0, 2, 1 / 30)
    closed = np.zeros(len(t), bool); closed[5:40] = True  # ~1.2 s
    assert events.detect_blinks(t, closed) == []


def test_single_step_saccade_detected_at_30fps():
    rng = np.random.default_rng(0)
    t = np.arange(0, 3, 1 / 30)
    x = np.where(t > 1.5, 10.0, 0.0) + rng.normal(0, 0.3, len(t))
    s = events.detect_saccades(t, x, np.zeros_like(x), np.ones(len(t), bool), min_amplitude=1)
    assert len(s) == 1
    assert s[0].dx == pytest.approx(10, abs=1.5)
    assert abs(s[0].t_start - 1.5) <= 1 / 30 + 1e-9


# ---------- calibration ---------------------------------------------------
def test_calibration_recovers_degrees():
    rec, stim, _ = simulate(fps=60, noise_deg=0.3)
    cal = calibration.fit(rec, stim)
    assert cal["n_points"] == 6 and cal["rmse_deg"] < 0.5
    calibration.apply(rec, cal)
    m = rec.task_mask("fixation") & (rec["frame_ok"] == 1) & (rec["blink_score"] < 0.5)
    assert np.nanmedian(rec["gx"][m]) == pytest.approx(0, abs=0.3)


def test_calibration_fails_cleanly_without_events():
    rec, _, _ = simulate(fps=30)
    assert calibration.fit(rec, []) is None


# ---------- accuracy vs ground truth -------------------------------------
def test_webcam_30fps_what_works():
    d, q, truth, _ = run(30, 0.5)
    assert d["saccade_latency_median"]["value"] == pytest.approx(truth["latency_median_ms"], abs=20)
    assert d["saccade_gain_median"]["value"] == pytest.approx(truth["saccade_gain"], abs=0.08)
    assert d["pursuit_velocity_gain"]["value"] == pytest.approx(truth["pursuit_gain"], abs=0.12)
    assert d["blink_duration_mean"]["value"] == pytest.approx(truth["blink_duration_ms"], abs=35)
    assert "low_temporal_resolution" in d["saccade_latency_median"]["quality_flags"]


def test_webcam_30fps_peak_velocity_is_flagged_underestimate():
    d, *_ , truth, _ = run(30, 0.5)
    pv = d["saccade_peak_velocity_median"]
    assert pv["value"] < 0.6 * truth["peak_velocity_median_deg_s"]  # the physics limit
    assert "undersampled" in pv["quality_flags"] and pv["confidence"] < 0.2


def test_lab_500fps_everything_matches():
    d, q, truth, _ = run(500, 0.03)
    assert d["saccade_latency_median"]["value"] == pytest.approx(truth["latency_median_ms"], abs=12)
    assert d["saccade_peak_velocity_median"]["value"] == pytest.approx(
        truth["peak_velocity_median_deg_s"], rel=0.1)
    assert d["pursuit_velocity_gain"]["value"] == pytest.approx(truth["pursuit_gain"], abs=0.05)
    assert d["pursuit_phase_lag"]["value"] == pytest.approx(truth["pursuit_lag_ms"], abs=10)
    swj_true = truth["swj_count"] / (13 / 60)
    assert d["square_wave_jerk_rate"]["value"] == pytest.approx(swj_true, rel=0.35)
    assert d["saccade_peak_velocity_median"]["quality_flags"] == []


def test_tracking_failures_lower_confidence():
    good, *_ = run(30, 0.5, dropout=0.01)
    bad, qb, *_ = run(30, 0.5, dropout=0.3)
    assert "many_tracking_failures" in qb["flags"]
    assert bad["blink_rate"]["confidence"] < good["blink_rate"]["confidence"]


def test_uncalibrated_still_gives_latency_in_ms():
    rec, stim, truth = simulate(fps=30, noise_deg=0.4)
    ms, q = features.compute(rec, stim)
    d = {m["name"]: m for m in ms}
    assert "uncalibrated" in q["flags"]
    assert d["saccade_latency_median"]["value"] == pytest.approx(truth["latency_median_ms"], abs=25)
    assert d["saccade_amplitude_median"]["unit"] == "eye_width"
    assert "saccade_gain_median" not in d  # needs degrees


# ---------- persistence + contract ---------------------------------------
def test_recording_roundtrip(tmp_path):
    rec, stim, _ = simulate(fps=30)
    rec.save(tmp_path)
    back = Recording.load(tmp_path)
    assert len(back) == len(rec)
    assert np.allclose(back["h"], rec["h"], equal_nan=True, rtol=1e-5)
    assert (back["task"] == rec["task"]).all()
    assert back.meta["stimulus_events"] == json.loads(json.dumps(stim))


def test_batch_matches_shared_json_schema():
    jsonschema = pytest.importorskip("jsonschema")
    rec, stim, _ = simulate(fps=30)
    rec.meta["started_at_utc"] = "2026-11-04T20:00:00.000Z"
    c = calibration.fit(rec, stim); calibration.apply(rec, c)
    ms, q = features.compute(rec, stim)
    batch = build_batch(rec, ms, q, stim, session_id="00000000-0000-4000-8000-000000000001")
    schema = json.loads(SCHEMA.read_text())
    jsonschema.validate(batch, schema, format_checker=jsonschema.FormatChecker())
    assert all(np.isfinite(m["value"]) for m in batch["measurements"])
    assert batch["recording"]["is_synthetic"] is True
    assert batch["events"][0]["t"].startswith("2026-11-04T20:00")
