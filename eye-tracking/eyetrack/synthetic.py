"""Synthetic eye-movement recordings with KNOWN ground truth.

Why: you cannot check whether a latency algorithm is right using real data
alone, because you don't know the true latency. Here we simulate an eye
doing the eye_v1 protocol at 1000 Hz using textbook properties, then sample
it like a camera would (any frame rate, any noise level) and compare what
the pipeline measures against what we put in.

Model details
* Saccade trajectory: minimum-jerk profile. Duration follows the "main
  sequence" D = 2.2*A + 21 ms (Carpenter 1988), so peak velocity = 1.875*A/D
  (~440 deg/s for 10 deg).
* Saccade latency ~ Normal(latency_ms, latency_sd_ms).
* Pursuit: smooth eye velocity = gain * target velocity delayed by lag, plus
  catch-up saccades whenever position error exceeds 1.5 deg.
* Blinks: Poisson process; during a blink the lid distorts the iris landmarks.
* Measurement noise: Gaussian, in degrees (webcam ~0.3-1 deg; IR lab tracker ~0.01-0.05).

All values are illustrative defaults, NOT Parkinson's or healthy norms.
"""

from __future__ import annotations

import math

import numpy as np

from .recording import Recording
from .stimulus import Protocol, eye_v1, eye_v2

K_H = 0.0075  # eye widths per degree, roughly realistic for MediaPipe h/v


def _minjerk(tau: float) -> float:
    tau = min(max(tau, 0.0), 1.0)
    return 10 * tau**3 - 15 * tau**4 + 6 * tau**5


