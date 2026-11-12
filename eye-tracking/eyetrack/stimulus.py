"""The on-screen test protocol: where the target dot is at every moment.

Measuring saccade LATENCY requires knowing exactly when the target jumped,
and measuring pursuit GAIN requires knowing how fast the target moved. So
the pipeline drives its own stimulus and logs every target change.

Protocol "eye_v1" (~100 s):
  calibration  6 dots (centre, left, right, up, down, centre), 2 s each
  fixation     hold gaze on a centre dot for 15 s   -> fixation stability, intrusions
  prosaccade   centre -> random left/right jump, 20 trials -> latency, gain, velocity
  pursuit      dot moves sinusoidally, 0.4 Hz, 15 s  -> pursuit gain, lag, catch-up saccades
Blinks are measured throughout.

Protocol "eye_v2" (~115 s, the default) = eye_v1 + three 5-second DRIFT CHECKS
(centre, left, right) before the prosaccade task, halfway through it, and
before pursuit. Webcam eye tracking drifts as people shift posture; each task
is then scored with the calibration measured just before it.

Positions are in degrees of visual angle, converted to screen pixels from
the viewing distance and physical screen width you supply.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Segment:
    task: str
    duration: float
    steps: list[tuple[float, float, float]] = field(default_factory=list)  # (t_local, x_deg, y_deg)
    pursuit: tuple[float, float] | None = None  # (amplitude_deg, freq_hz) for sinusoidal motion
    flashes: list[tuple[float, float]] = field(default_factory=list)  # (t_on, duration): white screen

    def light(self, t_local: float) -> bool:
        return any(t0 <= t_local < t0 + d for t0, d in self.flashes)

    def target(self, t_local: float) -> tuple[float, float]:
        if self.pursuit:
            amp, f = self.pursuit
            return amp * math.sin(2 * math.pi * f * t_local), 0.0
        x, y = 0.0, 0.0
        for ts, sx, sy in self.steps:
            if t_local >= ts:
                x, y = sx, sy
            else:
                break
        return x, y


@dataclass
class Protocol:
    name: str
    segments: list[Segment]

    @property
    def duration(self) -> float:
        return sum(s.duration for s in self.segments)

    def at(self, t: float) -> tuple[Segment | None, float]:
        """Active segment and time inside it for protocol time t."""
        start = 0.0
        for s in self.segments:
            if t < start + s.duration:
                return s, t - start
            start += s.duration
        return None, 0.0

    def step_events(self) -> list[dict]:
        """Every discrete target change, in protocol time."""
        out, start = [], 0.0
        for s in self.segments:
            prev = None
            for ts, x, y in s.steps:
                out.append({"t": start + ts, "task": s.task, "kind": "target_step",
                            "x_deg": x, "y_deg": y,
                            "from_x_deg": prev[0] if prev else None,
                            "from_y_deg": prev[1] if prev else None})
                prev = (x, y)
            if s.pursuit:
                out.append({"t": start, "task": s.task, "kind": "pursuit_start",
                            "amplitude_deg": s.pursuit[0], "freq_hz": s.pursuit[1]})
            for t0, d in s.flashes:
                out.append({"t": start + t0, "task": s.task, "kind": "light_on", "duration_s": d})
                out.append({"t": start + t0 + d, "task": s.task, "kind": "light_off"})
            start += s.duration
        return out


def eye_v1(amp_x: float = 10.0, amp_y: float = 7.0, n_trials: int = 20, seed: int = 0) -> Protocol:
    rng = random.Random(seed)
    cal_pts = [(0, 0), (-amp_x, 0), (amp_x, 0), (0, -amp_y), (0, amp_y), (0, 0)]
    calibration = Segment("calibration", 2.0 * len(cal_pts),
                          [(2.0 * i, x, y) for i, (x, y) in enumerate(cal_pts)])
    fixation = Segment("fixation", 15.0, [(0.0, 0.0, 0.0)])

    steps, t = [], 0.0
    for _ in range(n_trials):
        steps.append((t, 0.0, 0.0))
        t += rng.uniform(1.0, 2.0)          # random foreperiod so onsets can't be anticipated
        steps.append((t, rng.choice([-amp_x, amp_x]), 0.0))
        t += 1.2
    prosaccade = Segment("prosaccade", t, steps)

    pursuit = Segment("pursuit", 15.0, pursuit=(amp_x, 0.4))
    return Protocol("eye_v1", [calibration, fixation, prosaccade, pursuit])


@dataclass
class ScreenGeometry:
    width_px: int
    height_px: int
    width_cm: float
    distance_cm: float

    @property
    def px_per_cm(self) -> float:
        return self.width_px / self.width_cm

    def deg_to_px(self, x_deg: float, y_deg: float) -> tuple[int, int]:
        cx, cy = self.width_px / 2, self.height_px / 2
        x = cx + math.tan(math.radians(x_deg)) * self.distance_cm * self.px_per_cm
        y = cy + math.tan(math.radians(y_deg)) * self.distance_cm * self.px_per_cm
        return int(round(x)), int(round(y))

    def max_deg(self) -> tuple[float, float]:
        half_w = self.width_cm / 2
        half_h = half_w * self.height_px / self.width_px
        return (math.degrees(math.atan(half_w / self.distance_cm)),
                math.degrees(math.atan(half_h / self.distance_cm)))


def render(geom: ScreenGeometry, x_deg: float | None, y_deg: float | None, text: str = "",
           text_color: tuple[int, int, int] = (160, 160, 160), light: bool = False) -> np.ndarray:
    import cv2

    img = np.full((geom.height_px, geom.width_px, 3), 255 if light else 0, np.uint8)
    if x_deg is not None:
        x, y = geom.deg_to_px(x_deg, y_deg)
        r = max(6, int(0.3 * geom.px_per_cm))       # ~0.6 cm dot
        dot, mark = ((0, 0, 0), (255, 255, 255)) if light else ((255, 255, 255), (0, 0, 0))
        cv2.circle(img, (x, y), r, dot, -1)
        cv2.circle(img, (x, y), max(2, r // 4), mark, -1)  # centre mark helps precise fixation
    if text:
        cv2.putText(img, text, (30, geom.height_px - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, text_color, 2)
    return img


def _drift_check(amp_x: float) -> Segment:
    pts = [(0.0, 0.0), (-amp_x, 0.0), (amp_x, 0.0)]
    return Segment("drift_check", 1.6 * len(pts), [(1.6 * i, x, y) for i, (x, y) in enumerate(pts)])


def eye_v2(amp_x: float = 10.0, amp_y: float = 7.0, n_trials: int = 20, seed: int = 0) -> Protocol:
    v1 = eye_v1(amp_x, amp_y, n_trials, seed)
    calibration, fixation, prosaccade, pursuit = v1.segments
    # Split the prosaccade trials in two halves with a drift check between them.
    half = n_trials // 2
    steps = prosaccade.steps
    cut_t = steps[2 * half][0]           # start time of trial `half`
    first = Segment("prosaccade", cut_t, steps[:2 * half])
    second = Segment("prosaccade", prosaccade.duration - cut_t,
                     [(ts - cut_t, x, y) for ts, x, y in steps[2 * half:]])
    return Protocol("eye_v2", [calibration, fixation, _drift_check(amp_x), first,
                               _drift_check(amp_x), second, _drift_check(amp_x), pursuit])


def eye_v3(amp_x: float = 10.0, amp_y: float = 7.0, n_trials: int = 20, seed: int = 0) -> Protocol:
    """eye_v2 + a PUPILLARY LIGHT REFLEX block (needs the near-eye IR camera to measure).
    The screen turns white for 1 s, three times, 4 s apart, while the person looks at the centre dot."""
    v2 = eye_v2(amp_x, amp_y, n_trials, seed)
    plr = Segment("plr", 14.0, [(0.0, 0.0, 0.0)], flashes=[(3.0, 1.0), (7.5, 1.0), (12.0, 1.0)])
    return Protocol("eye_v3", v2.segments + [plr])


PROTOCOLS = {"eye_v1": eye_v1, "eye_v2": eye_v2, "eye_v3": eye_v3}
