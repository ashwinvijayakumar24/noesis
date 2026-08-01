"""Tests for the ceiling study.

The deliverable here is a set of hand judgements, so the tests guard the things
that would silently invalidate them: the label set drifting away from the one
the head-to-head scored, a hand label going missing or acquiring an unknown
category, the stratified sample stopping being reproducible from its seed, and
the weighted sweep losing the property that makes it interpretable (recall
monotonically non-increasing in the threshold).

Nothing here calls a model.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EVAL_DIR.parent.parent
for _p in (str(REPO_ROOT), str(REPO_ROOT / "services" / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.eval.ceiling import taxonomy  # noqa: E402
from scripts.eval.ceiling import calibrate_matcher as CM  # noqa: E402

CEILING_DIR = EVAL_DIR / "ceiling"


@pytest.fixture(scope="module")
def hand_labels() -> dict:
    return json.loads((CEILING_DIR / "hand_labels.json").read_text())


@pytest.fixture(scope="module")
def pair_labels() -> dict:
    return json.loads((CEILING_DIR / "pair_labels.json").read_text())


# ---------------------------------------------------------------------------
# The label set
# ---------------------------------------------------------------------------


def test_every_one_of_the_212_units_carries_a_hand_label(hand_labels):
    """Not 120, not a sample. A partial labelling would make the ceiling an
    extrapolation, and the whole point of the number is that it is not one."""
    assert hand_labels["n"] == 212
    assert len(hand_labels["labels"]) == 212
    assert len({row["unit_id"] for row in hand_labels["labels"]}) == 212


def test_the_labelled_units_are_the_head_to_head_units(hand_labels):
    """79 / 72 / 61 and total severity weight 85.4, matching HEADTOHEAD.md section 1.

    If this drifts, every recall number in this study is being computed against
    a different denominator than the one it claims to re-express.
    """
    counts: dict[str, int] = {}
    for row in hand_labels["labels"]:
        counts[row["draft_id"]] = counts.get(row["draft_id"], 0) + 1
    assert counts == {"10eQ4Cfh8p": 79, "kKRbAY4CXv": 72, "cXs5md5wAq": 61}
    total = sum(row["severity_weight"] for row in hand_labels["labels"])
    assert round(total, 1) == 85.4


def test_every_category_is_one_of_the_declared_ones(hand_labels):
    for row in hand_labels["labels"]:
        taxonomy.validate(row["category"])


def test_every_label_carries_a_justification_a_reader_can_disagree_with(hand_labels):
    """A label without a stated reason is not auditable, and auditability is the
    deliverable."""
    for row in hand_labels["labels"]:
        assert row["note"].strip(), row["unit_id"]


def test_the_addressable_subsets_are_nested(hand_labels):
    assert set(taxonomy.ADDRESSABLE) < set(taxonomy.ADDRESSABLE_WITH_RETRIEVAL)
    assert set(taxonomy.ADDRESSABLE) < set(taxonomy.ADDRESSABLE_INCLUDING_SURFACE)
    assert not set(taxonomy.ADDRESSABLE) & set(taxonomy.UNMATCHABLE)


def test_the_headline_ceiling_is_what_the_writeup_claims(hand_labels):
    """76 of 212 defect-addressable. Pinned so a relabelling cannot silently move
    the number CEILING.md is quoted on."""
    counts: dict[str, int] = {}
    for row in hand_labels["labels"]:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    assert counts["defect_addressable"] == 76
    assert counts["context_dependent"] == 27
    assert counts["surface_copyedit"] == 23
    assert counts["needs_literature"] == 21
    assert counts["needs_expertise"] == 27
    assert counts["request_not_defect"] == 34
    assert counts["generic_non_defect"] == 3
    assert counts["meta_venue"] == 1
    assert sum(counts.values()) == 212


# ---------------------------------------------------------------------------
# The pair sample and the sweep
# ---------------------------------------------------------------------------


def test_the_stratified_sample_is_reproducible_from_its_seed():
    """Same pairs, same seed, same draw -- twice, and independent of input order."""
    pairs = [
        {"finding_id": f"f{i:03d}", "unit_id": f"u{j:03d}", "cosine": ((i * 37 + j * 11) % 100) / 100.0}
        for i in range(40)
        for j in range(40)
    ]
    first = CM.stratified_sample(pairs, per_bin=5, seed=7)
    second = CM.stratified_sample(list(reversed(pairs)), per_bin=5, seed=7)
    assert [(p["finding_id"], p["unit_id"]) for p in first] == [
        (p["finding_id"], p["unit_id"]) for p in second
    ]


def test_every_labelled_pair_carries_its_stratum_weight(pair_labels):
    """Without bin_population / bin_drawn the sweep's precision is meaningless --
    the top bin is oversampled by three orders of magnitude."""
    for row in pair_labels["pairs"]:
        assert row["bin_population"] >= row["bin_drawn"] >= 1
        assert row["label"] in (0, 1)


def test_recall_is_non_increasing_in_the_threshold(pair_labels):
    rows = json.loads((CEILING_DIR / "sweep.json").read_text())["sweep"]
    recalls = [r["recall"] for r in rows if r["recall"] is not None]
    assert recalls == sorted(recalls, reverse=True)


def test_the_deployed_threshold_loses_most_true_matches(pair_labels):
    """The study's central claim about the matcher, pinned.

    At COS_THRESHOLD = 0.55 the prefilter's estimated recall is ~0.20: four in
    five true (finding, unit) matches never reach the confirmation judge and are
    scored as misses forever.
    """
    payload = json.loads((CEILING_DIR / "sweep.json").read_text())
    assert payload["at_0.55"]["recall"] < 0.30
    assert payload["at_0.45"]["recall"] > 0.75
    assert payload["operating_point"]["threshold"] <= 0.45


def test_the_weighted_sweep_matches_a_hand_computation():
    """Two bins, hand-arithmetic, so a refactor of _weighted_counts cannot quietly
    change what precision and recall mean."""
    labelled = [
        {"cosine": 0.60, "label": 1, "bin_population": 10, "bin_drawn": 2},
        {"cosine": 0.61, "label": 0, "bin_population": 10, "bin_drawn": 2},
        {"cosine": 0.40, "label": 1, "bin_population": 100, "bin_drawn": 2},
        {"cosine": 0.41, "label": 0, "bin_population": 100, "bin_drawn": 2},
    ]
    counts = CM._weighted_counts(labelled, 0.55)
    assert counts == {"tp": 5.0, "fp": 5.0, "fn": 50.0, "tn": 50.0}
    row = CM.sweep(labelled, [0.55])[0]
    assert row["precision"] == 0.5
    assert row["recall"] == pytest.approx(5.0 / 55.0, abs=1e-4)


def test_cohens_kappa_agrees_with_the_textbook_cases():
    assert CM.cohens_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == pytest.approx(1.0)
    # Perfect disagreement on a balanced set.
    assert CM.cohens_kappa([1, 1, 0, 0], [0, 0, 1, 1]) == pytest.approx(-1.0)


def test_the_operating_point_is_recall_first():
    """Given a feasible band, choose_operating_point takes the LOWEST threshold,
    not the highest F1 -- the asymmetry is that a prefilter false negative is
    unrecoverable."""
    rows = [
        {"threshold": 0.40, "recall": 1.00, "candidates_est": 90.0, "f1": 0.10},
        {"threshold": 0.45, "recall": 0.82, "candidates_est": 50.0, "f1": 0.36},
        {"threshold": 0.55, "recall": 0.20, "candidates_est": 10.0, "f1": 0.24},
    ]
    chosen = CM.choose_operating_point(rows, max_candidates_per_finding=1.0, n_findings=100)
    assert chosen["threshold"] == 0.40


# ---------------------------------------------------------------------------
# The scored sink
# ---------------------------------------------------------------------------


def test_the_sink_is_append_only_and_config_hash_keyed():
    rows = [json.loads(line) for line in (CEILING_DIR / "ceiling.jsonl").read_text().splitlines() if line.strip()]
    assert rows
    by_hash: dict[str, set[float]] = {}
    for row in rows:
        assert row["config_hash"]
        by_hash.setdefault(row["config_hash"], set()).add(row["threshold"])
    # One hash must never span two thresholds; that would make the rows differenceable
    # when they are not comparable.
    for thresholds in by_hash.values():
        assert len(thresholds) == 1


def test_neither_system_scores_meaningfully_on_the_unmatchable_categories():
    """A system credited for 'This will add more strength to the paper.' would mean
    the matcher is rewarding topical proximity, not shared concern. A few such
    credits are expected; a flood would invalidate the taxonomy's premise."""
    rows = [json.loads(line) for line in (CEILING_DIR / "ceiling.jsonl").read_text().splitlines() if line.strip()]
    for row in rows:
        union = row["systems"]["union"]
        assert union["matched_in_unmatchable"] <= 0.25 * union["units_matched"]
