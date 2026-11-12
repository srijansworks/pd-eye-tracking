"""Tremor and movement features from a wrist IMU (accelerometer + gyroscope).

Works on any wrist sensor: the PADS smartwatch dataset now, the team's own wrist
band later. Input: a (N, 3) accelerometer array in g and/or a (N, 3) gyroscope
array in rad/s, sampled at `fs` Hz (PADS: 100 Hz).

Why these features (textbook signal processing, nothing exotic):
* Parkinsonian rest tremor is typically ~4-6 Hz; essential tremor often 4-12 Hz
  and more during posture/action. So we measure power in frequency BANDS and
  where the dominant tremor peak sits.
* Gravity (constant ~1 g) is removed with a high-pass filter so only movement remains.
* PD usually starts on ONE side, so left/right ASYMMETRY is computed by the caller
  (pads.py) from per-wrist features.
"""

from __future__ import annotations

import numpy as np
from scipy import signal

BANDS = {
    "low_1_3hz": (1.0, 3.5),
    "tremor_3_7hz": (3.5, 7.5),       # parkinsonian tremor range
    "high_7_12hz": (7.5, 12.0),       # essential / physiological tremor range
}


def _highpass(x: np.ndarray, fs: float, fc: float = 0.5) -> np.ndarray:
    b, a = signal.butter(2, fc / (fs / 2), btype="high")
    return signal.filtfilt(b, a, x, axis=0)


def _features_one(x: np.ndarray, fs: float, prefix: str) -> dict[str, float]:
    """Features for one 3-axis sensor."""
    x = np.asarray(x, float)
    x = _highpass(x - x.mean(axis=0), fs)
    mag = np.linalg.norm(x, axis=1)                       # orientation-independent
    # Use the axis-summed PSD so tremor along any axis counts.
    f, pxx = signal.welch(x, fs=fs, nperseg=min(256, len(x)), axis=0)
    p = pxx.sum(axis=1)
    band = (f >= 1.0) & (f <= 12.0)
    total = float(np.trapezoid(p[band], f[band])) + 1e-12
    out = {f"{prefix}_rms": float(np.sqrt(np.mean(mag ** 2)))}
    for name, (lo, hi) in BANDS.items():
        m = (f >= lo) & (f < hi)
        bp = float(np.trapezoid(p[m], f[m]))
        out[f"{prefix}_power_{name}"] = float(np.log10(bp + 1e-12))
        out[f"{prefix}_relpower_{name}"] = bp / total
    m = (f >= 3.0) & (f <= 12.0)
    k = int(np.argmax(p[m]))
    out[f"{prefix}_peak_freq"] = float(f[m][k])
    out[f"{prefix}_peak_prominence"] = float(p[m][k] / (np.median(p[band]) + 1e-12))
    pn = p[band] / (p[band].sum() + 1e-12)
    out[f"{prefix}_spectral_entropy"] = float(-(pn * np.log(pn + 1e-12)).sum() / np.log(len(pn)))
    jerk = np.diff(x, axis=0) * fs
    out[f"{prefix}_jerk_rms"] = float(np.sqrt(np.mean(np.sum(jerk ** 2, axis=1))))
    return out


def wrist_features(acc: np.ndarray | None, gyro: np.ndarray | None, fs: float = 100.0) -> dict[str, float]:
    out: dict[str, float] = {}
    if acc is not None:
        out.update(_features_one(acc, fs, "acc"))
    if gyro is not None:
        out.update(_features_one(gyro, fs, "gyro"))
    return out
