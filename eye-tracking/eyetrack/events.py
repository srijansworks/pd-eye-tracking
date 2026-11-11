"""Turn a gaze time series into eye-movement EVENTS: blinks, saccades, fixations.

Saccade detection uses the adaptive velocity threshold of Engbert & Kliegl
(2003, Vision Research 43:1035): the threshold is lambda x the median-based
noise level of the velocity signal, so it adapts to how noisy each
recording is instead of using one fixed deg/s number.

Important limitation at webcam frame rates: a 10 deg saccade lasts ~40 ms,
which is only 1-2 frames at 30 fps. We can tell THAT a saccade happened,
WHEN (to within one frame) and HOW FAR the eye moved (comparing the frames
before and after), but not its true peak velocity. tests/test_events.py
quantifies this with synthetic data.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class Blink:
    t_start: float
    t_end: float
    duration: float


@dataclass
class Saccade:
    i_start: int
    i_end: int
    t_start: float
    t_end: float
    dx: float          # displacement (signal units), end - start
    dy: float
    amplitude: float
    peak_velocity: float


@dataclass
class Fixation:
    t_start: float
    t_end: float
    duration: float
    x: float
    y: float


def _runs(mask: np.ndarray) -> list[tuple[int, int]]:
    """(start, end_inclusive) index pairs of consecutive True values."""
    if not mask.any():
        return []
    d = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0] - 1
    return list(zip(starts, ends))


def closed_eye_mask(blink_score: np.ndarray, ear: np.ndarray, frame_ok: np.ndarray) -> np.ndarray:
    """Frames where the eyes are closed: the blink blendshape > 0.5, OR the
    eye aspect ratio drops below 70% of its own rolling ~1 s median.

    Why a rolling baseline: EAR also changes with gaze direction (looking
    down narrows the lids), so a single whole-recording median can mistake
    looking down for a blink, or miss blinks while looking up."""
    ok = frame_ok == 1
    closed = np.zeros(len(ok), bool)
    if np.isfinite(blink_score[ok]).any():
        closed |= ok & (blink_score > 0.5)
    if np.isfinite(ear[ok]).sum() > 5:
        e = np.where(ok, ear, np.nan)
        w = 31  # ~1 s at 30 fps; long enough that a blink doesn't drag the median down
        pad = np.pad(e, (w // 2, w // 2), mode="edge")
        from numpy.lib.stride_tricks import sliding_window_view
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                base = np.nanmedian(sliding_window_view(pad, w), axis=1)
        closed |= ok & (ear < 0.7 * base)
    return closed


def ear_dip_depth(ear: np.ndarray, frame_ok: np.ndarray) -> float:
    """Deepest EAR dip relative to its rolling median (1.0 = never dipped).
    Used by the camera check to confirm blinks are visible to the tracker."""
    ok = frame_ok == 1
    if np.isfinite(ear[ok]).sum() < 10:
        return float("nan")
    e = np.where(ok, ear, np.nan)
    w = 31
    pad = np.pad(e, (w // 2, w // 2), mode="edge")
    from numpy.lib.stride_tricks import sliding_window_view
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        base = np.nanmedian(sliding_window_view(pad, w), axis=1)
        return float(np.nanmin(e / base))


def detect_blinks(t: np.ndarray, closed: np.ndarray, max_blink_s: float = 0.5,
                  bridge_s: float = 0.04) -> list[Blink]:
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.0
    runs = _runs(closed)
    # A single dropped/misdetected frame in the middle of a blink would split it
    # into two short "blinks". Merge runs separated by a gap shorter than bridge_s.
    merged: list[list[int]] = []
    for a, b in runs:
        if merged and t[a] - t[merged[-1][1]] <= bridge_s + dt:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    out = []
    for a, b in merged:
        dur = (t[b] - t[a]) + dt  # frame-count based: resolution = 1 frame
        if dur <= max_blink_s:
            out.append(Blink(float(t[a]), float(t[b] + dt), float(dur)))
    return out


def velocity(t: np.ndarray, x: np.ndarray) -> np.ndarray:
    """Velocity of x in units per second.

    Below 100 fps: plain central difference (each frame matters; smoothing
    would smear 1-2 frame saccades away). At >= 100 fps: the 5-point
    moving-average differentiator of Engbert & Kliegl (2003), which
    suppresses the extra noise that comes with tiny frame intervals.
    NaNs (gaps, blinks) propagate to neighbouring velocity samples.
    """
    n = len(t)
    if n < 5:
        return np.full_like(x, np.nan, dtype=float)
    dt = float(np.median(np.diff(t)))
    if 1.0 / dt < 100:
        return np.gradient(x, t)
    v = np.full(n, np.nan)
    v[2:-2] = (x[4:] + x[3:-1] - x[1:-3] - x[:-4]) / (6 * dt)
    return v


def detect_saccades(
    t: np.ndarray, x: np.ndarray, y: np.ndarray, usable: np.ndarray,
    lam: float = 6.0, min_amplitude: float = 0.0, min_velocity: float = 0.0,
    extend_tail: bool = True, settle_s: float = 0.25,
) -> list[Saccade]:
    x = np.where(usable, x, np.nan)
    y = np.where(usable, y, np.nan)
    vx, vy = velocity(t, x), velocity(t, y)
    finite = np.isfinite(vx) & np.isfinite(vy)
    if finite.sum() < 10:
        return []

    def sigma(v):
        s = np.sqrt(np.median(v ** 2) - np.median(v) ** 2)
        return max(s, 1e-9)

    ex, ey = lam * sigma(vx[finite]), lam * sigma(vy[finite])
    speed = np.hypot(vx, vy)
    above = finite & (((vx / ex) ** 2 + (vy / ey) ** 2) > 1.0) & (speed >= min_velocity)

    # Offset extension: real webcam data (MediaPipe landmark smoothing + motion
    # blur) shows each saccade "gliding" into its landing point over 100-200 ms.
    # Ending the saccade at the detection threshold cut off ~25% of its size
    # (first real recording: gain 0.76 vs settled 0.94). So after detection we
    # keep extending the end while the eye still moves the same way faster than
    # a low threshold (20% of the detection threshold), for at most 200 ms.
    end_thr = 0.2 * max(ex, ey)
    dt_med = float(np.median(np.diff(t))) if len(t) > 1 else 0.0
    max_ext = int(round(0.2 / dt_med)) if dt_med > 0 else 0

    out = []
    last_end = -1
    runs = _runs(above)
    for k, (a, b) in enumerate(runs):
        if a <= last_end:
            continue  # already swallowed by the previous saccade's extended tail
        dvx, dvy = np.nansum(vx[a:b + 1]), np.nansum(vy[a:b + 1])
        norm = float(np.hypot(dvx, dvy)) or 1.0
        ux, uy = dvx / norm, dvy / norm
        b_detect = b  # end before tail extension (used for the gap check below)
        ext = 0
        while (extend_tail and ext < max_ext and b + 1 < len(x) and np.isfinite(vx[b + 1]) and np.isfinite(vy[b + 1])
               and (vx[b + 1] * ux + vy[b + 1] * uy) > end_thr):
            b += 1
            ext += 1
        last_end = b
        # Displacement: compare the last usable sample BEFORE the event with
        # the first usable sample AFTER it. With 1-2 frame saccades this
        # captures the whole movement.
        i0, i1 = a - 1, b + 1
        while i0 >= 0 and not np.isfinite(x[i0]):
            i0 -= 1
        while i1 < len(x) and not np.isfinite(x[i1]):
            i1 += 1
        if i0 < 0 or i1 >= len(x):
            continue
        # Movement hidden by a gap/blink -> can't measure it. Judge this on the
        # detected part only: the extended tail is allowed to be long.
        j = b_detect + 1
        while j < len(x) and not np.isfinite(x[j]):
            j += 1
        if j >= len(x) or (t[j] - t[i0]) > 0.25:
            continue
        x1, y1 = x[i1], y[i1]
        if extend_tail and settle_s > 0 and dt_med > 0:
            # Landing point = where the eye SETTLES: median of the last third of
            # the next `settle_s` seconds, stopping before the next saccade (so a
            # corrective saccade is not counted). Tracker smoothing (~75 ms in
            # real MediaPipe data) has mostly decayed by then.
            nxt = next((ra for ra, _ in runs[k + 1:] if ra > b), len(x))
            j_end = min(b + int(round(settle_s / dt_med)), nxt - 1, len(x) - 1)
            seg = np.arange(b + 1, j_end + 1)
            if len(seg) >= 3:
                tail = seg[len(seg) * 2 // 3:]
                if np.isfinite(x[tail]).sum() >= 1:
                    x1, y1 = np.nanmedian(x[tail]), np.nanmedian(y[tail])
        dx, dy = float(x1 - x[i0]), float(y1 - y[i0])
        amp = float(np.hypot(dx, dy))
        if amp < min_amplitude:
            continue
        out.append(Saccade(int(a), int(b), float(t[a]), float(t[b]), dx, dy, amp,
                           float(np.nanmax(speed[a:b + 1]))))
    return out


def detect_fixations(
    t: np.ndarray, x: np.ndarray, y: np.ndarray, usable: np.ndarray,
    saccades: list[Saccade], min_duration: float = 0.1,
) -> list[Fixation]:
    """Fixation = usable stretch between saccades lasting >= min_duration."""
    free = usable.copy()
    for s in saccades:
        free[max(0, s.i_start - 1): s.i_end + 2] = False
    dt = float(np.median(np.diff(t))) if len(t) > 1 else 0.0
    out = []
    for a, b in _runs(free):
        dur = t[b] - t[a] + dt
        if dur >= min_duration:
            out.append(Fixation(float(t[a]), float(t[b] + dt), float(dur),
                                float(np.nanmedian(x[a:b + 1])), float(np.nanmedian(y[a:b + 1]))))
    return out
