"""Pure metric functions for publish-gate calibration.

No I/O, no globals, no side effects — every function here is a deterministic
map from arrays to numbers, so it can be unit-tested against hand-computed
values. numpy and the standard library only: sklearn and scipy are deliberately
NOT dependencies of this lane.

Conventions used throughout, stated once:

* The **positive class is "degraded"**. ``y_true`` is 1 for a degraded run, 0
  for an acceptable one. This is the rare class.
* ``scores`` are oriented so that **higher means more likely positive**. The
  gate's own predictors run the other way (a *low* ``page_anchor_coverage``
  predicts degradation), so callers must negate them before passing them in.
  ``sweep.py`` does exactly that. Keeping the convention one-directional here
  means every formula below is the textbook one.
* The decision rule at a threshold ``t`` is ``predict positive iff score >= t``.
* Undefined quantities return ``float('nan')`` rather than 0.0. A precision of
  "no positive predictions were made" is not zero precision, and silently
  coercing it to zero biases every downstream average.
"""

from __future__ import annotations

import math
from typing import Callable, Iterable, Sequence

import numpy as np

NAN = float("nan")


# --------------------------------------------------------------------------
# input normalisation
# --------------------------------------------------------------------------


def _as_arrays(y_true: Iterable, scores: Iterable) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(list(y_true), dtype=float)
    s = np.asarray(list(scores), dtype=float)
    if y.shape != s.shape:
        raise ValueError(f"y_true and scores must be the same length, got {y.shape} and {s.shape}")
    if y.size and not np.all(np.isin(y, (0.0, 1.0))):
        raise ValueError("y_true must contain only 0 and 1")
    return y, s


# --------------------------------------------------------------------------
# point metrics at a threshold
# --------------------------------------------------------------------------


def confusion_matrix(y_true: Iterable, scores: Iterable, threshold: float) -> dict[str, int]:
    """Confusion counts under ``predict positive iff score >= threshold``.

    Returns ``{"tp", "fp", "tn", "fn"}`` as plain ints.
    """
    y, s = _as_arrays(y_true, scores)
    pred = s >= threshold
    pos = y == 1.0
    return {
        "tp": int(np.sum(pred & pos)),
        "fp": int(np.sum(pred & ~pos)),
        "tn": int(np.sum(~pred & ~pos)),
        "fn": int(np.sum(~pred & pos)),
    }


def _safe_div(num: float, den: float) -> float:
    return NAN if den == 0 else num / den


def precision(y_true: Iterable, scores: Iterable, threshold: float) -> float:
    """TP / (TP + FP). NaN when nothing was predicted positive."""
    c = confusion_matrix(y_true, scores, threshold)
    return _safe_div(c["tp"], c["tp"] + c["fp"])


def recall(y_true: Iterable, scores: Iterable, threshold: float) -> float:
    """TP / (TP + FN). NaN when there are no positives to recall."""
    c = confusion_matrix(y_true, scores, threshold)
    return _safe_div(c["tp"], c["tp"] + c["fn"])


def f1(y_true: Iterable, scores: Iterable, threshold: float) -> float:
    """Harmonic mean of precision and recall; 0.0 when both are 0."""
    p = precision(y_true, scores, threshold)
    r = recall(y_true, scores, threshold)
    if math.isnan(p) or math.isnan(r):
        return NAN
    if p + r == 0:
        return 0.0
    return 2 * p * r / (p + r)


def false_positive_rate(y_true: Iterable, scores: Iterable, threshold: float) -> float:
    """FP / (FP + TN) — share of acceptable runs the gate would wrongly withhold."""
    c = confusion_matrix(y_true, scores, threshold)
    return _safe_div(c["fp"], c["fp"] + c["tn"])


def false_negative_rate(y_true: Iterable, scores: Iterable, threshold: float) -> float:
    """FN / (FN + TP) — share of degraded runs the gate would wrongly ship."""
    c = confusion_matrix(y_true, scores, threshold)
    return _safe_div(c["fn"], c["fn"] + c["tp"])


def point_metrics(y_true: Iterable, scores: Iterable, threshold: float) -> dict[str, float]:
    """All threshold metrics in one pass, plus the confusion counts."""
    c = confusion_matrix(y_true, scores, threshold)
    return {
        "threshold": float(threshold),
        "precision": _safe_div(c["tp"], c["tp"] + c["fp"]),
        "recall": _safe_div(c["tp"], c["tp"] + c["fn"]),
        "f1": f1(y_true, scores, threshold),
        "fp_rate": _safe_div(c["fp"], c["fp"] + c["tn"]),
        "fn_rate": _safe_div(c["fn"], c["fn"] + c["tp"]),
        **{k: float(v) for k, v in c.items()},
    }


# --------------------------------------------------------------------------
# precision-recall curve
# --------------------------------------------------------------------------


