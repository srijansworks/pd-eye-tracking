"""Build a frame cache from LPW for training the neural pupil detector.

Split is BY PERSON (not by frame): frames of the same person look almost identical, so
mixing them across train/test would make the network look far better than it is on new
people. 16 participants train, 2 tune (validation), 4 are held out for the final test.

Frames are shrunk 4x to 160x120 grayscale (the network finds WHERE the pupil is; the
classic ellipse fit can then add sub-pixel precision at full resolution).

    python -m eyetrack.nearir.nn_data --data ../data/lpw --out ../data/lpw_cache
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from .eval_lpw import find_pairs, load_labels

SCALE = 4                 # 640x480 -> 160x120
TEST_PEOPLE = ["2", "5", "10", "17"]     # fixed before training: a mix of easy and hard recordings
VAL_PEOPLE = ["8", "20"]


def split_of(person: str) -> str:
    return "test" if person in TEST_PEOPLE else "val" if person in VAL_PEOPLE else "train"


def build(data_dir: str, out_dir: str, train_step: int = 4, eval_step: int = 10) -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    buckets = {s: {"X": [], "y": [], "meta": []} for s in ("train", "val", "test")}
    for video, lab_file in find_pairs(Path(data_dir)):
        person = video.parent.name
        split = split_of(person)
        step = train_step if split == "train" else eval_step
        labels = load_labels(lab_file)
        cap = cv2.VideoCapture(str(video))
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok or i >= len(labels):
                break
            if i % step == 0 and labels[i, 0] > 0 and labels[i, 1] > 0:
                g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                small = cv2.resize(g, (g.shape[1] // SCALE, g.shape[0] // SCALE), interpolation=cv2.INTER_AREA)
                b = buckets[split]
                b["X"].append(small)
                b["y"].append(labels[i] / SCALE)
                b["meta"].append((person, video.stem, i))
            i += 1
        cap.release()
    summary = {}
    for s, b in buckets.items():
        np.save(out / f"{s}_X.npy", np.stack(b["X"]).astype(np.uint8))
        np.save(out / f"{s}_y.npy", np.stack(b["y"]).astype(np.float32))
        (out / f"{s}_meta.json").write_text(json.dumps(b["meta"]))
        summary[s] = {"frames": len(b["X"]), "people": sorted({m[0] for m in b["meta"]}, key=int)}
    (out / "split.json").write_text(json.dumps(summary, indent=2))
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    print(json.dumps(build(a.data, a.out), indent=2))
