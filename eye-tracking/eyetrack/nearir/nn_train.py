"""Train the neural pupil detector on the LPW cache (person-level split).

    python -m eyetrack.nearir.nn_train --cache ../data/lpw_cache --epochs 12

Loss: the target is a small Gaussian at the labelled pupil centre; the network's
softmax heatmap is trained with cross-entropy against it, so it learns a probability
map of the pupil location.

Augmentation (on the GPU, per batch) teaches robustness to what fails in real use:
shifts/zoom/flip, brightness/contrast/gamma (different IR LEDs), blur (focus),
sensor noise, and fake glare blobs (glasses reflections).

Model selection uses the VALIDATION people only; the test people are never looked at
until the final evaluation.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

from .nn_model import DEFAULT_WEIGHTS, IN_H, IN_W, TinyUNet, decode

SCALE = 4  # cache is 4x smaller than the 640x480 frames


def gaussian_targets(y: torch.Tensor, H: int, W: int, sigma: float = 1.5) -> torch.Tensor:
    ys = torch.arange(H, device=y.device).view(1, H, 1).float()
    xs = torch.arange(W, device=y.device).view(1, 1, W).float()
    g = torch.exp(-((xs - y[:, 0].view(-1, 1, 1)) ** 2 + (ys - y[:, 1].view(-1, 1, 1)) ** 2) / (2 * sigma ** 2))
    return g / g.sum((1, 2), keepdim=True)


def augment(x: torch.Tensor, y: torch.Tensor, g: torch.Generator) -> tuple[torch.Tensor, torch.Tensor]:
    """x (B,1,H,W) in 0..1, y (B,2) pixel coords. Geometric + photometric augmentation."""
    B, _, H, W = x.shape
    dev = x.device
    r = lambda *s: torch.rand(*s, generator=g, device="cpu").to(dev)
    # --- geometry: flip, zoom 0.85-1.15, shift +-12%, small rotation
    flip = (r(B) < 0.5).float() * -2 + 1
    s = 0.85 + 0.3 * r(B)
    ang = (r(B) - 0.5) * math.radians(20)
    tx, ty = (r(B) - 0.5) * 0.24, (r(B) - 0.5) * 0.24
    cos, sin = torch.cos(ang) / s, torch.sin(ang) / s
    # theta maps OUTPUT normalised coords -> INPUT normalised coords
    theta = torch.stack([torch.stack([cos * flip, -sin, tx], 1), torch.stack([sin * flip, cos, ty], 1)], 1)
    grid = F.affine_grid(theta, x.shape, align_corners=False)
    x = F.grid_sample(x, grid, mode="bilinear", padding_mode="border", align_corners=False)
    # label: input normalised p_in -> output p_out = A^-1 (p_in - t)
    pin = torch.stack([(y[:, 0] + 0.5) / W * 2 - 1, (y[:, 1] + 0.5) / H * 2 - 1], 1)
    A = theta[:, :, :2]
    pout = torch.linalg.solve(A, (pin - theta[:, :, 2]).unsqueeze(-1)).squeeze(-1)
    y = torch.stack([(pout[:, 0] + 1) / 2 * W - 0.5, (pout[:, 1] + 1) / 2 * H - 0.5], 1)
    # --- photometric
    gamma = torch.exp((r(B) - 0.5) * 0.8).view(B, 1, 1, 1)
    x = x.clamp(1e-4, 1) ** gamma
    x = (x - 0.5) * (0.6 + 0.8 * r(B).view(B, 1, 1, 1)) + 0.5 + (r(B).view(B, 1, 1, 1) - 0.5) * 0.3
    blur = (r(B) < 0.3).view(B, 1, 1, 1).float()
    x = blur * F.avg_pool2d(x, 3, 1, 1) + (1 - blur) * x
    # glare: 0-3 bright soft blobs
    yy = torch.arange(H, device=dev).view(1, H, 1).float()
    xx = torch.arange(W, device=dev).view(1, 1, W).float()
    for _ in range(3):
        on = (r(B) < 0.3).view(B, 1, 1)
        cx, cy, rad = r(B).view(B, 1, 1) * W, r(B).view(B, 1, 1) * H, 1 + r(B).view(B, 1, 1) * 6
        blob = torch.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * rad ** 2))
        x = x + (on * blob * (0.5 + 0.5 * r(B).view(B, 1, 1))).unsqueeze(1)
    x = x + torch.randn(x.shape, generator=g, device="cpu").to(dev) * (0.01 + 0.03 * r(B).view(B, 1, 1, 1))
    return x.clamp(0, 1), y


def evaluate(model, X: np.ndarray, Y: np.ndarray, device: str, bs: int = 32) -> dict:
    model.eval()
    errs, confs = [], []
    with torch.no_grad():
        for i in range(0, len(X), bs):
            xb = torch.from_numpy(X[i:i + bs]).float().div(255).unsqueeze(1).to(device)
            c, conf = decode(model(xb))
            errs.append(torch.linalg.norm(c.cpu() - torch.from_numpy(Y[i:i + bs]), dim=1).numpy() * SCALE)
            confs.append(conf.cpu().numpy())
    if device == "mps":
        torch.mps.empty_cache()                            # give memory back (8 GB Macs)
    e, cf = np.concatenate(errs), np.concatenate(confs)   # errors in FULL-resolution (640x480) pixels
    return {"within5px": float(np.mean(e <= 5)), "within10px": float(np.mean(e <= 10)),
            "median_err_px": float(np.median(e)), "_err": e, "_conf": cf}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", required=True)
    ap.add_argument("--epochs", type=int, default=12)
    ap.add_argument("--bs", type=int, default=64)
    ap.add_argument("--lr", type=float, default=2e-3)
    ap.add_argument("--out", default=str(DEFAULT_WEIGHTS))
    a = ap.parse_args(argv)
    torch.manual_seed(0)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    c = Path(a.cache)
    Xtr, Ytr = np.load(c / "train_X.npy", mmap_mode="r"), np.load(c / "train_y.npy")   # read from disk on demand (8 GB Macs)
    Xva, Yva = np.load(c / "val_X.npy"), np.load(c / "val_y.npy")
    assert Xtr.shape[1:] == (IN_H, IN_W)
    model = TinyUNet().to(device)
    print(f"device {device}; {sum(p.numel() for p in model.parameters()) / 1e6:.2f} M parameters; "
          f"train {len(Xtr)} frames, val {len(Xva)}")
    opt = torch.optim.AdamW(model.parameters(), lr=a.lr, weight_decay=1e-4)
    steps = a.epochs * math.ceil(len(Xtr) / a.bs)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=a.lr, total_steps=steps, pct_start=0.15)
    g = torch.Generator().manual_seed(0)
    best, history = -1.0, []
    for ep in range(a.epochs):
        model.train()
        t0, perm, tot = time.time(), np.random.default_rng(ep).permutation(len(Xtr)), 0.0
        for i in range(0, len(perm), a.bs):
            idx = np.sort(perm[i:i + a.bs])            # sorted indices = faster reads from the memory-mapped file
            xb = torch.from_numpy(Xtr[idx]).float().div(255).unsqueeze(1).to(device)
            yb = torch.from_numpy(Ytr[idx]).to(device)
            xb, yb = augment(xb, yb, g)
            logits = model(xb)
            B, H, W = logits.shape
            target = gaussian_targets(yb, H, W)
            loss = -(target * F.log_softmax(logits.reshape(B, -1), 1).reshape(B, H, W)).sum((1, 2)).mean()
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            tot += float(loss.detach()) * len(idx)
        v = evaluate(model, Xva, Yva, device)
        history.append({"epoch": ep + 1, "loss": tot / len(Xtr), "val_within5px": v["within5px"],
                        "val_within10px": v["within10px"], "val_median_err_px": v["median_err_px"]})
        print(f"epoch {ep + 1:2d}  loss {tot / len(Xtr):.3f}  val within5px {v['within5px']:.1%}  "
              f"within10px {v['within10px']:.1%}  median {v['median_err_px']:.2f}px  ({time.time() - t0:.0f}s)", flush=True)
        if v["within5px"] > best:
            best = v["within5px"]
            Path(a.out).parent.mkdir(parents=True, exist_ok=True)
            torch.save(model.state_dict(), a.out)
    Path(a.out).with_suffix(".history.json").write_text(json.dumps(history, indent=2))
    print(f"best val within5px {best:.1%}; saved {a.out}")


if __name__ == "__main__":
    main()
