# Open-source eye-tracking: evaluation and decision

*Checked 2026-11-04. Licenses, stars and last-commit dates were pulled from the
GitHub and Hugging Face APIs on that day, not copied from READMEs. Re-check before
you depend on them.*

## TL;DR

* **Use now:** MediaPipe Face Landmarker (Apache-2.0) for webcam face, eye and iris landmarks,
  plus our own event detection and feature code (`eye-tracking/eyetrack/`).
* **Use next, when we have an infrared camera running at 120 fps or more:** Pupil Labs' `pupil-detectors` + `pye3d`
  (LGPL-3.0) for real pupil tracking, and REMoDNaV (MIT) for event classification.
* **Do not use YOLO** for eye-movement measurement (reasons below).
* **The hardware is the real limit, not the software.** Our synthetic benchmark
  (`docs/benchmark_output.txt`) shows what a 30 fps webcam can and cannot measure.

## A. Repositories inspected

| Technology | Repository | Detection capability | Ocular measurements it supports | Hardware | License | Recommendation |
|---|---|---|---|---|---|---|
| **MediaPipe Face Landmarker** | [google-ai-edge/mediapipe](https://github.com/google-ai-edge/mediapipe) (37.5k★, active) | Face → 478 landmarks incl. eye corners, lids and **10 iris points**; blink blendshapes; head pose matrix | Iris position, so (after calibration) gaze angle, saccade timing and amplitude, pursuit, blinks. **No pupil.** | Any RGB webcam; CPU real-time | Apache-2.0 ✅ | **Adopted now** (built into `landmarks.py`) |
| **Pupil Core software** | [pupil-labs/pupil](https://github.com/pupil-labs/pupil) (1.7k★, active) | Pupil ellipse in near-eye IR images; 3D eye model | Pupil diameter (mm), gaze, built-in fixation and blink detectors, 120–200 Hz | Head-mounted IR eye cameras (Pupil Core or DIY) | LGPL-3.0 ⚠️ | **Adopt in phase 2** (IR hardware) |
| pupil-detectors / pye3d | [pupil-labs/pupil-detectors](https://github.com/pupil-labs/pupil-detectors), [pye3d-detector](https://github.com/pupil-labs/pye3d-detector) | Standalone 2D pupil detector (C++) and 3D eye model | Pupil centre, ellipse, diameter | IR near-eye camera | LGPL-3.0 ⚠️ | Use these libraries directly instead of the whole Pupil app |
| **OpenIris** (Otero-Millan lab) | [ocular-motor-lab/OpenIris](https://github.com/ocular-motor-lab/OpenIris) (active) | Research video-oculography (VOG): pupil, corneal reflection, **torsion**; plugins (e.g. Dual Purkinje) | High-speed (hundreds of Hz) eye position, research grade | IR cameras, C#/.NET on Windows | **AGPL-3.0** ⛔ for closed distribution | Reference design; too heavy and the license is restrictive for us now |
| EyeTrackVR "OpenIris" | [EyeTrackVR/OpenIris](https://github.com/EyeTrackVR/OpenIris) | ESP32 camera **firmware** for DIY VR eye tracking (a different project with the same name) | None by itself (it streams video) | ESP32-CAM + IR LEDs | MIT | Not relevant except as cheap IR-camera hardware inspiration |
| GazeTracking | [antoinelame/GazeTracking](https://github.com/antoinelame/GazeTracking) (2.7k★) | dlib 68-point face landmarks + OpenCV threshold "pupil" inside eye crop | Horizontal/vertical ratio, blink (eye-width ratio). No timestamps, velocity or calibration | Webcam | MIT code, **but** dlib's 68-pt model was trained on iBUG 300-W (non-commercial terms) ⚠️ | Learn from it; MediaPipe's iris model is more precise and has a clean license |
| EyeStalker | [brouns-tech/eyestalker](https://github.com/brouns-tech/eyestalker) (last commit 2022) | Robust pupil tracking in high-speed IR video (recursive estimation) | Pupil position and size | IR high-speed camera, C++/Qt | GPL-3.0 ⚠️ | Unmaintained; read the algorithm paper, don't depend on it |
| EyeLoop | [simonarvin/eyeloop](https://github.com/simonarvin/eyeloop) (**archived**) | Pupil and corneal-reflection tracking, >1 kHz on consumer IR cams | Pupil size/position, closed-loop experiments | IR camera | GPL-3.0 | Archived; nice reference for high-rate Python loops |
| DeepVOG | [pydsgz/DeepVOG](https://github.com/pydsgz/DeepVOG) (2023) | U-Net pupil segmentation + 3D eye model, trained on clinical VOG | Pupil, gaze from IR VOG video | IR VOG goggles | GPL-3.0 ⚠️ | Strong candidate if Pupil Labs' detector struggles on our IR footage |
| RITnet | [AayushKrChaudhary/RITnet](https://github.com/AayushKrChaudhary/RITnet) (2021) | Real-time segmentation of pupil, iris and sclera (~0.25M params) | Pupil and iris masks, so diameter and centre | Near-eye IR images (OpenEDS) | MIT code; weights trained on OpenEDS (check dataset terms) | Option for custom fine-tuning later |
| L2CS-Net | [Ahmednull/L2CS-Net](https://github.com/Ahmednull/L2CS-Net) | Appearance-based **gaze direction** from a face image | Where you look (~3–4° error); not precise enough for saccade dynamics | Webcam + GPU preferred | MIT code; trained on Gaze360/MPIIGaze (non-commercial datasets) ⚠️ | Not needed: we measure eye rotation relative to the head instead |
| OpenFace 2.0 | [TadasBaltrusaitis/OpenFace](https://github.com/TadasBaltrusaitis/OpenFace) | Landmarks, gaze, action units | Gaze direction, blinks via AUs | Webcam | **Academic non-commercial only** ⛔ | Avoid (license) |
| WebGazer.js | [brownhci/WebGazer](https://github.com/brownhci/WebGazer) | Browser regression from eye patches to screen point | Screen gaze point (errors of 100+ px); too noisy for saccade metrics | Webcam in browser | GPL-3.0 ⚠️ | Not suitable for biomarkers |
| jeelizPupillometry | [jeeliz/jeelizPupillometry](https://github.com/jeeliz/jeelizPupillometry) | Browser pupillometry from a **4K** webcam close-up | Relative pupil size (works best with light irises) | 4K webcam very close to the eye | Apache-2.0 | Interesting visible-light experiment; IR is more reliable |
| **REMoDNaV** | [psychoinformatics-de/remodnav](https://github.com/psychoinformatics-de/remodnav) (maintained) | Classifies an existing gaze signal | Saccades, post-saccadic oscillations, fixations, **smooth pursuit** | Needs a well-sampled signal (designed for ≥ 250–1000 Hz) | MIT ✅ | **Adopt in phase 2** for event classification |
| I2MC | [dcnieho/I2MC_Python](https://github.com/dcnieho/I2MC_Python) | Fixation classification robust to noise and data loss | Fixations in noisy, low-rate data | Any gaze signal | MIT ✅ | Good cross-check for our fixation durations on webcam data |
| Ultralytics YOLO | [ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) | Boxes, segmentation, pose | None directly | GPU preferred | **AGPL-3.0** ⛔ (or paid licence) | **Not used** (see B) |

Licence key: ✅ permissive (OK for any use, keep the notice) · ⚠️ copyleft (LGPL:
fine to *use* as a library, but modifications to the library itself must be shared;
GPL: if we distribute software that includes it, our code must be GPL too) ·
⛔ AGPL/non-commercial (AGPL even applies to software offered over a network).

### Top 5 for us, ranked

1. **MediaPipe Face Landmarker**: the only option that is permissive, actively maintained, real-time on a laptop, and gives iris landmarks with no extra hardware. Implemented.
2. **Pupil Labs pupil-detectors + pye3d**: the established open path to *real* pupil diameter and high-rate gaze once we have an IR eye camera. LGPL is fine as long as we use it as a library.
3. **REMoDNaV**: a published, MIT-licensed event classifier that includes smooth pursuit. Use it when data is ≥ 250 Hz; at 30 fps our simpler detector is more appropriate.
4. **DeepVOG / RITnet**: deep-learning pupil segmentation backups if classic detection fails on our IR footage (glasses, eyelashes, mascara). Mind GPL (DeepVOG) and dataset terms (RITnet).
5. **OpenIris**: the best research-grade open VOG design to learn from (high-speed, torsion), but Windows/C# and AGPL make it a reference rather than a dependency.

## B. Is YOLO useful here?

**No, not for measurement. At most for detection, and we don't need it there either.**

* **What YOLO outputs:** bounding boxes (or masks/keypoints with -seg/-pose). A box centre for
  an eye region jitters by several pixels between frames. A 1° eye rotation moves the iris
  by only about **0.2 mm**. For a 720p laptop webcam at 50 cm (≈ 0.5 mm per pixel) that is
  **under one pixel**. Box jitter is many times larger than the signal; only sub-pixel
  landmark or ellipse fitting can see it.
* **Pretrained weights:** a Hugging Face search found only small hobby models: eye *boxes*
  (`hugolb/yolo8-eyes`, MIT), an eye-closure classifier (`Jaemani/eye-closure-detector-yolo-tflite`, MIT)
  and a CC-BY-**NC**-SA eye detector. On GitHub, "yolo pupil" returns student projects
  with ≤ 5 stars and no license. There is no validated pretrained YOLO pupil or iris model.
* **What the job actually needs:** sub-pixel landmark localisation (MediaPipe iris model) in
  visible light, or ellipse fitting/segmentation of a dark pupil in IR (Pupil Labs, RITnet,
  DeepVOG). Those are purpose-built.
* **Where detection is needed:** finding the face and eyes in a webcam frame. MediaPipe
  already does this as part of the same model call. With a head-mounted IR camera the eye
  is always in the same place, so no detector is needed at all.
* **License:** Ultralytics is AGPL-3.0. Any software we distribute that uses it, including
  over a network, would have to be AGPL too, unless we buy a licence.

| Approach | Good at | Bad at | Verdict |
|---|---|---|---|
| YOLO | Fast object boxes | Sub-pixel precision; licence | ✗ |
| MediaPipe | Face + eye + iris landmarks in one call, any webcam | Pupil; applies temporal smoothing; 30 fps cameras | ✓ now |
| OpenCV classic (threshold, Hough, ellipse fit) | Dark-pupil IR images | Visible-light webcams (pupil vs iris contrast too low) | ✓ inside the IR pipeline (that's what Pupil Labs uses) |
| CNN pupil detectors (PuRe-style, DeepVOG) | Robust pupil in messy IR frames | Need IR; some have restrictive licences | ✓ backup |
| Segmentation (RITnet) | Pupil, iris and sclera masks | Training data is near-eye IR | ✓ later |
| Gaze-estimation CNNs (L2CS) | Where someone looks, roughly | Precision for saccade metrics; dataset licences | ✗ |

## C. Each measurement: how, what's needed, and whether a webcam is enough

"Estimated gaze direction" (where on the screen someone looks) is **not** the same as "measured eye
rotation". We measure **iris position relative to the eye corners** (eye-in-head). After a 6-point
calibration this becomes degrees of rotation. Head movement after calibration breaks
the mapping, which is why we track head pose as a quality flag and why a chin rest helps.

| # | Measurement | How it's calculated | Needs | Webcam (30 fps)? | IR needed? | Our 30 fps synthetic result |
|---|---|---|---|---|---|---|
| 1 | Saccade peak velocity | Max of the speed signal during the saccade | ≥ 250 Hz (a saccade lasts 20–80 ms) | **No**: only 1–2 frames per saccade | Recommended | 143 °/s measured vs 425 true (flagged `undersampled`) |
| 2 | Saccade latency | Saccade onset minus target-jump time | Stimulus timestamps; resolution = 1 frame | **Roughly** (±33 ms resolution plus a constant camera delay) | No | 199 vs 197 ms (median of 20 trials) |
| 3 | Saccade amplitude / gain | Position after minus before; gain = amplitude ÷ target step | Calibration | **Yes** (~0.5–1° error) | No | gain 0.93 vs 0.95 |
| 4 | Fixation duration | Time between saccades | Saccade detection | Partly (small saccades missed) | No | — |
| 5 | Fixation stability | BCEA (68% ellipse area), SD; square-wave jerks | Low noise (≪ 0.5°), ≥ 120 Hz for jerks | **No** for small jerks: webcam noise ≈ jerk size | Yes | 2° jerks: 0 detected at 30 fps; 72–80% at ≥ 120 fps |
| 6 | Smooth pursuit | Sinusoid fit of eye velocity → gain and phase lag; catch-up saccade rate | Moving-target stimulus | Gain **roughly**; lag biased | No | gain 0.90 vs 0.85; lag 31 vs 60 ms (biased) |
| 7 | Blink rate and duration | Eyelid-closure runs (blendshape or eye aspect ratio) | Lid visible | **Yes** (blinks last 100–400 ms) | No | 148 vs 150 ms |
| 8 | Pupil diameter | Ellipse fit to the dark pupil | IR illumination + IR camera | **No** | **Yes** | not measured |
| 9 | Pupil movement over time | Pupil-centre track | IR | No (we track the iris instead) | Yes | — |
| 10 | Gaze trajectory | Calibrated iris positions over time | Calibration, still head | Yes (low precision) | No | plotted in `plot.png` |

Camera specs that matter, in order: **frame rate** (for velocity and timing), **pixels across the
iris** (sit about 50 cm away; aim for ≥ 20 px), **even front lighting** (dim light lowers the
webcam frame rate through longer exposure), **global shutter** (rolling shutter skews fast
motion), and **IR + IR-pass filter** (pupil contrast, independent of room light and iris colour).
