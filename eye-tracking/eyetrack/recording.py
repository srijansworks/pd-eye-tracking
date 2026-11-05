"""The in-memory representation of one recording, shared by every module.

A recording is a table of per-frame samples (one row per camera frame) plus
metadata (camera, screen geometry, stimulus events, calibration).

Column meanings
---------------
t            seconds since recording start (monotonic clock, taken when the frame arrived)
frame_ok     1 if a face + both irises were found in the frame, else 0
h, v         eye-in-head iris position, normalised by eye width (dimensionless).
             h > 0 = iris toward the right of the image, v > 0 = iris lower in the image.
gx, gy       calibrated gaze angle in degrees (NaN until calibration is applied)
ear          eye aspect ratio (lid opening), mean of both eyes
blink_score  MediaPipe blendshape eyeBlink, mean of both eyes (0 open .. 1 closed)
iris_px      iris diameter in pixels (resolution check; human iris ~11.7 mm)
yaw/pitch/roll  head rotation in degrees (from the face transformation matrix)
brightness   mean grey level (0-255) of the eye region
task         protocol segment active when the frame was captured
target_x/y   stimulus target position in degrees (NaN if no target)
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

COLUMNS = [
    "t", "frame_ok", "h", "v", "gx", "gy", "ear", "blink_score", "iris_px",
    "yaw", "pitch", "roll", "brightness", "task", "target_x", "target_y",
]
NUMERIC = [c for c in COLUMNS if c != "task"]


@dataclass
class Recording:
    data: dict[str, np.ndarray]
    meta: dict = field(default_factory=dict)

    # ---- convenience -------------------------------------------------
    def __len__(self) -> int:
        return len(self.data["t"])

    def __getitem__(self, key: str) -> np.ndarray:
        return self.data[key]

    @property
    def fps(self) -> float:
        """Effective frame rate from the median frame interval."""
        t = self.data["t"]
        if len(t) < 2:
            return float("nan")
        return float(1.0 / np.median(np.diff(t)))

    @property
    def calibrated(self) -> bool:
        return bool(np.isfinite(self.data["gx"]).any())

    def task_mask(self, task: str) -> np.ndarray:
        return self.data["task"] == task

    # ---- construction ------------------------------------------------
    @classmethod
    def from_rows(cls, rows: list[dict], meta: dict | None = None) -> "Recording":
        data: dict[str, np.ndarray] = {}
        for c in COLUMNS:
            if c == "task":
                data[c] = np.array([r.get(c, "") or "" for r in rows], dtype=object)
            else:
                data[c] = np.array([r.get(c, np.nan) for r in rows], dtype=float)
        return cls(data=data, meta=meta or {})

    # ---- persistence: samples.csv + meta.json --------------------------
    def save(self, directory: str | Path) -> Path:
        d = Path(directory)
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "samples.csv", "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS)
            for i in range(len(self)):
                row = []
                for c in COLUMNS:
                    val = self.data[c][i]
                    if c == "task":
                        row.append(val)
                    elif np.isnan(val):
                        row.append("")
                    else:
                        row.append(f"{val:.6g}")
                w.writerow(row)
        (d / "meta.json").write_text(json.dumps(self.meta, indent=2, default=float))
        return d

    @classmethod
    def load(cls, directory: str | Path) -> "Recording":
        d = Path(directory)
        rows = []
        with open(d / "samples.csv", newline="") as f:
            for r in csv.DictReader(f):
                rows.append({
                    k: (r[k] if k == "task" else (float(r[k]) if r[k] != "" else np.nan))
                    for k in COLUMNS
                })
        meta = json.loads((d / "meta.json").read_text()) if (d / "meta.json").exists() else {}
        return cls.from_rows(rows, meta)
