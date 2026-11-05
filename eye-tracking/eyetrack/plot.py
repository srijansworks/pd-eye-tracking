"""Plot a recording over time: gaze vs target, speed, blinks, tracking quality."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from . import events as ev
from .recording import Recording


def plot_recording(rec: Recording, out_png: str | Path, stim_events: list[dict] | None = None) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = rec["t"]
    cal = rec.calibrated
    x, y = (rec["gx"], rec["gy"]) if cal else (rec["h"], rec["v"])
    unit = "deg" if cal else "eye widths"
    closed = ev.closed_eye_mask(rec["blink_score"], rec["ear"], rec["frame_ok"])

    fig, axes = plt.subplots(4, 1, figsize=(14, 10), sharex=True,
                             gridspec_kw={"height_ratios": [3, 2, 2, 1]})
    ax = axes[0]
    ax.plot(t, x, lw=0.8, label=f"gaze x ({unit})")
    if cal:
        ax.plot(t, rec["target_x"], lw=1, color="k", alpha=0.5, label="target x")
    ax.set_ylabel(f"horizontal ({unit})")
    ax.legend(loc="upper right", fontsize=8)
    # Shade protocol segments
    tasks = rec["task"]
    for task, color in [("calibration", "#eee"), ("fixation", "#e6f2ff"),
                        ("prosaccade", "#fff3e0"), ("pursuit", "#e8f5e9")]:
        m = tasks == task
        if m.any():
            for a in axes:
                a.axvspan(t[m][0], t[m][-1], color=color, zorder=-1)
            ax.text(t[m][0], ax.get_ylim()[1], task, fontsize=8, va="top")

    axes[1].plot(t, y, lw=0.8, color="tab:purple")
    axes[1].set_ylabel(f"vertical ({unit})")

    speed = np.hypot(ev.velocity(t, x), ev.velocity(t, y))
    axes[2].plot(t, speed, lw=0.6, color="tab:red")
    axes[2].set_ylabel(f"speed ({unit}/s)")

    axes[3].fill_between(t, 0, (rec["frame_ok"] == 0).astype(float), step="mid",
                         color="tab:gray", label="tracking lost")
    axes[3].fill_between(t, 0, closed.astype(float), step="mid", color="tab:blue",
                         alpha=0.6, label="eyes closed")
    axes[3].set_yticks([]); axes[3].legend(loc="upper right", fontsize=8)
    axes[3].set_xlabel("time (s)")

    title = "Synthetic recording" if rec.meta.get("is_synthetic") else "Recording"
    fig.suptitle(f"{title} — {rec.fps:.0f} fps, {'calibrated' if cal else 'uncalibrated'} "
                 "(research prototype, not clinical)")
    fig.tight_layout()
    out = Path(out_png)
    fig.savefig(out, dpi=110)
    plt.close(fig)
    return out
