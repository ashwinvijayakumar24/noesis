"""Tests for the first-stage recall diagnosis.

Two kinds live here and they are kept apart on purpose:

* pure tests, which need no database and no network, and which pin the
  arithmetic -- ceilings, pooling, the three-way failure split;
* one DB-gated test that pins the **published** numbers. It skips cleanly when
  the local pgvector container is absent, but when it runs it will fail if the
  characterisation in FIRSTSTAGE.md stops reproducing. A published number with
  no test behind it decays silently, which is how this repo lost its eval
  history the first time.
"""

from __future__ import annotations

import types

import pytest

from scripts.eval.retrieval import firststage as fs


# ---------------------------------------------------------------------------
# Fixtures: a tiny synthetic world, no DB
# ---------------------------------------------------------------------------


def _gt(qrels, topic_of=None, doc_ids=None):
    docs = {d: object() for d in (doc_ids or sorted({d for r in qrels.values() for d in r}))}
    return fs.GroundTruth(
        label_set=types.SimpleNamespace(docs=docs),
        # `text` is real because contentless.partition() lexically analyses it;
        # a stub without it would make the contentless breakdown untestable here.
        query_list=[types.SimpleNamespace(query_id=q, topic=(topic_of or {}).get(q, "T"),
                                          text=f"a claim about SysNet-{q} and BERT variants")
                    for q in qrels],
        qrels={q: set(r) for q, r in qrels.items()},
        id_map={},
        topic_of=topic_of or {q: "T" for q in qrels},
    )


# ---------------------------------------------------------------------------
# split_text
# ---------------------------------------------------------------------------


def test_split_text_produces_n_contiguous_pieces():
    text = " ".join(f"w{i}" for i in range(90))
    parts = fs.split_text(text, 3)
    assert len(parts) == 3
    # Contiguous and lossless: granularity is the only variable in the arm, so a
    # split that dropped or duplicated text would make the comparison about
    # coverage instead.
    assert " ".join(parts) == text


def test_split_text_is_a_noop_below_one_part():
    assert fs.split_text("a b c", 1) == ["a b c"]


def test_split_text_refuses_to_shatter_text_shorter_than_n_parts():
    # Two words cannot become three pieces without inventing empty ones, and an
    # empty string is not embeddable.
    assert fs.split_text("only two", 3) == ["only two"]


def test_split_text_never_emits_an_empty_piece():
    for n in (2, 3, 5, 8):
        for size in range(1, 40):
            text = " ".join("w" * (i % 4 + 1) for i in range(size))
            assert all(p.strip() for p in fs.split_text(text, n))


# ---------------------------------------------------------------------------
# pooling and ranking -- must match metrics.pool_to_unit / metrics.truncate
# ---------------------------------------------------------------------------


def test_pool_documents_takes_the_max_not_the_sum():
    # Summing would reward a document for occupying more chunk slots, which is a
    # length bias rather than a relevance signal.
    rows = [("d1", "c1", 0.3), ("d1", "c2", 0.9), ("d1", "c3", 0.1), ("d2", "c4", 0.5)]
    assert fs.pool_documents(rows) == {"d1": 0.9, "d2": 0.5}


def test_pool_documents_drops_chunks_from_documents_outside_the_label_corpus():
    # An unmappable id is a legitimate distractor, not an error.
    assert fs.pool_documents([(None, "c1", 0.9), ("d1", "c2", 0.4)]) == {"d1": 0.4}


def test_rank_documents_breaks_ties_by_doc_id_so_the_order_is_deterministic():
    assert fs.rank_documents({"b": 0.5, "a": 0.5, "c": 0.9}) == ["c", "a", "b"]


# ---------------------------------------------------------------------------
# ceilings and oracles
# ---------------------------------------------------------------------------


def test_recall_ceiling_is_min_k_over_relevant_averaged_over_queries():
    qrels = {"q1": {"a", "b"}, "q2": {f"d{i}" for i in range(20)}}
    # q1: min(10,2)/2 = 1.0 ; q2: min(10,20)/20 = 0.5
    assert fs.recall_ceiling(qrels, 10) == pytest.approx(0.75)


def test_recall_ceiling_is_recomputed_per_subset_and_never_carried():
    qrels = {"q1": {"a", "b"}, "q2": {f"d{i}" for i in range(20)}}
    assert fs.recall_ceiling(qrels, 10) == pytest.approx(0.75)
    assert fs.recall_ceiling({"q2": qrels["q2"]}, 10) == pytest.approx(0.5)
    assert fs.recall_ceiling({}, 10) == 0.0


