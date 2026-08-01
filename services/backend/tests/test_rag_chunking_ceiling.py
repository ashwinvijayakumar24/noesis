"""The 50-chunk cost ceiling (app/services/rag_chunking.py) and whether it holds.

`MAX_CHUNKS_PER_DOCUMENT` is a COST ceiling. A cost ceiling that can be exceeded
is not a ceiling, so the property under test here is narrow and absolute: after
`apply_cost_ceiling` has fired, the re-estimated chunk count must be <= the limit
it was given. Nothing here asserts that the ceiling is a good retrieval
strategy -- it is not, and the module docstring says so.

The legacy arm is kept and tested as an arm, not as a bug to be deleted: it is
the geometry every number in `docs/BENCHMARKS.md` and the 5,948-chunk corpus was
measured under, so it has to remain runnable for an old-vs-new comparison to
mean anything.
"""

import pytest

from app.services import rag_chunking
from app.services.rag_chunking import (
    CHUNKING_TIERS,
    MAX_CHUNKS_PER_DOCUMENT,
    apply_cost_ceiling,
    calculate_estimated_chunks,
    get_chunking_strategy,
)


# The worst real document in the eval corpus: Bommasani et al. 2021, "On the
# Opportunities and Risks of Foundation Models" -- 214 pages, 207,394 tokens.
# Chosen over a synthetic input because the overshoot is a claim about the real
# corpus and should fail on a document that is actually in it.
#
# The token count is the RAW document count (PyMuPDF text -> cl100k_base), which
# is what get_chunking_strategy is called with. It is NOT the `token_count` in
# scripts/eval/cache/ingest_manifest.jsonl -- that field is the sum over emitted
# chunks and so counts every overlap region twice (243,358 for this document).
# Using the manifest figure here would put the fixture ~17% off the real input.
BOMMASANI_PAGES = 214
BOMMASANI_TOKENS = 207_394


@pytest.fixture(autouse=True)
def _clear_geometry_env(monkeypatch):
    """Each test states its own arm; none inherits the developer's shell."""
    monkeypatch.delenv(rag_chunking.CEILING_GEOMETRY_ENV, raising=False)


def _arm(monkeypatch, value):
    monkeypatch.setenv(rag_chunking.CEILING_GEOMETRY_ENV, value)


# ---------------------------------------------------------------------------
# The reproduction
# ---------------------------------------------------------------------------


def test_legacy_arm_overshoots_the_ceiling_on_a_real_corpus_document(monkeypatch):
    """The legacy geometry produces MORE than max_chunks. This is the bug.

    It is asserted rather than skipped so the legacy arm cannot quietly change
    meaning: if this ever passes, the arms have converged and the comparison in
    scripts/eval/retrieval/CHUNK_CEILING.md no longer measures anything.
    """
    _arm(monkeypatch, "legacy")
    strategy = get_chunking_strategy(
        page_count=BOMMASANI_PAGES, total_tokens=BOMMASANI_TOKENS
    )
    assert strategy["was_adjusted"] is True
    assert strategy["estimated_chunks"] == 55  # limit is 50


def test_exact_arm_respects_the_ceiling_on_the_same_document(monkeypatch):
    _arm(monkeypatch, "exact")
    strategy = get_chunking_strategy(
        page_count=BOMMASANI_PAGES, total_tokens=BOMMASANI_TOKENS
    )
    assert strategy["was_adjusted"] is True
    assert strategy["estimated_chunks"] <= MAX_CHUNKS_PER_DOCUMENT


def test_default_arm_is_legacy(monkeypatch):
    """Unset env == today's shipped behaviour. The fix is opt-in, not a swap."""
    strategy = get_chunking_strategy(
        page_count=BOMMASANI_PAGES, total_tokens=BOMMASANI_TOKENS
    )
    assert strategy["estimated_chunks"] == 55


def test_unknown_arm_falls_back_to_legacy(monkeypatch):
    _arm(monkeypatch, "not-an-arm")
    strategy = get_chunking_strategy(
        page_count=BOMMASANI_PAGES, total_tokens=BOMMASANI_TOKENS
    )
    assert strategy["estimated_chunks"] == 55


# ---------------------------------------------------------------------------
# The property, swept
# ---------------------------------------------------------------------------


