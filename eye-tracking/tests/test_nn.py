"""Neural pupil detector building blocks (skipped if PyTorch isn't installed)."""

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from eyetrack.nearir.nn_model import DEFAULT_WEIGHTS, TinyUNet, decode  # noqa: E402
from eyetrack.nearir.nn_train import augment, gaussian_targets  # noqa: E402


def test_decode_finds_subpixel_peak():
    y = torch.tensor([[40.3, 70.7], [100.0, 20.5]])
    logits = torch.log(gaussian_targets(y, 120, 160, sigma=1.5) + 1e-12)
    c, conf = decode(logits)
    assert torch.allclose(c, y, atol=0.15)
    assert (conf > 0.9).all()


def test_augmentation_keeps_label_on_the_pupil():
    H, W = 120, 160
    img = torch.full((16, 1, H, W), 0.7)
    ys = torch.tensor([[50.0 + i, 60.0 - i] for i in range(16)])
    yy, xx = torch.meshgrid(torch.arange(H).float(), torch.arange(W).float(), indexing="ij")
    for i in range(16):
        img[i, 0][(xx - ys[i, 0]) ** 2 + (yy - ys[i, 1]) ** 2 <= 36] = 0.05   # dark "pupil" disc
    xa, ya = augment(img, ys, torch.Generator().manual_seed(0))
    for i in range(16):
        x, y = int(round(ya[i, 0].item())), int(round(ya[i, 1].item()))
        if 3 <= x < W - 3 and 3 <= y < H - 3:
            patch = xa[i, 0, y - 1:y + 2, x - 1:x + 2]
            assert patch.mean() < xa[i, 0].mean() - 0.1   # label still sits on the dark disc


def test_model_shapes():
    m = TinyUNet().eval()
    with torch.no_grad():
        out = m(torch.rand(2, 1, 120, 160))
    assert out.shape == (2, 120, 160)
    assert sum(p.numel() for p in m.parameters()) < 1_000_000   # small enough for real time


@pytest.mark.skipif(not DEFAULT_WEIGHTS.exists(), reason="trained weights not present")
def test_trained_network_runs_on_a_frame():
    from eyetrack.nearir.nn_model import PupilNet
    from eyetrack.nearir.render import EyeCamera, EyeState, render
    img, tr = render(EyeCamera(width=320, height=240), EyeState(0, 0, 4.0), np.random.default_rng(0))
    x, y, conf = PupilNet(device="cpu").predict(img)
    assert 0 <= x < 320 and 0 <= y < 240 and 0 <= conf <= 1


@pytest.mark.skipif(not DEFAULT_WEIGHTS.exists(), reason="trained weights not present")
def test_hybrid_tracker_is_subpixel_on_synthetic_glasses_frames():
    """Trained only on real LPW eyes, the hybrid must still work on our glasses camera model."""
    from eyetrack.nearir.render import EyeCamera, EyeState, render
    from eyetrack.nearir.tracker import NearIRTracker
    cam, rng, trk = EyeCamera(), np.random.default_rng(5), NearIRTracker(method="hybrid")
    errs = []
    for i in range(30):
        img, tr = render(cam, EyeState(rng.uniform(-15, 15), rng.uniform(-8, 8), rng.uniform(3, 6)), rng)
        ef = trk.process(img, i / 120)
        errs.append(np.hypot(ef.h * cam.width + cam.width / 2 - tr["cx"], ef.v * cam.width + cam.height / 2 - tr["cy"]))
    assert np.median(errs) < 0.3 and np.max(errs) < 2.0
