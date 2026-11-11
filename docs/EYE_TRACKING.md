# Eye-tracking subsystem

Research prototype. **Not clinically validated; it does not detect Parkinson's disease.**

## Pipeline

```
camera.py ──frames+timestamps──▶ landmarks.py (MediaPipe: face, eye corners, lids, iris, head pose)
                                      │  per-frame: h, v, EAR, blink score, iris px, yaw/pitch/roll, brightness
stimulus.py (dot on screen) ──target positions + actual onset times──┐
                                      ▼                               ▼
                               recording.py  (samples.csv + meta.json — derived numbers only, no video)
                                      ▼
                         calibration.py (6 dots → affine map h,v → degrees, reports RMSE)
                                      ▼
                     events.py (blinks, saccades [Engbert–Kliegl adaptive threshold], fixations)
                                      ▼
                  features.py (task-specific measurements + confidence + quality flags)
                                      ▼
          export.py (measurements.json in shared batch format, CSV) → plot.py (plot.png) → upload.py (API)
```

The suggested module list (`face_detection.py`, `eye_detection.py`, `pupil_tracking.py`,
`gaze_estimation.py`) collapsed into `landmarks.py` + `calibration.py`. MediaPipe finds the face,
eyes and iris in **one** model call, so separate modules would only pass data around.
`synthetic.py` simulates eyes with known ground truth so we can test the measurement code.

### Key idea: eye-in-head position
`h, v` = iris centre relative to the midpoint of the two eye corners, divided by eye width.
Eye corners move with the head, not the eyeball, so this cancels head translation, distance to
camera and head roll (unit-tested in `test_eye_in_head_*`). It does **not** cancel large head
turns, so the protocol asks for a still head and flags `head_movement`.

## Protocol `eye_v2` (~111 s, default)
| Segment | What the dot does | Measurements |
|---|---|---|
| calibration (12 s) | centre, ±10° horizontal, ±7° vertical, centre | calibration map, `calibration_rmse` / `_x` / `_y` |
| fixation (15 s) | stays at centre | `fixation_bcea_68`, `fixation_sd_x/y`, `intrusive_saccade_rate`, `square_wave_jerk_rate` |
| **drift check** (4.8 s) | centre, left, right | re-fits horizontal offset + scale → `calibration_scale_drift_max` |
| prosaccade, trials 1–10 | centre → random ±10° after a random 1–2 s wait | `saccade_latency_median/sd`, `saccade_gain_median`, `saccade_amplitude_median`, `saccade_peak_velocity_median`, `saccade_direction_error_rate` |
| **drift check** (4.8 s) | centre, left, right | |
| prosaccade, trials 11–20 | same | |
| **drift check** (4.8 s) | centre, left, right | |
| pursuit (15 s) | 0.4 Hz sinusoid, ±10° | `pursuit_velocity_gain`, `pursuit_position_gain`, `pursuit_phase_lag`, `pursuit_catchup_saccade_rate` |
| whole recording | — | `blink_rate`, `blink_duration_mean`, `valid_frame_fraction`, `effective_fps`, `iris_diameter_px` |

**Why drift checks:** people slowly change posture during a test. In our first real recordings the head
tilted back 7–14° over 90 s and the eye-signal scale changed by up to 19%, which biased saccade gain low
(0.84 → 0.72 across sessions). Each task is now scored with the calibration taken just before it. In the
synthetic test with the same drift, saccade gain reads 0.83 without drift checks and 0.95 with them (truth 0.95).
A **live posture warning** also appears on screen if the head moves > 4° from its pose at the last
calibration, and the moment is logged as a `posture_warning_start` event.

The original `eye_v1` protocol (no drift checks) is kept for comparison.

Stimulus onset times are logged when each frame **reaches the screen**, not when it was scheduled.

## How good is it? Synthetic benchmark
`eyetrack benchmark` simulates 5 participants per setup (textbook saccade main sequence, pursuit
with lag, blinks, square-wave jerks, measurement noise), samples them like each camera would, and
compares the measured values with the true ones (`docs/benchmark_output.txt`):

| measured / true | webcam 30 fps | webcam 60 fps | IR 120 fps | IR 250 fps | lab 500 fps |
|---|---|---|---|---|---|
| saccade latency (ms) | 195 / 194 | 202 / 194 | 193 / 194 | 198 / 194 | 197 / 194 |
| **saccade peak velocity (°/s)** | **145 / 425** | 262 / 425 | 308 / 425 | 387 / 425 | 422 / 425 |
| saccade gain | 0.98 / 0.95 | 0.96 / 0.95 | 0.95 / 0.95 | 0.95 / 0.95 | 0.95 / 0.95 |
| pursuit velocity gain | 0.90 / 0.85 | 0.91 / 0.85 | 0.84 / 0.85 | 0.85 / 0.85 | 0.85 / 0.85 |
| pursuit phase lag (ms) | 29 / 60 | 36 / 60 | 59 / 60 | 59 / 60 | 59 / 60 |
| blink duration (ms) | 152 / 150 | 150 / 150 | 150 / 150 | 149 / 150 | 150 / 150 |
| **square-wave jerks (/min)** | **0 / 28** | 0 / 28 | 22 / 28 | 19 / 28 | 20 / 28 |

