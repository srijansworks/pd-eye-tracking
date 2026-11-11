"""Compute ocular measurements from a recording.

Every measurement is a dict in the shared measurement format
(docs/DATA_FORMAT.md):  name, value, unit, task, confidence, quality_flags, metadata.

`confidence` (0-1) is a HEURISTIC data-quality score built from: the share of
usable frames, how many events went into the number, and whether the frame
rate is high enough for that measurement. It is not a statistical
confidence interval and says nothing about clinical meaning.
"""

from __future__ import annotations

import math

import numpy as np

from . import events as ev
from .recording import Recording

# Frame rate needed before a measurement is considered properly sampled.
# Peak velocity needs >= 250 Hz (saccades last 20-80 ms); latency and durations
# are usable at >= 120 Hz (8 ms resolution); 30 Hz gives 33 ms resolution.
FPS_FOR_PEAK_VELOCITY = 250.0
FPS_FOR_TIMING = 120.0


def _m(name, value, unit, task, confidence, flags=(), **metadata) -> dict:
    return {
        "name": name, "value": float(value), "unit": unit, "task": task,
        "confidence": float(round(max(0.0, min(1.0, confidence)), 3)),
        "quality_flags": sorted(set(flags)), "metadata": metadata,
    }


def quality_summary(rec: Recording) -> dict:
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)   # all-NaN columns (e.g. no head pose on glasses)
        return _quality_summary(rec)


def _quality_summary(rec: Recording) -> dict:
    t = rec["t"]
    dt = np.diff(t) if len(t) > 1 else np.array([np.nan])
    ok = rec["frame_ok"] == 1
    med_dt = float(np.median(dt))
    q = {
        "n_frames": int(len(rec)),
        "duration_s": float(t[-1] - t[0]) if len(t) > 1 else 0.0,
        "valid_frame_fraction": float(ok.mean()) if len(ok) else 0.0,
        "effective_fps": float(1 / med_dt) if med_dt > 0 else float("nan"),
        "frame_interval_jitter_ms": float(np.std(dt) * 1000),
        "dropped_frame_count": int((dt > 1.5 * med_dt).sum()),
        "iris_diameter_px_median": float(np.nanmedian(rec["iris_px"][ok])) if ok.any() else float("nan"),
        "eye_brightness_median": float(np.nanmedian(rec["brightness"][ok])) if ok.any() else float("nan"),
        "head_yaw_sd_deg": float(np.nanstd(rec["yaw"][ok])) if ok.any() else float("nan"),
        "head_pitch_sd_deg": float(np.nanstd(rec["pitch"][ok])) if ok.any() else float("nan"),
    }
    flags = []
    if q["valid_frame_fraction"] < 0.8:
        flags.append("many_tracking_failures")
    if q["effective_fps"] < FPS_FOR_TIMING:
        flags.append("low_fps")
    if q["iris_diameter_px_median"] < 15:
        flags.append("low_eye_resolution")       # move closer / higher-res camera
    if q["eye_brightness_median"] < 50:
        flags.append("low_light")
    if max(q["head_yaw_sd_deg"], q["head_pitch_sd_deg"]) > 3:
        flags.append("head_movement")             # calibration assumes a still head
    if "calibration" in rec.meta:
        c = rec.meta["calibration"]
        q["calibration_rmse_deg"] = c["rmse_deg"]
        q["calibration_rmse_x_deg"] = c.get("rmse_x_deg", c["rmse_deg"])
        q["calibration_rmse_y_deg"] = c.get("rmse_y_deg", c["rmse_deg"])
        # The timed tasks are horizontal, so "poor_calibration" is judged on the
        # horizontal axis; a bad vertical axis only affects vertical measures.
        if q["calibration_rmse_x_deg"] > 1.5:
            flags.append("poor_calibration")
        if q["calibration_rmse_y_deg"] > 2.0:
            flags.append("poor_vertical_calibration")
    else:
        flags.append("uncalibrated")
    q["flags"] = flags
    return q


