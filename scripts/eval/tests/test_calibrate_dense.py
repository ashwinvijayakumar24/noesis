"""Tests for the dense matcher calibration.

Everything here is free and offline. Nothing calls a model; the paid paths
(``--confirm``, ``--judge-variance``) are excluded by construction and their
results live in ``sweep_dense.json`` for inspection.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

from scripts.eval.ceiling import calibrate_dense as cd

CEILING_DIR = Path(cd.__file__).resolve().parent


# --------------------------------------------------------------------------- #
# The label sets
# --------------------------------------------------------------------------- #

def test_dense_labels_are_complete_and_auditable():
    payload = json.loads(cd.DENSE_LABELS.read_text())
    assert payload["n"] == len(payload["pairs"]) == 120
    for row in payload["pairs"]:
        assert row["label"] in (0, 1)
        assert row["reason"].strip(), f"{row['pair_id']} has no reason"
        assert row["finding_text"].strip() and row["unit_text"].strip()
        # Blindness is a property of the file, not just of the process.
        assert "system" not in row


def test_dense_labels_hit_thirty_per_bin_without_exhaustion():
    rows = cd.load_dense_labels()
    by_bin: dict[str, list[dict]] = {}
    for row in rows:
        by_bin.setdefault(row["dense_bin"], []).append(row)
    assert len(by_bin) == len(cd.DENSE_BINS)
    for name, bucket in by_bin.items():
        assert len(bucket) == cd.DENSE_PER_BIN, name
        # No bin was widened to reach the target, and none ran out of candidates.
        assert bucket[0]["exhausted"] is False, name
        assert bucket[0]["bin_candidates_unlabelled"] > cd.DENSE_PER_BIN, name


def test_ceil_labels_are_untouched():
    """CEIL's file is an input. If this fails, the two studies are no longer separable."""
    base = cd.load_base_labels()
    assert len(base) == 146
    assert sum(int(p["label"]) for p in base) == 24


def test_dense_sample_excludes_everything_ceil_already_labelled():
    dense = {(r["finding_id"], r["unit_id"]) for r in cd.load_dense_labels()}
    base = {(r["finding_id"], r["unit_id"]) for r in cd.load_base_labels()}
    assert dense & base == set()


# --------------------------------------------------------------------------- #
# Stratification and weighting
# --------------------------------------------------------------------------- #

def test_stratum_of_partitions_the_range_and_drops_negatives():
    assert cd.stratum_of(0.0) == "[0.000,0.300)"
    assert cd.stratum_of(0.4499) == "[0.435,0.450)"
    assert cd.stratum_of(0.45) == "[0.450,0.465)"
    assert cd.stratum_of(0.9) == "[0.700,1.010)"
    assert cd.stratum_of(-0.01) is None


def test_union_strata_refine_ceils_bins():
    """Every CEIL bin edge survives, so no CEIL stratum is split across a dense one."""
    dense_edges = {e for pair in cd.UNION_BINS for e in pair}
    for low, high in ((0.40, 0.45), (0.45, 0.50)):
        assert low in dense_edges and high in dense_edges


def test_n_eff_equals_n_for_equal_weights_and_collapses_for_unequal():
    assert cd._n_eff([2.0] * 10) == pytest.approx(10.0)
    # One label carrying almost all the weight is worth roughly one observation.
    assert cd._n_eff([1000.0] + [1.0] * 9) < 1.1


# --------------------------------------------------------------------------- #
# Wilson intervals
# --------------------------------------------------------------------------- #

def test_wilson_matches_a_known_value():
    lo, hi = cd.wilson(5, 20)
    assert lo == pytest.approx(0.1122, abs=1e-3)
    assert hi == pytest.approx(0.4687, abs=1e-3)


def test_wilson_brackets_the_point_estimate_and_stays_in_range():
    for successes, n in ((0, 10), (1, 20), (9, 10), (10, 10), (7.5, 19.14)):
        lo, hi = cd.wilson(successes, n)
        point = successes / n
        assert lo <= point + 1e-9 and hi + 1e-9 >= point
        assert 0.0 <= lo <= 1.0 and 0.0 <= hi <= 1.0