How to read this:
* A 30 fps webcam is fine for **latency (median), saccade gain, pursuit gain, blinks**.
* **Peak velocity needs ≥ 250 fps.** At 30 fps it reads about a third of the true value, so it is flagged `undersampled` with confidence ≈ 0.1.
* **Small intrusions (square-wave jerks) need ≥ 120 fps and low noise.**
* Pursuit lag is biased below about 120 fps, because small catch-up saccades are missed.
* This is the **best case**: synthetic data lacks MediaPipe's own temporal smoothing, camera
  latency, lighting changes and head motion. Real accuracy has to be checked against a reference
  tracker or a test with known stimuli.

## First real recordings (Srijan, laptop webcam, 2026-11-11, protocol eye_v1)
Not clinical values; one healthy person, three runs on the same day.

| | Rec 1 | Rec 2 | Rec 3 |
|---|---|---|---|
| valid frames / fps / iris size | 100% / 29.5 / 32 px | 100% / 29.4 / 30 px | 100% / 29.4 / 34 px |
| calibration error x / y (°) | 0.65 / 1.44 | 0.91 / 2.85 | 0.83 / 0.57 |
| head pitch change over the run | +7° | +14° | +11° |
| saccade latency (median) | 229 ms | 234 ms | 245 ms |
| saccade gain | 0.84 | 0.79 | 0.72 |
| pursuit position gain | 0.93 | 0.78 | 0.70 |
| blinks detected | 0 | 6 | 4 |

Run 4 (protocol **eye_v2** with drift checks, after the smoothing fix): no head-drift flags,
calibration error x 0.32°, eye-signal scale drift −2%, saccade latency 231 ms, **saccade gain 0.92**,
pursuit position gain 0.86, 0 direction errors in 20 trials.

What we learned and fixed:
* **Latency repeats** within ~15 ms; **gains drifted** with posture → drift checks + posture warning (eye_v2).
* The **vertical** channel is much worse than horizontal on a webcam → timed tasks use horizontal only;
  calibration error is reported per axis.
* Low pursuit *velocity* gain with good *position* gain = catch-up-saccade-driven ("saccadic") pursuit →
  added `pursuit_position_gain`.
* Blinks are detectable (EAR dips to ~0.2 of baseline); zero blinks in recording 1 was real blink suppression
  during a demanding visual task (`check-camera` now includes a blink self-test).
* A head-mounted camera (the hardware team's glasses) removes the posture problem at its source.

## Known limitations (be honest about these in the Conrad write-up)
1. **No pupil diameter** with an RGB webcam. Needs IR (phase 2).
2. **Absolute latency includes camera + display delay** (typically tens of ms, constant per setup).
   Compare latencies only within the same hardware, or measure the delay (film the screen and
   your eye with a 240 fps phone camera).
3. **Tracker smoothing (measured):** in real recordings each saccade glides into its landing point over
   ~150 ms (about 75 ms of first-order smoothing from MediaPipe + motion blur). Ending a saccade at the
   speed threshold under-read gain (0.76 vs 0.94 settled), so saccade amplitude is now taken at the
   **settled landing point** (≤ 250 ms after the saccade, stopping before any corrective saccade).
   Synthetic check with 75 ms smoothing: gain 0.93 (true 0.95). Remaining effects of smoothing:
   latency reads ~15 ms late (constant per setup) and pursuit velocity gain reads slightly high.
4. Calibration is linear and assumes a still head. Glasses, heavy eye makeup, drooping lids or
   very dark rooms reduce tracking quality (shown in `valid_frame_fraction` and the flags).
5. `confidence` is a heuristic data-quality score, not a statistical interval.

## Hardware
| Stage | Camera | What it unlocks |
|---|---|---|
| Now | Built-in laptop webcam (30 fps, ≥ 720p), lamp in front, chin on hands or a chin rest, ~50 cm | latency, gain, pursuit gain, blinks |
| **Phase 2 (recommended)** | Monochrome **global-shutter USB camera at ≥ 120 fps** (e.g. OV9281-sensor boards), **850 nm IR LED** illumination, IR-pass filter, **chin rest**, close-up on one eye | pupil diameter (via Pupil Labs detectors), square-wave jerks, better pursuit |
| Phase 3 | ≥ 250–500 fps IR | true saccade peak velocity / main sequence |

IR safety: use low-power, diffused 850 nm LEDs, keep exposure within eye-safety limits
(IEC 62471), and have an adult or mentor review the illumination design before testing on people.

## Commands
```bash
cd eye-tracking
uv venv -p 3.12 .venv && uv pip install --python .venv/bin/python -e ".[dev]"
bash scripts/download_model.sh
.venv/bin/eyetrack check-camera                       # 10 s: fps, iris px, lighting, advice
.venv/bin/eyetrack record --out recordings/test01 --screen-width-cm 30 --distance-cm 50
.venv/bin/eyetrack analyze recordings/test01          # recompute + plot.png
.venv/bin/eyetrack simulate --out recordings/syn --fps 30
.venv/bin/eyetrack benchmark
.venv/bin/python -m pytest -q
```
Outputs per recording folder: `samples.csv` (per-frame derived signals), `meta.json`
(camera, screen, stimulus events, calibration), `measurements.json` (shared format),
`measurements.csv`, `plot.png`. Raw video only with `--save-video --consent-confirmed`.
