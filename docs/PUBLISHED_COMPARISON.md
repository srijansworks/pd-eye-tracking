# Comparing a wearer to published data, and glasses + wrist fusion

*Written 2026-11-18. Research prototype. It produces a similarity score against published group values. It is not a diagnosis.*

## What the code does
`ml/pdml/published.py` holds published Parkinson's (PD) vs healthy numbers, each tied to its paper. `eye_score()` turns a
wearer's measurements into a log-likelihood ratio (evidence toward PD vs healthy). `fuse()` adds that to the wrist model's
log-odds. `python -m pdml.assess --eye measurements.json --wrist-prob 0.7` prints the per-marker table and the combined score.

## Published values we use (read from the papers 2026-11-18)
| Marker | Healthy | PD | Effect | Source |
|---|---|---|---|---|
| Antisaccade error rate | 0.19 [0.16-0.22] | 0.34 [0.30-0.39] | g = 0.99 [0.76-1.21], 39 studies (bias-adjusted 0.68) | Waldthaler et al. 2021, Neuropsychol Rev 31(4):628 |
| Antisaccade latency, step paradigm | 368.6 ms | 411.7 ms | g = 0.84 [0.52-1.15], 34 studies (bias-adjusted 0.41) | same |
| Pupil light reflex latency | n/a | slower | SMD +0.46 [0.10-0.81], 9 studies | Diagnostics 15(9):1167, 2025 |
| PLR constriction amplitude | n/a | smaller | SMD -0.58 [-1.17-0.01], 10 studies | same |
| PLR peak constriction velocity | n/a | slower | SMD -0.92 [-1.56 to -0.28], 9 studies | same |
| Prosaccade latency | n/a | +19.4 ms overall, +26.5 ms step | 47 studies | Chambers & Prescott 2010 |

SDs for the two antisaccade rows are implied from g (difference / g). Studies disagree a lot (I2 65-88%).
Direction-only, with no number we could verify: smaller saccades, lower pursuit gain, lower blink rate, more square-wave jerks.

## What can be scored today, and what cannot
- **Scored now:** antisaccade error rate (absolute published values, not tied to our camera).
- **Needs our own healthy reference:** antisaccade latency, light-reflex measures. They shift with camera and display delay, and the
  PLR papers give only effect sizes. After ~10-20 healthy volunteers wear the glasses, pass their mean/SD with `--reference`.
- **Not scored:** prosaccade latency (small, hardware dependent), and everything with direction only.
- **PD vs other movement disorders:** no published eye distributions for that question, so the eye side is not used for it.

## Does adding the glasses help? (simulation, `ml/pdml/fusion_study.py`)
Real PADS wrist scores (PD 276 vs healthy 79, AUC 0.88) paired with simulated eyes drawn from the published distributions.
`rho` = how correlated the two sensors' evidence is inside a class (unknown until paired data exist).

| Eye markers used | rho | Wrist AUC | Glasses AUC | Both AUC |
|---|---|---|---|---|
| error rate only (scoreable today) | 0.0 / 0.3 / 0.5 | 0.886 | 0.76 | 0.904 / 0.894 / 0.885 |
| error rate + latency + 3 PLR markers (needs own reference) | 0.0 / 0.3 / 0.5 | 0.885 | 0.92 | 0.938 / 0.924 / 0.914 |

Reading: if the sensors are mostly independent, adding glasses lifts AUC by about 0.02 (error rate only) to 0.05 (full set).
If they share a lot (rho 0.5), the error-rate-only gain disappears. A pilot of 30 PD + 30 healthy would show a positive gain
in 94% / 78% / 57% of runs (rho 0 / 0.3 / 0.5) for error rate only, and 98-100% for the full set. The simulated glasses AUC
(0.92) is optimistic: it ignores hardware noise, medication state, age matching and study heterogeneity. **This is a plan,
not evidence.** Only paired recordings on real people can show whether fusion helps.

Reproduce: `cd ml && ../eye-tracking/.venv/bin/python -m pdml.wrist_oof --data ../data/pads && ../eye-tracking/.venv/bin/python -m pdml.fusion_study`
Demo with virtual wearers: `python -m pdml.demo`.