def precision_recall_curve(
    y_true: Iterable, scores: Iterable
) -> tuple[list[float], list[float], list[float]]:
    """Precision-recall curve, evaluated at every distinct score value.

    Why PR and not ROC: degraded runs are the *rare* class here (a minority of
    runs are bad). ROC's x-axis is the false positive rate, whose denominator is
    the large negative class, so a classifier can rack up a large absolute number
    of false positives while the FPR barely moves. ROC-AUC therefore flatters
    rare-positive classifiers and can look respectable for a gate that is, in
    practice, mostly wrong whenever it fires. Precision's denominator is the
    positive *predictions*, so PR keeps the cost of a false alarm visible at the
    scale the user actually experiences it.

    Returns ``(precisions, recalls, thresholds)`` in order of increasing
    threshold (decreasing recall). ``thresholds`` are the distinct score values;
    ``precisions`` and ``recalls`` are the values obtained by predicting positive
    at ``score >= threshold``.

    Returns three empty lists when there is no positive class, since recall is
    undefined without one.
    """
    y, s = _as_arrays(y_true, scores)
    n_pos = int(np.sum(y == 1.0))
    if y.size == 0 or n_pos == 0:
        return [], [], []

    order = np.argsort(-s, kind="mergesort")  # stable, descending
    y_sorted = y[order]
    s_sorted = s[order]

    tp_cum = np.cumsum(y_sorted == 1.0)
    fp_cum = np.cumsum(y_sorted == 0.0)

    # Only take the last index of each run of tied scores: a threshold cannot
    # split a tie, so intermediate cut points are not achievable operating
    # points.
    distinct = np.where(np.diff(s_sorted))[0]
    idx = np.r_[distinct, s_sorted.size - 1]

    tp = tp_cum[idx]
    fp = fp_cum[idx]
    with np.errstate(divide="ignore", invalid="ignore"):
        prec = np.where(tp + fp > 0, tp / np.maximum(tp + fp, 1), NAN)
    rec = tp / n_pos
    thr = s_sorted[idx]

    # Reverse so thresholds ascend (recall descends) — reads more naturally as a
    # "how strict am I being" sweep.
    return list(map(float, prec[::-1])), list(map(float, rec[::-1])), list(map(float, thr[::-1]))


def auc_pr(y_true: Iterable, scores: Iterable) -> float:
    """Area under the precision-recall curve, as **average precision**.

    Computed as ``sum_n (R_n - R_{n-1}) * P_n`` over operating points ordered by
    decreasing threshold. This is the step-wise (rectangular) estimator, not the
    trapezoidal one: trapezoidal interpolation between PR operating points is
    optimistic, because the PR curve is not linear between achievable points.

    NaN when there is no positive class (the curve is undefined).
    """
    y, s = _as_arrays(y_true, scores)
    if y.size == 0 or int(np.sum(y == 1.0)) == 0:
        return NAN

    prec, rec, _ = precision_recall_curve(y, s)
    # precision_recall_curve returns ascending threshold; walk it the other way
    # so recall increases monotonically from 0.
    prec_desc = prec[::-1]
    rec_desc = rec[::-1]

    total = 0.0
    prev_recall = 0.0
    for p, r in zip(prec_desc, rec_desc):
        if math.isnan(p):
            continue
        total += (r - prev_recall) * p
        prev_recall = r
    return float(total)


def base_rate(y_true: Iterable) -> float:
    """Prevalence of the positive class — the AUC-PR a random scorer converges to."""
    y = np.asarray(list(y_true), dtype=float)
    if y.size == 0:
        return NAN
    return float(np.sum(y == 1.0) / y.size)


# --------------------------------------------------------------------------
# calibration
# --------------------------------------------------------------------------


def reliability_diagram(
    y_true: Iterable, probs: Iterable, n_bins: int = 10
) -> list[dict[str, float]]:
    """Binned predicted probability vs observed frequency.

    Equal-width bins over [0, 1]. Bins are ``[lo, hi)`` except the last, which is
    closed so that a prediction of exactly 1.0 lands somewhere. Empty bins are
    returned with ``count == 0`` and NaN statistics, rather than dropped, so the
    caller can see the coverage holes.
    """
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    y, p = _as_arrays(y_true, probs)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out: list[dict[str, float]] = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        if i == n_bins - 1:
            mask = (p >= lo) & (p <= hi)
        else:
            mask = (p >= lo) & (p < hi)
        count = int(np.sum(mask))
        out.append(
            {
                "bin_lower": float(lo),
                "bin_upper": float(hi),
                "count": count,
                "mean_predicted": float(np.mean(p[mask])) if count else NAN,
                "observed_freq": float(np.mean(y[mask])) if count else NAN,
            }
        )
    return out


