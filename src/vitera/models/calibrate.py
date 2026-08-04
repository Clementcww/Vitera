"""Calibration, prior correction and threshold selection — bucket 8.

`config/thresholds.yaml` has carried placeholder values since bucket 2 with a
note saying they are set here. This module is what sets them, and it exists
because of one line in CLAUDE.md's data rules:

    Correct for the deployment prior. Training on balanced classes and
    deploying where ~90% of codes are correct produces over-flagging.

Our pair corpus is ~44% positive. A hospital's is ~10%. A model trained on the
first and thresholded as if it were the second flags roughly four times as much
as it should, the koder stops reading the queue in week two, and the adoption
argument for criterion 5 dies. `prior_shift` is the correction, applied in
log-odds space where it is exact for a shift in class prior alone.

Two further commitments from CLAUDE.md are discharged here:

- aggregate accuracy is meaningless on imbalanced data, so `report` returns
  PR-AUC and calibration and never returns accuracy;
- recall is never reported without the clean-claim false positive rate, so
  `recommend_thresholds` picks the operating point *from* a target FPR rather
  than reporting recall at an arbitrary 0.5.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, TypeAlias

import numpy as np

Floats: TypeAlias = "Sequence[float] | np.ndarray[Any, Any]"
Ints: TypeAlias = "Sequence[int] | np.ndarray[Any, Any]"


def sigmoid(x: Floats) -> np.ndarray[Any, Any]:
    z = np.clip(np.asarray(x, dtype=float), -60, 60)
    return np.asarray(1.0 / (1.0 + np.exp(-z)))


def logit(p: Floats, eps: float = 1e-6) -> np.ndarray[Any, Any]:
    q = np.clip(np.asarray(p, dtype=float), eps, 1 - eps)
    return np.asarray(np.log(q / (1 - q)))


# ---------------------------------------------------------------------------
# Temperature scaling
# ---------------------------------------------------------------------------


def fit_temperature(logits: Floats, labels: Ints) -> float:
    """Single-parameter temperature that minimises NLL on a held-out split.

    Held out **by site**, like everything else here. Fitting temperature on the
    same episodes the model trained on returns T≈1 and a calibration plot that
    flatters the model.
    """
    from scipy.optimize import minimize_scalar

    z = np.asarray(logits, dtype=float)
    y = np.asarray(labels, dtype=float)

    def nll(log_t: float) -> float:
        p = sigmoid(z / math.exp(log_t))
        p = np.clip(p, 1e-7, 1 - 1e-7)
        return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))

    res = minimize_scalar(
        nll, bounds=(math.log(0.05), math.log(20.0)), method="bounded"
    )
    return float(math.exp(res.x))


# ---------------------------------------------------------------------------
# Deployment prior correction
# ---------------------------------------------------------------------------


def prior_shift(
    probs: Floats, train_prior: float, deployment_prior: float
) -> np.ndarray[Any, Any]:
    """Move calibrated probabilities from the training prior to deployment.

    Exact under the assumption that only the class prior changes and the
    class-conditional densities do not — the standard label-shift correction.
    That assumption is stated, not proven, and belongs in the limitations
    section rather than in a footnote.
    """
    if not 0 < train_prior < 1 or not 0 < deployment_prior < 1:
        raise ValueError("priors must lie strictly between 0 and 1")
    offset = math.log(deployment_prior / (1 - deployment_prior)) - math.log(
        train_prior / (1 - train_prior)
    )
    return sigmoid(logit(np.asarray(probs, dtype=float)) + offset)


# ---------------------------------------------------------------------------
# Calibration quality
# ---------------------------------------------------------------------------


def ece(probs: Floats, labels: Ints, bins: int = 10) -> float:
    """Expected calibration error, equal-width bins."""
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p > lo) & (p <= hi) if lo > 0 else (p >= lo) & (p <= hi)
        if not m.any():
            continue
        total += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(total)


def reliability(
    probs: Floats, labels: Ints, bins: int = 10
) -> list[dict[str, float]]:
    """Bins for the reliability diagram. Committed to results/ as data, so the
    figure is reproducible without rerunning the model."""
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    out = []
    for lo, hi in zip(edges[:-1], edges[1:], strict=True):
        m = (p > lo) & (p <= hi) if lo > 0 else (p >= lo) & (p <= hi)
        if not m.any():
            continue
        out.append(
            {
                "bin_lo": round(float(lo), 3),
                "bin_hi": round(float(hi), 3),
                "n": int(m.sum()),
                "mean_predicted": round(float(p[m].mean()), 4),
                "observed_rate": round(float(y[m].mean()), 4),
            }
        )
    return out


# ---------------------------------------------------------------------------
# Operating point
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OperatingPoint:
    flag_at: float
    abstain_below: float
    target_false_positive_rate: float
    achieved_false_positive_rate: float
    recall_at_flag_at: float
    precision_at_flag_at: float
    recall_captured_above_abstain: float
    bands_crossed: bool


def recommend_thresholds(
    probs: Floats,
    labels: Ints,
    *,
    target_fpr: float,
    abstain_recall: float = 0.95,
) -> OperatingPoint:
    """Pick `flag_at` from a false-positive budget, `abstain_below` from recall.

    `flag_at` is the lowest threshold whose false positive rate on supported
    codes stays inside the budget — the number a hospital actually negotiates
    over, since it is the share of correct codes the koder is asked to re-open.

    `abstain_below` is set so that the grey band still contains `abstain_recall`
    of the true defects. Below it the system says clean and means it; inside it
    the system abstains, which architectural rule 10 makes a first-class output
    rather than a hedge.
    """
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=int)
    pos, neg = p[y == 1], p[y == 0]
    if pos.size == 0 or neg.size == 0:
        raise ValueError("need both classes to choose an operating point")

    grid = np.unique(np.round(np.concatenate([p, [0.0, 1.0]]), 4))
    flag_at = 1.0
    achieved = 0.0
    for t in grid:
        fpr = float((neg >= t).mean())
        if fpr <= target_fpr:
            flag_at, achieved = float(t), fpr
            break

    # Lowest threshold that still leaves `abstain_recall` of the positives above it.
    abstain_below = 0.0
    for t in grid[::-1]:
        if float((pos >= t).mean()) >= abstain_recall:
            abstain_below = float(t)
            break
    # The two budgets can cross when the model separates so well that the
    # recall threshold sits ABOVE the false-positive threshold. Clamping is
    # right, but it empties the abstention band, and architectural rule 10
    # makes abstention a first-class output — an empty band is a finding to
    # report, never something to hide inside a min().
    crossed = abstain_below > flag_at
    abstain_below = min(abstain_below, flag_at)

    flagged = p >= flag_at
    tp = int((flagged & (y == 1)).sum())
    return OperatingPoint(
        flag_at=round(flag_at, 4),
        abstain_below=round(abstain_below, 4),
        target_false_positive_rate=target_fpr,
        achieved_false_positive_rate=round(achieved, 4),
        recall_at_flag_at=round(tp / max(1, int((y == 1).sum())), 4),
        precision_at_flag_at=round(tp / max(1, int(flagged.sum())), 4),
        recall_captured_above_abstain=round(
            float((pos >= abstain_below).mean()), 4
        ),
        bands_crossed=crossed,
    )


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def report(probs: Floats, labels: Ints) -> dict[str, Any]:
    """PR-AUC, ROC-AUC, Brier, ECE. Deliberately no accuracy field — see the
    module docstring and CLAUDE.md's reporting rules."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=int)
    both = len(set(y.tolist())) == 2
    return {
        "n": int(y.size),
        "positive_rate": round(float(y.mean()), 4),
        "pr_auc": round(float(average_precision_score(y, p)), 4) if both else None,
        "roc_auc": round(float(roc_auc_score(y, p)), 4) if both else None,
        "brier": round(float(np.mean((p - y) ** 2)), 4),
        "ece": round(ece(p, y), 4),
    }


def bootstrap_ci(
    probs: Floats,
    labels: Ints,
    *,
    metric: str = "pr_auc",
    n_boot: int = 1000,
    seed: int = 0,
) -> tuple[float, float]:
    """Percentile bootstrap CI. Reported with every headline number, because a
    point estimate on 1332 test episodes invites a question we should answer
    before it is asked."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    fn = average_precision_score if metric == "pr_auc" else roc_auc_score
    p = np.asarray(probs, dtype=float)
    y = np.asarray(labels, dtype=int)
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, y.size, y.size)
        if len(set(y[idx].tolist())) < 2:
            continue
        vals.append(fn(y[idx], p[idx]))
    if not vals:
        return (float("nan"), float("nan"))
    return (
        round(float(np.percentile(vals, 2.5)), 4),
        round(float(np.percentile(vals, 97.5)), 4),
    )


__all__ = [
    "OperatingPoint",
    "bootstrap_ci",
    "ece",
    "fit_temperature",
    "logit",
    "prior_shift",
    "recommend_thresholds",
    "reliability",
    "report",
    "sigmoid",
]
