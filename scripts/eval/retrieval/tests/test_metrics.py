"""Metric correctness against hand-computed values.

If these drift, every number the harness has ever produced is suspect.
"""

import math

import pytest

from scripts.eval.retrieval.adapters import RetrievedDoc
from scripts.eval.retrieval.metrics import (
    UNIT_CHUNK,
    UNIT_DOCUMENT,
    UNIT_SECTION,
    FailureMode,
    attribute_failures,
    compute_metrics,
    evaluate_run,
    percent_of_attainable,
    pool_to_unit,
    recall_ceilings,
    truncate,
)


def _doc(doc_id, score, rank, section=None, chunk=None):
    return RetrievedDoc(
        doc_id=doc_id,
        chunk_id=chunk or f"{doc_id}::c0",
        score=score,
        rank=rank,
        section_id=section if section is not None else f"{doc_id}::s0",
    )


# ---------------------------------------------------------------------------
# Hand-computed ground truth
# ---------------------------------------------------------------------------


def test_ndcg_at_3_matches_hand_computation():
    """Tiny fixture, computed by hand.

    qrels q1 = {d1: 1, d2: 1}
    run   q1 = d1@0.9 (rank 1), d3@0.5 (rank 2), d2@0.4 (rank 3)

    Binary gains, log2 discount, rank i starting at 1, discount = 1/log2(i+1):
        DCG@3  = 1/log2(2) + 0/log2(3) + 1/log2(4)
               = 1/1 + 0 + 1/2
               = 1.5
    Ideal ordering places both relevant docs first:
        IDCG@3 = 1/log2(2) + 1/log2(3)
               = 1 + 1/1.5849625
               = 1.6309298
        NDCG@3 = 1.5 / 1.6309298 = 0.9197208
    """
    qrels = {"q1": {"d1": 1, "d2": 1}}
    run = {"q1": {"d1": 0.9, "d3": 0.5, "d2": 0.4}}

    dcg = 1 / math.log2(2) + 0 / math.log2(3) + 1 / math.log2(4)
    idcg = 1 / math.log2(2) + 1 / math.log2(3)
    expected = dcg / idcg
    assert expected == pytest.approx(0.9197208, abs=1e-6)

    scores = compute_metrics(qrels, run, ["ndcg@3"])
    assert scores["ndcg@3"] == pytest.approx(expected, abs=1e-9)


def test_recall_and_mrr_on_same_fixture():
    """recall@2 = 1 of 2 relevant docs in top 2 = 0.5. MRR: first hit at rank 1."""
    qrels = {"q1": {"d1": 1, "d2": 1}}
    run = {"q1": {"d1": 0.9, "d3": 0.5, "d2": 0.4}}
    scores = compute_metrics(qrels, run, ["recall@2", "recall@3", "mrr", "map"])
    assert scores["recall@2"] == pytest.approx(0.5)
    assert scores["recall@3"] == pytest.approx(1.0)
    assert scores["mrr"] == pytest.approx(1.0)
    # AP = (1/1 + 2/3) / 2 = 0.8333...
    assert scores["map"] == pytest.approx((1 / 1 + 2 / 3) / 2)


def test_perfect_ranking_is_all_ones():
    qrels = {"q1": {"d1": 1, "d2": 1, "d3": 1}}
    run = {"q1": {"d1": 0.9, "d2": 0.8, "d3": 0.7, "d9": 0.1}}
    scores = compute_metrics(qrels, run, ["recall@3", "recall@10", "mrr", "ndcg@10", "map"])
    assert scores["recall@3"] == pytest.approx(1.0)
    assert scores["recall@10"] == pytest.approx(1.0)
    assert scores["mrr"] == pytest.approx(1.0)
    assert scores["ndcg@10"] == pytest.approx(1.0)
    assert scores["map"] == pytest.approx(1.0)


def test_reversed_ranking_gives_known_lower_values():
    """Relevant docs at ranks 3 and 4 of 4.

    MRR = 1/3.
    recall@2 = 0. recall@4 = 1.
    DCG@10  = 1/log2(4) + 1/log2(5) = 0.5 + 0.4306766 = 0.9306766
    IDCG@10 = 1/log2(2) + 1/log2(3) = 1.6309298
    NDCG@10 = 0.5707
    """
    qrels = {"q1": {"d1": 1, "d2": 1}}
    run = {"q1": {"d8": 0.9, "d9": 0.8, "d1": 0.7, "d2": 0.6}}
    scores = compute_metrics(qrels, run, ["recall@2", "recall@4", "mrr", "ndcg@10"])
    assert scores["recall@2"] == pytest.approx(0.0)
    assert scores["recall@4"] == pytest.approx(1.0)
    assert scores["mrr"] == pytest.approx(1 / 3)
    expected_ndcg = (1 / math.log2(4) + 1 / math.log2(5)) / (1 / math.log2(2) + 1 / math.log2(3))
    assert scores["ndcg@10"] == pytest.approx(expected_ndcg, abs=1e-6)
    assert expected_ndcg == pytest.approx(0.5707, abs=1e-4)


