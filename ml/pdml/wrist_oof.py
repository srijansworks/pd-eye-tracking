"""Save PADS wrist-model out-of-fold scores (every person scored by a model that never saw them).

    python -m pdml.wrist_oof --data ../data/pads [--out results/pads_wrist_oof.npz]

The fusion study (fusion_study.py) pairs these REAL wrist scores with simulated eye scores,
so it needs the per-person scores, not just the AUC numbers in pads_wrist.json.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from .model import cross_validate
from .pads import build_table
from .run_pads import DIFFERENTIAL


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default="results/pads_wrist_oof.npz")
    a = ap.parse_args(argv)

    X, names, meta = build_table(a.data)
    cond = np.array([m["condition"] for m in meta])
    out = {"ids": np.array([m["id"] for m in meta]), "condition": cond}
    # Same model choices as run_pads.py: logreg for PD vs healthy, boosting for the hard question.
    for key, neg, kind, reps in (("healthy", cond == "Healthy", "logreg", 5),
                                 ("other", np.isin(cond, list(DIFFERENTIAL)), "hgb", 2)):
        pos = cond == "Parkinson's"
        m = pos | neg
        r = cross_validate(X[m], pos[m].astype(int), kind, key, n_repeats=reps)
        print(r.summary(), flush=True)
        out[f"y_{key}"] = pos[m].astype(int)
        out[f"p_{key}"] = r.oof_proba
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    np.savez(a.out, **out)
    print("saved", a.out)


if __name__ == "__main__":
    main()