def test_wilson_narrows_as_n_grows():
    width = [cd.wilson(0.5 * n, n)[1] - cd.wilson(0.5 * n, n)[0] for n in (10, 50, 250)]
    assert width[0] > width[1] > width[2]


def test_wilson_handles_zero_n():
    assert all(math.isnan(x) for x in cd.wilson(0, 0))


# --------------------------------------------------------------------------- #
# The curve
# --------------------------------------------------------------------------- #

def _toy() -> list[dict]:
    rows = []
    for i in range(10):
        rows.append({"cosine": 0.30 + 0.05 * i, "label": 1 if i >= 6 else 0, "weight": 1.0})
    return rows


def test_sweep_recall_is_monotone_non_increasing():
    rows = cd.sweep_with_intervals(_toy(), [round(0.30 + 0.05 * i, 2) for i in range(10)])
    recalls = [r["recall"] for r in rows]
    assert all(a >= b for a, b in zip(recalls, recalls[1:]))


def test_sweep_intervals_bracket_the_estimates():
    rows = cd.sweep_with_intervals(_toy(), [0.4, 0.5, 0.6])
    for row in rows:
        assert row["precision_ci"][0] <= row["precision"] <= row["precision_ci"][1]
        assert row["recall_ci"][0] <= row["recall"] <= row["recall_ci"][1]


def test_committed_curve_reproduces_from_the_committed_labels():
    """The headline numbers must fall out of the labels, not out of a cache.

    ``sweep_dense.json`` carries the weighted union, so the whole curve can be
    recomputed here with no embeddings, no model, and no cache.
    """
    committed = json.loads((CEILING_DIR / "sweep_dense.json").read_text())
    labels = committed["labels"]
    assert len(labels) == committed["n_labelled_union"] == 266
    assert sorted({r["source"] for r in labels}) == ["ceil", "dense"]
    assert sum(1 for r in labels if r["source"] == "ceil") == 146
    assert sum(1 for r in labels if r["source"] == "dense") == 120

    recomputed = cd.sweep_with_intervals(labels, [r["threshold"] for r in committed["sweep"]])
    assert recomputed == committed["sweep"]

    # And the weights are a real stratification, not free parameters.
    for row in labels:
        assert row["weight"] == pytest.approx(row["stratum_population"] / row["stratum_labelled"])
        assert cd.stratum_of(row["cosine"]) == row["stratum"]

    at45 = committed["at_0.45"]
    assert at45["recall"] == pytest.approx(0.819, abs=0.002)
    assert at45["recall_ci"][0] == pytest.approx(0.599, abs=0.002)
    assert at45["recall_ci"][1] == pytest.approx(0.932, abs=0.002)
    assert at45["precision"] == pytest.approx(0.228, abs=0.002)


def test_the_recommended_point_beats_the_deployed_one_on_both_axes_of_the_argument():
    committed = json.loads((CEILING_DIR / "sweep_dense.json").read_text())
    at44 = next(r for r in committed["sweep"] if r["threshold"] == 0.44)
    at55 = committed["at_0.55"]
    # Recall gain is the whole case, and it is outside the deployed point's interval.
    assert at44["recall"] > at55["recall_ci"][1]
    # And the precision loss is inside noise, which is why it is not a tradeoff.
    assert at44["precision"] > at55["precision_ci"][0]


def test_the_thin_bin_no_longer_carries_the_curve():
    """CEIL's caveat: 1 label in [0.40,0.45) decided the 0.82. Now it is 7 of 68."""
    committed = json.loads((CEILING_DIR / "sweep_dense.json").read_text())
    band = [r for r in committed["labels"] if 0.40 <= r["cosine"] < 0.45]
    assert len(band) >= 68
    assert sum(int(r["label"]) for r in band) >= 7