# ---------------------------------------------------------------------------
# Degenerate cases
# ---------------------------------------------------------------------------


def test_empty_result_set_scores_zero_not_crash():
    qrels = {"q1": {"d1": 1}}
    result = evaluate_run(qrels, {"q1": []}, corpus_doc_ids={"d1"}, k=10)
    assert result.metrics["recall@10"] == 0.0
    assert result.metrics["mrr"] == 0.0
    assert result.metrics["ndcg@10"] == 0.0


def test_query_with_no_relevant_docs_is_excluded_not_zeroed():
    """A query with no ground truth is unscorable; averaging in a 0 would be a lie."""
    qrels = {"q1": {"d1": 1}, "q2": {}}
    raw = {"q1": [_doc("d1", 0.9, 1)], "q2": [_doc("d5", 0.9, 1)]}
    result = evaluate_run(qrels, raw, corpus_doc_ids={"d1", "d5"}, k=10)
    assert result.n_queries == 2
    assert result.n_queries_scored == 1
    assert result.metrics["recall@10"] == pytest.approx(1.0)


def test_no_scorable_queries_returns_zeros():
    assert compute_metrics({}, {}, ["ndcg@10"])["ndcg@10"] == 0.0


def test_relevant_doc_absent_from_corpus():
    qrels = {"q1": {"d1": 1, "ghost": 1}}
    raw = {"q1": [_doc("d1", 0.9, 1)]}
    result = evaluate_run(qrels, raw, corpus_doc_ids={"d1"}, k=10)
    assert result.metrics["recall@10"] == pytest.approx(0.5)
    assert result.failure_breakdown[FailureMode.UNRESOLVED.value] == 1


# ---------------------------------------------------------------------------
# Pooling
# ---------------------------------------------------------------------------


def test_document_pooling_takes_max_not_sum():
    """A long document with many mediocre chunks must not out-rank a short strong one."""
    results = [
        _doc("long", 0.4, 1, chunk="long::c0"),
        _doc("long", 0.4, 2, chunk="long::c1"),
        _doc("long", 0.4, 3, chunk="long::c2"),
        _doc("short", 0.7, 4, chunk="short::c0"),
    ]
    pooled = pool_to_unit(results, UNIT_DOCUMENT)
    assert pooled == {"long": 0.4, "short": 0.7}
    assert max(pooled, key=pooled.get) == "short"


def test_chunk_unit_does_not_pool():
    results = [_doc("d1", 0.4, 1, chunk="d1::c0"), _doc("d1", 0.9, 2, chunk="d1::c1")]
    assert pool_to_unit(results, UNIT_CHUNK) == {"d1::c0": 0.4, "d1::c1": 0.9}


def test_section_unit_refuses_partial_coverage():
    results = [RetrievedDoc("d1", "d1::c0", 0.9, 1, section_id=None)]
    with pytest.raises(ValueError, match="section_id=None"):
        pool_to_unit(results, UNIT_SECTION)


def test_invalid_unit_rejected():
    with pytest.raises(ValueError, match="unit must be one of"):
        pool_to_unit([], "paragraph")


def test_truncate_is_deterministic_under_ties():
    pooled = {"b": 0.5, "a": 0.5, "c": 0.9}
    assert list(truncate(pooled, 2)) == ["c", "a"]


# ---------------------------------------------------------------------------
# Failure attribution
# ---------------------------------------------------------------------------


def test_attribution_classifies_all_three_modes():
    qrels = {"q1": {"hit": 1, "ranked_low": 1, "not_indexed": 1, "never_resolved": 1}}
    full_runs = {
        "q1": {
            "hit": 0.99,
            "noise1": 0.9,
            "noise2": 0.8,
            "ranked_low": 0.1,  # in the run but below k=2
        }
    }
    corpus = {"hit", "ranked_low", "not_indexed"}  # 'never_resolved' has no doc id

    misses, breakdown = attribute_failures(qrels, full_runs, k=2, corpus_doc_ids=corpus)
    by_doc = {m.doc_id: m for m in misses}

    assert "hit" not in by_doc
    assert by_doc["ranked_low"].mode is FailureMode.RANKING
    assert by_doc["ranked_low"].rank == 4
    assert by_doc["not_indexed"].mode is FailureMode.RETRIEVAL
    assert by_doc["never_resolved"].mode is FailureMode.UNRESOLVED

    assert breakdown["ranking_failure"] == 1
    assert breakdown["retrieval_failure"] == 1
    assert breakdown["unresolved"] == 1
    assert breakdown["total_misses"] == 3


