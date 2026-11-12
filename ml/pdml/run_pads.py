"""Train and honestly evaluate wrist-only models on PADS.

    python -m pdml.run_pads --data ../data/pads [--out results/pads_wrist.json]

Questions answered (each with repeated 5-fold CV, AUC + 95% CI):
  1. Parkinson's vs healthy controls
  2. Parkinson's vs other movement disorders (the clinically hard question)
  3. Baselines using only age (+ sex): a model must beat these to mean anything.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from .model import cross_validate, top_features
from .pads import build_table

DIFFERENTIAL = {"Other Movement Disorders", "Atypical Parkinsonism", "Essential Tremor", "Multiple Sclerosis"}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="results/pads_wrist.json")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args(argv)

    t0 = time.time()
    X, names, meta = build_table(a.data, a.limit)
    cond = np.array([m["condition"] for m in meta])
    age = np.array([m["age"] for m in meta], float)
    sex = np.array([1.0 if m["gender"] == "female" else 0.0 for m in meta])
    print(f"Loaded {len(meta)} participants, {len(names)} wrist features in {time.time() - t0:.0f}s")
    print("Conditions:", {c: int((cond == c).sum()) for c in sorted(set(cond))})

    results = {"n_features": len(names), "conditions": {c: int((cond == c).sum()) for c in set(cond)},
               "comparisons": {}}
    comparisons = {
        "PD_vs_healthy": (cond == "Parkinson's", cond == "Healthy"),
        "PD_vs_other_disorders": (cond == "Parkinson's", np.isin(cond, list(DIFFERENTIAL))),
    }
    for cname, (pos, neg) in comparisons.items():
        m = pos | neg
        y = pos[m].astype(int)
        demo = np.column_stack([age[m], sex[m]])
        print(f"\n== {cname}: {int(y.sum())} PD vs {int((1 - y).sum())} comparison ==")
        specs = [
            ("age_only (baseline)", age[m].reshape(-1, 1), "logreg", 5, "age only (baseline)"),
            ("age_sex (baseline)", demo, "logreg", 5, "age + sex (baseline)"),
            ("wrist_logreg", X[m], "logreg", 5, "wrist features, logistic regression"),
            # Gradient boosting is slow on this machine (~10 s per fit), so 2 x 5-fold here.
            ("wrist_hgb", X[m], "hgb", 2, "wrist features, gradient boosting"),
            ("wrist_plus_age_hgb", np.column_stack([X[m], demo]), "hgb", 2, "wrist + age + sex, gradient boosting"),
        ]
        rows = {}
        for key, Xm, kind, reps, label in specs:
            rows[key] = cross_validate(Xm, y, kind, label, n_repeats=reps)
            print("  " + rows[key].summary(), flush=True)
        results["comparisons"][cname] = {
            k: {"auc": r.auc, "auc_ci": r.auc_ci, "balanced_accuracy": r.balanced_accuracy,
                "sensitivity_at_90_specificity": r.sensitivity_at_90_spec, "n": r.n, "n_pos": r.n_pos}
            for k, r in rows.items()}
        tf = top_features(X[m], y, names, k=8)
        results["comparisons"][cname]["top_features_logreg"] = tf
        print("  most influential wrist features:", ", ".join(f"{n} ({c:+.2f})" for n, c in tf[:5]))

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(results, indent=2))
    print(f"\nSaved {a.out}")


if __name__ == "__main__":
    main()
