"""Face, eye and iris localisation with MediaPipe Face Landmarker.

Why one module instead of separate face/eye/pupil detectors? MediaPipe's
Face Landmarker finds the face, the 468-point face mesh (which includes eye
corners and eyelids) AND 10 iris landmarks in a single model call. Splitting
that into three modules would only add plumbing.

What it gives us per frame
--------------------------
* iris centre + 4 iris boundary points per eye (landmarks 468-477)
* eye corners and eyelid points (used for eye-in-head position + blink)
* blink blendshapes (eyeBlinkLeft / eyeBlinkRight, 0..1)
* a 4x4 face transformation matrix (head rotation)

What it does NOT give us: the pupil. In visible light a webcam usually
cannot separate a dark pupil from a brown iris, and MediaPipe does not try.
Pupil diameter needs infrared imaging (see docs/EYE_TRACKING.md).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "models" / "face_landmarker.task"

# MediaPipe face-mesh indices. "Right"/"left" are the SUBJECT's eyes.
R_IRIS_CENTER, R_IRIS_RING = 468, (469, 470, 471, 472)
L_IRIS_CENTER, L_IRIS_RING = 473, (474, 475, 476, 477)
R_CORNERS = (33, 133)    # outer, inner
L_CORNERS = (263, 362)   # outer, inner
# Eye-aspect-ratio points: (corner, top1, top2, corner, bottom2, bottom1)
R_EAR = (33, 160, 158, 133, 153, 144)
L_EAR = (362, 385, 387, 263, 373, 380)
HUMAN_IRIS_MM = 11.7  # average horizontal visible iris diameter, roughly constant across adults


@dataclass
class EyeFrame:
    ok: bool
    h: float = math.nan          # eye-in-head horizontal (eye widths)
    v: float = math.nan          # eye-in-head vertical (eye widths)
    ear: float = math.nan
    blink_score: float = math.nan
    iris_px: float = math.nan
    yaw: float = math.nan
    pitch: float = math.nan
    roll: float = math.nan
    brightness: float = math.nan
    pupil_px: float = math.nan     # pupil diameter (near-eye IR camera only)
    pupil_conf: float = math.nan   # pupil detector confidence 0..1 (IR only)
    points: dict | None = None   # pixel coords for drawing overlays


def _ear(p: np.ndarray, idx: tuple[int, ...]) -> float:
    c1, t1, t2, c2, b2, b1 = (p[i] for i in idx)
    width = np.linalg.norm(c1 - c2)
    return float((np.linalg.norm(t1 - b1) + np.linalg.norm(t2 - b2)) / (2.0 * width + 1e-9))


def eye_in_head(iris: np.ndarray, c_a: np.ndarray, c_b: np.ndarray) -> tuple[float, float]:
    """Iris centre relative to the midpoint of the two eye corners.

    Eye corners move with the head, not the eyeball, so measuring the iris
    relative to them cancels most head translation and in-plane head tilt.
    The axis always points toward image-right so both eyes share a sign
    convention. Dividing by eye width makes the value independent of how
    far the person sits from the camera.
    """
    a, b = (c_a, c_b) if c_a[0] < c_b[0] else (c_b, c_a)
    axis = b - a
    width = float(np.linalg.norm(axis))
    ux = axis / (width + 1e-9)
    uy = np.array([-ux[1], ux[0]])  # perpendicular, pointing image-down
    rel = iris - (a + b) / 2.0
    return float(rel @ ux / width), float(rel @ uy / width)


def euler_from_matrix(m: np.ndarray) -> tuple[float, float, float]:
    """Approximate yaw, pitch, roll (degrees) from a 4x4 rotation matrix."""
    r = m[:3, :3]
    sy = math.hypot(r[0, 0], r[1, 0])
    pitch = math.degrees(math.atan2(r[2, 1], r[2, 2]))
    yaw = math.degrees(math.atan2(-r[2, 0], sy))
    roll = math.degrees(math.atan2(r[1, 0], r[0, 0]))
    return yaw, pitch, roll


class EyeLandmarker:
    """Thin wrapper around MediaPipe FaceLandmarker in VIDEO mode."""

    def __init__(self, model_path: str | Path = DEFAULT_MODEL):
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions, vision

        model_path = Path(model_path)
        if not model_path.exists():
            raise FileNotFoundError(
                f"Model not found at {model_path}. Run: bash scripts/download_model.sh"
            )
        self._mp = mp
        options = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model_path)),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
        self._lm = vision.FaceLandmarker.create_from_options(options)
        self._last_ms = -1

    def process(self, bgr: np.ndarray, t_seconds: float) -> EyeFrame:
        ms = int(round(t_seconds * 1000))
        if ms <= self._last_ms:  # MediaPipe requires strictly increasing timestamps
            ms = self._last_ms + 1
        self._last_ms = ms

        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        res = self._lm.detect_for_video(image, ms)
        if not res.face_landmarks:
            return EyeFrame(ok=False)

        hgt, wid = bgr.shape[:2]
        # Convert normalised (0..1) coords to pixels so x and y share a scale.
        p = np.array([[lm.x * wid, lm.y * hgt] for lm in res.face_landmarks[0]])
        if len(p) < 478:
            return EyeFrame(ok=False)  # model without iris landmarks

        hr, vr = eye_in_head(p[R_IRIS_CENTER], p[R_CORNERS[0]], p[R_CORNERS[1]])
        hl, vl = eye_in_head(p[L_IRIS_CENTER], p[L_CORNERS[0]], p[L_CORNERS[1]])

        def iris_d(ring):
            return (np.linalg.norm(p[ring[0]] - p[ring[2]]) + np.linalg.norm(p[ring[1]] - p[ring[3]])) / 2

        blink = math.nan
        if res.face_blendshapes:
            scores = {c.category_name: c.score for c in res.face_blendshapes[0]}
            if "eyeBlinkLeft" in scores:
                blink = (scores["eyeBlinkLeft"] + scores["eyeBlinkRight"]) / 2

        yaw = pitch = roll = math.nan
        if res.facial_transformation_matrixes:
            yaw, pitch, roll = euler_from_matrix(np.asarray(res.facial_transformation_matrixes[0]))

        # Eye-region brightness: a crude lighting check.
        eye_pts = p[[*R_CORNERS, *L_CORNERS, 159, 145, 386, 374]].astype(int)
        x0, y0 = np.clip(eye_pts.min(0) - 10, 0, None)
        x1, y1 = eye_pts.max(0) + 10
        roi = bgr[y0:y1, x0:x1]
        brightness = float(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).mean()) if roi.size else math.nan

        return EyeFrame(
            ok=True,
            h=(hr + hl) / 2, v=(vr + vl) / 2,
            ear=(_ear(p, R_EAR) + _ear(p, L_EAR)) / 2,
            blink_score=blink,
            iris_px=float((iris_d(R_IRIS_RING) + iris_d(L_IRIS_RING)) / 2),
            yaw=yaw, pitch=pitch, roll=roll,
            brightness=brightness,
            points={
                "iris": [p[R_IRIS_CENTER], p[L_IRIS_CENTER]],
                "corners": [p[i] for i in (*R_CORNERS, *L_CORNERS)],
            },
        )

    def close(self) -> None:
        self._lm.close()


def draw_overlay(img: np.ndarray, ef: EyeFrame) -> None:
    if not ef.ok or not ef.points:
        cv2.putText(img, "NO FACE", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        return
    for pt in ef.points["iris"]:
        cv2.circle(img, tuple(int(c) for c in pt), 3, (0, 255, 0), -1)
    for pt in ef.points["corners"]:
        cv2.circle(img, tuple(int(c) for c in pt), 2, (255, 200, 0), -1)
