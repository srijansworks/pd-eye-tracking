# Public datasets we can train or validate on

*Week 1 deliverable (software team). Checked 2026-11-11. Re-check each license before you download.*

**Rules for using these**
- Download only from the official host (PhysioNet, UCI, figshare, Synapse). Don't use pirated copies.
- Never commit dataset files to git; keep them in a local `data/` folder (git-ignored).
- **NC** (non-commercial) licenses are fine for a student competition, but they would block a commercial
  product built on a model trained with that data. Record which dataset every model was trained on.
- None of these datasets makes our system clinically valid. They give us development data and benchmarks.

## 1. Wrist / tremor (priority)

| Dataset | What's in it | Access / license | Fit for us |
|---|---|---|---|
| **[PADS: Parkinson's Disease Smartwatch](https://physionet.org/content/parkinsons-disease-smartwatch/1.0.0/)** (Varghese et al., *npj Parkinson's Disease* 2024) | **469 people**: PD, differential diagnoses (essential tremor, atypical parkinsonism, MS…) and healthy controls. Apple Watch on **both wrists**, accelerometer + gyroscope at **100 Hz**, 11 tremor-provoking tasks of 10–20 s each, plus clinical questionnaires | Open download on PhysioNet; **CC BY-NC-SA 4.0** (per [AWS registry](https://registry.opendata.aws/parkinsons-disease-smartwatch/)) | ⭐ **Best starting point.** Same sensor type as our wrist module, has PD-vs-tremor-mimic labels, and a published ML baseline to compare against ([paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC10770131)) |
| [MJFF Levodopa Response Study](https://www.michaeljfox.org/news/levodopa-response-study) | 31 PD patients over 4 days, wrist devices (GENEActiv + Pebble) + phone, clinician-scored tasks, diaries | Synapse, **registration + data-use agreement** | Good for tremor *severity* over medication cycles; slower to get |
| CIS-PD / REAL-PD (BEAT-PD DREAM Challenge) | Apple/Motorola smartwatch data in daily life with on/off, dyskinesia and **tremor severity** labels | Synapse, data-use agreement | Real-world tremor scoring; heavier to process |

## 2. Gait

| Dataset | What's in it | License | Fit |
|---|---|---|---|
| **[Gait in Parkinson's Disease (gaitpdb)](https://physionet.org/content/gaitpdb/)** | 93 PD + 73 controls walking; vertical ground-reaction force from 8 sensors under each foot (100 Hz) | Open Data Commons Attribution 1.0 | ⭐ Stride timing / variability for PD vs controls. Note: foot-pressure insoles, not an ankle IMU |
| **[Daphnet Freezing of Gait](https://archive.ics.uci.edu/dataset/245/daphnet+freezing+of+gait)** | PD patients with freezing of gait; 3 accelerometers (ankle, thigh, trunk) with labelled freeze episodes | CC BY 4.0 | ⭐ Closest to an ankle-sensor design; small (10 patients) |

## 3. Eye movements

**Finding: there is no large, openly downloadable dataset of eye video or saccade recordings from
Parkinson's patients.** The big PD eye-tracking studies (e.g. a pro/antisaccade study of about 100 PD patients
and about 100 controls, and a 2026 VR study with 44 PD and 34 controls) don't show a public download;
access would mean emailing the authors. So we split the problem in two:

| Dataset | What's in it | Access | How we use it |
|---|---|---|---|
| **[GazeBase](https://figshare.com/articles/dataset/GazeBase_Data_Repository/12912257)** (Griffith et al., *Scientific Data* 2021) | 12,334 recordings from **322 healthy** adults, EyeLink 1000 at **1000 Hz**, 7 tasks incl. random saccades, fixation and video viewing | figshare, open (confirm the license on the page) | ⭐ **Validate our saccade/fixation algorithms** on real high-rate data, and downsample to 30 fps to measure webcam error on real eyes, not just synthetic ones |
| [PD visual pursuit study data](https://pmc.ncbi.nlm.nih.gov/articles/PMC6109371/) | Raw gaze `.mat` files per observer, PD and controls, pursuit tasks | Supplementary files with the paper | Small, but real PD pursuit traces; check its license before use |
| [ET_PD_VIS (Mendeley)](https://data.mendeley.com/datasets/83htprx9y6/1) | Eye-tracking **visualisation images** from PD and controls during a Trail Making Test | Mendeley Data (check license) | Images, not gaze signals; low value for us |
| Author requests | e.g. [Brien et al. 2023, video eye tracking in PD](https://www.researchgate.net/publication/368373682_Classification_and_staging_of_Parkinson's_disease_using_video-based_eye_tracking); [VR eye-tracking PD study 2026](https://link.springer.com/article/10.1186/s12883-026-04634-w) | Email the corresponding authors | Possible PD eye data and baseline numbers. A good message to add to the clinician outreach |

**Recommendation:** we won't *train* a PD eye classifier on public data (none exists). Use GazeBase to
validate the measurement code. Use the published PD-vs-control effect sizes from the literature review as our
"benchline". Then collect our own data under a consent protocol.

## Next steps
1. Download PADS (open, no sign-up) and write a loader that converts it into our measurement-batch format,
   so wrist features flow through the same backend as eye features.
2. Run our saccade detector on GazeBase random-saccade recordings at 1000 Hz and at 30 fps; report the error.
3. Register on Synapse only if PADS turns out to be insufficient.
