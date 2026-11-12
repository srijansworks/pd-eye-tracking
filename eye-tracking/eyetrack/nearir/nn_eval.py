"""Head-to-head on the HELD-OUT test people (never used in training or model selection):
classic detector vs neural network vs hybrid (network finds it, ellipse fit refines it).

Same frames as eval_lpw (every 10th frame of each test-person video), errors in 640x480 pixels.

    python -m eyetrack.nearir.nn_eval --data ../data/lpw
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
from .nn_model import PupilNet
from .pupil import PupilDetector, PupilDetectorConfig


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--step", type=int, default=10)
    ap.add_argument("--out", default="results/lpw_nn_test.json")
    a = ap.parse_args(argv)
    net = PupilNet()
    cfg = PupilDetectorConfig(max_diameter_px=200.0)
    pairs = [(v, l) for v, l in find_pairs(Path(a.data)) if v.parent.name in TEST_PEOPLE]
    rows, all_e = [], {"classic": [], "nn": [], "hybrid": []}
    t_nn = t_hy = t_cl = 0.0
    n_total = 0
    for video, lab_file in pairs:
        labels = load_labels(lab_file)
        classic, refiner = PupilDetector(cfg), PupilDetector(cfg)
        cap = cv2.VideoCapture(str(video))
        e = {"classic": [], "nn": [], "hybrid": []}
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok or i >= len(labels):
                break
            g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            t0 = time.perf_counter(); pc = classic.detect(g); t_cl += time.perf_counter() - t0   # every frame (temporal state)
            if i % a.step == 0 and labels[i, 0] > 0 and labels[i, 1] > 0:
                lx, ly = labels[i]
                t0 = time.perf_counter(); nx, ny, nconf = net.predict(g); t_nn += time.perf_counter() - t0
                t0 = time.perf_counter()
                pr = refiner.refine_near(g, nx, ny, radius=15.0)
                hx, hy = (pr.cx, pr.cy) if pr.ok else (nx, ny)
                t_hy += time.perf_counter() - t0
                e["classic"].append(np.hypot(pc.cx - lx, pc.cy - ly) if pc.ok else np.inf)
                e["nn"].append(np.hypot(nx - lx, ny - ly))
                e["hybrid"].append(np.hypot(hx - lx, hy - ly))
                n_total += 1
            i += 1
        cap.release()
        row = {"video": f"{video.parent.name}/{video.name}", "n": len(e["nn"])}
        for k, v in e.items():
            v = np.array(v)
            row[k] = float(np.mean(v <= 5))
            all_e[k].extend(v.tolist())
        rows.append(row)
        print(f"  {row['video']:10s} n={row['n']:3d}  within 5 px: classic {row['classic']:.0%}  "
              f"NN {row['nn']:.0%}  hybrid {row['hybrid']:.0%}", flush=True)
    summary = {"test_people": TEST_PEOPLE, "frames": n_total}
    for k, v in all_e.items():
        v = np.array(v)
        summary[k] = {"within5px": float(np.mean(v <= 5)), "within10px": float(np.mean(v <= 10)),
                      "median_err_px": float(np.median(v))}
    summary["ms_per_frame"] = {"nn": 1000 * t_nn / n_total, "hybrid_extra": 1000 * t_hy / n_total,
                               "classic": 1000 * t_cl / max(1, sum(r["n"] for r in rows) * a.step)}
    print(json.dumps(summary, indent=2))
    Path(a.out).write_text(json.dumps({"summary": summary, "per_video": rows}, indent=2))


if __name__ == "__main__":
    main()
