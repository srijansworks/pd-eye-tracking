"""Build the shared measurement batch (docs/DATA_FORMAT.md) and write files.

The batch is the contract between every sensor (eye, wrist, gait) and the
backend: the same JSON shape is POSTed to /api/v1/ingest by all of them.
"""

from __future__ import annotations

import csv
import json
import platform
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import __version__
from .recording import Recording

SCHEMA_VERSION = "1.0"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def build_batch(rec: Recording, measurements: list[dict], quality: dict,
                stim_events: list[dict], session_id: str | None = None) -> dict:
    started = rec.meta.get("started_at_utc")
    t0 = datetime.fromisoformat(started.replace("Z", "+00:00")) if started else datetime.now(timezone.utc)
    duration = float(rec["t"][-1] - rec["t"][0]) if len(rec) > 1 else 0.0

    def at(seconds: float) -> str:
        return _iso(t0 + timedelta(seconds=float(seconds)))

    cam = rec.meta.get("camera", {})
    return {
        "schema_version": SCHEMA_VERSION,
        "session_id": session_id,
        "recording": {
            "modality": "eye",
            "started_at": _iso(t0),
            "ended_at": at(duration),
            "sample_rate_hz": round(quality["effective_fps"], 2) if quality["effective_fps"] == quality["effective_fps"] else None,
            "protocol": rec.meta.get("protocol"),
            "is_synthetic": bool(rec.meta.get("is_synthetic", False)),
            "clock": {"source": "system_utc", "offset_ms": 0},
            "device_info": {
                "kind": "webcam" if rec.meta.get("source") != "synthetic" else "synthetic",
                "camera": cam,
                "illumination": rec.meta.get("illumination", "visible"),
                "software": f"eyetrack {__version__}",
                "host": platform.platform(terse=True),
            },
            "quality": quality,
            "raw_media_stored": False,
        },
        "measurements": [{**m, "t": None} for m in measurements],
        "events": [
            {"t": at(e["t"]), "kind": e["kind"], "task": e["task"],
             "data": {k: v for k, v in e.items() if k not in ("t", "kind", "task")}}
            for e in stim_events
        ],
    }


def write_outputs(directory: str | Path, batch: dict) -> dict[str, Path]:
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    jp = d / "measurements.json"
    jp.write_text(json.dumps(batch, indent=2))
    cp = d / "measurements.csv"
    with open(cp, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "value", "unit", "task", "confidence", "quality_flags"])
        for m in batch["measurements"]:
            w.writerow([m["name"], f"{m['value']:.6g}", m["unit"], m["task"], m["confidence"],
                        ";".join(m["quality_flags"])])
    return {"json": jp, "csv": cp}
