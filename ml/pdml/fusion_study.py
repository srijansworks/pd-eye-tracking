"""Would adding the glasses improve on the wrist band? A simulation, NOT a result.

No dataset has eye and wrist on the same people, so the true answer needs our own paired pilot.
What we CAN do today is a "what if" planning study:

  * wrist side: the REAL out-of-fold PADS scores (ml/results/pads_wrist_oof.npz), PD vs healthy
  * eye side: simulated people drawn from the PUBLISHED PD/healthy distributions (published.py),
    scored with the exact same eye_score() code a real wearer would go through
  * pairing: wrist and eye scores are linked within each class by a Gaussian copula with
    correlation rho (0 = independent evidence; real sensors share disease severity, so rho > 0)

Output: expected AUC of wrist / glasses / both for each rho and eye-marker set, and how often a small
pilot (n per group) would actually SHOW a gain. Assumptions are printed in the JSON.

    python -m pdml.fusion_study [--oof results/pads_wrist_oof.npz] [--out results/fusion_study.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from scipy.stats import norm
from sklearn.metrics import roc_auc_score, roc_curve

from .published import MARKERS

EYE_SETS = {
    "error_rate_only": ["antisaccade_error_rate"],                      # scoreable today without our own controls
    "error_rate+latency+PLR": ["antisaccade_error_rate", "antisaccade_latency_median",
                               "plr_latency", "plr_constriction_amplitude", "plr_max_constriction_velocity"],
}
WITHIN_EYE_RHO = 0.3        # markers from one person correlate; assumed, not measured
SHRINK, CLAMP = 0.5, 3.0    # same as published.eye_score


def _eye_params(name):
    """(HC, PD) Gaussians for simulation. SMD-only markers live in z-units (reference = N(0,1))."""
    m = MARKERS[name]
    if m.hc and m.pd:
        return m.hc, m.pd
    return (0.0, 1.0), (m.smd, 1.0)


def simulate_eye_llr(names, is_pd, rng, rho=WITHIN_EYE_RHO):
    """Eye LLR (after shrink + clamp) for simulated people, markers correlated within a person."""
    n, k = len(is_pd), len(names)
    cov = np.full((k, k), rho) + (1 - rho) * np.eye(k)
    z = rng.multivariate_normal(np.zeros(k), cov, size=n)
    llr = np.zeros(n)
    for j, name in enumerate(names):
        hc, pd = _eye_params(name)
        mu = np.where(is_pd, pd[0], hc[0])
        sd = np.where(is_pd, pd[1], hc[1])
        x = mu + sd * z[:, j]
        if name == "antisaccade_error_rate":
            x = np.clip(x, 0, 1)                      # a rate cannot leave 0-1
        l = np.log(hc[1] / pd[1]) + 0.5 * (((x - hc[0]) / hc[1]) ** 2 - ((x - pd[0]) / pd[1]) ** 2)   # == published._norm_llr
        llr += np.clip(l, -CLAMP, CLAMP)
    return SHRINK * llr


def paired_wrist(eye_llr, is_pd, wrist_pd, wrist_hc, rho_ws, rng):
    """Draw wrist scores from the real OOF distributions, rank-linked to the eye score within class."""
    out = np.empty(len(eye_llr))
    for cls, pool in ((True, wrist_pd), (False, wrist_hc)):
        idx = np.where(is_pd == cls)[0]
        q = (np.argsort(np.argsort(eye_llr[idx])) + 0.5) / len(idx)            # eye rank within class
        u = norm.cdf(rho_ws * norm.ppf(q) + np.sqrt(1 - rho_ws ** 2) * rng.standard_normal(len(idx)))
        out[idx] = np.quantile(np.sort(pool), u)
    return out


def _fused_logit(wrist_p, eye_llr):
    w = np.log(np.clip(wrist_p, 1e-4, 1 - 1e-4) / (1 - np.clip(wrist_p, 1e-4, 1 - 1e-4)))
    return w + eye_llr


def sens_at_90_spec(y, s):
    fpr, tpr, _ = roc_curve(y, s)
    return float(tpr[fpr <= 0.10].max())


def study(oof_path, n_big=20000, n_pilot=(15, 30, 60), n_rep=300, seed=0):
    d = np.load(oof_path, allow_pickle=True)
    y, p = d["y_healthy"].astype(bool), d["p_healthy"]
    wrist_pd, wrist_hc = p[y], p[~y]
    rng = np.random.default_rng(seed)
    res = {"assumptions": {
        "wrist": f"real PADS out-of-fold scores, PD (n={len(wrist_pd)}) vs healthy (n={len(wrist_hc)})",
        "eye": "simulated from published distributions (Waldthaler 2021; PLR meta-analysis 2025), scored by eye_score logic",
        "within_person_eye_marker_correlation": WITHIN_EYE_RHO, "eye_llr_shrink": SHRINK,
        "sensor_correlation_within_class": "rho_ws varied below; real value unknown until paired pilot data exist",
        "PLR_markers": "assume a perfect healthy reference was measured on our hardware (optimistic)",
        "not_covered": "PD vs other movement disorders (no published eye distributions for that contrast)"},
        "expected": {}, "pilot": {}}
    for set_name, names in EYE_SETS.items():
        for rho in (0.0, 0.3, 0.5):
            is_pd = np.r_[np.ones(n_big, bool), np.zeros(n_big, bool)]
            eye = simulate_eye_llr(names, is_pd, rng)
            w = paired_wrist(eye, is_pd, wrist_pd, wrist_hc, rho, rng)
            f = _fused_logit(w, eye)
            key = f"{set_name}|rho={rho}"
            res["expected"][key] = {
                "auc_wrist": float(roc_auc_score(is_pd, w)), "auc_glasses": float(roc_auc_score(is_pd, eye)),
                "auc_both": float(roc_auc_score(is_pd, f)),
                "sens90_wrist": sens_at_90_spec(is_pd, w), "sens90_both": sens_at_90_spec(is_pd, f)}
            for n in n_pilot:                              # n people per group in a pilot
                gains = []
                for _ in range(n_rep):
                    ip = np.r_[np.ones(n, bool), np.zeros(n, bool)]
                    e = simulate_eye_llr(names, ip, rng)
                    ww = paired_wrist(e, ip, wrist_pd, wrist_hc, rho, rng)
                    gains.append(roc_auc_score(ip, _fused_logit(ww, e)) - roc_auc_score(ip, ww))
                gains = np.array(gains)
                res["pilot"][f"{key}|n={n}+{n}"] = {
                    "mean_auc_gain": float(gains.mean()), "p_gain_positive": float((gains > 0).mean()),
                    "gain_p5_p95": [float(np.percentile(gains, 5)), float(np.percentile(gains, 95))]}
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--oof", default="results/pads_wrist_oof.npz")
    ap.add_argument("--out", default="results/fusion_study.json")
    a = ap.parse_args(argv)
    res = study(a.oof)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2))
    print(f"{'eye markers | sensor corr':44s} wrist  glasses  both   (AUC, expected)")
    for k, v in res["expected"].items():
        print(f"{k:44s} {v['auc_wrist']:.3f}  {v['auc_glasses']:.3f}   {v['auc_both']:.3f}")
    print("\nPilot size -> chance the combined model scores higher than wrist alone:")
    for k, v in res["pilot"].items():
        print(f"{k:56s} mean gain {v['mean_auc_gain']:+.3f}  P(gain>0) {v['p_gain_positive']:.0%}")
    print("saved", a.out)


if __name__ == "__main__":
    main()
