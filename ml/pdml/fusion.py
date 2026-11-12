"""Late fusion of eye, wrist and gait models, tolerant of missing sensors.

Design:
* One model PER MODALITY, trained on whoever has that modality. This matters
  because public data never has all sensors on the same people (PADS = wrist only,
  no PD eye datasets exist), and in our own study some sessions will miss a sensor.
* Each modality model outputs a probability; fusion averages the available
  modalities in log-odds space (optionally weighted). A person with only wrist
  data still gets a prediction, with `modalities_used` telling you which.
* Fusion can only be shown to HELP with participants who have several modalities
  recorded together. Until our own study has those, any fusion accuracy is unknown.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .model import make_model


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


@dataclass
class LateFusion:
    kind: str = "logreg"
    weights: dict[str, float] = field(default_factory=dict)
    models: dict = field(default_factory=dict)
    feature_names: dict[str, list[str]] = field(default_factory=dict)

    def fit(self, data: dict[str, tuple[np.ndarray, np.ndarray, list[str]]]) -> "LateFusion":
        """data[modality] = (X, y, feature_names) for participants that HAVE that modality."""
        for mod, (X, y, names) in data.items():
            if len(set(np.asarray(y).tolist())) < 2:
                continue
            self.models[mod] = make_model(self.kind).fit(np.asarray(X, float), np.asarray(y, int))
            self.feature_names[mod] = list(names)
        return self

    def predict(self, sample: dict[str, np.ndarray | None]) -> dict:
        """sample[modality] = one participant's feature vector (or None if not recorded)."""
        logits, used, per = [], [], {}
        for mod, model in self.models.items():
            x = sample.get(mod)
            if x is None:
                continue
            p = float(model.predict_proba(np.asarray(x, float).reshape(1, -1))[0, 1])
            per[mod] = p
            w = self.weights.get(mod, 1.0)
            logits.append((w, _logit(np.array([p]))[0]))
            used.append(mod)
        if not logits:
            return {"probability": None, "modalities_used": [], "per_modality": {}}
        z = sum(w * l for w, l in logits) / sum(w for w, _ in logits)
        return {"probability": float(1 / (1 + np.exp(-z))), "modalities_used": used, "per_modality": per,
                "research_only": True}