def expected_calibration_error(y_true: Iterable, probs: Iterable, n_bins: int = 10) -> float:
    """ECE: count-weighted mean gap between predicted probability and observed rate.

    ``sum_b (n_b / N) * |observed_b - mean_predicted_b|``. Zero for a perfectly
    calibrated scorer; grows as predictions drift from the frequencies they
    imply. Bin count matters — too many bins and every bin is noise, too few and
    opposing miscalibrations cancel. 10 is the usual default.
    """
    y, p = _as_arrays(y_true, probs)
    if y.size == 0:
        return NAN
    total = 0.0
    for b in reliability_diagram(y, p, n_bins=n_bins):
        if b["count"] == 0:
            continue
        total += (b["count"] / y.size) * abs(b["observed_freq"] - b["mean_predicted"])
    return float(total)


def brier_score(y_true: Iterable, probs: Iterable) -> float:
    """Mean squared error of the predicted probabilities: ``mean((p - y)^2)``.

    Lower is better; 0.0 is perfect. Unlike ECE it penalises both calibration and
    sharpness, so a scorer that always predicts the base rate is perfectly
    calibrated (ECE 0) but has a mediocre Brier score.
    """
    y, p = _as_arrays(y_true, probs)
    if y.size == 0:
        return NAN
    return float(np.mean((p - y) ** 2))


# --------------------------------------------------------------------------
# uncertainty
# --------------------------------------------------------------------------


def bootstrap_ci(
    y_true: Iterable,
    scores: Iterable,
    metric_fn: Callable[[Sequence[float], Sequence[float]], float],
    n_boot: int = 1000,
    alpha: float = 0.05,
    seed: int = 0,
) -> dict[str, float]:
    """Percentile bootstrap confidence interval for a metric.

    ``metric_fn`` takes ``(y_true, scores)`` and returns a float; wrap
    threshold-dependent metrics in a lambda that closes over the threshold.

    Deterministic for a fixed ``seed``. Resamples that produce a NaN metric
    (typically because the resample happened to contain no positives) are
    discarded rather than counted as zero.

    Returns ``{"point", "lo", "hi", "n_boot_effective"}``. With very few labels
    the interval will be embarrassingly wide — that is the honest answer, and the
    reason ``sweep.py`` refuses to report AUC below ten labels.

    Note: a percentile interval is not guaranteed to contain the point estimate
    for a badly skewed statistic. If that happens the statistic is telling you it
    is not trustworthy at this sample size; it is not a bug to be clamped away.
    """
    y, s = _as_arrays(y_true, scores)
    point = float(metric_fn(y, s))
    n = y.size
    if n == 0:
        return {"point": point, "lo": NAN, "hi": NAN, "n_boot_effective": 0}

    rng = np.random.default_rng(seed)
    vals: list[float] = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        v = metric_fn(y[idx], s[idx])
        if v is not None and not math.isnan(float(v)):
            vals.append(float(v))

    if not vals:
        return {"point": point, "lo": NAN, "hi": NAN, "n_boot_effective": 0}

    arr = np.sort(np.asarray(vals))
    lo = float(np.percentile(arr, 100 * alpha / 2))
    hi = float(np.percentile(arr, 100 * (1 - alpha / 2)))
    return {"point": point, "lo": lo, "hi": hi, "n_boot_effective": len(vals)}


# --------------------------------------------------------------------------
# inter-rater agreement
# --------------------------------------------------------------------------


def cohens_kappa(rater_a: Sequence, rater_b: Sequence) -> float:
    """Cohen's kappa: agreement corrected for agreement expected by chance.

    ``(p_o - p_e) / (1 - p_e)``. Works on any hashable categorical labels, so it
    accepts the raw ``degraded``/``ok``/``unsure`` strings directly.

    1.0 is perfect agreement, 0.0 is exactly chance, negative is worse than
    chance. Returns 1.0 in the degenerate case where both raters used a single
    identical category for everything (``p_e == 1``): they agree on every item,
    and the chance correction has nothing to subtract.
    """
    a = list(rater_a)
    b = list(rater_b)
    if len(a) != len(b):
        raise ValueError("raters must have labelled the same number of items")
    n = len(a)
    if n == 0:
        return NAN

    p_o = sum(1 for x, y in zip(a, b) if x == y) / n

    cats = set(a) | set(b)
    p_e = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)

    if p_e == 1.0:
        return 1.0 if p_o == 1.0 else NAN
    return float((p_o - p_e) / (1 - p_e))


# --------------------------------------------------------------------------
# cost-sensitive operating point
# --------------------------------------------------------------------------


def expected_cost(
    y_true: Iterable,
    scores: Iterable,
    threshold: float,
    fp_cost: float = 1.0,
    fn_cost: float = 1.0,
) -> float:
    """Total misclassification cost at a threshold: ``fp_cost*FP + fn_cost*FN``.

    Shipping a degraded critique (a false *negative* for this gate, since the
    gate failed to catch it) and withholding a good one (a false positive) are
    not equally bad, and which is worse is a product decision, not a statistical
    one. Making the ratio an explicit parameter forces that decision to be stated
    rather than smuggled in via F1, which silently assumes they cost the same.
    """
    c = confusion_matrix(y_true, scores, threshold)
    return float(fp_cost * c["fp"] + fn_cost * c["fn"])
