import numpy as np
import pytest

from pdml.assess import assess
from pdml.published import MARKERS, eye_score, fuse, posterior


def m(name, value, conf=0.9):
    return {"name": name, "value": value, "confidence": conf}


def test_every_scoreable_number_is_cited_and_consistent():
    e = MARKERS["antisaccade_error_rate"]
    assert (e.hc[0], e.pd[0], e.smd) == (0.19, 0.34, 0.99)
    assert (e.pd[0] - e.hc[0]) / e.hc[1] == pytest.approx(e.smd, abs=0.005)        # implied SD matches g
    for mk in MARKERS.values():
        assert mk.source and (mk.hc is None) == (mk.pd is None)


def test_error_rate_direction_and_clamp():
    low = eye_score([m("antisaccade_error_rate", 0.05)])["llr"]
    high = eye_score([m("antisaccade_error_rate", 0.60)])["llr"]
    assert low < 0 < high
    assert abs(eye_score([m("antisaccade_error_rate", 1.0)])["llr"]) <= 0.5 * 3 + 1e-9


def test_hardware_sensitive_markers_need_own_reference():
    ms = [m("antisaccade_latency_median", 500), m("plr_latency", 300)]
    r = eye_score(ms)
    assert r["n_used"] == 0 and len(r["skipped"]) == 2
    ref = {"antisaccade_latency_median": (330.0, 40.0), "plr_latency": (230.0, 20.0)}
    r2 = eye_score(ms, ref)
    assert r2["n_used"] == 2 and r2["llr"] > 0                       # slower than own healthy -> toward PD


def test_low_confidence_marker_is_skipped():
    assert eye_score([m("antisaccade_error_rate", 0.6, conf=0.2)])["n_used"] == 0


def test_fuse_adds_log_odds_and_handles_missing_sensor():
    assert fuse(0.7, 0.0)["probability"] == pytest.approx(0.7)
    assert fuse(0.5, 1.0)["probability"] == pytest.approx(posterior(1.0))
    assert fuse(None, None)["probability"] is None
    assert fuse(None, 1.0)["sensors_used"] == ["glasses"]
    assert fuse(0.7, 1.0)["probability"] > fuse(0.7, 0.0)["probability"]


def test_assess_end_to_end_report():
    a = assess([m("antisaccade_error_rate", 0.45), m("blink_rate", 8)], wrist_prob=0.6)
    assert a["combined"]["sensors_used"] == ["wrist", "glasses"] and a["combined"]["probability"] > 0.6
    assert "blink_rate" in a["context_only"] and "Not a diagnosis" in a["disclaimer"]