def test_pool_oracle_bounds_measured_recall():
    # Reranking is a permutation of a fixed pool, so no arm over these pools can
    # exceed the oracle. This is the inequality the whole rerank lane sits under.
    qrels = {"q": {"a", "b", "c"}}
    pools = {"q": {"a": 0.9, "z": 0.8}}
    assert fs.recall_at_k(pools, qrels, 10) <= fs.pool_oracle(pools, qrels, 10)
    assert fs.pool_oracle(pools, qrels, 10) == pytest.approx(1 / 3)


def test_pool_oracle_is_capped_at_k_not_at_the_pool_size():
    qrels = {"q": {f"d{i}" for i in range(30)}}
    pools = {"q": {f"d{i}": 1.0 for i in range(30)}}
    assert fs.pool_oracle(pools, qrels, 10) == pytest.approx(10 / 30)


def test_recall_at_k_uses_the_top_k_of_the_pooled_ranking():
    qrels = {"q": {"a", "b"}}
    pools = {"q": {"a": 0.9, "x": 0.8, "b": 0.1}}
    assert fs.recall_at_k(pools, qrels, 2) == pytest.approx(0.5)
    assert fs.recall_at_k(pools, qrels, 3) == pytest.approx(1.0)


def test_arm_summary_reports_n_and_a_ceiling_alongside_every_recall():
    qrels = {"q": {"a", "b"}}
    s = fs.arm_summary({"q": {"a": 1.0}}, qrels, 10)
    assert s["n"] == 1
    assert set(s) >= {"n", "recall@10", "ceiling", "pool_oracle@10", "mean_pool_documents"}


# ---------------------------------------------------------------------------
# the three-way split -- the point of the module
# ---------------------------------------------------------------------------


def test_characterise_separates_the_three_causes_of_a_retrieval_failure():
    # d_hit is retrieved and ranked; d_rank is pooled but below k; d_ghost was
    # never ingested; d_dark is indexed but surfaces for nothing; d_other is
    # pooled for the *other* query only.
    qrels = {"q1": {"d_hit", "d_rank", "d_ghost", "d_dark", "d_other"}, "q2": {"d_other"}}
    gt = _gt(qrels, doc_ids=["d_hit", "d_rank", "d_ghost", "d_dark", "d_other"])
    pools = {
        "q1": {"d_hit": 0.9, "d_rank": 0.1},
        "q2": {"d_other": 0.9},
    }
    indexed = {"d_hit", "d_rank", "d_dark", "d_other"}  # d_ghost has no chunks
    ch = fs.characterise(gt, pools, indexed, k=1)

    assert ch.never_ingested == 1 and ch.never_ingested_docs == ["d_ghost"]
    assert ch.never_retrieved == 1 and ch.never_retrieved_docs == ["d_dark"]
    assert ch.retrieved_elsewhere == 1 and ch.retrieved_elsewhere_docs == 1
    assert ch.ranking_failures == 1  # d_rank
    assert ch.hits == 2  # d_hit for q1, d_other for q2
    assert ch.retrieval_failures == 3
    assert ch.hits + ch.retrieval_failures + ch.ranking_failures == ch.n_judgments


def test_characterise_buckets_are_a_partition_of_the_retrieval_failures():
    qrels = {"q1": {"a", "b", "c"}, "q2": {"b", "d"}}
    gt = _gt(qrels)
    pools = {"q1": {"a": 0.9}, "q2": {"b": 0.5}}
    ch = fs.characterise(gt, pools, {"a", "b", "c", "d"}, k=1)
    assert (ch.never_ingested + ch.never_retrieved + ch.retrieved_elsewhere
            == ch.retrieval_failures)


def test_dark_documents_counts_indexed_documents_no_query_reaches():
    # A superset of never_retrieved_docs: most dark documents are nobody's
    # reference, so they cost no recall. Reporting only the cited ones would make
    # the index look tighter than it is.
    qrels = {"q1": {"a"}}
    gt = _gt(qrels, doc_ids=["a", "b", "c"])
    ch = fs.characterise(gt, {"q1": {"a": 0.9}}, {"a", "b", "c"}, k=1)
    assert ch.dark_documents == 2
    assert ch.never_retrieved_docs == []


def test_characterise_reports_a_per_topic_rate_with_its_denominator():
    qrels = {"q1": {"a", "b"}, "q2": {"c"}}
    gt = _gt(qrels, topic_of={"q1": "T1", "q2": "T2"})
    ch = fs.characterise(gt, {"q1": {"a": 0.9}, "q2": {}}, {"a", "b", "c"}, k=1)
    assert ch.by_topic["T1"]["judgments"] == 2
    assert ch.by_topic["T2"]["retrieval_failure_rate"] == 1.0


