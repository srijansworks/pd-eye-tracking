"""Published Parkinson's-vs-control eye-movement values, and a transparent way to compare a wearer to them.

Every number in MARKERS was read from the paper named in `source` (checked 2026-11-18); nothing is
invented. Where a paper gives only an effect size (SMD), we cannot say what a healthy value looks
like on OUR hardware, so that marker is only scored once the caller supplies a `reference` of
healthy values measured with our own glasses (see `eye_score`).

This is a research comparison, NOT a diagnosis: published group means are not validated cut-offs,
studies disagree (I2 up to 87%), and our hardware adds its own delays.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

WALDTHALER = ("Waldthaler J. et al., Antisaccades in Parkinson's Disease: A Meta-Analysis, "
              "Neuropsychology Review 31(4):628, 2021 (PMC8592977)")
CHAMBERS = ("Chambers J.M. & Prescott T.J., Response times for visually guided saccades in persons with "
            "Parkinson's disease: a meta-analytic review, Neuropsychologia 48(4):887-899, 2010")
PLR_META = ("'Can the Pupillary Light Reflex and Pupillary Unrest Be Used as Biomarkers of Parkinson's "
            "Disease?' systematic review and meta-analysis, Diagnostics 15(9):1167, 2025 (PMC12071770)")


@dataclass(frozen=True)
class Marker:
    name: str                  # our measurement name (docs/DATA_FORMAT.md)
    label: str
    unit: str
    hc: tuple[float, float] | None      # (mean, SD) healthy controls, published or implied
    pd: tuple[float, float] | None      # (mean, SD) Parkinson's
    smd: float | None                   # pooled standardised mean difference (PD - HC; Hedges g)
    smd_ci: tuple[float, float] | None
    k: int | None                       # studies pooled
    source: str
    hardware_sensitive: bool            # absolute value shifts with camera/display delay
    note: str = ""


# SD for the two antisaccade rows is IMPLIED: (PD mean - HC mean) / pooled g.
MARKERS: dict[str, Marker] = {m.name: m for m in [
    Marker("antisaccade_error_rate", "Antisaccade direction-error rate", "ratio",
           hc=(0.19, 0.152), pd=(0.34, 0.152), smd=0.99, smd_ci=(0.76, 1.21), k=39, source=WALDTHALER,
           hardware_sensitive=False,
           note="Pooled error rates PD 0.34 [0.30-0.39] vs HC 0.19 [0.16-0.22]; SD 0.152 implied by g = 0.99. "
                "Publication-bias-adjusted g = 0.68. Prediction interval for a new study: g -0.29 to 2.26."),
    Marker("antisaccade_latency_median", "Antisaccade latency (correct trials)", "ms",
           hc=(368.6, 51.3), pd=(411.7, 51.3), smd=0.84, smd_ci=(0.52, 1.15), k=34, source=WALDTHALER,
           hardware_sensitive=True,
           note="Step paradigm (ours): PD 411.7 ms vs HC 368.6 ms; SD 51 ms implied by g = 0.84. "
                "Bias-adjusted g = 0.41. Lab eye trackers; our camera + display add a constant delay."),
    Marker("plr_latency", "Pupil light reflex latency", "ms", hc=None, pd=None, smd=0.46, smd_ci=(0.10, 0.81),
           k=9, source=PLR_META, hardware_sensitive=True,
           note="PD slower. I2 = 65%. Needs healthy reference on our glasses + screen flash."),
    Marker("plr_constriction_amplitude", "Pupil light reflex constriction amplitude", "ratio", hc=None, pd=None,
           smd=-0.58, smd_ci=(-1.17, 0.01), k=10, source=PLR_META, hardware_sensitive=True,
           note="PD smaller constriction. CI touches zero, I2 = 88%."),
    Marker("plr_max_constriction_velocity", "Pupil light reflex peak constriction velocity", "mm/s", hc=None,
           pd=None, smd=-0.92, smd_ci=(-1.56, -0.28), k=9, source=PLR_META, hardware_sensitive=True,
           note="PD slower. Largest pupil effect, but I2 = 87%."),
    Marker("saccade_latency_median", "Prosaccade latency", "ms", hc=None, pd=None, smd=None, smd_ci=None, k=47,
           source=CHAMBERS, hardware_sensitive=True,
           note="PD longer by 19.4 ms overall (95% CI half-width 9.8), 26.5 ms in step paradigms (47 studies). "
                "Small and hardware-dependent, so context only, never scored."),
]}

# Direction of change reported in the literature (reviews we read gave no pooled number), NOT scored:
DIRECTION_ONLY = {
    "saccade_gain_median": "PD: smaller (hypometric) saccades",
    "pursuit_velocity_gain": "PD: reduced smooth-pursuit gain",
    "blink_rate": "PD: reduced blink rate",
    "square_wave_jerk_rate": "PD: more square-wave jerks (higher in advanced disease)",
}


def _norm_llr(x: float, hc: tuple[float, float], pd: tuple[float, float]) -> float:
    """log N(x; PD) - log N(x; HC) for two Gaussians."""
    (m0, s0), (m1, s1) = hc, pd
    return (math.log(s0 / s1) + 0.5 * (((x - m0) / s0) ** 2 - ((x - m1) / s1) ** 2))


def marker_params(name: str, reference: dict[str, tuple[float, float]] | None = None):
    """(HC (mean, SD), PD (mean, SD), source) for one marker, or None when it cannot be scored.

    A reference measured on our own hardware (mean, SD of healthy volunteers) always wins; the
    PD distribution is then the reference shifted by the published SMD."""
    m = MARKERS.get(name)
    if m is None:
        return None
    if reference and name in reference and m.smd is not None:
        mu, sd = reference[name]
        return (mu, sd), (mu + m.smd * sd, sd), "own healthy reference + published SMD"
    if m.hc and m.pd and not m.hardware_sensitive:
        return m.hc, m.pd, "published group values"
    return None


def eye_score(measurements: list[dict], reference: dict[str, tuple[float, float]] | None = None,
              min_confidence: float = 0.5, max_abs_llr: float = 3.0, shrink: float = 0.5) -> dict:
    """Combine the scoreable published markers into one log-likelihood ratio (PD : healthy).

    - each marker's LLR is clamped to +-`max_abs_llr` (one noisy number cannot dominate);
    - the sum is multiplied by `shrink` (0.5) because markers from one person are correlated and
      published effects are heterogeneous. This is a heuristic, not a fitted model.
    Returns the LLR, which markers were used, and why others were skipped."""
    by_name = {m["name"]: m for m in measurements}
    used, skipped, total = [], [], 0.0
    for name, mk in MARKERS.items():
        meas = by_name.get(name)
        if meas is None:
            continue
        params = marker_params(name, reference)
        if params is None:
            why = ("hardware-dependent: needs a healthy reference measured on our glasses"
                   if mk.hardware_sensitive else "no published distribution")
            skipped.append({"name": name, "reason": why})
            continue
        if meas["confidence"] < min_confidence:
            skipped.append({"name": name, "reason": f"low measurement confidence ({meas['confidence']:.2f})"})
            continue
        hc, pd, basis = params
        llr = max(-max_abs_llr, min(max_abs_llr, _norm_llr(meas["value"], hc, pd)))
        total += llr
        used.append({"name": name, "label": mk.label, "value": meas["value"], "unit": mk.unit,
                     "healthy": hc, "parkinsons": pd, "llr": llr, "basis": basis, "source": mk.source})
    return {"llr": shrink * total, "n_used": len(used), "used": used, "skipped": skipped, "shrink": shrink}


def _logit(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def posterior(llr: float, prior: float = 0.5) -> float:
    return 1 / (1 + math.exp(-(_logit(prior) + llr)))


def fuse(wrist_prob: float | None, eye_llr: float | None) -> dict:
    """Glasses + wrist: add the eye log-likelihood ratio to the wrist model's log-odds.

    The wrist model is trained with balanced classes, so its output already behaves like a 50% prior
    posterior. Adding the eye LLR assumes the two sensors carry independent evidence; they do not
    quite (both track disease severity), so treat the fused number as optimistic."""
    z, used = 0.0, []
    if wrist_prob is not None:
        z += _logit(wrist_prob); used.append("wrist")
    if eye_llr is not None:
        z += eye_llr; used.append("glasses")
    return {"probability": (1 / (1 + math.exp(-z))) if used else None, "sensors_used": used, "research_only": True}
