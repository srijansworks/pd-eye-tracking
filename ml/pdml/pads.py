"""Load the PADS smartwatch dataset (Varghese et al., npj Parkinson's Disease 2024)
and turn it into one feature row per participant.

Dataset: https://physionet.org/content/parkinsons-disease-smartwatch/1.0.0/
License: CC BY-NC-SA 4.0 (non-commercial; cite the paper and the DOI 10.13026/m0w9-zx22).

Layout used here (raw files, not the binary preprocessed ones):
  patients/patient_XXX.json              condition, age, gender, handedness, ...
  movement/timeseries/XXX_<Task>_<Left|Right>Wrist.txt   comma-separated, 100 Hz:
                                          time, acc X/Y/Z (g), gyro X/Y/Z (rad/s)

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
TASK_GROUPS = {   # the 11 raw task names in movement/timeseries/ (checked against observation_*.json)
    "rest": ("Relaxed",),
    "rest_dualtask": ("RelaxedTask",),
    "posture": ("StretchHold", "LiftHold", "HoldWeight"),
    "action": ("PointFinger", "DrinkGlas", "CrossArms", "TouchIndex", "TouchNose"),
    "entrainment": ("Entrainment",),
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
    """Return (acc[N,3] in g, gyro[N,3] in rad/s).

    Column order from the dataset's own metadata (movement/observation_*.json):
    Time [s], Accelerometer_X/Y/Z [g], Gyroscope_X/Y/Z [rad/s]. Note the Apple
    Watch accelerometer here has gravity already removed (all axes average ~0).
    """
    a = np.loadtxt(path, delimiter=",", ndmin=2)
    if a.shape[1] != 7:
        raise ValueError(f"{path.name}: expected 7 columns (time + 6 channels), got {a.shape[1]}")
    return a[:, 1:4], a[:, 4:7]


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
        # The "tremor side" = wrist with more 3.5-7.5 Hz power. Frequency-type features
        # (where the peak is, how peaked) only mean something on the trembling wrist;
        # on a still wrist the "peak" is random noise.
        pl = np.mean(per.get((g, "Left", "acc_power_tremor_3_7hz"), [-np.inf]))
        pr = np.mean(per.get((g, "Right", "acc_power_tremor_3_7hz"), [-np.inf]))
        tremor_side = "Left" if pl >= pr else "Right"
        for k in names:
            L = np.mean(per.get((g, "Left", k), [np.nan]))
            R = np.mean(per.get((g, "Right", k), [np.nan]))
            feats[f"{g}__{k}__mean"] = float(np.nanmean([L, R]))
            if k.endswith(("peak_freq", "spectral_entropy", "peak_prominence")):
                feats[f"{g}__{k}__max"] = float(L if tremor_side == "Left" else R)   # value on the tremor side
            else:
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