# ---------------------------------------------------------------------------
# snapshot and corpus assertions
# ---------------------------------------------------------------------------


def test_assert_snapshot_raises_on_a_different_label_snapshot():
    ls = types.SimpleNamespace(fingerprint=lambda: "deadbeefdeadbeef")
    with pytest.raises(fs.SnapshotMismatch, match="ceilings move|Ceilings move"):
        fs.assert_snapshot(ls, [])


def test_assert_snapshot_accepts_the_published_snapshot():
    from scripts.eval.retrieval import queries as queries_mod

    ls = types.SimpleNamespace(fingerprint=lambda: fs.SNAPSHOT)
    qs = [types.SimpleNamespace()]
    orig = queries_mod.fingerprint
    queries_mod.fingerprint = lambda _: fs.QUERIES_FINGERPRINT
    try:
        fs.assert_snapshot(ls, qs)
    finally:
        queries_mod.fingerprint = orig


def test_assert_corpus_compares_the_digest_not_the_row_count():
    # A row count is not a corpus identity: the incident's restore returned the
    # count to 5,948 while replacing 324 chunk ids, so every count-based check
    # passed at every moment while the measurement moved.
    with pytest.raises(fs.SnapshotMismatch):
        fs.assert_corpus({"index_state": fs.INDEX_STATE, "index_digest": "0000000000000000"})
    fs.assert_corpus({"index_state": fs.INDEX_STATE, "index_digest": fs.INDEX_DIGEST})


def test_retrieve_pools_rejects_an_unknown_plan():
    with pytest.raises(ValueError, match="index"):
        fs.retrieve_pools(_gt({"q": {"a"}}), 10, plan="hnsw")


def test_published_constants_are_the_restored_corpus_not_the_retired_one():
    # 0.2195 belongs to a corpus that no longer exists. Differencing against it
    # would convert a corpus change into an apparent retriever delta.
    assert fs.CONTROL_R10 == 0.2200
    assert fs.SNAPSHOT == "230c6ea9d9b7e8fd"
    assert fs.INDEX_DIGEST == "8d3edbe3f3b28cdb"


# ---------------------------------------------------------------------------
# DB-gated: the published characterisation must reproduce
# ---------------------------------------------------------------------------


def _db_available() -> bool:
    try:
        from scripts.eval import db

        return db.healthcheck()
    except Exception:  # noqa: BLE001
        return False


needs_db = pytest.mark.skipif(not _db_available(), reason="local pgvector not running")


@needs_db
def test_published_characterisation_reproduces():
    gt = fs.load_ground_truth()
    fs.assert_corpus(fs.index_identity())
    assert gt.n == 338
    assert gt.n_judgments == 8554

    pools, plan = fs.retrieve_pools(gt, 50, "index", fs.RPC_EF_SEARCH)
    assert plan == "index"
    ch = fs.characterise(gt, pools, fs.indexed_document_ids(gt), k=10)

    # The three numbers RERANK.md published, reproduced from a different driver.
    assert ch.retrieval_failures == 6011
    assert ch.ranking_failures == 933
    assert ch.hits == 1610

    # The split that is new here.
    assert (ch.never_ingested, ch.never_retrieved, ch.retrieved_elsewhere) == (20, 71, 5920)

    arm = fs.arm_summary(pools, gt.qrels, 10)
    assert arm["recall@10"] == fs.CONTROL_R10
    assert arm["ceiling"] == 0.5199
    assert arm["pool_oracle@10"] == 0.2982


@needs_db
def test_depth_beyond_120_chunks_buys_exactly_nothing():
    # The headline of the hypothesis sweep. If this ever stops holding, the
    # "deeper retrieval will not help" recommendation is void.
    gt = fs.load_ground_truth()
    readings = {}
    for depth in (120, 1000):
        pools, plan = fs.retrieve_pools(gt, depth, "seqscan")
        assert plan == "seqscan"
        readings[depth] = fs.arm_summary(pools, gt.qrels, 10)
    assert readings[120]["recall@10"] == readings[1000]["recall@10"] == fs.EXACT_R10
    # ...while the reranking headroom over those pools grows a great deal, which
    # is what makes the flatness a scoring result rather than a coverage one.
    assert readings[1000]["pool_oracle@10"] > readings[120]["pool_oracle@10"] + 0.10


@needs_db
def test_subchunk_arm_refuses_to_spend_without_authorisation():
    gt = fs.load_ground_truth()
    with pytest.raises(RuntimeError, match="allow-spend"):
        fs.subchunk_arm(gt, n_parts=7, allow_spend=False)
