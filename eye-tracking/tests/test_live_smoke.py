"""Headless smoke test of the live recording loop (live.record).

The real loop needs a webcam, a face and a screen. Here the camera, the
MediaPipe tracker and the OpenCV window are replaced with fakes, and the
protocol is shortened, so the whole loop runs in a couple of seconds:
positioning screen -> protocol with drift checks -> posture warning -> files.
"""

import time

import numpy as np

from eyetrack import live
from eyetrack.landmarks import EyeFrame
from eyetrack.recording import Recording
from eyetrack.stimulus import Protocol, Segment


class FakeCam:
    def __init__(self, *_a, **_k):
        self.info, self.dropped = {"width": 640, "height": 480, "fps_reported": 30.0}, 0
        self._last = time.monotonic()

    def start(self):
        return self

    def frames(self):
        now, out = time.monotonic(), []
        while self._last + 1 / 30 <= now:  # deliver frames at 30 fps
            self._last += 1 / 30
            out.append(type("F", (), {"t": self._last, "image": np.zeros((480, 640, 3), np.uint8)}))
        return out

    def stop(self):
        pass


class FakeLandmarker:
    """Head pitch creeps up 10 deg during the prosaccade task -> should trigger a warning."""
    t0 = None

    def process(self, _img, t):
        FakeLandmarker.t0 = FakeLandmarker.t0 or t
        el = t - FakeLandmarker.t0
        pitch = 8.0 + (10.0 * min(1.0, max(0.0, (el - 1.0) / 0.6)) if el > 1.0 else 0.0)
        return EyeFrame(ok=True, h=0.01, v=-0.03, ear=0.3, blink_score=0.05, iris_px=30, yaw=0.0,
                        pitch=pitch, roll=0.0, brightness=100.0, points=None)

    def close(self):
        pass


def test_record_loop_runs_end_to_end(tmp_path, monkeypatch):
    keys = iter([-1, 32])  # first waitKey is the window warm-up; then SPACE on the positioning screen
    monkeypatch.setattr(live, "Camera", FakeCam)
    monkeypatch.setattr(live, "EyeLandmarker", FakeLandmarker)
    monkeypatch.setattr(live.cv2, "namedWindow", lambda *a, **k: None)
    monkeypatch.setattr(live.cv2, "setWindowProperty", lambda *a, **k: None)
    monkeypatch.setattr(live.cv2, "imshow", lambda *a, **k: None)
    monkeypatch.setattr(live.cv2, "destroyAllWindows", lambda *a, **k: None)
    monkeypatch.setattr(live.cv2, "getWindowImageRect", lambda *a: (0, 0, 1440, 900))
    monkeypatch.setattr(live.cv2, "waitKey", lambda *_a: next(keys, -1))
    short = Protocol("eye_v2", [
        Segment("calibration", 0.6, [(0.0, 0, 0), (0.2, -10, 0), (0.4, 10, 0)]),
        Segment("drift_check", 0.3, [(0.0, 0, 0), (0.1, -10, 0), (0.2, 10, 0)]),
        Segment("prosaccade", 0.9, [(0.0, 0, 0), (0.4, 10, 0)]),
        Segment("drift_check", 0.3, [(0.0, 0, 0), (0.1, -10, 0), (0.2, 10, 0)]),
        Segment("pursuit", 0.4, pursuit=(10, 0.4)),
    ])
    monkeypatch.setattr(live, "eye_v2", lambda **_k: short)

    rec = live.record(tmp_path, screen_width_cm=28, distance_cm=50)

    back = Recording.load(tmp_path)
    assert len(back) == len(rec) > 40                      # ~2.5 s at 30 fps
    assert set(back["task"]) >= {"calibration", "drift_check", "prosaccade", "pursuit"}
    kinds = [e["kind"] for e in back.meta["stimulus_events"]]
    assert kinds.count("target_step") >= 9 and "pursuit_start" in kinds
    assert "posture_warning_start" in kinds                # head crept up during prosaccade
    assert back.meta["protocol"] == "eye_v2" and back.meta["raw_video_saved"] is False
