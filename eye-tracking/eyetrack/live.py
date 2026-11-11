"""Live webcam sessions: a camera check, and the full stimulus recording.

Privacy default: only derived numbers (iris positions, blink scores, head
angles) are kept. Raw video is written only with --save-video AND
--consent-confirmed, and never leaves the machine unless you move it.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from .camera import Camera
from .landmarks import EyeLandmarker, draw_overlay
from .recording import Recording
from .stimulus import ScreenGeometry, eye_v1, render

WIN = "eyetrack"


def _row(tf: float, ef, task: str, target: tuple[float, float] | None) -> dict:
    return {
        "t": tf, "frame_ok": 1.0 if ef.ok else 0.0, "h": ef.h, "v": ef.v,
        "gx": np.nan, "gy": np.nan, "ear": ef.ear, "blink_score": ef.blink_score,
        "iris_px": ef.iris_px, "yaw": ef.yaw, "pitch": ef.pitch, "roll": ef.roll,
        "brightness": ef.brightness, "task": task,
        "target_x": target[0] if target else np.nan, "target_y": target[1] if target else np.nan,
    }


def check_camera(index: int = 0, seconds: float = 10.0, show: bool = True) -> dict:
    """Run face/iris tracking for a few seconds and report whether the setup is usable."""
    cam = Camera(index).start()
    lm = EyeLandmarker()
    rows, t_start = [], time.monotonic()
    try:
        while time.monotonic() - t_start < seconds:
            for fr in cam.frames():
                ef = lm.process(fr.image, fr.t)
                rows.append(_row(fr.t - t_start, ef, "check", None))
                if show:
                    img = fr.image.copy()
                    draw_overlay(img, ef)
                    txt = (f"iris {ef.iris_px:.0f}px  bright {ef.brightness:.0f}  EAR {ef.ear:.3f}  "
                           f"blink {ef.blink_score:.2f}") if ef.ok else ""
                    cv2.putText(img, txt, (20, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                    cv2.putText(img, "BLINK SLOWLY 3 TIMES during this check", (20, 120),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                    cv2.imshow(WIN, img)
            if show and (cv2.waitKey(1) & 0xFF) == 27:
                break
            time.sleep(0.002)
    finally:
        info, dropped = cam.info, cam.dropped
        cam.stop(); lm.close()
        if show:
            cv2.destroyAllWindows()

    rec = Recording.from_rows(rows)
    ok = rec["frame_ok"] == 1
    rep = {
        "camera": info,
        "frames": len(rec),
        "effective_fps": round(rec.fps, 1) if len(rec) > 1 else 0,
        "face_found_fraction": round(float(ok.mean()), 3) if len(rec) else 0,
        "iris_diameter_px_median": round(float(np.nanmedian(rec["iris_px"][ok])), 1) if ok.any() else None,
        "eye_brightness_median": round(float(np.nanmedian(rec["brightness"][ok])), 1) if ok.any() else None,
        "h_noise_sd": round(float(np.nanstd(np.diff(rec["h"][ok]))), 5) if ok.sum() > 2 else None,
        "dropped_frames": dropped,
    }
    # Blink self-test: the user is asked to blink 3 times. If the tracker sees none,
    # blink measurements from this setup can't be trusted.
    from . import events as ev
    closed = ev.closed_eye_mask(rec["blink_score"], rec["ear"], rec["frame_ok"])
    rep["blinks_detected"] = len(ev.detect_blinks(rec["t"], closed)) if len(rec) > 1 else 0
    rep["deepest_ear_dip"] = round(ev.ear_dip_depth(rec["ear"], rec["frame_ok"]), 3) if len(rec) > 10 else None
    rep["blink_score_max"] = round(float(np.nanmax(rec["blink_score"][ok])), 3) if ok.any() else None
    adv = []
    if rep["effective_fps"] < 25:
        adv.append("Frame rate below 25 fps: improve lighting (auto-exposure lengthens frames in dim light).")
    if rep["face_found_fraction"] < 0.95:
        adv.append("Face lost in >5% of frames: face the camera, remove backlight, keep the whole face in view.")
    if rep["iris_diameter_px_median"] is not None and rep["iris_diameter_px_median"] < 20:
        adv.append("Iris < 20 px across: sit closer (~45-55 cm) or use a higher-resolution camera.")
    if rep["eye_brightness_median"] is not None and rep["eye_brightness_median"] < 60:
        adv.append("Eye region is dark: add a lamp in front of you (not behind).")
    if rep["blinks_detected"] < 2:
        adv.append("Fewer than 2 blinks detected although you were asked to blink 3 times: "
                   "blink measurements are NOT reliable with this setup (see deepest_ear_dip; "
                   "a real blink should dip well below 0.7).")
    rep["advice"] = adv or ["Setup looks usable for webcam-grade measurements."]
    rep["frames_raw"] = rec  # caller may save it
    return rep


def record(out_dir: str | Path, index: int = 0, screen_width_cm: float = 30.4,
           distance_cm: float = 55.0, seed: int = 0, save_video: bool = False,
           participant_label: str = "") -> Recording:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cam = Camera(index).start()
    lm = EyeLandmarker()

    cv2.namedWindow(WIN, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WIN, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.imshow(WIN, np.zeros((10, 10, 3), np.uint8)); cv2.waitKey(300)
    _, _, w, h = cv2.getWindowImageRect(WIN)
    if w < 200 or h < 200:
        w, h = 1440, 900
    geom = ScreenGeometry(w, h, screen_width_cm, distance_cm)
    mx, my = geom.max_deg()
    proto = eye_v1(amp_x=min(10.0, mx - 2), amp_y=min(7.0, my - 2), seed=seed)

    writer = None
    rows: list[dict] = []
    stim_events: list[dict] = []
    try:
        # ---- 1. positioning screen ------------------------------------
        while True:
            frames = cam.frames()
            if frames:
                fr = frames[-1]
                ef = lm.process(fr.image, fr.t)
                prev = fr.image.copy(); draw_overlay(prev, ef)
                canvas = np.zeros((h, w, 3), np.uint8)
                ph = min(h - 200, int(prev.shape[0] * (w * 0.6) / prev.shape[1]))
                pw = int(prev.shape[1] * ph / prev.shape[0])
                canvas[50:50 + ph, (w - pw) // 2:(w - pw) // 2 + pw] = cv2.resize(prev, (pw, ph))
                status = (f"face OK  iris {ef.iris_px:.0f}px  brightness {ef.brightness:.0f}  "
                          f"head yaw {ef.yaw:+.0f} pitch {ef.pitch:+.0f}") if ef.ok else "NO FACE"
                for i, line in enumerate([status,
                                          f"Sit {distance_cm:.0f} cm from the screen, keep your head still.",
                                          "Follow the dot with your EYES only. SPACE = start, ESC = quit."]):
                    cv2.putText(canvas, line, (40, h - 110 + 35 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                                (0, 255, 0) if (i == 0 and ef.ok) else (200, 200, 200), 2)
                cv2.imshow(WIN, canvas)
            k = cv2.waitKey(1) & 0xFF
            if k == 27:
                raise KeyboardInterrupt
            if k == 32:
                break

        if save_video:
            info = cam.info
            writer = cv2.VideoWriter(str(out_dir / "raw_video.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
                                     30, (info["width"], info["height"]))

        # ---- 2. protocol ----------------------------------------------
        cam.frames()  # discard frames from the positioning phase
        t_start = time.monotonic()
        started_utc = datetime.now(timezone.utc)
        shown = None
        while True:
            now = time.monotonic() - t_start
            seg, tl = proto.at(now)
            if seg is None:
                break
            tx, ty = seg.target(tl)
            cv2.imshow(WIN, render(geom, tx, ty))
            if (cv2.waitKey(1) & 0xFF) == 27:
                raise KeyboardInterrupt
            t_disp = time.monotonic() - t_start
            # Log the ACTUAL time each target change reached the screen (not the
            # scheduled time) — this is what saccade latency is measured from.
            key = (seg.task, round(tx, 3), round(ty, 3)) if not seg.pursuit else (seg.task, "pursuit")
            if key != shown:
                if seg.pursuit:
                    stim_events.append({"t": t_disp, "task": seg.task, "kind": "pursuit_start",
                                        "amplitude_deg": seg.pursuit[0], "freq_hz": seg.pursuit[1]})
                else:
                    prev_xy = (shown[1], shown[2]) if shown and shown[0] == seg.task else (None, None)
                    stim_events.append({"t": t_disp, "task": seg.task, "kind": "target_step",
                                        "x_deg": tx, "y_deg": ty,
                                        "from_x_deg": prev_xy[0], "from_y_deg": prev_xy[1]})
                shown = key
            for fr in cam.frames():
                tf = fr.t - t_start
                ef = lm.process(fr.image, fr.t)
                fseg, ftl = proto.at(tf)
                rows.append(_row(tf, ef, fseg.task if fseg else "", fseg.target(ftl) if fseg else None))
                if writer is not None:
                    writer.write(fr.image)
    finally:
        info, dropped = cam.info, cam.dropped
        cam.stop(); lm.close()
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()

    meta = {
        "source": "webcam", "protocol": proto.name, "seed": seed,
        "started_at_utc": started_utc.isoformat().replace("+00:00", "Z"),
        "camera": {**info, "index": index}, "dropped_frames": dropped,
        "screen": {"width_px": w, "height_px": h, "width_cm": screen_width_cm, "distance_cm": distance_cm},
        "illumination": "visible", "participant_label": participant_label,
        "raw_video_saved": bool(save_video), "stimulus_events": stim_events, "is_synthetic": False,
    }
    rec = Recording.from_rows(rows, meta)
    rec.save(out_dir)
    return rec


def process_video(path: str, out_dir: str | Path) -> Recording:
    """Run the tracker on an existing video file (no stimulus → uncalibrated)."""
    from .camera import video_frames

    lm = EyeLandmarker()
    rows = []
    for fr in video_frames(path):
        ef = lm.process(fr.image, fr.t)
        rows.append(_row(fr.t, ef, "video", None))
    lm.close()
    rec = Recording.from_rows(rows, {"source": "video", "video_file": Path(path).name,
                                     "stimulus_events": [], "is_synthetic": False})
    rec.save(out_dir)
    return rec
