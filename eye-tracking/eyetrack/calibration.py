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
    # Per-axis error matters: webcam vertical tracking is much worse than
    # horizontal (eyelids), and the timed tasks only use the horizontal axis.
    cal = {"method": "affine_v1", "coef_x": cx.tolist(), "coef_y": cy.tolist(),
           "n_points": len(H), "rmse_deg": float(np.sqrt(np.mean(err ** 2))),
           "rmse_x_deg": float(np.sqrt(np.mean((pred[:, 0] - X) ** 2))),
           "rmse_y_deg": float(np.sqrt(np.mean((pred[:, 1] - Y) ** 2)))}
    cal["drift_checks"] = _fit_drift_checks(rec, events, usable, cx)
    return cal


def _fit_drift_checks(rec: Recording, events: list[dict], usable: np.ndarray, cx: np.ndarray) -> list[dict]:
    """Re-fit the HORIZONTAL mapping at each drift check (protocol eye_v2).

    A drift check shows 3 dots (centre, left, right). With only horizontal
    dots we refit the offset and scale (gx = a + b*h + c*v) and keep the
    vertical-crosstalk term c from the full calibration. Webcam posture drift
    changes mostly the offset and scale, so this is what needs refreshing.
    """
    steps = [e for e in events if e["task"] == "drift_check" and e["kind"] == "target_step"]
    if not steps:
        return []
    blocks, cur = [], [steps[0]]
    for e in steps[1:]:
        if e["t"] - cur[-1]["t"] < 2.5:   # dots 1.6 s apart = same block
            cur.append(e)
        else:
            blocks.append(cur)
            cur = [e]
    blocks.append(cur)

    t, h, v = rec["t"], rec["h"], rec["v"]
    out = []
    for blk in blocks:
        Hs, Vs, Xs = [], [], []
        for i, e in enumerate(blk):
            t_end = blk[i + 1]["t"] if i + 1 < len(blk) else e["t"] + 1.6
            m = usable & (t >= e["t"] + SETTLE_S) & (t < t_end)
            if m.sum() >= 3:
                Hs.append(np.median(h[m])); Vs.append(np.median(v[m])); Xs.append(e["x_deg"])
        rec_ = {"t_start": float(blk[0]["t"]), "n_points": len(Hs), "used": False}
        if len(Hs) >= 3 and len(set(Xs)) >= 2:
            Hs, Vs, Xs = map(np.array, (Hs, Vs, Xs))
            M = np.column_stack([np.ones(len(Hs)), Hs])
            (a, b), *_ = np.linalg.lstsq(M, Xs - cx[2] * Vs, rcond=None)
            rmse = float(np.sqrt(np.mean((M @ [a, b] + cx[2] * Vs - Xs) ** 2)))
            rec_.update({"coef_x": [float(a), float(b), float(cx[2])], "rmse_x_deg": rmse,
                         # Reported as change in eye-SIGNAL size: -0.2 = the same dot
                         # now moves the iris 20% less than at calibration.
                         "scale_change": float(cx[1] / b - 1) if b else None})
            # Use it only if it fits well and the scale is sane (guards against a
            # drift check where the person blinked or looked away).
            rec_["used"] = bool(rmse < 2.0 and b and cx[1] and abs(cx[1] / b - 1) < 0.5)
        out.append(rec_)
    return out


def apply(rec: Recording, cal: dict) -> None:
    cx, cy = np.array(cal["coef_x"]), np.array(cal["coef_y"])
    A = np.column_stack([np.ones(len(rec)), rec["h"], rec["v"]])
    gx = A @ cx
    # Piecewise: from each accepted drift check onwards, use its horizontal mapping.
    for d in cal.get("drift_checks", []):
        if d.get("used"):
            m = rec["t"] >= d["t_start"]
            gx[m] = A[m] @ np.array(d["coef_x"])
    rec.data["gx"] = gx
    rec.data["gy"] = A @ cy
    rec.meta["calibration"] = cal
