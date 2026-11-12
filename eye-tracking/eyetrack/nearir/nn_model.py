"""Small neural network that finds the pupil in a near-eye IR image.

Input: 160x120 grayscale (the camera frame shrunk 4x). Output: a "heatmap" with one
score per pixel; a softmax over all pixels turns it into a probability map of where the
pupil centre is. The centre = probability-weighted average around the peak (sub-pixel),
confidence = probability mass near the peak.

Architecture: a tiny U-Net (encoder shrinks the image to see context like "this dark
blob is inside an iris", decoder brings it back to full resolution with skip connections
for precise location). ~0.3 M parameters: small enough for real-time on a laptop.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
except ImportError:  # torch is optional: only needed for the neural detector
    torch = None
    nn = None

IN_W, IN_H = 160, 120
DEFAULT_WEIGHTS = Path(__file__).resolve().parents[2] / "models" / "pupilnet.pt"


if nn is not None:
    def _block(cin, cout):
        return nn.Sequential(nn.Conv2d(cin, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True),
                             nn.Conv2d(cout, cout, 3, padding=1, bias=False), nn.BatchNorm2d(cout), nn.ReLU(inplace=True))

    class TinyUNet(nn.Module):
        def __init__(self, ch=(16, 32, 64, 96)):
            super().__init__()
            self.e1, self.e2, self.e3, self.e4 = _block(1, ch[0]), _block(ch[0], ch[1]), _block(ch[1], ch[2]), _block(ch[2], ch[3])
            self.d3, self.d2, self.d1 = _block(ch[3] + ch[2], ch[2]), _block(ch[2] + ch[1], ch[1]), _block(ch[1] + ch[0], ch[0])
            self.head = nn.Conv2d(ch[0], 1, 1)

        def forward(self, x):                       # x: (B,1,120,160) in 0..1
            e1 = self.e1(x)
            e2 = self.e2(F.max_pool2d(e1, 2))
            e3 = self.e3(F.max_pool2d(e2, 2))
            e4 = self.e4(F.max_pool2d(e3, 2))
            up = lambda a, b: F.interpolate(a, size=b.shape[-2:], mode="bilinear", align_corners=False)
            d3 = self.d3(torch.cat([up(e4, e3), e3], 1))
            d2 = self.d2(torch.cat([up(d3, e2), e2], 1))
            d1 = self.d1(torch.cat([up(d2, e1), e1], 1))
            return self.head(d1)[:, 0]              # (B,120,160) logits

    def decode(logits: "torch.Tensor", win: int = 2) -> tuple["torch.Tensor", "torch.Tensor"]:
        """Logits (B,H,W) -> centres (B,2) in heatmap pixels and confidence (B,)."""
        B, H, W = logits.shape
        p = torch.softmax(logits.reshape(B, -1), 1).reshape(B, H, W)
        idx = p.reshape(B, -1).argmax(1)
        py, px = idx // W, idx % W
        ys = torch.arange(H, device=p.device).view(1, H, 1).float()
        xs = torch.arange(W, device=p.device).view(1, 1, W).float()
        near = ((ys - py.view(B, 1, 1).float()).abs() <= win) & ((xs - px.view(B, 1, 1).float()).abs() <= win)
        pm = p * near
        mass = pm.sum((1, 2)).clamp_min(1e-9)
        cx = (pm * xs).sum((1, 2)) / mass
        cy = (pm * ys).sum((1, 2)) / mass
        return torch.stack([cx, cy], 1), mass


class PupilNet:
    """Inference wrapper: full-resolution grayscale frame -> (cx, cy, confidence) in frame pixels."""

    def __init__(self, weights: str | Path = DEFAULT_WEIGHTS, device: str | None = None):
        if torch is None:
            raise ImportError("PyTorch is needed for the neural pupil detector: uv pip install torch")
        self.device = device or ("mps" if torch.backends.mps.is_available() else "cpu")
        self.model = TinyUNet().to(self.device).eval()
        self.model.load_state_dict(torch.load(weights, map_location=self.device))

    @torch.no_grad() if torch is not None else (lambda f: f)
    def predict(self, gray: np.ndarray) -> tuple[float, float, float]:
        import cv2
        H, W = gray.shape
        small = cv2.resize(gray, (IN_W, IN_H), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        x = torch.from_numpy(small).to(self.device)[None, None]
        c, conf = decode(self.model(x))
        sx, sy = W / IN_W, H / IN_H
        # Heatmap pixel centre i corresponds to frame coordinate (i + 0.5) * scale - 0.5.
        return float((c[0, 0] + 0.5) * sx - 0.5), float((c[0, 1] + 0.5) * sy - 0.5), float(conf[0])