def simulate(
    fps: float = 30.0,
    noise_deg: float = 0.4,
    latency_ms: float = 200.0,
    latency_sd_ms: float = 30.0,
    saccade_gain: float = 0.95,
    pursuit_gain: float = 0.85,
    pursuit_lag_ms: float = 60.0,
    blink_rate_per_min: float = 15.0,
    blink_duration_ms: float = 150.0,
    swj_count: int = 6,
    swj_amp_deg: float = 2.0,
    dropout: float = 0.01,
    jitter_ms: float = 1.0,
    scale_drift: float = 0.0,
    offset_drift_deg: float = 0.0,
    pitch_drift_deg: float = 0.0,
    smoothing_ms: float = 0.0,
    protocol: Protocol | None = None,
    seed: int = 1,
) -> tuple[Recording, list[dict], dict]:
    rng = np.random.default_rng(seed)
    proto = protocol or eye_v2(seed=seed)
    stim = proto.step_events()
    T = proto.duration
    dt = 0.001
    th = np.arange(0, T, dt)

    # --- schedule step-driven saccades ---------------------------------
    sched: list[tuple[float, float, float, str]] = []  # (start_t, x_target, y_target, kind)
    truth_lat, truth_pv = [], []
    for e in stim:
        if e["kind"] != "target_step" or e["task"] == "pursuit":
            continue
        lat = max(0.09, rng.normal(latency_ms, latency_sd_ms) / 1000)
        g = saccade_gain if e["task"] == "prosaccade" else 1.0
        sched.append((e["t"] + lat, e["x_deg"] * g, e["y_deg"] * g, e["task"]))
        if e["task"] == "prosaccade" and e["x_deg"] != 0:
            truth_lat.append(lat)
            A = abs(e["x_deg"] * g)
            truth_pv.append(1.875 * A / ((2.2 * A + 21) / 1000))
    # square-wave jerks during fixation: away then back after ~250 ms
    fix_seg_start = sum(s.duration for s in proto.segments[:1])
    for i in range(swj_count):
        t0 = fix_seg_start + 1.5 + i * (13.0 / max(1, swj_count))
        d = swj_amp_deg * (1 if i % 2 else -1)
        sched += [(t0, d, 0.0, "swj"), (t0 + 0.25, 0.0, 0.0, "swj")]
    sched.sort()

    # --- integrate the eye at 1 kHz -------------------------------------
    gx = np.zeros_like(th); gy = np.zeros_like(th)
    pos = np.zeros(2)
    active = None  # (t_start, from, to, dur)
    k = 0
    lag = pursuit_lag_ms / 1000
    n_catchup = 0
    for i, t in enumerate(th):
        seg, tl = proto.at(t)
        if active:
            t0, p0, p1, dur = active
            pos = p0 + (p1 - p0) * _minjerk((t - t0) / dur)
            if t - t0 >= dur:
                pos, active = p1.copy(), None
        else:
            if seg and seg.pursuit:
                A, f = seg.pursuit
                w = 2 * math.pi * f
                tv = A * w * math.cos(w * (tl - lag)) if tl > lag else 0.0
                pos[0] += pursuit_gain * tv * dt
                pos[1] = 0.0
                target = seg.target(tl)[0]
                err = target - pos[0]
                if abs(err) > 1.5 and tl > 0.3:
                    # catch-up saccade lands slightly ahead of the moving target
                    to = np.array([target + A * w * math.cos(w * tl) * 0.05, 0.0])
                    amp = abs(to[0] - pos[0])
                    active = (t, pos.copy(), to, (2.2 * amp + 21) / 1000)
                    n_catchup += 1
            while k < len(sched) and sched[k][0] <= t and active is None:
                _, x1, y1, _kind = sched[k]
                to = np.array([x1, y1])
                amp = float(np.linalg.norm(to - pos))
                if amp > 0.05:
                    active = (t, pos.copy(), to, (2.2 * amp + 21) / 1000)
                k += 1
        gx[i], gy[i] = pos

    # --- sample like a camera -------------------------------------------
    ts = np.arange(0, T, 1 / fps)
    jit = min(jitter_ms / 1000, 0.1 / fps)  # jitter can't exceed ~10% of a frame interval
    ts = np.clip(ts + rng.normal(0, jit, len(ts)), 0, T - dt)
    ts.sort()
    sx = np.interp(ts, th, gx) + rng.normal(0, noise_deg, len(ts))
    sy = np.interp(ts, th, gy) + rng.normal(0, noise_deg, len(ts))
    if smoothing_ms > 0:
        # Tracker-style temporal smoothing (first-order low-pass), as seen in real
        # MediaPipe webcam data: saccades "glide" into their landing point.
        alpha = 1 - np.exp(-(1 / fps) / (smoothing_ms / 1000))
        for arr in (sx, sy):
            for i in range(1, len(arr)):
                arr[i] = arr[i - 1] + alpha * (arr[i] - arr[i - 1])

    n = len(ts)
    blink_score = np.clip(rng.normal(0.05, 0.03, n), 0, 1)
    ear = rng.normal(0.28, 0.01, n)
    n_blinks = rng.poisson(blink_rate_per_min * T / 60)
    blink_starts = np.sort(rng.uniform(1, T - 1, n_blinks))
    real_blinks = 0
    last_end = -1.0
    for b0 in blink_starts:
        if b0 < last_end + 0.3:
            continue
        m = (ts >= b0) & (ts < b0 + blink_duration_ms / 1000)
        if not m.any():
            continue
        real_blinks += 1
        last_end = b0 + blink_duration_ms / 1000
        blink_score[m] = 0.9; ear[m] = 0.08
        sy[m] += rng.normal(3, 1, m.sum())     # lids pull the iris landmarks down
    frame_ok = (rng.random(n) > dropout).astype(float)

    # Posture drift (seen in real webcam recordings): the eye-signal scale and
    # offset change slowly over the session while the head tilts.
    frac = ts / T
    h = -K_H * (1 + scale_drift * frac) * sx + 0.01 - K_H * offset_drift_deg * frac + rng.normal(0, 1e-4, n)
    v = K_H * sy - 0.02
    h[frame_ok == 0] = np.nan; v[frame_ok == 0] = np.nan

    tasks, tx, ty = [], [], []
    for t in ts:
        seg, tl = proto.at(t)
        tasks.append(seg.task if seg else "")
        x_, y_ = seg.target(tl) if seg else (np.nan, np.nan)
        tx.append(x_); ty.append(y_)

    data = {
        "t": ts, "frame_ok": frame_ok, "h": h, "v": v,
        "gx": np.full(n, np.nan), "gy": np.full(n, np.nan),
        "ear": ear, "blink_score": blink_score, "iris_px": np.full(n, 25.0),
        "yaw": rng.normal(0, 0.5, n), "pitch": rng.normal(0, 0.5, n) + pitch_drift_deg * frac, "roll": rng.normal(0, 0.3, n),
        "brightness": np.full(n, 120.0),
        "task": np.array(tasks, dtype=object), "target_x": np.array(tx), "target_y": np.array(ty),
    }
    meta = {"source": "synthetic", "fps_nominal": fps, "protocol": proto.name, "seed": seed,
            "stimulus_events": stim, "is_synthetic": True}
    truth = {
        "latency_median_ms": float(np.median(truth_lat) * 1000),
        "latency_sd_ms": float(np.std(truth_lat, ddof=1) * 1000),
        "peak_velocity_median_deg_s": float(np.median(truth_pv)),
        "saccade_gain": saccade_gain,
        "pursuit_gain": pursuit_gain,
        "pursuit_lag_ms": pursuit_lag_ms,
        "n_blinks": real_blinks,
        "blink_duration_ms": blink_duration_ms,
        "swj_count": swj_count,
        "n_catchup": n_catchup,
    }
    return Recording(data, meta), stim, truth