def test_attribution_surfaces_upstream_exclusions():
    """Unresolved references excluded from the denominator must remain visible."""
    _, breakdown = attribute_failures({"q1": {"d1": 1}}, {"q1": {"d1": 0.9}},
                                      k=5, corpus_doc_ids={"d1"}, unresolved_count=17)
    assert breakdown["total_misses"] == 0
    assert breakdown["unresolved_references_excluded_upstream"] == 17


def test_ranking_vs_retrieval_needs_untruncated_run():
    """The distinction is only recoverable from the full run, so k must not pre-filter."""
    qrels = {"q1": {"deep": 1}}
    full_runs = {"q1": {f"n{i}": 1.0 - i / 100 for i in range(50)} | {"deep": 0.001}}
    misses, _ = attribute_failures(qrels, full_runs, k=10, corpus_doc_ids={"deep"})
    assert misses[0].mode is FailureMode.RANKING
    assert misses[0].rank == 51


# ---------------------------------------------------------------------------
# Construction ceilings
# ---------------------------------------------------------------------------


def test_recall_ceiling_on_a_synthetic_label_set():
    """Hand computed.

    Every query inherits its manuscript's WHOLE reference list, so recall@k is
    capped at min(k, |rel_q|)/|rel_q| for that query, and the run's ceiling is
    the mean over queries -- the same unweighted-over-queries average ranx uses
    for recall, so measured/ceiling is a ratio of like for like.

    q1 has 2 relevant docs, q2 has 4, q3 has 10.
      k=1  : (1/2 + 1/4 + 1/10) / 3 = (0.5 + 0.25 + 0.1)/3   = 0.283333...
      k=5  : (2/2 + 4/4 + 5/10) / 3 = (1 + 1 + 0.5)/3         = 0.833333...
      k=10 : (2/2 + 4/4 + 10/10)/3  = 1.0
      k=20 : capped at 1.0 -- more depth than there are relevant docs
    """
    qrels = {
        "q1": {"a": 1, "b": 1},
        "q2": {"a": 1, "b": 1, "c": 1, "d": 1},
        "q3": {f"d{i}": 1 for i in range(10)},
    }
    c = recall_ceilings(qrels, [1, 5, 10, 20])
    assert c["recall@1"] == pytest.approx(0.2833333, abs=1e-6)
    assert c["recall@5"] == pytest.approx(0.8333333, abs=1e-6)
    assert c["recall@10"] == pytest.approx(1.0)
    assert c["recall@20"] == pytest.approx(1.0)


def test_recall_ceiling_is_1_when_every_query_has_one_relevant_doc():
    """The benchmark shape people quote recall@10 from. Ours is not this shape."""
    qrels = {f"q{i}": {"a": 1} for i in range(5)}
    assert recall_ceilings(qrels, [1, 10])["recall@1"] == pytest.approx(1.0)


def test_recall_ceiling_ignores_queries_with_no_relevant_docs():
    """Unscorable queries are dropped by compute_metrics too; including them in
    the ceiling would deflate it and inflate percent-of-attainable."""
    with_empty = recall_ceilings({"q1": {"a": 1, "b": 1}, "q2": {}}, [1])
    without = recall_ceilings({"q1": {"a": 1, "b": 1}}, [1])
    assert with_empty == without


def test_recall_ceiling_on_no_scorable_queries_is_zero_not_one():
    assert recall_ceilings({}, [1, 10]) == {"recall@1": 0.0, "recall@10": 0.0}


def test_percent_of_attainable_is_none_where_no_ceiling_exists():
    """None, not 1.0: "no ceiling computed" and "at its ceiling" are different
    claims and must not be confused in a results record."""
    pct = percent_of_attainable(
        {"recall@10": 0.25, "ndcg@10": 0.6}, {"recall@10": 0.5}
    )
    assert pct["recall@10"] == pytest.approx(0.5)
    assert pct["ndcg@10"] is None


def test_measured_recall_never_exceeds_its_own_ceiling():
    """The property that makes the ceiling worth reporting at all."""
    qrels = {"q1": {"a": 1, "b": 1, "c": 1}}
    run = {"q1": {"a": 0.9, "b": 0.8, "c": 0.7}}   # a perfect retriever
    measured = compute_metrics(qrels, run, ["recall@1", "recall@5"])
    ceiling = recall_ceilings(qrels, [1, 5])
    assert measured["recall@1"] <= ceiling["recall@1"] + 1e-9
    assert measured["recall@5"] == pytest.approx(ceiling["recall@5"])
