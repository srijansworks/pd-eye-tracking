"""Wrist features recover a known tremor frequency and separate tremor from no tremor."""

import numpy as np
import pytest

from pdml.wrist_features import wrist_features


def synth(freq=5.0, amp=0.05, fs=100.0, seconds=10.24, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(0, seconds, 1 / fs)
    acc = np.column_stack([amp * np.sin(2 * np.pi * freq * t), 0.3 * amp * np.sin(2 * np.pi * freq * t + 1),
                           np.ones_like(t)])                    # gravity on z
    acc += rng.normal(0, 0.005, acc.shape)
    gyro = np.gradient(acc, 1 / fs, axis=0) * 0.2 + rng.normal(0, 0.01, acc.shape)
    return acc, gyro


@pytest.mark.parametrize("f0", [4.5, 5.5, 9.0])
def test_peak_frequency_recovered(f0):
    acc, gyro = synth(freq=f0)
    d = wrist_features(acc, gyro)
    assert d["acc_peak_freq"] == pytest.approx(f0, abs=0.5)


def test_parkinsonian_band_power_higher_for_5hz_tremor():
    d_trem = wrist_features(*synth(freq=5.0, amp=0.05))
    d_none = wrist_features(*synth(freq=5.0, amp=0.0))
    assert d_trem["acc_relpower_tremor_3_7hz"] > 0.6
    assert d_trem["acc_power_tremor_3_7hz"] > d_none["acc_power_tremor_3_7hz"] + 1.5   # >30x power
    assert d_trem["acc_peak_prominence"] > 10 * d_none["acc_peak_prominence"]


def test_gravity_does_not_count_as_movement():
    acc, _ = synth(amp=0.0)
    assert wrist_features(acc, None)["acc_rms"] < 0.02
