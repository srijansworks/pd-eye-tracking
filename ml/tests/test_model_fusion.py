"""Mechanics of evaluation and fusion on synthetic data (no performance claims about PD)."""

import numpy as np
import pytest

from pdml.fusion import LateFusion
from pdml.model import cross_validate


def make(n=300, effect=1.0, seed=0, n_noise=5):
    rng = np.random.default_rng(seed)
    y = rng.integers(0, 2, n)
    X = rng.normal(0, 1, (n, n_noise))
    X[:, 0] += effect * y
    return X, y


def test_cv_finds_signal_and_reports_chance_for_noise():
    X, y = make(effect=1.5)
    assert cross_validate(X, y).auc > 0.8
    Xn, yn = make(effect=0.0, seed=1)
    r = cross_validate(Xn, yn)
    assert 0.35 < r.auc < 0.65 and r.auc_ci[0] < 0.5 < r.auc_ci[1]   # chance, and the CI says so


def test_fusion_handles_missing_modalities_and_combines_signal():
    rng = np.random.default_rng(3)
    n = 400
    y = rng.integers(0, 2, n)
    eye = rng.normal(0, 1, (n, 3)); eye[:, 0] += 0.8 * y          # weak, independent signals
    wrist = rng.normal(0, 1, (n, 3)); wrist[:, 0] += 0.8 * y
    tr, te = np.arange(300), np.arange(300, n)
    f = LateFusion().fit({"eye": (eye[tr], y[tr], ["e0", "e1", "e2"]),
                          "wrist": (wrist[tr], y[tr], ["w0", "w1", "w2"])})
    out = f.predict({"eye": eye[te[0]], "wrist": None})
    assert out["modalities_used"] == ["eye"] and 0 <= out["probability"] <= 1
    assert f.predict({})["probability"] is None
    from sklearn.metrics import roc_auc_score
    p_eye = [f.predict({"eye": eye[i]})["probability"] for i in te]
    p_both = [f.predict({"eye": eye[i], "wrist": wrist[i]})["probability"] for i in te]
    assert roc_auc_score(y[te], p_both) > roc_auc_score(y[te], p_eye)   # two independent signals beat one
