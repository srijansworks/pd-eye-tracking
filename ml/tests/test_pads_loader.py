"""PADS loader on a tiny fake dataset in the real on-disk format
(time + acc XYZ [g] + gyro XYZ [rad/s], 100 Hz; patients/patient_XXX.json)."""

import json

import numpy as np

from pdml.pads import build_table


def _write_subject(root, pid, condition, tremor_hz, left_amp, right_amp, age):
    (root / "patients").mkdir(parents=True, exist_ok=True)
    (root / "movement" / "timeseries").mkdir(parents=True, exist_ok=True)
    (root / "patients" / f"patient_{pid}.json").write_text(json.dumps(
        {"id": pid, "condition": condition, "age": age, "gender": "male", "handedness": "right"}))
    t = np.arange(0, 20.48, 0.01)
    rng = np.random.default_rng(int(pid))
    for wrist, amp in (("Left", left_amp), ("Right", right_amp)):
        acc = np.column_stack([amp * np.sin(2 * np.pi * tremor_hz * t)] * 3) + rng.normal(0, 0.003, (len(t), 3))
        gyro = rng.normal(0, 0.01, (len(t), 3))
        np.savetxt(root / "movement" / "timeseries" / f"{pid}_Relaxed_{wrist}Wrist.txt",
                   np.column_stack([t, acc, gyro]), delimiter=",", fmt="%.10f")


def test_build_table_reads_real_format_and_computes_asymmetry(tmp_path):
    root = tmp_path / "pads-parkinsons-disease-smartwatch-dataset-1.0.0"   # zip's top folder
    _write_subject(root, "001", "Healthy", 5.0, 0.0, 0.0, 50)
    _write_subject(root, "002", "Parkinson's", 5.0, 0.05, 0.0, 70)       # one-sided rest tremor
    X, names, meta = build_table(tmp_path)
    assert [m["condition"] for m in meta] == ["Healthy", "Parkinson's"]
    col = {n: i for i, n in enumerate(names)}
    asym = X[:, col["rest__acc_power_tremor_3_7hz__asym"]]
    assert asym[1] > asym[0] + 1.0          # >10x power difference between wrists for the PD case
    assert abs(X[1, col["rest__acc_peak_freq__max"]] - 5.0) < 0.5
