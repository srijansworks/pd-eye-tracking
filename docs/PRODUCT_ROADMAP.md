# Product software: where we are and what's next

*Updated 2026-11-11. Research prototype, not a medical device. Every number below is from
synthetic data or from the public PADS dataset, and none is a validated diagnostic accuracy.*

## The product
```
 Glasses: near-eye IR camera ─┐                       ┌─ eye measurements (saccades, pursuit, pupil, light reflex)
                              ├─ laptop/phone app ────┤
 Wrist band: IMU (acc+gyro) ──┘  (Python, local)      └─ wrist measurements (tremor bands, asymmetry, ...)
                                        │  shared measurement batch (JSON, per sensor, same session)
                                        ▼
                         Next.js API ─▶ Supabase (hosted) ─▶ fusion model ─▶ research report / dashboard
```
Each sensor gets its own model; a **late-fusion** layer combines whichever sensors were recorded
(`ml/pdml/fusion.py`). That's needed because no dataset has eye and wrist on the same people.

## Status by component
| Component | Status | Evidence |
|---|---|---|
| Webcam eye tracking (interim) | ✅ Working on real faces | 4 real recordings. Latency repeats within ~15 ms. Gain 0.92 after drift-check and smoothing fixes |
| **Glasses eye tracking (near-eye IR)** | ✅ **Built; tested on synthetic AND real IR eye video (LPW)** | Pupil centre error 0.05 px (open eye); 120 fps simulation: gain 0.949/0.95, pursuit 0.849/0.85, pupil 4.02/4.01 mm, light reflex latency 240/256 ms |
| Pupillary light reflex test | ✅ In protocol `eye_v3` (screen flashes) | Synthetic: amplitude 27–32% vs ~30% true |
| Wrist tremor features | ✅ Built | Recovers tremor frequency ±0.5 Hz on test signals |
| **Wrist model on real PD data (PADS)** | ✅ **Trained and cross-validated** | See below |
| Backend (hosted Supabase + API + dashboard) | ✅ Live | Real upload from Srijan's laptop stored |
| Fusion model | 🟡 Code done, untested on real paired data | No dataset has eye + wrist on the same people |
| Real glasses hardware | ❌ Hardware team | Spec: `docs/GLASSES_CAMERA_SPEC.md` |
| Real PD eye-movement data | ❌ None public | Needs author data requests or our own recordings |

## Wrist model on PADS (469 people, Apple Watch on both wrists)
Repeated 5-fold cross-validation: every person is scored by a model that never saw them. AUC with 95% CI.

| Question | Age + sex only (baseline) | Wrist model | What it means |
|---|---|---|---|
| **Parkinson's vs healthy** (276 vs 79) | 0.65 [0.58–0.73] | **0.88 [0.84–0.92]** (logistic regression) | Wrist movement separates PD from healthy far better than demographics. At 90% specificity it catches 72% of PD |
| **Parkinson's vs other movement disorders** (276 vs 114) | 0.61 [0.55–0.68] | **0.72 [0.66–0.77]** (gradient boosting) | The clinically hard question; wrist alone is only moderate |

**Most informative features:** left/right **asymmetry** of tremor power and movement, across rest, posture
and action tasks. That fits the clinical picture of PD usually starting on one side.

**Why this matters for the product:** wrist data alone struggles to tell PD from look-alike conditions
(essential tremor, atypical parkinsonism). That's exactly where eye movements and the pupil could add
independent information, which is the scientific case for combining glasses and wrist band. It's a
hypothesis until we have both sensors on the same people.

Caveats: one dataset, one device, one clinic; the PD group is larger than the others; there's no external test set.
The original PADS paper reports its own results; compare with it in the write-up rather than with ours alone.

## Pupil detector on REAL near-eye infrared video (LPW)
LPW = Labelled Pupils in the Wild (Tonsen et al., ETRA 2016; CC BY-NC 3.0): 66 videos, 22 people,
640×480, head-mounted dark-pupil IR camera, indoor + outdoor, glasses, make-up. Hand-labelled pupil centres.
Every 10th frame scored (13,086 frames); a missed frame counts as a failure.

| Detector version | Within 5 px | Within 10 px | High-confidence (≥0.8) frames correct |
|---|---|---|---|
| v1: single darkness threshold | 48.8% | 51.5% | 79% (49% of frames) |
| **v2: multi-threshold candidates + contrast check** | **54.7%** | **60.4%** | **90%** (38% of frames) |

For context, the LPW paper's 2016 detectors (incl. Pupil Labs') reached roughly 30% within 5 px. Newer
published detectors do better, and we haven't compared against them directly.
- 16+ videos ≥ 80% correct; the hardest are washed-out pupils behind glasses frames, blur, and heavy mascara.
- **Real-data bugs found and fixed:** a size "memory" that locked out the true pupil for whole videos (0% → 72%),
  and eyelashes darker than the pupil hiding it from a single threshold (several videos 0–2% → 33–51%).
- **Open issues:** some clean videos regressed in v2 (e.g. 96% → 70%), and speed is ~10 ms/frame at 640×480
  (real-time 120 fps needs < 8.3 ms).
- **Our own glasses will be easier than LPW:** a fixed IR LED setup, an IR-pass filter and a controlled indoor protocol.
- Reproduce: `cd eye-tracking && .venv/bin/python -m eyetrack.nearir.eval_lpw --data ../data/lpw --step 10`

## Next steps, in priority order
1. **Train a small neural network for pupil finding on LPW** (we now have 130k labelled real frames) and
   compare it with the classic detector on held-out participants. Then speed up detection for 120 fps.
2. **First glasses prototype → `eyetrack record --camera-type ir`** (protocol `eye_v3` with the light reflex).
3. **Wrist band prototype → same upload format** (`docs/DATA_FORMAT.md`), with the sync tap.
4. **Paired pilot data:** each volunteer wears both sensors in one session. Only this can show whether fusion helps.
   Needs a consent form and adult/mentor supervision. No patients until there's proper ethics oversight.
5. **Ask authors for PD eye-tracking data** (see `docs/DATASETS.md`) to train or check an eye model.

## Running the wrist experiment
```bash
cd ml && ../eye-tracking/.venv/bin/python -m pdml.run_pads --data ../data/pads   # ~10 min; writes results/pads_wrist.json
```