def _sweep_inputs():
    """Every tier crossed with token counts spanning 1x to 200x the ceiling.

    Deliberately includes the awkward sizes -- just over the ceiling, and just
    under a round multiple -- because the failure is an integer-division one and
    lives at exactly those boundaries.
    """
    for tier in CHUNKING_TIERS.values():
        size, overlap = tier["chunk_size"], tier["overlap"]
        for total in list(range(50_000, 400_001, 4_931)) + [
            size * 50,
            size * 50 + 1,
            size * 51,
            1_000_000,
            5_000_000,
        ]:
            yield total, size, overlap


@pytest.mark.parametrize("max_chunks", [1, 2, 10, 50, 200])
def test_exact_arm_never_exceeds_the_limit(monkeypatch, max_chunks):
    _arm(monkeypatch, "exact")
    for total_tokens, size, overlap in _sweep_inputs():
        adj_size, adj_overlap, adjusted = apply_cost_ceiling(
            total_tokens, size, overlap, max_chunks
        )
        produced = calculate_estimated_chunks(total_tokens, adj_size, adj_overlap)
        assert produced <= max_chunks, (
            f"{total_tokens=} {size=} {overlap=} {max_chunks=} -> {produced}"
        )
        if adjusted:
            assert adj_size >= size


def test_legacy_arm_fails_that_same_property(monkeypatch):
    """Quantifies the legacy arm rather than merely asserting it is wrong."""
    _arm(monkeypatch, "legacy")
    violations = 0
    total = 0
    for total_tokens, size, overlap in _sweep_inputs():
        adj_size, adj_overlap, _ = apply_cost_ceiling(
            total_tokens, size, overlap, MAX_CHUNKS_PER_DOCUMENT
        )
        total += 1
        if (
            calculate_estimated_chunks(total_tokens, adj_size, adj_overlap)
            > MAX_CHUNKS_PER_DOCUMENT
        ):
            violations += 1
    assert violations > 0
    # Not a tolerance -- a recorded fact about the arm being compared against.
    assert violations / total > 0.5


# ---------------------------------------------------------------------------
# Under-utilisation: a ceiling that undershoots wastes retrievable material
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("total_tokens", [90_000, 150_000, 207_394, 1_000_000])
def test_exact_arm_lands_on_the_ceiling_not_far_below_it(monkeypatch, total_tokens):
    """Fitting the limit exactly is the point; fitting it with room to spare is
    the same waste in the other direction. One chunk of slack is the most the
    integer rounding can leave."""
    _arm(monkeypatch, "exact")
    size, overlap = 2000, 300
    adj_size, adj_overlap, _ = apply_cost_ceiling(
        total_tokens, size, overlap, MAX_CHUNKS_PER_DOCUMENT
    )
    produced = calculate_estimated_chunks(total_tokens, adj_size, adj_overlap)
    assert MAX_CHUNKS_PER_DOCUMENT - 1 <= produced <= MAX_CHUNKS_PER_DOCUMENT


# ---------------------------------------------------------------------------
# Invariants both arms must keep
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("arm", ["legacy", "exact"])
def test_no_adjustment_when_document_already_fits(monkeypatch, arm):
    _arm(monkeypatch, arm)
    assert apply_cost_ceiling(5_000, 1200, 200, 50) == (1200, 200, False)


@pytest.mark.parametrize("arm", ["legacy", "exact"])
def test_minimum_chunk_size_floor_is_respected(monkeypatch, arm):
    """The 500-token floor must survive the arm change.

    It is unreachable from the production tiers -- at the point the ceiling
    fires the solved size is already ~chunk_size, and the smallest tier is 1200
    -- so this uses a sub-500 chunk size to exercise the branch at all.
    """
    _arm(monkeypatch, arm)
    adj_size, adj_overlap, adjusted = apply_cost_ceiling(4_000, 400, 50, 10)
    assert adjusted is True
    assert adj_size >= 500
    assert adj_overlap <= adj_size // 2


@pytest.mark.parametrize("arm", ["legacy", "exact"])
def test_cost_ceiling_record_reports_the_count_it_actually_produced(monkeypatch, arm):
    """`chunks_after_ceiling` is what a later analysis splits results on, so it
    must be the produced count and not the limit."""
    _arm(monkeypatch, arm)
    strategy = get_chunking_strategy(
        page_count=BOMMASANI_PAGES, total_tokens=BOMMASANI_TOKENS
    )
    record = strategy["cost_ceiling"]
    assert record["applied"] is True
    assert record["trigger"] == "estimated_tokens"
    assert record["chunks_after_ceiling"] == strategy["estimated_chunks"]
    assert record["chunks_before_ceiling"] > record["chunks_after_ceiling"]
