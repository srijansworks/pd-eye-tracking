"""Dark-pupil detector for near-eye infrared images (the glasses camera).

Same family of method as the Pupil Labs 2D detector and Świrski et al. (2012):

  1. COARSE: the pupil is the darkest compact blob. Threshold the blurred
     image just above its darkest level, remove thin dark lines (eyelashes)
     with a morphological opening, and pick the most pupil-like blob
     (size, roundness, darkness, closeness to last frame's pupil).
  2. GLINTS: bright LED reflections punch holes in the pupil; a closing
     fills them so they don't bend the outline.
  3. EDGES: edge pixels on the blob's border, ignoring pixels next to glints
     and next to the upper eyelid, are the pupil outline candidates.
  4. ROBUST ELLIPSE: RANSAC — fit ellipses to random 5-point subsets, keep
     the one most edge points agree with, refit on those. Eyelid / lash
     edges that don't belong to the pupil are rejected as outliers.
  5. CONFIDENCE: fraction of the fitted ellipse's outline supported by real
     edges (like Pupil Labs' "confidence"). A half-covered pupil gets ~0.5.

Outputs pupil centre (px), axes (px) and angle, with sub-pixel precision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class Pupil:
    ok: bool
    cx: float = math.nan
    cy: float = math.nan
    major: float = math.nan      # long axis = pupil diameter in px (not foreshortened)
    minor: float = math.nan
    angle: float = math.nan
    confidence: float = 0.0


@dataclass
class PupilDetectorConfig:
    min_diameter_px: float = 8.0
    max_diameter_px: float = 120.0
    dark_margin: float = 28.0          # threshold = darkest level + margin
    ransac_iters: int = 80
    inlier_px: float = 1.5
    min_confidence: float = 0.35
    # From a glasses camera within about +-25 deg of gaze, the pupil's short/long
    # axis ratio stays above ~0.6 (cosine of the viewing angle). Thinner "ellipses"
    # are slivers of a pupil cut off by the eyelid, so they are rejected.
    min_aspect: float = 0.55


def _ellipse_residual(pts: np.ndarray, e) -> np.ndarray:
    """Approximate geometric distance (px) of points to an OpenCV ellipse."""
    (cx, cy), (w, h), ang = e
    a, b = max(w, 1e-6) / 2, max(h, 1e-6) / 2
    t = math.radians(ang)
    c, s = math.cos(t), math.sin(t)
    x, y = pts[:, 0] - cx, pts[:, 1] - cy
    xr, yr = x * c + y * s, -x * s + y * c
    r = np.sqrt((xr / a) ** 2 + (yr / b) ** 2)
    return np.abs(r - 1) * min(a, b)


def _support(edges: np.ndarray, e, tol: float = 1.5) -> float:
    """Fraction of points sampled on the ellipse that lie near an edge pixel."""
    (cx, cy), (w, h), ang = e
    th = np.linspace(0, 2 * np.pi, 72, endpoint=False)
    t = math.radians(ang)
    xs = cx + (w / 2) * np.cos(th) * math.cos(t) - (h / 2) * np.sin(th) * math.sin(t)
    ys = cy + (w / 2) * np.cos(th) * math.sin(t) + (h / 2) * np.sin(th) * math.cos(t)
    dist = cv2.distanceTransform((edges == 0).astype(np.uint8), cv2.DIST_L2, 3)
    xi, yi = np.round(xs).astype(int), np.round(ys).astype(int)
    inside = (xi >= 0) & (yi >= 0) & (xi < edges.shape[1]) & (yi < edges.shape[0])
    if not inside.any():
        return 0.0
    return float((dist[yi[inside], xi[inside]] <= tol).sum() / len(th))


class PupilDetector:
    def __init__(self, cfg: PupilDetectorConfig | None = None, seed: int = 0):
        self.cfg = cfg or PupilDetectorConfig()
        self.prev: Pupil | None = None
        self.recent_major: list[float] = []
        self.rng = np.random.default_rng(seed)

    def detect(self, gray: np.ndarray) -> Pupil:
        cfg = self.cfg
        if gray.ndim == 3:
            gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)

        # ---- 1. coarse dark-blob search --------------------------------
        darkest = float(np.percentile(blur, 0.2))
        mask = (blur < darkest + cfg.dark_margin).astype(np.uint8)
        k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k_open)      # removes eyelashes (thin)
        k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k_close)    # fills glint holes
        n, lab, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
        best, best_score = None, -1e9
        min_area = math.pi * (cfg.min_diameter_px / 2) ** 2 * 0.3
        max_area = math.pi * (cfg.max_diameter_px / 2) ** 2
        for i in range(1, n):
            area = stats[i, cv2.CC_STAT_AREA]
            if not (min_area <= area <= max_area):
                continue
            w, h = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
            fill = area / float(w * h)                                # ~0.785 for an ellipse
            aspect = min(w, h) / max(w, h)
            score = -abs(fill - 0.785) * 4 + aspect + 0.002 * area ** 0.5
            if self.prev is not None and self.prev.ok:
                score -= 0.01 * math.hypot(cents[i][0] - self.prev.cx, cents[i][1] - self.prev.cy)
            if score > best_score:
                best, best_score = i, score
        if best is None:
            self.prev = Pupil(False)
            return self.prev

        # ---- 2/3. edges on the blob outline ----------------------------
        x, y, w, h = (stats[best, j] for j in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP, cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
        pad = int(max(w, h) * 0.4) + 4
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(gray.shape[1], x + w + pad), min(gray.shape[0], y + h + pad)
        roi = blur[y0:y1, x0:x1]
        blob = (lab[y0:y1, x0:x1] == best).astype(np.uint8)
        hi = float(np.median(roi[blob == 0])) if (blob == 0).any() else 255.0
        lo = float(np.median(roi[blob == 1]))
        edges = cv2.Canny(roi, max(5.0, 0.3 * (hi - lo)), max(10.0, 0.6 * (hi - lo)))
        near_border = cv2.dilate(blob, np.ones((5, 5), np.uint8)) - cv2.erode(blob, np.ones((5, 5), np.uint8))
        glint = cv2.dilate((roi > 225).astype(np.uint8), np.ones((7, 7), np.uint8))
        edges = edges * near_border * (1 - glint)
        pts = np.column_stack(np.nonzero(edges)[::-1]).astype(np.float32)
        if len(pts) < 8:
            contours, _ = cv2.findContours(blob, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            pts = max(contours, key=len).reshape(-1, 2).astype(np.float32) if contours else pts
        if len(pts) < 6:
            self.prev = Pupil(False)
            return self.prev

        # ---- 4. RANSAC ellipse ------------------------------------------
        best_e, best_inl = None, None
        for _ in range(cfg.ransac_iters):
            sample = pts[self.rng.choice(len(pts), 5, replace=False)]
            try:
                e = cv2.fitEllipse(sample)
            except cv2.error:
                continue
            (_, _), (ew, eh), _ = e
            if not (cfg.min_diameter_px <= max(ew, eh) <= cfg.max_diameter_px) or min(ew, eh) < cfg.min_aspect * max(ew, eh):
                continue
            inl = _ellipse_residual(pts, e) < cfg.inlier_px
            if best_inl is None or inl.sum() > best_inl.sum():
                best_e, best_inl = e, inl
        if best_e is None or best_inl.sum() < 6:
            self.prev = Pupil(False)
            return self.prev
        e = cv2.fitEllipse(pts[best_inl])
        (cx, cy), (ew, eh), ang = e
        if min(ew, eh) < cfg.min_aspect * max(ew, eh):
            self.prev = Pupil(False)
            return self.prev

        # ---- 5. confidence ---------------------------------------------
        conf = _support(edges, e)
        # Occlusion check: how much of the fitted ellipse is actually dark pupil?
        # A pupil half under the eyelid gives an ellipse whose top is bright skin.
        fill = np.zeros_like(blob)
        cv2.ellipse(fill, ((cx, cy), (ew * 0.9, eh * 0.9), ang), 1, -1)
        dark_inside = (roi < lo + 0.5 * (hi - lo)) & (fill == 1)
        visible = float(dark_inside.sum() / max(1, fill.sum()))
        conf *= min(1.0, visible / 0.9)
        major = max(ew, eh)
        # Video prior: pupil size changes slowly (< ~25% between frames even
        # during the light reflex at >= 30 fps). A sudden jump = a bad fit.
        if self.recent_major:
            ref = float(np.median(self.recent_major))
            if abs(major / ref - 1) > 0.25:
                conf *= 0.3
        res = Pupil(ok=conf >= cfg.min_confidence, cx=cx + x0, cy=cy + y0,
                    major=major, minor=min(ew, eh), angle=ang, confidence=conf)
        if res.ok:
            self.recent_major = (self.recent_major + [major])[-15:]
        self.prev = res
        return res

    def reset(self) -> None:
        """Forget temporal state (new recording / independent images)."""
        self.prev, self.recent_major = None, []
