"""Load the PADS smartwatch dataset (Varghese et al., npj Parkinson's Disease 2024)
and turn it into one feature row per participant.

Dataset: https://physionet.org/content/parkinsons-disease-smartwatch/1.0.0/
License: CC BY-NC-SA 4.0 (non-commercial; cite the paper and the DOI 10.13026/m0w9-zx22).

Layout used here (raw files, not the binary preprocessed ones):
  patients/patient_XXX.json              condition, age, gender, handedness, ...
  movement/timeseries/XXX_<Task>_<Left|Right>Wrist.txt   comma-separated, 100 Hz,
                                          accelerometer (g) + gyroscope (rad/s) channels
Column order is detected from the data (accelerometer magnitude ~1 g from gravity).

Per participant: wrist features per task and wrist -> averaged within task groups
(rest / posture / action / ...) -> mean of both wrists, the larger value, and the
left/right asymmetry (PD typically starts on one side).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

import numpy as np

from .wrist_features import wrist_features

FS = 100.0
TASK_GROUPS = {
    "rest": ("Relaxed1", "Relaxed2"),
    "rest_dualtask": ("RelaxedTask1", "RelaxedTask2"),
    "posture": ("StretchHold", "HoldWeight"),
    "action": ("DrinkGlas", "CrossArms", "TouchNose"),
    "entrainment": ("Entrainment1", "Entrainment2"),
}
GROUP_OF = {task: g for g, tasks in TASK_GROUPS.items() for task in tasks}
FNAME = re.compile(r"^(\d+)_([A-Za-z0-9]+)_(Left|Right)Wrist\.txt$")


def find_root(path: str | Path) -> Path:
    """Folder that contains patients/ and movement/ (the zip adds a top folder)."""
    p = Path(path)
    for cand in [p, *p.glob("*"), *p.glob("*/*")]:
        if (cand / "patients").is_dir() and (cand / "movement").is_dir():
            return cand
    raise FileNotFoundError(f"No PADS patients/ + movement/ folders under {p}")


def load_signal(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return (acc[N,3] in g, gyro[N,3] in rad/s), detecting the column layout."""
    a = np.loadtxt(path, delimiter=",", ndmin=2)
    if a.shape[1] == 7:          # leading time column
        a = a[:, 1:]
    if a.shape[1] != 6:
        raise ValueError(f"{path.name}: expected 6 channels, got {a.shape[1]}")
    g1 = np.median(np.linalg.norm(a[:, :3], axis=1))
    g2 = np.median(np.linalg.norm(a[:, 3:], axis=1))
    # Accelerometer at (near) rest reads ~1 g; gyroscope reads ~0 rad/s.
    return (a[:, :3], a[:, 3:]) if abs(g1 - 1) < abs(g2 - 1) else (a[:, 3:], a[:, :3])


def load_patients(root: Path) -> dict[str, dict]:
    out = {}
    for f in sorted((root / "patients").glob("patient_*.json")):
        d = json.loads(f.read_text())
        out[str(d["id"]).zfill(3)] = d
    return out


def participant_features(root: Path, pid: str) -> dict[str, float]:
    per = defaultdict(list)          # (group, wrist, feature) -> values
    for f in sorted((root / "movement" / "timeseries").glob(f"{pid}_*Wrist.txt")):
        m = FNAME.match(f.name)
        if not m or m.group(2) not in GROUP_OF:
            continue
        acc, gyro = load_signal(f)
        if len(acc) < 256:
            continue
        for k, v in wrist_features(acc, gyro, FS).items():
            per[(GROUP_OF[m.group(2)], m.group(3), k)].append(v)
    feats: dict[str, float] = {}
    groups = {g for g, _, _ in per}
    names = {k for _, _, k in per}
    for g in groups:
        for k in names:
            L = np.mean(per.get((g, "Left", k), [np.nan]))
            R = np.mean(per.get((g, "Right", k), [np.nan]))
            feats[f"{g}__{k}__mean"] = float(np.nanmean([L, R]))
            feats[f"{g}__{k}__max"] = float(np.nanmax([L, R]))
            if not k.endswith(("peak_freq", "spectral_entropy")):
                # log-power features: asymmetry as absolute difference; others: relative difference
                diff = abs(L - R)
                feats[f"{g}__{k}__asym"] = float(diff if "power_" in k and "rel" not in k
                                                 else diff / (abs(L) + abs(R) + 1e-9))
    return feats


def build_table(data_dir: str | Path, limit: int | None = None):
    """Return (X, feature_names, meta_rows) — one row per participant with movement data."""
    root = find_root(data_dir)
    patients = load_patients(root)
    rows, metas = [], []
    for i, (pid, p) in enumerate(sorted(patients.items())):
        if limit and i >= limit:
            break
        f = participant_features(root, pid)
        if not f:
            continue
        rows.append(f)
        metas.append({"id": pid, "condition": p.get("condition"), "age": p.get("age"),
                      "gender": p.get("gender"), "handedness": p.get("handedness")})
    names = sorted(set().union(*rows))
    X = np.array([[r.get(n, np.nan) for n in names] for r in rows], float)
    return X, names, metas
