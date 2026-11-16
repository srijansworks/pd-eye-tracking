"""Sequential (every frame, in order) evaluation of the NearIRTracker on the held-out LPW people.

Unlike nn_eval (every 10th frame, no temporal state) this runs the tracker the way live
recording does, so it measures the real per-frame cost and the accuracy of 'fast' tracking.

    python -m eyetrack.nearir.eval_tracker --data ../data/lpw --methods hybrid fast
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from .eval_lpw import find_pairs, load_labels
from .nn_data import TEST_PEOPLE
from .pupil import PupilDetectorConfig
from .tracker import NearIRTracker


def run(method: str, pairs, max_frames: int | None, **kw) -> dict:
    cfg = PupilDetectorConfig(max_diameter_px=200.0)
    errs, ms = [], []
    for video, lab_file in pairs:
        labels = load_labels(lab_file)
        trk = NearIRTracker(cfg, method=method, **kw)
        cap = cv2.VideoCapture(str(video))
        for i in range(len(labels)):
            ok, frame = cap.read()
            if not ok or (max_frames and i >= max_frames):
                break
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            t0 = time.perf_counter()
            f = trk.process(g, i / 30.0)
            ms.append(1000 * (time.perf_counter() - t0))
            if labels[i, 0] > 0 and labels[i, 1] > 0:
                W = g.shape[1]
                if f.blink_score >= 1.0:
                    errs.append(np.inf)
                else:
                    errs.append(np.hypot(f.h * W + W / 2 - labels[i, 0], f.v * W + g.shape[0] / 2 - labels[i, 1]))
        cap.release()
    e, m = np.array(errs), np.array(ms)
    return {"method": method, "frames": len(m), "within5px": float(np.mean(e <= 5)), "within10px": float(np.mean(e <= 10)),
            "median_err_px": float(np.median(e)), "ms_mean": float(m.mean()), "ms_median": float(np.median(m)), "ms_p95": float(np.percentile(m, 95)),
            "ms_max": float(m.max()), "fraction_over_8.3ms": float(np.mean(m > 8.33))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--methods", nargs="+", default=["hybrid", "fast"])
    ap.add_argument("--max-frames", type=int, default=None, help="per video (quick test)")
    ap.add_argument("--nn-every", type=int, default=30)
    ap.add_argument("--out", default="results/lpw_tracker.json")
    a = ap.parse_args(argv)
    pairs = [(v, l) for v, l in find_pairs(Path(a.data)) if v.parent.name in TEST_PEOPLE]
    res = []
    for m in a.methods:
        kw = {"nn_every": a.nn_every} if m == "fast" else {}
        r = run(m, pairs, a.max_frames, **kw)
        res.append(r)
        print(json.dumps(r), flush=True)
    Path(a.out).parent.mkdir(exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
