"""Map eye-in-head position (h, v) to gaze angle in degrees.

Raw h/v are "fractions of an eye width" — fine for timing (latency) but not
for amplitudes or velocities in degrees. During the calibration segment the
person looks at dots at known angles. We take the median h/v while fixating
each dot and fit a linear (affine) map:

    gx = a0 + a1*h + a2*v
    gy = b0 + b1*h + b2*v

Linear is a deliberate choice: with 6 points a quadratic would overfit. The
residual error at the calibration points (calibration_rmse_deg) is reported
so we know how trustworthy the degree values are. The head must stay still
after calibration — this method does not compensate for large head turns.
"""

from __future__ import annotations

import numpy as np

from .recording import Recording

SETTLE_S = 0.5  # ignore the first 0.5 s after each jump (reaction + saccade)


def fit(rec: Recording, events: list[dict]) -> dict | None:
    steps = [e for e in events if e["task"] == "calibration" and e["kind"] == "target_step"]
    if len(steps) < 4:
        return None
    t, h, v = rec["t"], rec["h"], rec["v"]
    usable = (rec["frame_ok"] == 1) & np.isfinite(h)
    if np.isfinite(rec["blink_score"]).any():
        usable &= ~(rec["blink_score"] > 0.4)

    H, V, X, Y = [], [], [], []
    for i, e in enumerate(steps):
        t_end = steps[i + 1]["t"] if i + 1 < len(steps) else e["t"] + 2.0
        m = usable & (t >= e["t"] + SETTLE_S) & (t < t_end)
        if m.sum() < 3:
            continue
        H.append(np.median(h[m])); V.append(np.median(v[m]))
        X.append(e["x_deg"]); Y.append(e["y_deg"])
    if len(H) < 4:
        return None

    A = np.column_stack([np.ones(len(H)), H, V])
    cx, *_ = np.linalg.lstsq(A, np.array(X), rcond=None)
    cy, *_ = np.linalg.lstsq(A, np.array(Y), rcond=None)
    pred = np.column_stack([A @ cx, A @ cy])
    err = np.hypot(pred[:, 0] - X, pred[:, 1] - Y)
    return {"method": "affine_v1", "coef_x": cx.tolist(), "coef_y": cy.tolist(),
            "n_points": len(H), "rmse_deg": float(np.sqrt(np.mean(err ** 2)))}


def apply(rec: Recording, cal: dict) -> None:
    cx, cy = np.array(cal["coef_x"]), np.array(cal["coef_y"])
    A = np.column_stack([np.ones(len(rec)), rec["h"], rec["v"]])
    rec.data["gx"] = A @ cx
    rec.data["gy"] = A @ cy
    rec.meta["calibration"] = cal
