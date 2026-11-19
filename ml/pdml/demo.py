"""End-to-end demo with SIMULATED glasses data: virtual wearers -> eye measurements -> published comparison -> fusion.

Eyes are synthetic (error rates 0.19 healthy-like, 0.34 PD-like, from the published pooled values), wrists are
real out-of-fold PADS scores (a typical PD and a typical healthy person). Shows the pipeline works; says nothing about accuracy.
    python -m pdml.demo
"""
import numpy as np

from eyetrack import calibration, features
from eyetrack.stimulus import eye_v4
from eyetrack.synthetic import simulate

from .assess import assess, render


def virtual_eye(anti_error_rate, seed):
    rec, stim, _ = simulate(fps=120, noise_deg=0.1, protocol=eye_v4(seed=seed), seed=seed, anti_error_rate=anti_error_rate)
    calibration.apply(rec, calibration.fit(rec, stim))
    return features.compute(rec, stim)[0]


def main(oof="results/pads_wrist_oof.npz"):
    d = np.load(oof, allow_pickle=True)
    y, p = d["y_healthy"].astype(bool), d["p_healthy"]
    wrist = {"PD": float(np.median(p[y])), "healthy": float(np.median(p[~y]))}
    cases = [("PD-like eyes, PD wrist", 0.34, "PD"), ("healthy-like eyes, healthy wrist", 0.19, "healthy"),
             ("PD-like eyes, healthy-looking wrist", 0.34, "healthy"), ("healthy-like eyes, PD-looking wrist", 0.19, "PD")]
    for i, (label, err, w) in enumerate(cases):
        print(f"\n=== {label} (wrist score {wrist[w]:.2f}) ===")
        print(render(assess(virtual_eye(err, 20 + i), wrist[w])))


if __name__ == "__main__":
    main()
