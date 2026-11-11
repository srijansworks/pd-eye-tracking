"""Synthetic near-eye INFRARED camera frames with known ground truth.

What a glasses-mounted IR eye camera sees (850 nm illumination, IR-pass filter):
skin and sclera look bright, the iris mid-grey (iris colour mostly vanishes in IR),
the pupil very dark ("dark-pupil" setup), plus small saturated glints where the IR
LEDs reflect off the cornea. Eyelids and eyelashes partly cover the pupil.

The eye is modelled as a sphere viewed by a camera slightly below it. A gaze
rotation moves the pupil on the sphere; seen from the camera the round pupil
becomes an ellipse whose short axis points toward the eye centre. Everything
is drawn 4x larger and shrunk (anti-aliasing) so pupil edges are sub-pixel accurate.

Purpose: test the pupil detector BEFORE the glasses exist, against exact truth.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class EyeCamera:
    width: int = 320
    height: int = 240
    px_per_mm: float = 9.0          # ~ a 200-px-wide eye region, like small glasses eye cams
    eye_cx: float = 160.0           # where the eyeball centre projects in the image
    eye_cy: float = 128.0
    camera_tilt_deg: float = 20.0   # camera below the eye, looking up
    pupil_depth_mm: float = 10.5    # eyeball centre -> pupil plane (approx.)
    iris_mm: float = 11.7


@dataclass
class EyeState:
    gaze_x_deg: float = 0.0         # + = toward image right
    gaze_y_deg: float = 0.0         # + = toward image bottom
    pupil_mm: float = 4.0
    lid_open: float = 1.0           # 1 open, 0 closed (blink)


def project(cam: EyeCamera, st: EyeState) -> dict:
    """Ground-truth pupil ellipse in pixels for an eye state."""
    gx, gy = math.radians(st.gaze_x_deg), math.radians(st.gaze_y_deg + cam.camera_tilt_deg)
    # Unit gaze vector (camera looks along +z toward the eye; eye looks along -z).
    d = np.array([math.sin(gx) * math.cos(gy), math.sin(gy), math.cos(gx) * math.cos(gy)])
    tilt = math.radians(cam.camera_tilt_deg)
    cx = cam.eye_cx + cam.px_per_mm * cam.pupil_depth_mm * d[0]
    cy = cam.eye_cy + cam.px_per_mm * cam.pupil_depth_mm * (d[1] - math.sin(tilt))
    cos_view = max(0.05, d[2])                  # foreshortening of the pupil disc
    radial = math.degrees(math.atan2(d[1], d[0])) if abs(d[0]) + abs(d[1]) > 1e-6 else 0.0
    major = st.pupil_mm * cam.px_per_mm
    return {"cx": cx, "cy": cy, "major": major, "minor": major * cos_view,
            "angle": radial + 90.0, "cos_view": cos_view}


def render(cam: EyeCamera, st: EyeState, rng: np.random.Generator | None = None,
           noise: float = 5.0, glints: bool = True, lashes: bool = True) -> tuple[np.ndarray, dict]:
    rng = rng or np.random.default_rng(0)
    S = 4                                        # supersampling factor
    W, H = cam.width * S, cam.height * S
    img = np.full((H, W), 165, np.float32)      # skin (bright in IR)

    truth = project(cam, st)
    ecx, ecy = cam.eye_cx * S, cam.eye_cy * S
    # Sclera: visible eye opening (almond), slightly darker than skin edges.
    cv2.ellipse(img, (int(ecx), int(ecy)), (int(15 * cam.px_per_mm * S), int(7.5 * cam.px_per_mm * S)),
                0, 0, 360, 200, -1, cv2.LINE_AA)
    # Iris (same projection as pupil but bigger), then pupil.
    k = cam.iris_mm / max(st.pupil_mm, 0.1)
    # Sub-pixel drawing: OpenCV's `shift` = fractional bits. A full-res pixel i
    # averages supersampled pixels i*S..i*S+S-1, so full-res coordinate u maps
    # to supersampled X = u*S + (S-1)/2.
    F = 16
    def ss(u):
        return int(round((u * S + (S - 1) / 2) * F))
    cxy = (ss(truth["cx"]), ss(truth["cy"]))
    ax = lambda d: int(round(d * S / 2 * F))
    cv2.ellipse(img, cxy, (ax(truth["major"] * k), ax(truth["minor"] * k)),
                truth["angle"], 0, 360, 120, -1, cv2.LINE_AA, 4)
    cv2.ellipse(img, cxy, (ax(truth["major"]), ax(truth["minor"])),
                truth["angle"], 0, 360, 22, -1, cv2.LINE_AA, 4)
    # Glints: corneal reflections of 2 LEDs; they move ~half as much as the pupil.
    if glints:
        for ox, oy in ((-1.6, 1.2), (1.6, 1.2)):
            gxp = (cam.eye_cx + 0.5 * (truth["cx"] - cam.eye_cx) + ox * cam.px_per_mm) * S
            gyp = (cam.eye_cy + 0.5 * (truth["cy"] - cam.eye_cy) + oy * cam.px_per_mm) * S
            cv2.circle(img, (int(gxp), int(gyp)), int(0.35 * cam.px_per_mm * S), 255, -1, cv2.LINE_AA)
    # Upper eyelid: everything above a curved lid edge becomes skin.
    open_px = 7.5 * cam.px_per_mm * S
    lid_y = ecy - open_px * (2 * st.lid_open - 1)          # lid_open 1 -> top of opening; 0 -> bottom
    xs = np.arange(W)
    edge = lid_y + (((xs - ecx) / (15 * cam.px_per_mm * S)) ** 2) * open_px * 0.6
    yy = np.arange(H)[:, None]
    lid_mask = yy < edge[None, :]
    img[lid_mask] = 160
    if lashes and st.lid_open > 0.05:
        for x0 in range(int(ecx - 13 * cam.px_per_mm * S), int(ecx + 13 * cam.px_per_mm * S), int(1.1 * cam.px_per_mm * S)):
            y0 = int(edge[min(max(x0, 0), W - 1)])
            cv2.line(img, (x0, y0), (x0 + int(rng.integers(-6, 6) * S / 2), y0 + int(2.2 * cam.px_per_mm * S)),
                     40, max(1, S), cv2.LINE_AA)
    img = cv2.resize(img, (cam.width, cam.height), interpolation=cv2.INTER_AREA)
    # Illumination falloff + sensor noise.
    yv, xv = np.mgrid[0:cam.height, 0:cam.width]
    vign = 1 - 0.25 * (((xv - cam.width / 2) / cam.width) ** 2 + ((yv - cam.height / 2) / cam.height) ** 2) * 4
    img = img * vign + rng.normal(0, noise, img.shape)
    out = np.clip(img, 0, 255).astype(np.uint8)

    # How much of the pupil is uncovered by the lid (truth for "is the pupil visible").
    pm = np.zeros((cam.height, cam.width), np.uint8)
    cv2.ellipse(pm, (int(truth["cx"]), int(truth["cy"])), (max(1, int(truth["major"] / 2)), max(1, int(truth["minor"] / 2))),
                truth["angle"], 0, 360, 1, -1)
    lid_small = cv2.resize(lid_mask.astype(np.uint8), (cam.width, cam.height), interpolation=cv2.INTER_NEAREST).astype(bool)
    area = pm.sum()
    truth["visible_fraction"] = float((pm.astype(bool) & ~lid_small).sum() / area) if area else 0.0
    truth["pupil_px"] = truth["major"]
    return out, truth
