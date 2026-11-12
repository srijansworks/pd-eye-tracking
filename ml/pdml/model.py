"""Honest evaluation of a participant-level classifier.

Rules this module enforces, because they are where most PD-detection claims break:
* One row per PARTICIPANT. Splitting recordings of the same person across train
  and test leaks identity and inflates accuracy, so callers aggregate first.
* Repeated stratified k-fold cross-validation; every participant is scored only
  by models that never saw them.
* Report AUC with a bootstrap 95% CI, not a single lucky number.
* Always compare against a confound-only baseline (e.g. age): PD patients are
  older than controls, so "detecting PD" can secretly be "detecting age".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, roc_auc_score, roc_curve
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def make_model(kind: str = "logreg"):
    if kind == "logreg":
        # Regularised, standardised logistic regression: simple, hard to overfit, interpretable.
        return make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                             LogisticRegression(C=0.3, class_weight="balanced", max_iter=2000))
    if kind == "hgb":
        return make_pipeline(SimpleImputer(strategy="median"),
                             HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=200,
                                                            l2_regularization=1.0, class_weight="balanced",
                                                            random_state=0))
    raise ValueError(kind)


@dataclass
class EvalResult:
    name: str
    n: int
    n_pos: int
    auc: float
    auc_ci: tuple[float, float]
    balanced_accuracy: float
    sensitivity_at_90_spec: float
    oof_proba: np.ndarray = field(repr=False)

    def summary(self) -> str:
        return (f"{self.name:38s} n={self.n:4d} (pos {self.n_pos:3d})  AUC {self.auc:.3f} "
                f"[{self.auc_ci[0]:.3f}-{self.auc_ci[1]:.3f}]  bal.acc {self.balanced_accuracy:.3f}  "
                f"sens@90%spec {self.sensitivity_at_90_spec:.2f}")


def cross_validate(X: np.ndarray, y: np.ndarray, kind: str = "logreg", name: str = "",
                   n_splits: int = 5, n_repeats: int = 5, seed: int = 0) -> EvalResult:
    X, y = np.asarray(X, float), np.asarray(y, int)
    proba_sum, count = np.zeros(len(y)), np.zeros(len(y))
    cv = RepeatedStratifiedKFold(n_splits=n_splits, n_repeats=n_repeats, random_state=seed)
    for tr, te in cv.split(X, y):
        m = make_model(kind).fit(X[tr], y[tr])
        proba_sum[te] += m.predict_proba(X[te])[:, 1]
        count[te] += 1
    p = proba_sum / count
    auc = roc_auc_score(y, p)
    rng = np.random.default_rng(seed)
    boots = []
    for _ in range(1000):
        idx = rng.integers(0, len(y), len(y))
        if len(set(y[idx])) == 2:
            boots.append(roc_auc_score(y[idx], p[idx]))
    fpr, tpr, _ = roc_curve(y, p)
    sens90 = float(tpr[fpr <= 0.10].max()) if (fpr <= 0.10).any() else 0.0
    return EvalResult(name or kind, len(y), int(y.sum()), float(auc),
                      (float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))),
                      float(balanced_accuracy_score(y, p >= 0.5)), sens90, p)


def top_features(X: np.ndarray, y: np.ndarray, names: list[str], k: int = 10) -> list[tuple[str, float]]:
    """Standardised logistic-regression coefficients fitted on all data (for explanation only)."""
    m = make_model("logreg").fit(X, y)
    coef = m[-1].coef_[0]
    order = np.argsort(-np.abs(coef))[:k]
    return [(names[i], float(coef[i])) for i in order]
