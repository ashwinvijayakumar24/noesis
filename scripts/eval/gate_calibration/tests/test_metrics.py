"""Unit tests for gate_calibration.metrics.

Every metric is checked against a value computed by hand in the comments, not
against another implementation and not against the module's own output. A test
that only asserts self-consistency will happily certify a metric that is wrong in
the same way twice.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gate_calibration import metrics as M  # noqa: E402


# ---------------------------------------------------------------------------
# The 10-point fixture, hand-computed once and reused.
#
#   score | y          rank   tp  fp   precision   recall
#   ------+---        -----  --- ---   ---------   ------
#    0.95 | 1           1      1   0   1/1 = 1.00   0.2
#    0.90 | 1           2      2   0   2/2 = 1.00   0.4
#    0.85 | 0           3      2   1   2/3 = 0.667  0.4
#    0.80 | 1           4      3   1   3/4 = 0.750  0.6
#    0.75 | 0           5      3   2   3/5 = 0.600  0.6
#    0.70 | 1           6      4   2   4/6 = 0.667  0.8
#    0.60 | 0           7      4   3   4/7 = 0.571  0.8
#    0.50 | 0           8      4   4   4/8 = 0.500  0.8
#    0.40 | 1           9      5   4   5/9 = 0.556  1.0
#    0.30 | 0          10      5   5   5/10= 0.500  1.0
#
#   5 positives, 5 negatives -> base rate 0.5
# ---------------------------------------------------------------------------

Y = [1, 1, 0, 1, 0, 1, 0, 0, 1, 0]
S = [0.95, 0.90, 0.85, 0.80, 0.75, 0.70, 0.60, 0.50, 0.40, 0.30]


class TestPointMetrics:
    """At threshold 0.75 the top five are predicted positive: y = 1,1,0,1,0.

    tp=3, fp=2, and of the bottom five (y = 1,0,0,1,0) fn=2, tn=3.
        precision = 3/(3+2) = 0.6
        recall    = 3/(3+2) = 0.6
        f1        = 2*0.6*0.6/(0.6+0.6) = 0.6
        fp_rate   = 2/(2+3) = 0.4
        fn_rate   = 2/(2+3) = 0.4
    """

    def test_confusion_matrix(self):
        assert M.confusion_matrix(Y, S, 0.75) == {"tp": 3, "fp": 2, "tn": 3, "fn": 2}

    def test_precision(self):
        assert M.precision(Y, S, 0.75) == pytest.approx(0.6)

    def test_recall(self):
        assert M.recall(Y, S, 0.75) == pytest.approx(0.6)

    def test_f1(self):
        assert M.f1(Y, S, 0.75) == pytest.approx(0.6)

    def test_fp_rate(self):
        assert M.false_positive_rate(Y, S, 0.75) == pytest.approx(0.4)

    def test_fn_rate(self):
        assert M.false_negative_rate(Y, S, 0.75) == pytest.approx(0.4)

    def test_threshold_above_everything_predicts_nothing(self):
        # Nothing scores >= 2.0: tp=0, fp=0, fn=5, tn=5.
        # precision is UNDEFINED (0/0), not zero.
        c = M.confusion_matrix(Y, S, 2.0)
        assert c == {"tp": 0, "fp": 0, "tn": 5, "fn": 5}
        assert math.isnan(M.precision(Y, S, 2.0))
        assert M.recall(Y, S, 2.0) == 0.0

    def test_threshold_below_everything_predicts_all(self):
        # tp=5, fp=5, fn=0, tn=0 -> precision 0.5, recall 1.0
        assert M.precision(Y, S, 0.0) == pytest.approx(0.5)
        assert M.recall(Y, S, 0.0) == pytest.approx(1.0)
        assert M.false_positive_rate(Y, S, 0.0) == pytest.approx(1.0)

    def test_point_metrics_bundle_matches_individual_functions(self):
        pm = M.point_metrics(Y, S, 0.75)
        assert pm["precision"] == pytest.approx(0.6)
        assert pm["recall"] == pytest.approx(0.6)
        assert pm["f1"] == pytest.approx(0.6)
        assert pm["tp"] == 3 and pm["fp"] == 2 and pm["tn"] == 3 and pm["fn"] == 2

    def test_f1_is_zero_when_precision_and_recall_are_both_zero(self):
        # scores put the only negative on top and the only positive below.
        assert M.f1([0, 1], [1.0, 0.0], 0.5) == 0.0

    def test_rejects_mismatched_lengths(self):
        with pytest.raises(ValueError):
            M.precision([1, 0], [0.5], 0.5)

    def test_rejects_non_binary_labels(self):
        with pytest.raises(ValueError):
            M.precision([1, 2], [0.5, 0.5], 0.5)


class TestPrecisionRecallCurve:
    def test_curve_has_one_point_per_distinct_score(self):
        prec, rec, thr = M.precision_recall_curve(Y, S)
        assert len(prec) == len(rec) == len(thr) == 10

    def test_curve_values_match_the_hand_table(self):
        prec, rec, thr = M.precision_recall_curve(Y, S)
        # returned ascending by threshold; reverse to match the table above
        assert thr[::-1] == pytest.approx(S)
        assert prec[::-1] == pytest.approx(
            [1.0, 1.0, 2 / 3, 3 / 4, 3 / 5, 4 / 6, 4 / 7, 0.5, 5 / 9, 0.5]
        )
        assert rec[::-1] == pytest.approx([0.2, 0.4, 0.4, 0.6, 0.6, 0.8, 0.8, 0.8, 1.0, 1.0])

    def test_tied_scores_collapse_to_one_operating_point(self):
        # A threshold cannot split a tie, so 4 points at 2 distinct scores
        # give exactly 2 achievable operating points.
        prec, rec, thr = M.precision_recall_curve([1, 0, 1, 0], [0.9, 0.9, 0.1, 0.1])
        assert len(thr) == 2

    def test_no_positives_gives_empty_curve(self):
        assert M.precision_recall_curve([0, 0, 0], [0.1, 0.2, 0.3]) == ([], [], [])


class TestAucPr:
    def test_hand_computed_average_precision(self):
        # AP = sum (R_n - R_{n-1}) * P_n over the table above:
        #   (0.2-0.0)*1.000 = 0.200000
        #   (0.4-0.2)*1.000 = 0.200000
        #   (0.4-0.4)*0.667 = 0.000000
        #   (0.6-0.4)*0.750 = 0.150000
        #   (0.6-0.6)*0.600 = 0.000000
        #   (0.8-0.6)*4/6   = 0.133333
        #   (0.8-0.8)*4/7   = 0.000000
        #   (0.8-0.8)*0.500 = 0.000000
        #   (1.0-0.8)*5/9   = 0.111111
        #   (1.0-1.0)*0.500 = 0.000000
        #                    ----------
        #                     0.794444
        assert M.auc_pr(Y, S) == pytest.approx(0.55 + 2 / 15 + 1 / 9)
        assert M.auc_pr(Y, S) == pytest.approx(0.7944444, abs=1e-6)

    def test_perfect_classifier_scores_one(self):
        y = [1, 1, 1, 0, 0, 0]
        s = [0.9, 0.8, 0.7, 0.3, 0.2, 0.1]
        assert M.auc_pr(y, s) == pytest.approx(1.0)

    def test_worst_classifier_is_far_below_base_rate(self):
        # every negative ranked above every positive
        y = [1, 1, 1, 0, 0, 0]
        s = [0.1, 0.2, 0.3, 0.7, 0.8, 0.9]
        assert M.auc_pr(y, s) < M.base_rate(y)

    def test_uninformative_scorer_lands_near_the_base_rate(self):
        # 200 points, 30% positive, labels shuffled independently of the scores
        # under a fixed seed. A scorer that carries no signal converges on
        # AUC-PR == base rate; small samples wobble around it, so 200 points and
        # a 0.08 tolerance. This is the number every real predictor must beat.
        import numpy as np

        rng = np.random.default_rng(0)
        y = np.array([1] * 60 + [0] * 140)
        rng.shuffle(y)
        s = np.linspace(1.0, 0.0, 200)
        assert M.base_rate(y) == pytest.approx(0.30)
        assert M.auc_pr(y, s) == pytest.approx(0.30, abs=0.08)

    def test_all_scores_identical_gives_base_rate(self):
        # Degenerate curve: one operating point, precision = 5/10, recall = 1.0,
        # so AP = (1.0 - 0) * 0.5 = 0.5, which is exactly the base rate.
        assert M.auc_pr(Y, [0.5] * 10) == pytest.approx(0.5)

    def test_all_positive_labels_gives_one(self):
        # precision is 1.0 at every cut, so AP = 1.0
        assert M.auc_pr([1, 1, 1], [0.3, 0.2, 0.1]) == pytest.approx(1.0)

    def test_all_negative_labels_is_undefined(self):
        assert math.isnan(M.auc_pr([0, 0, 0], [0.3, 0.2, 0.1]))

    def test_empty_input_is_undefined(self):
        assert math.isnan(M.auc_pr([], []))

    def test_single_point(self):
        assert M.auc_pr([1], [0.5]) == pytest.approx(1.0)
        assert math.isnan(M.auc_pr([0], [0.5]))


class TestBaseRate:
    def test_base_rate(self):
        assert M.base_rate(Y) == pytest.approx(0.5)
        assert M.base_rate([1, 0, 0, 0]) == pytest.approx(0.25)

    def test_empty(self):
        assert math.isnan(M.base_rate([]))


class TestCalibration:
    def test_brier_worked_example(self):
        # p = [0.9, 0.1, 0.8, 0.2], y = [1, 0, 1, 0]
        # residuals: -0.1, 0.1, -0.2, 0.2
        # squares:    0.01, 0.01, 0.04, 0.04  -> sum 0.10 / 4 = 0.025
        assert M.brier_score([1, 0, 1, 0], [0.9, 0.1, 0.8, 0.2]) == pytest.approx(0.025)

    def test_brier_perfect_is_zero(self):
        assert M.brier_score([1, 0, 1], [1.0, 0.0, 1.0]) == pytest.approx(0.0)

    def test_brier_maximally_wrong_is_one(self):
        assert M.brier_score([1, 0], [0.0, 1.0]) == pytest.approx(1.0)

    def test_brier_empty(self):
        assert math.isnan(M.brier_score([], []))

    def test_ece_is_zero_for_a_perfectly_calibrated_set(self):
        # Three bins, each internally exact:
        #   10 points predicted 0.0, all y=0   -> observed 0.0, gap 0
        #   10 points predicted 0.5, 5 are y=1 -> observed 0.5, gap 0
        #   10 points predicted 1.0, all y=1   -> observed 1.0, gap 0
        probs = [0.0] * 10 + [0.5] * 10 + [1.0] * 10
        y = [0] * 10 + [1] * 5 + [0] * 5 + [1] * 10
        assert M.expected_calibration_error(y, probs, n_bins=10) == pytest.approx(0.0, abs=1e-12)

    def test_ece_flags_systematic_overconfidence(self):
        # 20 points all predicted 0.95, but only half are actually positive.
        # Single occupied bin: |0.5 - 0.95| * (20/20) = 0.45
        probs = [0.95] * 20
        y = [1] * 10 + [0] * 10
        assert M.expected_calibration_error(y, probs, n_bins=10) == pytest.approx(0.45)
        assert M.expected_calibration_error(y, probs, n_bins=10) > 0.1

    def test_ece_empty(self):
        assert math.isnan(M.expected_calibration_error([], []))

    def test_reliability_diagram_shape_and_contents(self):
        probs = [0.05, 0.05, 0.95, 0.95]
        y = [0, 0, 1, 1]
        bins = M.reliability_diagram(y, probs, n_bins=10)
        assert len(bins) == 10
        assert bins[0]["count"] == 2
        assert bins[0]["mean_predicted"] == pytest.approx(0.05)
        assert bins[0]["observed_freq"] == pytest.approx(0.0)
        assert bins[9]["count"] == 2
        assert bins[9]["observed_freq"] == pytest.approx(1.0)
        # unoccupied bins are reported, not dropped
        assert bins[4]["count"] == 0
        assert math.isnan(bins[4]["mean_predicted"])

    def test_reliability_diagram_includes_exactly_one_in_last_bin(self):
        bins = M.reliability_diagram([1], [1.0], n_bins=10)
        assert bins[9]["count"] == 1

    def test_reliability_diagram_rejects_zero_bins(self):
        with pytest.raises(ValueError):
            M.reliability_diagram([1, 0], [0.5, 0.5], n_bins=0)


class TestCohensKappa:
    def test_perfect_agreement_is_one(self):
        a = ["ok", "degraded", "ok", "degraded"]
        # p_o = 1.0; marginals are 0.5/0.5 for both raters so p_e = 0.5
        # kappa = (1.0 - 0.5) / (1 - 0.5) = 1.0
        assert M.cohens_kappa(a, list(a)) == pytest.approx(1.0)

    def test_chance_agreement_is_zero(self):
        # a: ok ok deg deg      marginals 0.5 / 0.5
        # b: ok deg ok deg      marginals 0.5 / 0.5
        # agreements at positions 1 and 4 -> p_o = 0.5
        # p_e = 0.5*0.5 + 0.5*0.5 = 0.5
        # kappa = (0.5 - 0.5) / 0.5 = 0.0 exactly
        a = ["ok", "ok", "degraded", "degraded"]
        b = ["ok", "degraded", "ok", "degraded"]
        assert M.cohens_kappa(a, b) == pytest.approx(0.0)

    def test_total_disagreement_is_negative(self):
        a = ["ok", "ok", "degraded", "degraded"]
        b = ["degraded", "degraded", "ok", "ok"]
        # p_o = 0.0, p_e = 0.5 -> kappa = -1.0
        assert M.cohens_kappa(a, b) == pytest.approx(-1.0)

    def test_three_categories(self):
        a = ["ok", "degraded", "unsure", "ok"]
        b = ["ok", "degraded", "ok", "ok"]
        # p_o = 3/4 = 0.75
        # a marginals: ok 2/4, degraded 1/4, unsure 1/4
        # b marginals: ok 3/4, degraded 1/4, unsure 0
        # p_e = .5*.75 + .25*.25 + .25*0 = 0.375 + 0.0625 = 0.4375
        # kappa = (0.75 - 0.4375) / (1 - 0.4375) = 0.3125 / 0.5625 = 5/9
        assert M.cohens_kappa(a, b) == pytest.approx(5 / 9)

    def test_single_category_used_by_both_is_one(self):
        # p_e == 1 degenerate case: they agree on everything.
        assert M.cohens_kappa(["ok"] * 5, ["ok"] * 5) == pytest.approx(1.0)

    def test_empty_is_undefined(self):
        assert math.isnan(M.cohens_kappa([], []))

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            M.cohens_kappa(["ok"], ["ok", "ok"])


class TestBootstrapCi:
    def test_is_deterministic_under_a_fixed_seed(self):
        a = M.bootstrap_ci(Y, S, M.auc_pr, n_boot=200, seed=42)
        b = M.bootstrap_ci(Y, S, M.auc_pr, n_boot=200, seed=42)
        assert a == b

    def test_different_seeds_give_different_intervals(self):
        a = M.bootstrap_ci(Y, S, M.auc_pr, n_boot=200, seed=1)
        b = M.bootstrap_ci(Y, S, M.auc_pr, n_boot=200, seed=2)
        assert (a["lo"], a["hi"]) != (b["lo"], b["hi"])

    def test_interval_contains_the_point_estimate(self):
        r = M.bootstrap_ci(Y, S, M.auc_pr, n_boot=500, seed=7)
        assert r["point"] == pytest.approx(0.7944444, abs=1e-6)
        assert r["lo"] <= r["point"] <= r["hi"]

    def test_interval_is_ordered_and_bounded(self):
        r = M.bootstrap_ci(Y, S, M.auc_pr, n_boot=300, seed=3)
        assert r["lo"] <= r["hi"]
        assert 0.0 <= r["lo"] and r["hi"] <= 1.0

    def test_narrows_as_the_sample_grows(self):
        small = M.bootstrap_ci(Y, S, M.auc_pr, n_boot=400, seed=5)
        big_y, big_s = Y * 20, S * 20
        big = M.bootstrap_ci(big_y, big_s, M.auc_pr, n_boot=400, seed=5)
        assert (big["hi"] - big["lo"]) < (small["hi"] - small["lo"])

    def test_works_with_a_threshold_closure(self):
        r = M.bootstrap_ci(
            Y, S, lambda yy, ss: M.precision(yy, ss, 0.75), n_boot=200, seed=11
        )
        assert r["point"] == pytest.approx(0.6)

    def test_empty_input(self):
        r = M.bootstrap_ci([], [], M.auc_pr, n_boot=10, seed=0)
        assert math.isnan(r["lo"]) and math.isnan(r["hi"])
        assert r["n_boot_effective"] == 0

    def test_all_negative_labels_yields_no_effective_resamples(self):
        r = M.bootstrap_ci([0, 0, 0], [0.1, 0.2, 0.3], M.auc_pr, n_boot=50, seed=0)
        assert r["n_boot_effective"] == 0
        assert math.isnan(r["point"])


class TestExpectedCost:
    def test_symmetric_cost_counts_errors(self):
        # at 0.75: fp=2, fn=2 -> cost 4
        assert M.expected_cost(Y, S, 0.75, 1.0, 1.0) == pytest.approx(4.0)

    def test_asymmetric_cost_weights_false_negatives(self):
        # fp=2 at cost 1, fn=2 at cost 5 -> 2 + 10 = 12
        assert M.expected_cost(Y, S, 0.75, fp_cost=1.0, fn_cost=5.0) == pytest.approx(12.0)

    def test_cost_of_a_perfect_split_is_zero(self):
        assert M.expected_cost([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1], 0.5, 3.0, 7.0) == 0.0
