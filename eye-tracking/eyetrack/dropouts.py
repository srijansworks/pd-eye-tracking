"""Tracking cut-outs: every run of frames where the face or iris was lost.

One row per dropout, with what the tracker saw just before it was lost
(brightness, iris size, head angle, lid opening), so you can see *why* it cut out.
`pool` summarises many recording folders into one table (one row per session),
for comparing people and lighting conditions.
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

from .events import _runs
from .recording import Recording

BEFORE_S = 0.3          # window of valid frames before a dropout used for the "_before" values
BEFORE_COLS = ("brightness", "iris_px", "yaw", "pitch", "ear")
DROPOUT_FIELDS = ["start_t", "end_t", "duration_s", "n_frames", "task"] + [f"{c}_before" for c in BEFORE_COLS]
POOL_FIELDS = ["session", "label", "condition", "duration_s", "valid_frac", "n_dropouts",
               "longest_dropout_s", "dropouts_per_min", "brightness_median", "iris_px_median", "flags"]


def find_dropouts(rec: Recording) -> list[dict]:
    t, ok = rec["t"], rec["frame_ok"] == 1
    out = []
    for s, e in _runs(~ok):
        if t[s] < 0:
            continue    # camera warm-up frames buffered before the check's clock started, not a real loss
        # End = first frame after the gap that tracked again (or last frame if it never came back).
        end_t = float(t[e + 1]) if e + 1 < len(t) else float(t[e])
        before = ok & (t < t[s]) & (t >= t[s] - BEFORE_S)
        d = {"start_t": round(float(t[s]), 3), "end_t": round(end_t, 3),
             "duration_s": round(end_t - float(t[s]), 3), "n_frames": int(e - s + 1),
             "task": rec["task"][s]}
        for c in BEFORE_COLS:
            d[f"{c}_before"] = round(float(np.nanmedian(rec[c][before])), 2) if before.any() else ""
        out.append(d)
    return out


def write_csv(path: str | Path, rows: list[dict], fields: list[str]) -> Path:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return Path(path)


def write_dropouts(rec: Recording, directory: str | Path) -> list[dict]:
    drops = find_dropouts(rec)
    write_csv(Path(directory) / "dropouts.csv", drops, DROPOUT_FIELDS)
    return drops


def session_row(rec: Recording, name: str) -> dict:
    from .features import quality_summary
    drops = find_dropouts(rec)
    q = quality_summary(rec)
    dur = q["duration_s"]
    return {
        "session": name, "label": rec.meta.get("participant_label", ""),
        "condition": rec.meta.get("condition", ""), "duration_s": round(dur, 1),
        "valid_frac": round(q["valid_frame_fraction"], 3), "n_dropouts": len(drops),
        "longest_dropout_s": max((d["duration_s"] for d in drops), default=0.0),
        "dropouts_per_min": round(len(drops) / (dur / 60), 2) if dur > 0 else 0.0,
        "brightness_median": round(q["eye_brightness_median"], 1),
        "iris_px_median": round(q["iris_diameter_px_median"], 1),
        "flags": ",".join(q["flags"]),
    }


def pool(root: str | Path) -> list[dict]:
    """One row per recording folder under root (any folder holding samples.csv), worst first."""
    rows = [session_row(Recording.load(p.parent), p.parent.name)
            for p in sorted(Path(root).glob("*/samples.csv"))]
    return sorted(rows, key=lambda r: r["valid_frac"])


def by_condition(rows: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for cond in sorted({r["condition"] for r in rows}):
        rs = [r for r in rows if r["condition"] == cond]
        out[cond or "(none)"] = {
            "sessions": len(rs),
            "valid_frac_mean": round(float(np.mean([r["valid_frac"] for r in rs])), 3),
            "dropouts_per_min_mean": round(float(np.mean([r["dropouts_per_min"] for r in rs])), 2),
            "longest_dropout_s": max(r["longest_dropout_s"] for r in rs),
        }
    return out
