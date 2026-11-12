"""Simulate a full GLASSES recording: the eye_v2 protocol seen by a near-eye IR camera.

1. synthetic.simulate() produces a clean 1 kHz eye trajectory (saccades, pursuit,
   square-wave jerks) and blink times, with known ground truth.
2. Each camera frame is rendered (render.py) with the eye in that state, a slowly
   varying pupil size (+ a light-reflex constriction after optional flashes), and
   eyelids closing during blinks.
3. The real pupil detector tracks every frame (tracker.py), and the result goes
   through the SAME calibration / event / feature code as webcam recordings.

This lets us measure end-to-end accuracy of the glasses pipeline before hardware exists.
"""

from __future__ import annotations

import math

import numpy as np

from .. import synthetic
from ..recording import Recording
from .render import EyeCamera, EyeState, render
from .tracker import NearIRTracker


def simulate_ir(fps: float = 120.0, seed: int = 1, duration_s: float | None = None,
                pupil_mm: float = 4.0, noise: float = 5.0, camera: EyeCamera | None = None,
                protocol: str = "eye_v3", plr_amplitude_mm: float = 1.2, plr_latency_s: float = 0.24,
                plr_tau_constrict_s: float = 0.15, plr_tau_redilate_s: float = 0.8,
                **eye_kwargs) -> tuple[Recording, list[dict], dict]:
    from ..stimulus import PROTOCOLS
    cam = camera or EyeCamera()
    proto = PROTOCOLS[protocol](seed=seed)
    _, stim, truth = synthetic.simulate(fps=fps, seed=seed, return_trajectory=True, protocol=proto, **eye_kwargs)
    lights = [(e["t"], e["t"] + e["duration_s"]) for e in stim if e["kind"] == "light_on"]
    th, gx, gy = truth.pop("_trajectory")
    blinks = truth.pop("_blinks")
    rng = np.random.default_rng(seed + 1000)
    T = th[-1] if duration_s is None else min(duration_s, th[-1])
    ts = np.arange(0, T, 1 / fps)

    tracker = NearIRTracker()
    rows, true_pupil_px = [], []
    resp, dt = 0.0, 1 / fps            # light-reflex constriction state (mm)
    for t in ts:
        ex, ey = float(np.interp(t, th, gx)), float(np.interp(t, th, gy))
        # Pupil: slow "hippus" oscillation around the base size.
        # Light reflex: after a latency the pupil constricts quickly toward
        # -plr_amplitude_mm while the light is on, then re-dilates slowly.
        lit = any(a + plr_latency_s <= t < b + plr_latency_s for a, b in lights)
        target, tau = (plr_amplitude_mm, plr_tau_constrict_s) if lit else (0.0, plr_tau_redilate_s)
        resp += (target - resp) * (1 - math.exp(-dt / tau))
        pmm = pupil_mm + 0.25 * math.sin(2 * math.pi * 0.15 * t) - resp
        lid = 1.0
        for b0, dur in blinks:
            if b0 <= t < b0 + dur:           # triangular close-open profile
                ph = (t - b0) / dur
                lid = abs(2 * ph - 1)
        # Screen y is + downward; camera image y is + downward too.
        img, tr = render(cam, EyeState(ex, ey, pmm, lid), rng, noise=noise)
        ef = tracker.process(img, t)
        seg, tl = proto.at(t)
        target = seg.target(tl) if seg else (np.nan, np.nan)
        rows.append({
            "t": t, "frame_ok": 1.0, "h": ef.h, "v": ef.v, "gx": np.nan, "gy": np.nan,
            "ear": np.nan, "blink_score": ef.blink_score, "iris_px": np.nan,
            "yaw": np.nan, "pitch": np.nan, "roll": np.nan, "brightness": ef.brightness,
            "task": seg.task if seg else "", "target_x": target[0], "target_y": target[1],
            "pupil_px": ef.pupil_px, "pupil_conf": ef.pupil_conf,
        })
        true_pupil_px.append(tr["pupil_px"] if tr["visible_fraction"] > 0.5 else np.nan)

    stim = [e for e in stim if e["t"] < T]
    meta = {"source": "synthetic_nearir", "camera_type": "nearir", "fps_nominal": fps,
            "protocol": proto.name, "seed": seed, "stimulus_events": stim, "is_synthetic": True,
            "camera": {"width": cam.width, "height": cam.height, "px_per_mm": cam.px_per_mm},
            "illumination": "infrared_850nm", "mm_per_px": 1 / cam.px_per_mm}
    truth["pupil_px_median"] = float(np.nanmedian(true_pupil_px))
    truth["pupil_mm_median"] = float(np.nanmedian(true_pupil_px) / cam.px_per_mm)
    truth["plr_latency_ms"] = plr_latency_s * 1000
    truth["plr_amplitude_mm"] = plr_amplitude_mm * (1 - math.exp(-1.0 / plr_tau_constrict_s))   # 1 s flash
    truth["plr_max_velocity_mm_s"] = plr_amplitude_mm / plr_tau_constrict_s                    # first-order peak
    return Recording.from_rows(rows, meta), stim, truth