def compute(rec: Recording, stim_events: list[dict]) -> tuple[list[dict], dict]:
    """Return (measurements, quality_summary)."""
    q = quality_summary(rec)
    fps = q["effective_fps"]
    base_flags = [f for f in q["flags"] if f in ("low_eye_resolution", "low_light", "head_movement",
                                                 "poor_calibration", "uncalibrated")]
    valid = q["valid_frame_fraction"]
    t = rec["t"]

    cal = rec.calibrated
    x, y = (rec["gx"], rec["gy"]) if cal else (rec["h"], rec["v"])
    pos_u = "deg" if cal else "eye_width"
    vel_u = "deg/s" if cal else "eye_width/s"
    min_amp = 1.0 if cal else 0.007            # ~1 degree either way
    min_vel = 30.0 if cal else 0.0

    closed = ev.closed_eye_mask(rec["blink_score"], rec["ear"], rec["frame_ok"])
    # Exclude frames around blinks: lids distort the iris landmarks.
    pad = max(1, int(round(0.05 * fps))) if math.isfinite(fps) else 1
    near_blink = np.convolve(closed.astype(int), np.ones(2 * pad + 1), "same") > 0
    usable = (rec["frame_ok"] == 1) & ~near_blink & np.isfinite(x)

    # After calibration every eye_v1 target moves HORIZONTALLY only, so saccades
    # are detected on the horizontal channel. On real webcam data the vertical
    # channel is the weaker one (eyelids cover the iris top/bottom, and head
    # pitch changes leak into it), and it only added noise here.
    sacc = ev.detect_saccades(t, x, np.zeros_like(x), usable, min_amplitude=min_amp, min_velocity=min_vel)
    # Pursuit: the eye is always moving, so extending saccade ends or waiting for it
    # to "settle" makes no sense there; use plain threshold detection.
    sacc_pursuit = ev.detect_saccades(t, x, np.zeros_like(x), usable, min_amplitude=min_amp,
                                      min_velocity=min_vel, extend_tail=False)
    out: list[dict] = []

    # Head drift since calibration: the affine calibration is only valid for the
    # head pose it was fitted in. Flag tasks where the head turned/tilted > 3 deg.
    task_flags: dict[str, list[str]] = {}
    task_conf: dict[str, float] = {}
    okf = rec["frame_ok"] == 1
    tasks_arr = rec["task"]
    q["head_drift_deg"] = {}
    has_pose = bool(np.isfinite(rec["pitch"]).any())   # no head pose from a head-mounted camera
    for task in ("fixation", "prosaccade", "pursuit"):
        tm = rec.task_mask(task) & okf
        task_flags[task], task_conf[task] = [], 1.0
        if tm.sum() <= 10 or not has_pose:
            continue
        # Reference pose = the calibration/drift-check block right before each
        # stretch of this task (eye_v2 recalibrates before every task).
        drifts = []
        idx = np.where(rec.task_mask(task))[0]
        runs = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)
        for run in runs:
            prev = np.where((np.arange(len(rec)) < run[0]) & okf &
                            np.isin(tasks_arr, ["calibration", "drift_check"]))[0]
            if len(prev) < 10:
                continue
            # last contiguous calibration/drift-check block before this run
            blk = np.split(prev, np.where(np.diff(prev) > 1)[0] + 1)[-1]
            rm = np.zeros(len(rec), bool); rm[run] = True; rm &= okf
            if rm.sum() > 10:
                drifts.append(max(abs(np.nanmedian(rec[a][rm]) - np.nanmedian(rec[a][blk]))
                                  for a in ("yaw", "pitch")))
        if drifts:
            drift = max(drifts)
            q["head_drift_deg"][task] = round(float(drift), 2)
            if drift > 3.0:
                task_flags[task], task_conf[task] = ["head_moved_since_calibration"], 0.6
    if any(task_flags.values()) and "head_drift" not in q["flags"]:
        q["flags"].append("head_drift")
    timing_flags = ["low_temporal_resolution"] if fps < FPS_FOR_TIMING else []
    timing_factor = min(1.0, fps / FPS_FOR_TIMING)

    # ---- Blinks (whole recording) ------------------------------------
    blinks = ev.detect_blinks(t, closed)
    minutes = q["duration_s"] / 60
    if minutes > 0.25:
        out.append(_m("blink_rate", len(blinks) / minutes, "1/min", "all",
                      valid, base_flags, n_blinks=len(blinks)))
    if blinks:
        out.append(_m("blink_duration_mean", 1000 * np.mean([b.duration for b in blinks]), "ms", "all",
                      valid * timing_factor * min(1, len(blinks) / 5), base_flags + timing_flags,
                      n_blinks=len(blinks)))

    # ---- Fixation task: stability + intrusions ----------------------
    fm = rec.task_mask("fixation")
    if fm.sum() > 10:
        fu = usable & fm
        for s in sacc:
            fu[max(0, s.i_start - 1): s.i_end + 2] = False
        if fu.sum() > 10:
            fx, fy = x[fu], y[fu]
            sx, sy = np.std(fx), np.std(fy)
            rho = np.corrcoef(fx, fy)[0, 1] if sx > 0 and sy > 0 else 0.0
            # Bivariate contour ellipse area containing 68.2% of samples (Steinman 1965).
            k = -math.log(1 - 0.682)
            bcea = 2 * k * math.pi * sx * sy * math.sqrt(max(0.0, 1 - rho ** 2))
            frac = fu.sum() / fm.sum()
            out.append(_m("fixation_bcea_68", bcea, pos_u + "^2", "fixation", frac, base_flags,
                          n_samples=int(fu.sum()),
                          note="Webcam noise inflates this; compare only within the same setup."))
            out.append(_m("fixation_sd_x", sx, pos_u, "fixation", frac, base_flags))
            out.append(_m("fixation_sd_y", sy, pos_u, "fixation", frac, base_flags))
        fix_sacc = [s for s in sacc if fm[s.i_start]]
        dur = fm.sum() / fps if fps > 0 else 0
        if dur > 3:
            # Square-wave jerks: a small saccade away and one back, 100-500 ms apart.
            swj = sum(1 for a, b in zip(fix_sacc, fix_sacc[1:])
                      if 0.1 <= b.t_start - a.t_end <= 0.5 and a.dx * b.dx < 0
                      and 0.5 <= abs(b.dx) / max(abs(a.dx), 1e-9) <= 2.0)
            fl = base_flags + (["undersampled"] if fps < FPS_FOR_PEAK_VELOCITY else [])
            out.append(_m("intrusive_saccade_rate", len(fix_sacc) / dur, "1/s", "fixation",
                          valid * min(1, fps / FPS_FOR_PEAK_VELOCITY), fl, n=len(fix_sacc),
                          min_amplitude=min_amp))
            out.append(_m("square_wave_jerk_rate", swj / (dur / 60), "1/min", "fixation",
                          valid * min(1, fps / FPS_FOR_PEAK_VELOCITY), fl, n=swj,
                          note="Small (<1 deg) jerks are invisible at webcam noise levels."))
        fixes = ev.detect_fixations(t, x, y, usable & fm, sacc)
        if fixes:
            out.append(_m("fixation_duration_mean", 1000 * np.mean([f.duration for f in fixes]), "ms",
                          "fixation", valid * timing_factor, base_flags + timing_flags, n=len(fixes)))

    # ---- Prosaccade task: latency, gain, peak velocity ---------------
    trials = [e for e in stim_events if e["task"] == "prosaccade" and e["kind"] == "target_step"
              and e["x_deg"] != 0]
    lat, gain, amp, pv, errors, n_ok = [], [], [], [], 0, 0
    for e in trials:
        t0, sign, target_amp = e["t"], np.sign(e["x_deg"]), abs(e["x_deg"])
        win = [s for s in sacc if t0 + 0.08 <= s.t_start <= t0 + 0.7]
        if not win:
            continue
        first = win[0]
        # Horizontal direction in signal units: calibrated gx has the target's sign
        # convention; uncalibrated h is mirrored (subject's left = image right).
        moved = np.sign(first.dx) if cal else -np.sign(first.dx)
        if moved != sign:
            errors += 1
            continue
        n_ok += 1
        lat.append(first.t_start - t0)
        amp.append(first.amplitude)
        pv.append(first.peak_velocity)
        if cal:
            gain.append(abs(first.dx) / target_amp)
    if trials:
        cover = n_ok / len(trials)
        if lat:
            out.append(_m("saccade_latency_median", 1000 * np.median(lat), "ms", "prosaccade",
                          cover * timing_factor, base_flags + timing_flags, n_trials=n_ok,
                          resolution_ms=round(1000 / fps, 1),
                          note="Includes a constant camera/display delay; see docs."))
            if len(lat) > 2:
                out.append(_m("saccade_latency_sd", 1000 * np.std(lat, ddof=1), "ms", "prosaccade",
                              cover * timing_factor, base_flags + timing_flags, n_trials=n_ok))
            out.append(_m("saccade_amplitude_median", np.median(amp), pos_u, "prosaccade",
                          cover, base_flags, n_trials=n_ok))
            out.append(_m("saccade_peak_velocity_median", np.median(pv), vel_u, "prosaccade",
                          cover * min(1, fps / FPS_FOR_PEAK_VELOCITY),
                          base_flags + (["undersampled"] if fps < FPS_FOR_PEAK_VELOCITY else []),
                          n_trials=n_ok,
                          note="At < 250 fps this is a large UNDER-estimate of true peak velocity."))
        if gain:
            out.append(_m("saccade_gain_median", np.median(gain), "ratio", "prosaccade",
                          cover, base_flags, n_trials=len(gain)))
        out.append(_m("saccade_direction_error_rate", errors / len(trials), "ratio", "prosaccade",
                      valid, base_flags, n_trials=len(trials)))

    # ---- Pursuit task: gain, phase lag, catch-up saccades ------------
    starts = [e for e in stim_events if e["task"] == "pursuit" and e["kind"] == "pursuit_start"]
    pm = rec.task_mask("pursuit")
    if starts and pm.sum() > 30:
        e = starts[0]
        A, f = e["amplitude_deg"], e["freq_hz"]
        w = 2 * math.pi * f
        pu = usable & pm & (t >= e["t"] + 1.0)  # skip pursuit initiation
        for s in sacc_pursuit:
            pu[max(0, s.i_start - 1): s.i_end + 2] = False  # "desaccade"
        vx = ev.velocity(t, np.where(usable, x, np.nan))
        # Drop residual velocity spikes (missed saccade edges) — > 3x the target's peak speed.
        peak = A * w * (1.0 if cal else 0.0075)
        fit_m = pu & np.isfinite(vx) & (np.abs(vx) < 3 * peak)
        if fit_m.sum() > 30:
            tt = t[fit_m] - e["t"]
            # Least-squares fit of eye velocity to a sinusoid at the target frequency.
            # Fitting the whole curve averages out per-frame noise, which is why this
            # works even at 30 fps.
            M = np.column_stack([np.sin(w * tt), np.cos(w * tt), np.ones_like(tt)])
            (a, b, _c), *_ = np.linalg.lstsq(M, vx[fit_m], rcond=None)
            # Target velocity = A*w*cos(wt). Eye velocity = R*cos(wt - phi).
            R = math.hypot(a, b)
            phi = math.atan2(a, b)
            sign_ok = (b > 0) if cal else (b < 0)   # uncalibrated h is mirrored
            if not cal:
                phi = math.atan2(-a, -b)
            cover = fit_m.sum() / pm.sum()
            if cal:
                out.append(_m("pursuit_velocity_gain", R / (A * w), "ratio", "pursuit", cover,
                              base_flags + ([] if sign_ok else ["phase_inverted"]),
                              freq_hz=f, amplitude_deg=A, n_samples=int(fit_m.sum())))
            out.append(_m("pursuit_phase_lag", 1000 * phi / w, "ms", "pursuit", cover * timing_factor,
                          base_flags + timing_flags, freq_hz=f,
                          note="Below ~120 fps small catch-up saccades go undetected and bias "
                               "lag low / gain high (synthetic benchmark: 60 ms true -> ~30 ms at 30 fps)."))
        # Position gain: how much of the target's swing the eye covers, by ANY means
        # (smooth tracking + catch-up saccades). Sturdier at 30 fps than velocity
        # gain; a low velocity gain with a normal position gain = "saccadic pursuit".
        pp = usable & pm & (t >= e["t"] + 1.0)
        if cal and pp.sum() > 30:
            tt = t[pp] - e["t"]
            M = np.column_stack([np.sin(w * tt), np.cos(w * tt), np.ones_like(tt)])
            (a2, b2, _c2), *_ = np.linalg.lstsq(M, x[pp], rcond=None)
            out.append(_m("pursuit_position_gain", math.hypot(a2, b2) / A, "ratio", "pursuit",
                          pp.sum() / pm.sum(), base_flags, freq_hz=f, amplitude_deg=A))
        pur_sacc = [s for s in sacc_pursuit if pm[s.i_start]]
        pdur = pm.sum() / fps if fps > 0 else 0
        if pdur > 3:
            out.append(_m("pursuit_catchup_saccade_rate", len(pur_sacc) / pdur, "1/s", "pursuit",
                          valid * min(1, fps / FPS_FOR_PEAK_VELOCITY),
                          base_flags + (["undersampled"] if fps < FPS_FOR_PEAK_VELOCITY else []),
                          n=len(pur_sacc)))

    # ---- Quality measurements (so the backend can filter on them) ---
    out.append(_m("valid_frame_fraction", q["valid_frame_fraction"], "ratio", "all", 1.0))
    out.append(_m("effective_fps", fps, "Hz", "all", 1.0))
    if math.isfinite(q["iris_diameter_px_median"]):
        out.append(_m("iris_diameter_px", q["iris_diameter_px_median"], "px", "all", 1.0))
    if "calibration_rmse_deg" in q:
        out.append(_m("calibration_rmse", q["calibration_rmse_deg"], "deg", "calibration", 1.0))
        out.append(_m("calibration_rmse_x", q["calibration_rmse_x_deg"], "deg", "calibration", 1.0))
        out.append(_m("calibration_rmse_y", q["calibration_rmse_y_deg"], "deg", "calibration", 1.0))
        dcs = [d for d in rec.meta["calibration"].get("drift_checks", []) if d.get("scale_change") is not None]
        if dcs:
            # How much the eye-signal scale moved during the session. Large values =
            # posture drift that WOULD have biased gains without the drift checks.
            worst = max(dcs, key=lambda d: abs(d["scale_change"]))
            out.append(_m("calibration_scale_drift_max", worst["scale_change"], "ratio", "drift_check", 1.0,
                          n_checks=len(dcs), n_used=sum(1 for d in dcs if d.get("used"))))

    for m in out:
        if task_flags.get(m["task"]):
            m["quality_flags"] = sorted(set(m["quality_flags"]) | set(task_flags[m["task"]]))
            m["confidence"] = round(m["confidence"] * task_conf[m["task"]], 3)
        if m["name"] == "fixation_sd_y":
            m["quality_flags"] = sorted(set(m["quality_flags"]) | {"vertical_less_reliable"})
        if m["name"] in ("fixation_sd_y", "fixation_bcea_68") and "poor_vertical_calibration" in q["flags"]:
            m["quality_flags"] = sorted(set(m["quality_flags"]) | {"poor_vertical_calibration"})

    # ---- Pupil (near-eye IR camera only) ----------------------------
    pupil = rec["pupil_px"]
    if np.isfinite(pupil).sum() > 30:
        found = float(np.isfinite(pupil).mean())
        pv = pupil[np.isfinite(pupil) & ~near_blink]
        mmpp = rec.meta.get("mm_per_px")
        scale, unit = (mmpp, "mm") if mmpp else (1.0, "px")
        out.append(_m("pupil_found_fraction", found, "ratio", "all", 1.0))
        out.append(_m("pupil_diameter_median", float(np.median(pv)) * scale, unit, "all", found, base_flags,
                      note=None if mmpp else "Pixels; set meta mm_per_px from a camera calibration to get mm."))
        out.append(_m("pupil_diameter_cv", float(np.std(pv) / np.mean(pv)), "ratio", "all", found, base_flags,
                      note="Variability of pupil size over the recording (includes normal hippus)."))
        if "nearir" not in q["flags"]:
            q["flags"].append("nearir")
    else:
        q["unavailable"] = {
            "pupil_diameter": "Needs infrared imaging; RGB webcam cannot separate pupil from iris.",
        }
    q["n_saccades"] = len(sacc)
    q["n_blinks"] = len(blinks)
    return out, q
