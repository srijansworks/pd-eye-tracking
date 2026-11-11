"""Command-line entry point:  eyetrack <command> ...

  check-camera   10-second tracking test; prints fps, iris size, lighting, advice
  record         run the eye_v1 stimulus protocol with the webcam, then analyze
  analyze        (re)compute measurements + plot for a saved recording folder
  video          run the tracker on a video file (uncalibrated)
  simulate       make a synthetic recording with known ground truth
  benchmark      synthetic truth-vs-measured table at several frame rates
  upload         send measurements.json to the backend API
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import calibration, features
from .export import build_batch, write_outputs
from .recording import Recording


def analyze(rec_dir: str | Path, session_id: str | None = None, plot: bool = True) -> dict:
    rec_dir = Path(rec_dir)
    rec = Recording.load(rec_dir)
    stim = rec.meta.get("stimulus_events", [])
    cal = calibration.fit(rec, stim)
    if cal:
        calibration.apply(rec, cal)
        rec.save(rec_dir)  # persist gx/gy
    ms, q = features.compute(rec, stim)
    batch = build_batch(rec, ms, q, stim, session_id=session_id)
    paths = write_outputs(rec_dir, batch)
    if plot:
        from .plot import plot_recording
        paths["plot"] = plot_recording(rec, rec_dir / "plot.png", stim)
    _print_summary(ms, q)
    print("\nWrote:", ", ".join(str(p) for p in paths.values()))
    return batch


def _print_summary(ms: list[dict], q: dict) -> None:
    print(f"\nQuality: {q['valid_frame_fraction']:.1%} valid frames, {q['effective_fps']:.1f} fps, "
          f"flags={q['flags']}")
    print(f"{'measurement':34s} {'value':>10s}  unit        conf  flags")
    for m in ms:
        print(f"{m['name']:34s} {m['value']:10.3f}  {m['unit']:10s}  {m['confidence']:.2f}  "
              f"{','.join(m['quality_flags'])}")


def benchmark() -> None:
    from .synthetic import simulate

    rows = [("saccade_latency_median", "latency_median_ms"),
            ("saccade_peak_velocity_median", "peak_velocity_median_deg_s"),
            ("saccade_gain_median", "saccade_gain"),
            ("pursuit_velocity_gain", "pursuit_gain"),
            ("pursuit_phase_lag", "pursuit_lag_ms"),
            ("blink_duration_mean", "blink_duration_ms"),
            ("square_wave_jerk_rate", None)]
    setups = [("webcam 30fps", 30, 0.5), ("webcam 60fps", 60, 0.4),
              ("IR 120fps", 120, 0.15), ("IR 250fps", 250, 0.08), ("lab 500fps", 500, 0.03)]
    results = {}
    for label, fps, noise in setups:
        vals = {}
        for seed in range(1, 6):  # average 5 synthetic participants
            rec, stim, truth = simulate(fps=fps, noise_deg=noise, seed=seed)
            c = calibration.fit(rec, stim); calibration.apply(rec, c)
            ms, _ = features.compute(rec, stim)
            d = {m["name"]: m["value"] for m in ms}
            truth["square_wave_jerk_rate"] = truth["swj_count"] / (13.0 / 60)
            for name, tkey in rows:
                vals.setdefault(name, []).append((d.get(name, float("nan")), truth[tkey or name]))
        results[label] = vals
    print("Synthetic benchmark: measured / true (mean of 5 synthetic participants)\n")
    print(f"{'measurement':30s}" + "".join(f"{s[0]:>18s}" for s in setups))
    import numpy as np
    for name, _ in rows:
        line = f"{name:30s}"
        for label, *_ in setups:
            m = np.nanmean([a for a, _ in results[label][name]])
            t = np.mean([b for _, b in results[label][name]])
            line += f"{m:9.2f}/{t:<8.2f}"
        print(line)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="eyetrack", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check-camera"); c.add_argument("--camera", type=int, default=0)
    c.add_argument("--seconds", type=float, default=10); c.add_argument("--no-window", action="store_true")
    c.add_argument("--save", help="folder to save the tracked samples")
    c.add_argument("--camera-type", choices=["webcam", "ir"], default="webcam")

    r = sub.add_parser("record")
    r.add_argument("--out", required=True)
    r.add_argument("--camera", type=int, default=0)
    r.add_argument("--screen-width-cm", type=float, required=True,
                   help="physical width of the visible screen area")
    r.add_argument("--distance-cm", type=float, default=55.0, help="eye-to-screen distance")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--label", default="", help="pseudonymous label only — never a real name")
    r.add_argument("--save-video", action="store_true")
    r.add_argument("--consent-confirmed", action="store_true",
                   help="required with --save-video: participant agreed to raw video storage")
    r.add_argument("--camera-type", choices=["webcam", "ir"], default="webcam",
                   help="'ir' = near-eye infrared camera on the glasses")
    r.add_argument("--mm-per-px", type=float, help="IR camera scale (from a ruler/calibration) to report pupil in mm")

    a = sub.add_parser("analyze"); a.add_argument("dir"); a.add_argument("--session-id")
    v = sub.add_parser("video"); v.add_argument("file"); v.add_argument("--out", required=True)
    v.add_argument("--camera-type", choices=["webcam", "ir"], default="webcam")
    v.add_argument("--mm-per-px", type=float)
    sg = sub.add_parser("simulate-glasses", help="synthetic near-eye IR recording through the real pupil detector")
    sg.add_argument("--out", required=True); sg.add_argument("--fps", type=float, default=120)
    sg.add_argument("--seed", type=int, default=1)
    s = sub.add_parser("simulate"); s.add_argument("--out", required=True)
    s.add_argument("--fps", type=float, default=30); s.add_argument("--noise-deg", type=float, default=0.4)
    s.add_argument("--seed", type=int, default=1)
    sub.add_parser("benchmark")
    u = sub.add_parser("upload"); u.add_argument("dir")
    g = u.add_mutually_exclusive_group(required=True)
    g.add_argument("--session-id"); g.add_argument("--participant", help="participant code, creates a session")

    args = p.parse_args(argv)

    if args.cmd == "check-camera":
        from .live import check_camera
        rep = check_camera(args.camera, args.seconds, show=not args.no_window, camera_type=args.camera_type)
        rec = rep.pop("frames_raw")
        if args.save:
            rec.save(args.save)
        print(json.dumps(rep, indent=2))
    elif args.cmd == "record":
        if args.save_video and not args.consent_confirmed:
            sys.exit("--save-video requires --consent-confirmed (raw facial video is identifiable).")
        from .live import record
        record(args.out, args.camera, args.screen_width_cm, args.distance_cm, args.seed,
               args.save_video, args.label, camera_type=args.camera_type, mm_per_px=args.mm_per_px)
        analyze(args.out)
    elif args.cmd == "analyze":
        analyze(args.dir, args.session_id)
    elif args.cmd == "video":
        from .live import process_video
        process_video(args.file, args.out, camera_type=args.camera_type, mm_per_px=args.mm_per_px)
        analyze(args.out)
    elif args.cmd == "simulate-glasses":
        from .nearir.simulate import simulate_ir
        rec, stim, truth = simulate_ir(fps=args.fps, seed=args.seed)
        rec.save(args.out)
        Path(args.out, "truth.json").write_text(json.dumps(truth, indent=2))
        analyze(args.out)
        print("\nGround truth:", json.dumps(truth, indent=2))
    elif args.cmd == "simulate":
        from .synthetic import simulate
        rec, stim, truth = simulate(fps=args.fps, noise_deg=args.noise_deg, seed=args.seed)
        rec.save(args.out)
        Path(args.out, "truth.json").write_text(json.dumps(truth, indent=2))
        analyze(args.out)
        print("\nGround truth:", json.dumps(truth, indent=2))
    elif args.cmd == "benchmark":
        benchmark()
    elif args.cmd == "upload":
        from .upload import create_session, upload_batch
        path = Path(args.dir, "measurements.json")
        batch = json.loads(path.read_text())
        if args.session_id:
            batch["session_id"] = args.session_id
        elif not batch.get("session_id"):
            batch["session_id"] = create_session(args.participant, batch["recording"].get("protocol") or "eye_v1")
        else:
            print(f"Reusing session {batch['session_id']} saved from a previous upload.")
        # Save the session id so re-running upload is a safe retry, not a new session.
        path.write_text(json.dumps(batch, indent=2))
        print(json.dumps(upload_batch(batch), indent=2))


if __name__ == "__main__":
    main()
