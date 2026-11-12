"""Evaluate the pupil detector on REAL near-eye infrared video: the LPW dataset.

LPW = "Labelled Pupils in the Wild" (Tonsen, Zhang, Sugano & Bulling, ETRA 2016,
doi 10.1145/2857491.2857520): 66 eye videos, 22 people, 640x480, ~95 fps, dark-pupil
head-mounted tracker, indoor + outdoor, glasses, make-up. Non-commercial use only.

Metric (standard in pupil-detection papers): DETECTION RATE = share of labelled frames
where the detector returns a pupil within 5 px of the hand label. A missed frame
counts as a failure. In the LPW paper the best 2016 detectors reached roughly 30%
within 5 px.

    python -m eyetrack.nearir.eval_lpw --data ../data/lpw [--step 5] [--out results.json]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from .pupil import PupilDetector, PupilDetectorConfig


def find_pairs(root: Path) -> list[tuple[Path, Path]]:
    """(video, label file) pairs. LPW stores <n>.avi next to <n>.txt (one 'x y' per frame)."""
    pairs = []
    for v in sorted(root.rglob("*.avi")) + sorted(root.rglob("*.mp4")):
        lab = v.with_suffix(".txt")
        if lab.exists():
            pairs.append((v, lab))
    return pairs


def load_labels(path: Path) -> np.ndarray:
    rows = []
    for line in path.read_text().split("\n"):
        parts = line.replace(",", " ").split()
        if len(parts) >= 2:
            try:
                rows.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
    return np.array(rows, float)


def evaluate_video(video: Path, labels: np.ndarray, cfg: PupilDetectorConfig, step: int = 1) -> dict:
    cap = cv2.VideoCapture(str(video))
    det = PupilDetector(cfg)
    errs, confs, n, i, t_det = [], [], 0, 0, 0.0
    while True:
        ok, frame = cap.read()
        if not ok or i >= len(labels):
            break
        if i % step == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            t0 = time.perf_counter()
            p = det.detect(gray)
            t_det += time.perf_counter() - t0
            lx, ly = labels[i]
            if lx > 0 and ly > 0:                 # (0,0)/negative = no label
                n += 1
                errs.append(np.hypot(p.cx - lx, p.cy - ly) if p.ok else np.inf)
                confs.append(p.confidence if p.ok else 0.0)
        elif step > 1:
            det.detect(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))   # keep temporal state realistic
        i += 1
    cap.release()
    e = np.array(errs)
    return {"video": str(video.relative_to(video.parents[1])), "n": n,
            "rate_5px": float(np.mean(e <= 5)) if n else None,
            "rate_10px": float(np.mean(e <= 10)) if n else None,
            "detected": float(np.mean(np.isfinite(e))) if n else None,
            "median_err_px_detected": float(np.median(e[np.isfinite(e)])) if np.isfinite(e).any() else None,
            "ms_per_frame": 1000 * t_det / max(1, n),
            "_errs": e.tolist(), "_confs": confs}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--step", type=int, default=5, help="evaluate every Nth frame (all frames still tracked)")
    ap.add_argument("--limit", type=int, help="only the first N videos")
    ap.add_argument("--out", default="lpw_results.json")
    a = ap.parse_args(argv)
    pairs = find_pairs(Path(a.data))
    if a.limit:
        pairs = pairs[: a.limit]
    print(f"{len(pairs)} labelled videos")
    cfg = PupilDetectorConfig(max_diameter_px=200.0)      # LPW is 640x480; pupils can be large
    per = []
    for v, lab in pairs:
        r = evaluate_video(v, load_labels(lab), cfg, a.step)
        per.append(r)
        print(f"  {r['video']:20s} n={r['n']:4d}  within5px {r['rate_5px']:.0%}  within10px {r['rate_10px']:.0%}  "
              f"detected {r['detected']:.0%}  median err {r['median_err_px_detected'] or float('nan'):.1f}px  "
              f"{r['ms_per_frame']:.1f} ms", flush=True)
    allerr = np.concatenate([np.array(r["_errs"]) for r in per])
    allconf = np.concatenate([np.array(r["_confs"]) for r in per])
    summary = {"videos": len(per), "frames": int(len(allerr)),
               "rate_5px": float(np.mean(allerr <= 5)), "rate_10px": float(np.mean(allerr <= 10)),
               "detected": float(np.mean(np.isfinite(allerr))),
               "per_video_rate_5px_median": float(np.median([r["rate_5px"] for r in per]))}
    # Is confidence meaningful? Accuracy of accepted detections by confidence band.
    bands = {}
    for lo, hi in ((0.35, 0.6), (0.6, 0.8), (0.8, 1.01)):
        m = (allconf >= lo) & (allconf < hi)
        if m.any():
            bands[f"{lo:.2f}-{min(hi, 1):.2f}"] = {"share": float(m.mean()), "within5px": float(np.mean(allerr[m] <= 5))}
    summary["by_confidence"] = bands
    print(json.dumps(summary, indent=2))
    for r in per:
        r.pop("_errs"); r.pop("_confs")
    Path(a.out).write_text(json.dumps({"summary": summary, "per_video": per}, indent=2))
    print(f"Saved {a.out}")


if __name__ == "__main__":
    main()
