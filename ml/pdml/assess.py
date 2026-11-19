"""Compare one wearer to published Parkinson's values and fuse glasses + wrist. RESEARCH ONLY.

    python -m pdml.assess --eye ../eye-tracking/recordings/x/measurements.json --wrist-prob 0.7
    python -m pdml.assess --eye measurements.json --pads-id 123          # wrist score of a PADS person (demo)
    python -m pdml.assess --eye measurements.json --reference healthy_ref.json   # {"plr_latency": [mean, sd], ...}

Prints which published markers were used, where the wearer sits relative to the published healthy
and Parkinson's groups, and the combined score. It is a similarity score, not a diagnosis.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .published import DIRECTION_ONLY, MARKERS, eye_score, fuse, posterior

DISCLAIMER = ("RESEARCH PROTOTYPE. Not a diagnosis and not validated on our hardware. The score says how much this "
              "wearer's numbers look like published Parkinson's group values versus published healthy values.")


def assess(measurements: list[dict], wrist_prob: float | None = None, reference=None) -> dict:
    eye = eye_score(measurements, reference)
    eye_llr = eye["llr"] if eye["n_used"] else None
    return {"eye": eye, "wrist_probability": wrist_prob,
            "eye_only_probability": posterior(eye_llr) if eye_llr is not None else None,
            "combined": fuse(wrist_prob, eye_llr),
            "context_only": {n: DIRECTION_ONLY[n] for n in DIRECTION_ONLY if any(m["name"] == n for m in measurements)},
            "disclaimer": DISCLAIMER}


def render(a: dict) -> str:
    L = [DISCLAIMER, ""]
    for u in a["eye"]["used"]:
        (hm, hs), (pm, ps) = u["healthy"], u["parkinsons"]
        L.append(f"- {u['label']}: wearer {u['value']:.3g} {u['unit']} | published healthy {hm:.3g}±{hs:.3g}, "
                 f"Parkinson's {pm:.3g}±{ps:.3g} | evidence {u['llr']:+.2f} ({'toward PD' if u['llr'] > 0 else 'toward healthy'})")
    for s in a["eye"]["skipped"]:
        L.append(f"- not scored: {s['name']} ({s['reason']})")
    for n, t in a["context_only"].items():
        L.append(f"- context only: {n}: {t}")
    f = lambda p: "n/a" if p is None else f"{p:.0%}"
    L += ["", f"glasses only: {f(a['eye_only_probability'])}   wrist only: {f(a['wrist_probability'])}   "
              f"COMBINED ({'+'.join(a['combined']['sensors_used']) or 'none'}): {f(a['combined']['probability'])}"]
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--eye", required=True, help="measurements.json from `eyetrack analyze`")
    ap.add_argument("--wrist-prob", type=float)
    ap.add_argument("--pads-id", help="demo: use this PADS person's out-of-fold wrist score")
    ap.add_argument("--oof", default="results/pads_wrist_oof.npz")
    ap.add_argument("--reference", help="JSON {name: [mean, sd]} of healthy volunteers on our own glasses")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    ms = json.loads(Path(a.eye).read_text())["measurements"]
    wp = a.wrist_prob
    if a.pads_id:
        d = np.load(a.oof, allow_pickle=True)
        keep = (d["condition"] == "Parkinson's") | (d["condition"] == "Healthy")
        ids = list(d["ids"][keep])
        wp = float(d["p_healthy"][ids.index(a.pads_id)])
    ref = {k: tuple(v) for k, v in json.loads(Path(a.reference).read_text()).items()} if a.reference else None
    res = assess(ms, wp, ref)
    print(render(res))
    if a.out:
        Path(a.out).write_text(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
