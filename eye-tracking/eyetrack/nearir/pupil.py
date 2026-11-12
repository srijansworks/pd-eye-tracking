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
    min_contrast: float = 35.0       # grey levels darker than the surrounding iris for full confidence


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
        self.prior_rejects = 0
        self.rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------
    def _candidates(self, blur: np.ndarray) -> list[tuple[float, np.ndarray, tuple[int, int, int, int], float]]:
        """Dark compact blobs at SEVERAL darkness levels.

        One threshold fails when mascara/eyelashes are darker than the pupil (seen in
        real LPW videos): the pupil then never enters the mask. Trying several
        margins above the darkest level and scoring every blob fixes that.
        """
        cfg = self.cfg
        H, W = blur.shape
        # Scale-aware minimum size: tiny lash clumps are not pupils.
        min_d = max(cfg.min_diameter_px, 0.02 * W)
        min_area = math.pi * (min_d / 2) ** 2 * 0.5
        max_area = math.pi * (cfg.max_diameter_px / 2) ** 2
        k_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5) if W < 400 else (7, 7))
        k_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
        darkest = float(np.percentile(blur, 0.2))
        out = []
        for margin in (cfg.dark_margin * 0.7, cfg.dark_margin, cfg.dark_margin * 1.6, cfg.dark_margin * 2.4):
            mask = (blur < darkest + margin).astype(np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k_open)      # removes thin eyelashes
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k_close)    # fills glint holes
            n, lab, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
            for i in range(1, n):
                area = stats[i, cv2.CC_STAT_AREA]
                if not (min_area <= area <= max_area):
                    continue
                x, y, w, h = (int(stats[i, j]) for j in (cv2.CC_STAT_LEFT, cv2.CC_STAT_TOP,
                                                          cv2.CC_STAT_WIDTH, cv2.CC_STAT_HEIGHT))
                fill = area / float(w * h)                            # ~0.785 for an ellipse
                aspect = min(w, h) / max(w, h)
                if fill < 0.5 or aspect < cfg.min_aspect * 0.9:
                    continue
                blob = (lab[y:y + h, x:x + w] == i)
                # Contrast: a pupil is clearly darker than the ring of iris around it.
                pad = max(3, int(0.3 * max(w, h)))
                X0, Y0, X1, Y1 = max(0, x - pad), max(0, y - pad), min(W, x + w + pad), min(H, y + h + pad)
                big = blur[Y0:Y1, X0:X1]
                inner = np.zeros(big.shape, bool)
                inner[y - Y0:y - Y0 + h, x - X0:x - X0 + w] = blob
                ring = cv2.dilate(inner.astype(np.uint8), np.ones((2 * pad + 1, 2 * pad + 1), np.uint8)).astype(bool) & ~inner
                contrast = float(np.median(big[ring]) - np.median(big[inner])) if ring.any() else 0.0
                score = (-abs(fill - 0.785) * 4 + aspect + contrast / 40.0 + 0.25 * math.log(area))
                if self.prev is not None and self.prev.ok and self.prev.confidence >= 0.7:   # trust only good history
                    score -= 0.01 * math.hypot(cents[i][0] - self.prev.cx, cents[i][1] - self.prev.cy)
                out.append((score, lab == i, (x, y, w, h), contrast))
        # De-duplicate (the same pupil appears at several thresholds): keep best per location.
        out.sort(key=lambda c: -c[0])
        kept: list = []
        for c in out:
            cx, cy = c[2][0] + c[2][2] / 2, c[2][1] + c[2][3] / 2
            if all(math.hypot(cx - (k[2][0] + k[2][2] / 2), cy - (k[2][1] + k[2][3] / 2)) > 0.5 * max(k[2][2], k[2][3])
                   for k in kept):
                kept.append(c)
            if len(kept) >= 3:
                break
        return kept

    def _refine(self, blur: np.ndarray, mask_full: np.ndarray, bbox) -> tuple | None:
        """Edges on the blob outline -> RANSAC ellipse -> confidence. Returns (Pupil-ish tuple)."""
        cfg = self.cfg
        x, y, w, h = bbox
        pad = int(max(w, h) * 0.4) + 4
        x0, y0 = max(0, x - pad), max(0, y - pad)
        x1, y1 = min(blur.shape[1], x + w + pad), min(blur.shape[0], y + h + pad)
        roi = blur[y0:y1, x0:x1]
        blob = mask_full[y0:y1, x0:x1].astype(np.uint8)
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
            return None
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
            return None
        e = cv2.fitEllipse(pts[best_inl])
        (cx, cy), (ew, eh), ang = e
        if min(ew, eh) < cfg.min_aspect * max(ew, eh):
            return None
        conf = _support(edges, e)
        # Occlusion check: how much of the fitted ellipse is actually dark pupil?
        fill = np.zeros_like(blob)
        cv2.ellipse(fill, ((cx, cy), (ew * 0.9, eh * 0.9), ang), 1, -1)
        dark_inside = (roi < lo + 0.5 * (hi - lo)) & (fill == 1)
        conf *= min(1.0, float(dark_inside.sum() / max(1, fill.sum())) / 0.9)
        return (cx + x0, cy + y0, max(ew, eh), min(ew, eh), ang, conf)

    def detect(self, gray: np.ndarray) -> Pupil:
        """1) candidates at several darkness levels, 2) fit the best few, 3) keep the
        one with the strongest edge evidence (+ temporal checks)."""
        cfg = self.cfg
        if gray.ndim == 3:
            gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        fits = []
        for _, m, bb, contrast in self._candidates(blur):
            f = self._refine(blur, m, bb)
            if f:
                # A real pupil is clearly darker than the iris around it. Shadows,
                # vignetted corners and lid creases have edges but little contrast.
                fits.append(f[:5] + (f[5] * min(1.0, max(0.0, contrast) / cfg.min_contrast),))
        if not fits:
            self.prev = Pupil(False)
            return self.prev
        cx, cy, major, minor, ang, conf = max(fits, key=lambda f: f[5])
        raw_conf = conf
        # Video prior: pupil size changes slowly (< ~25% between frames even during
        # the light reflex at >= 30 fps), so a sudden jump usually means a bad fit.
        # BUT the prior itself can be wrong (learned from early mistakes). Real LPW
        # video showed it locking out the true pupil for a whole recording, so:
        #  * only high-confidence detections teach the prior, and
        #  * 3 clearly good detections in a row that disagree with it reset it.
        if self.recent_major:
            ref = float(np.median(self.recent_major))
            if abs(major / ref - 1) > 0.25:
                if raw_conf >= 0.8:
                    self.prior_rejects += 1
                if self.prior_rejects >= 3:
                    self.recent_major, self.prior_rejects = [], 0      # re-acquire
                else:
                    conf *= 0.3
            else:
                self.prior_rejects = 0
        res = Pupil(ok=conf >= cfg.min_confidence, cx=cx, cy=cy, major=major, minor=minor,
                    angle=ang, confidence=conf)
        if res.ok and raw_conf >= 0.7:
            self.recent_major = (self.recent_major + [major])[-15:]
        self.prev = res
        return res

    def refine_near(self, gray: np.ndarray, cx: float, cy: float, radius: float) -> Pupil:
        """Classic ellipse fit restricted to candidates near a given point (e.g. the
        neural network's guess). Used by the hybrid detector: the network decides WHERE,
        the ellipse fit adds sub-pixel precision and the pupil size."""
        cfg = self.cfg
        if gray.ndim == 3:
            gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        best = None
        for _, m, bb, contrast in self._candidates(blur):
            bx, by = bb[0] + bb[2] / 2, bb[1] + bb[3] / 2
            if math.hypot(bx - cx, by - cy) > radius:
                continue
            f = self._refine(blur, m, bb)
            if f and math.hypot(f[0] - cx, f[1] - cy) <= radius:
                conf = f[5] * min(1.0, max(0.0, contrast) / cfg.min_contrast)
                if best is None or conf > best[5]:
                    best = f[:5] + (conf,)
        if best is None:
            return Pupil(False)
        return Pupil(ok=best[5] >= cfg.min_confidence, cx=best[0], cy=best[1], major=best[2],
                     minor=best[3], angle=best[4], confidence=best[5])

    def reset(self) -> None:
        """Forget temporal state (new recording / independent images)."""
        self.prev, self.recent_major, self.prior_rejects = None, [], 0
