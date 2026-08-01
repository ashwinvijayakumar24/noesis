"""Tests for the native-dimensionality embedding arm.

Two kinds, kept apart deliberately:

* pure tests, needing no database and no network, pinning the arithmetic and the
  guardrails -- config-hash separation, the max-pool, the separation statistic,
  and the refusal to spend without authorisation;
* DB-gated tests that pin the **published** numbers in ``EMBEDDING.md``. They
  skip cleanly without the local pgvector container, and when they run they fail
  if the result stops reproducing. A published number with no test behind it
  decays silently, which is how this repo lost its eval history the first time.

The most load-bearing DB test is not the arm at all -- it is
``test_control_separation_reproduces_the_published_0593``. The separation
diagnostic computed here lands on 0.4415 / 0.3821 / gap 0.0594 with n = 7,346
and 55,562, which is ``FIRSTSTAGE.md``'s published figure to four decimals and
to the exact population size. That is what makes the arm's own separation number
believable rather than merely internally consistent.
"""

from __future__ import annotations

import json
import types

import numpy as np
import pytest

from scripts.eval.retrieval import embed_arms as ea


# ---------------------------------------------------------------------------
# Fixtures: a tiny synthetic world, no DB
# ---------------------------------------------------------------------------


def _gt(qrels, texts=None):
    docs = {d: object() for d in sorted({d for r in qrels.values() for d in r})}
    return types.SimpleNamespace(
        label_set=types.SimpleNamespace(docs=docs),
        query_list=[
            types.SimpleNamespace(query_id=q, topic="T", text=(texts or {}).get(q, f"claim {q}"))
            for q in qrels
        ],
        qrels={q: set(r) for q, r in qrels.items()},
        id_map={},
        topic_of={q: "T" for q in qrels},
        n=len(qrels),
    )


# ---------------------------------------------------------------------------
# The guardrail that this whole lane exists under
# ---------------------------------------------------------------------------


def test_the_arm_never_names_document_chunks_as_a_write_target():
    """The shared corpus is read-only here, and that is checked textually.

    S2 runs full-pipeline arms against this same database concurrently. The
    concurrency incident (docs/ENGINEERING_LOG.md) cost a published result
    because one agent mutated ``document_chunks`` while another measured against
    it, and both records carried identical config hashes. This test is cheap and
    it fails the moment somebody adds a write to the shared table.
    """
    source = (ea.EVAL_DIR / "retrieval" / "embed_arms.py").read_text()
    for verb in (
        "INSERT INTO public.document_chunks ",
        "INSERT INTO public.document_chunks(",
        "UPDATE public.document_chunks",
        "DELETE FROM public.document_chunks",
        "TRUNCATE public.document_chunks\n",
        'TRUNCATE public.document_chunks"',
        "DROP INDEX IF EXISTS public.idx_document_chunks_embedding",
        "REINDEX",
    ):
        assert verb not in source, f"{verb!r} would mutate the shared corpus"
    # The arm's own table differs from the shared one by a suffix, so the checks
    # above are written to require a boundary after `document_chunks`. Its own
    # TRUNCATE is spelled through the constant and is expected to be present.
    assert "TRUNCATE public.{ARM_3072_TABLE}" in source


def test_the_migration_is_halfvec_and_local_only():
    sql = ea.SCHEMA_SQL.read_text()
    assert "halfvec(3072)" in sql
    assert "halfvec_cosine_ops" in sql
    assert "LOCAL EVAL DATABASE ONLY" in sql
    # vector(3072) cannot carry an HNSW index on pgvector 0.8.6 -- that is the
    # whole reason halfvec is here, and a silent revert to `vector` would fail at
    # index creation rather than at review time.
    assert "vector(3072)" not in sql.replace("HNSW on vector(3072)", "")


# ---------------------------------------------------------------------------
# Config hash -- the two arms must not collide
# ---------------------------------------------------------------------------


def _spec(name, table, coltype, dims, opclass):
    return ea.ArmSpec(name, table, coltype, dims, opclass, None)


def _corpus():
    return {"index_state": "5948c/344d", "index_digest": "8d3edbe3f3b28cdb"}


def test_config_hash_separates_the_two_widths():
    """Dimensionality is in the hash, so 1536 and 3072 can never share a record.

    Without it the two arms are identical in every recorded field -- same chunk
    ids, same labels, same k, same ef_search -- and the sink would read the
    second arm as run-to-run variance on the first. Run-to-run variance on a
    fixed corpus is 0.0000, so that misreading would have looked like a real
    effect appearing out of nowhere.
    """
    gt = _gt({"q1": {"d1"}})
    a = ea.arm_config(_spec("a", "document_chunks", "vector", 1536, "vector_cosine_ops"),
                      gt, _corpus(), 50)
    b = ea.arm_config(_spec("b", ea.ARM_3072_TABLE, "halfvec", 3072, "halfvec_cosine_ops"),
                      gt, _corpus(), 50)
    from scripts.eval.retrieval.run_retrieval_eval import config_hash

    assert config_hash(a) != config_hash(b)
    assert a["embed_dimensions"] == 1536 and b["embed_dimensions"] == 3072
    assert a["vector_column_type"] == "vector" and b["vector_column_type"] == "halfvec"


def test_config_hash_moves_on_width_alone():
    """Width alone flips the hash, with the arm name and table held constant.

    The previous test changes four fields at once, so it would still pass if the
    hash keyed only on the table name. This one isolates the requirement.
    """
    from scripts.eval.retrieval.run_retrieval_eval import config_hash

    gt = _gt({"q1": {"d1"}})
    base = ea.arm_config(_spec("x", "t", "halfvec", 3072, "halfvec_cosine_ops"), gt, _corpus(), 50)
    narrow = dict(base, embed_dimensions=1536)
    assert config_hash(base) != config_hash(narrow)


def test_config_hash_carries_the_corpus_identity():
    from scripts.eval.retrieval.run_retrieval_eval import config_hash

    gt = _gt({"q1": {"d1"}})
    spec = _spec("x", "t", "halfvec", 3072, "halfvec_cosine_ops")
    a = ea.arm_config(spec, gt, _corpus(), 50)
    b = ea.arm_config(spec, gt, {"index_state": "5948c/344d", "index_digest": "deadbeef"}, 50)
    assert config_hash(a) != config_hash(b)


# ---------------------------------------------------------------------------
# Max-pooling and the separation statistic
# ---------------------------------------------------------------------------


def test_maxpooled_takes_the_best_chunk_not_the_mean():
    # Document 0 has one chunk aligned with the query and one orthogonal to it.
    # Max-pooling must read 1.0; averaging would read 0.5 and would be a
    # different quantity from the one the retriever ranks by.
    vecs = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    pooled = ea._MaxPooled(vecs, np.array([0, 0]), n_docs=1)
    assert pooled @ np.array([1.0, 0.0], dtype=np.float32) == pytest.approx([1.0])


def test_maxpooled_marks_documents_with_no_chunks_as_absent():
    vecs = np.array([[1.0, 0.0]], dtype=np.float32)
    pooled = ea._MaxPooled(vecs, np.array([0]), n_docs=2)
    out = pooled @ np.array([1.0, 0.0], dtype=np.float32)
    # -2.0 is below any cosine, so "no chunks" never outranks a real score.
    assert out[1] == -2.0


def test_documents_in_top_chunks_counts_chunks_not_documents():
    """Depth counts chunks; the relevance unit is documents. Not the same thing.

    Two chunks of document 0 outrank document 1's only chunk, so a depth of 2
    admits ONE document. Reading depth as a document count would admit both and
    would silently change the population the separation figure is computed over.
    """
    vecs = np.array([[1.0, 0.0], [0.99, 0.14], [0.0, 1.0]], dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    pooled = ea._MaxPooled(vecs, np.array([0, 0, 1]), n_docs=2)
    mask = pooled.documents_in_top_chunks(np.array([1.0, 0.0], dtype=np.float32), 2)
    assert mask.tolist() == [True, False]


def test_separation_reports_both_populations_and_they_differ():
    """Truncating the pool raises the irrelevant mean and shrinks the gap.

    This is why a separation number without its population is unreadable: the
    same vectors give 0.0886 over the whole corpus and 0.0594 over a 1,000-chunk
    pool, and the published figure is the second.
    """
    rng = np.random.default_rng(0)
    n_docs = 40
    vecs = rng.normal(size=(n_docs, 16)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    docs = [f"d{i}" for i in range(n_docs)]
    index = {d: i for i, d in enumerate(docs)}
    pooled = ea._MaxPooled(vecs, np.arange(n_docs), n_docs)

    gt = _gt({"q1": {"d0", "d1"}})
    q = vecs[0].copy()
    out = ea.separation(gt, pooled, index, lambda _t: q.tolist())

    assert set(out) == {"whole_corpus", f"pool_depth_{ea.PUBLISHED_SEPARATION_DEPTH}"}
    whole = out["whole_corpus"]
    assert whole["relevant"]["n"] == 2
    assert whole["irrelevant"]["n"] == n_docs - 2
    # d0 is the query itself, so relevant must separate upward.
    assert whole["gap"] > 0


def test_separation_gap_is_reported_in_standard_deviations():
    rng = np.random.default_rng(1)
    vecs = rng.normal(size=(10, 8)).astype(np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    index = {f"d{i}": i for i in range(10)}
    pooled = ea._MaxPooled(vecs, np.arange(10), 10)
    # Two relevant documents, not one: a standard deviation needs more than a
    # single observation, and a gap reported without one is not interpretable.
    out = ea.separation(_gt({"q1": {"d0", "d1"}}), pooled, index, lambda _t: vecs[0].tolist())
    w = out["whole_corpus"]
    assert w["pooled_sd"] is not None
    # The finding is stated in sigmas, not in raw cosine: a gap of 0.06 means
    # nothing until you know the spread it sits against.
    assert w["gap_in_sd"] == pytest.approx(w["gap"] / w["pooled_sd"], abs=1e-2)


# ---------------------------------------------------------------------------
# Ceilings
# ---------------------------------------------------------------------------


def test_ceiling_is_recomputed_for_whatever_query_set_is_passed():
    """A ceiling never travels. Two query sets, two ceilings, from the same code.

    Carrying one ceiling across subsets silently rescales every arm it touches,
    which is the single easiest way to publish a wrong percent-of-attainable.
    """
    gt_small = _gt({"q1": {"d1", "d2"}})           # 2 relevant -> ceiling@10 = 1.0
    gt_large = _gt({"q1": {f"d{i}" for i in range(20)}})  # 20 relevant -> 10/20
    small = ea.score_arm(gt_small, {"q1": {"d1": 0.9}}, k=10)
    large = ea.score_arm(gt_large, {"q1": {"d1": 0.9}}, k=10)
    assert small["ceilings"]["recall@10"] == 1.0
    assert large["ceilings"]["recall@10"] == 0.5


def test_score_arm_carries_n_alongside_every_number():
    gt = _gt({"q1": {"d1"}, "q2": {"d2"}})
    out = ea.score_arm(gt, {"q1": {"d1": 0.9}, "q2": {}}, k=10)
    assert out["n"] == 2
    assert out["n_judgments"] == 2
    assert set(out["ceilings"]) == {f"recall@{k}" for k in ea.CEILING_KS}


# ---------------------------------------------------------------------------
# Spend refusal
# ---------------------------------------------------------------------------


def test_query_embedding_refuses_to_spend_without_authorisation(tmp_path, monkeypatch):
    monkeypatch.setattr(ea, "QUERY_CACHE", tmp_path / "queries.json")
    gt = _gt({"q1": {"d1"}})
    with pytest.raises(ea.ArmError, match="allow-spend"):
        ea.embed_queries_3072(gt.query_list, allow_spend=False)


def test_query_embedding_rejects_a_cache_at_the_wrong_width(tmp_path, monkeypatch):
    """A 1536-wide cache under the 3072 name would silently measure the control twice.

    That failure is invisible in every downstream number: the arm would run, the
    plan would read `index`, recall would land near the control, and the
    conclusion would be "no signal in the discarded dimensions" for the wrong
    reason. So the width is asserted rather than assumed.
    """
    cache = tmp_path / "queries.json"
    cache.write_text(json.dumps({ea._key_of("claim q1"): [0.0] * 1536}))
    monkeypatch.setattr(ea, "QUERY_CACHE", cache)
    with pytest.raises(ea.ArmError, match="widths"):
        ea.embed_queries_3072(_gt({"q1": {"d1"}}).query_list, allow_spend=False)


def test_cost_estimate_is_labelled_as_an_upper_bound_not_the_bill():
    # The harness records prompt tokens as len(text)//4. Measured against
    # cl100k_base on this corpus that under-counts by 17.6% -- 8.90M estimated
    # against 10.46M actual -- so the ledger figure is a FLOOR on the bill, not
    # the bill. EMBEDDING.md reports both.
    source = (ea.EVAL_DIR / "retrieval" / "embed_arms.py").read_text()
    assert "upper bound on the bill" in source


# ---------------------------------------------------------------------------
# DB-gated: the published arms must reproduce
# ---------------------------------------------------------------------------


def _db_available() -> bool:
    try:
        from scripts.eval import db

        return db.healthcheck()
    except Exception:  # noqa: BLE001
        return False


def _arm_table_loaded() -> bool:
    try:
        from scripts.eval import db

        with db.get_connection() as conn, conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM public.{ea.ARM_3072_TABLE}")
            return cur.fetchone()[0] == 5948
    except Exception:  # noqa: BLE001
        return False


needs_db = pytest.mark.skipif(not _db_available(), reason="local pgvector not running")
needs_arm = pytest.mark.skipif(
    not _arm_table_loaded(),
    reason="document_chunks_3072 not loaded; run embed_arms --mode embed --allow-spend then --mode load",
)


@needs_db
def test_control_separation_reproduces_the_published_0593():
    """The instrument check that makes the arm's number believable.

    ``FIRSTSTAGE.md`` §2.5 published 0.4415 relevant against 0.3821 irrelevant,
    n = 7,346 and 55,562, over a pool rather than the whole corpus. This module
    recomputes it from scratch, through different code, and must land on the same
    four decimals AND the same two population sizes. Matching means matching --
    a gap that reproduced over a population of a different size would be a
    coincidence, not a reproduction.
    """
    from scripts.eval.retrieval import firststage as fs
    from scripts.eval.retrieval.adapters import production_embed_fn

    gt = fs.load_ground_truth()
    fs.assert_corpus(fs.index_identity())
    mat, index = ea.doc_matrix_1536(gt)
    out = ea.separation(gt, mat, index, production_embed_fn(ea.EMBED_MODEL))
    pool = out[f"pool_depth_{ea.PUBLISHED_SEPARATION_DEPTH}"]

    assert pool["relevant"]["mean"] == pytest.approx(0.4415, abs=0.0002)
    assert pool["irrelevant"]["mean"] == pytest.approx(0.3821, abs=0.0002)
    assert pool["gap"] == pytest.approx(0.0594, abs=0.0002)
    assert pool["relevant"]["n"] == 7346
    assert pool["irrelevant"]["n"] == 55562
    # Under one standard deviation. This is the sentence the whole embedding lane
    # was opened on, and it is asserted so it cannot decay into folklore.
    assert pool["gap_in_sd"] < 1.0


@needs_db
def test_control_exact_reproduces_the_published_2227():
    """The exact whole-corpus control, with no HNSW graph in it, is 0.2227.

    Published in FIRSTSTAGE.md §2.1 from a sequential-scan query; recomputed here
    in memory from the same stored vectors. The two must agree, otherwise this
    module's in-memory scoring path is not measuring the same thing the database
    measures and every exact delta it reports is void.
    """
    from scripts.eval.retrieval import firststage as fs
    from scripts.eval.retrieval.adapters import production_embed_fn

    gt = fs.load_ground_truth()
    mat, index = ea.doc_matrix_1536(gt)
    pools = ea.exact_pools(gt, mat, index, production_embed_fn(ea.EMBED_MODEL))
    scored = ea.score_arm(gt, pools, 10)
    assert scored["n"] == 338
    assert scored["metrics"]["recall@10"] == pytest.approx(0.2227, abs=0.0002)
    assert scored["ceilings"]["recall@10"] == 0.5199


@needs_db
@needs_arm
def test_the_arm_table_holds_the_same_chunks_at_full_width():
    """Same chunk ids, different width. Anything else and the arms are not comparable."""
    from scripts.eval import db

    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT count(*) FROM public.{ea.ARM_3072_TABLE} a
            FULL OUTER JOIN public.document_chunks c ON c.id = a.id
            WHERE a.id IS NULL OR c.id IS NULL
            """
        )
        assert cur.fetchone()[0] == 0
        cur.execute(f"SELECT DISTINCT vector_dims(embedding) FROM public.{ea.ARM_3072_TABLE}")
        assert [r[0] for r in cur.fetchall()] == [3072]


@needs_db
@needs_arm
def test_the_arm_index_is_hnsw_over_halfvec_and_the_plan_is_an_index_scan():
    """A plan flip is not an embedding result, so the plan is pinned, not assumed."""
    from scripts.eval import db
    from scripts.eval.retrieval import firststage as fs

    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT indexdef FROM pg_indexes WHERE indexname = %s",
            (f"idx_{ea.ARM_3072_TABLE}_embedding",),
        )
        indexdef = cur.fetchone()[0]
    assert "USING hnsw" in indexdef
    assert "halfvec_cosine_ops" in indexdef

    gt = fs.load_ground_truth()
    q3072 = ea.embed_queries_3072(gt.query_list, allow_spend=False)
    spec = ea.ArmSpec("native_3072_halfvec", ea.ARM_3072_TABLE, "halfvec", 3072,
                      "halfvec_cosine_ops", q3072)
    out = ea.retrieve_arm(gt, spec, lambda t: q3072[ea._key_of(t)], depth=50)
    assert out["plan_observed"] == "index"


@needs_db
@needs_arm
def test_published_arms_reproduce_and_the_separation_does_not_move():
    """The result in EMBEDDING.md, end to end.

    The headline is a NULL and it is pinned as one. If a future change makes the
    3072 arm actually win, this test fails and the document has to be rewritten
    -- which is the correct outcome, not a nuisance. What must not happen is the
    number drifting while the prose keeps saying "flat".
    """
    record = ea.run_arms(allow_spend=False, with_separation=True, write=False)
    control, arm = record["arms"]

    assert record["n"] == 338
    assert control["ceilings"]["recall@10"] == 0.5199
    assert arm["ceilings"]["recall@10"] == 0.5199
    assert control["config_hash"] != arm["config_hash"]
    assert control["plan_observed"] == "index" and arm["plan_observed"] == "index"

    # The shared corpus was untouched across the whole run.
    assert record["document_chunks_digest_before"] == "8d3edbe3f3b28cdb"
    assert record["document_chunks_digest_after"] == "8d3edbe3f3b28cdb"

    assert control["metrics"]["recall@10"] == pytest.approx(0.2199, abs=0.0002)
    assert arm["metrics"]["recall@10"] == pytest.approx(0.2229, abs=0.0002)
    assert control["exact_whole_corpus"]["metrics"]["recall@10"] == pytest.approx(0.2227, abs=2e-4)
    assert arm["exact_whole_corpus"]["metrics"]["recall@10"] == pytest.approx(0.2247, abs=2e-4)

    # THE FINDING. Doubling the width moves recall@10 by under 0.003 with the
    # HNSW graph in the comparison and under 0.002 without it, against 0.2972 of
    # headroom -- and the separation, which is the mechanism any real embedding
    # gain would have to move, does not move at all.
    assert abs(record["delta"]["recall@10"]) < 0.005
    assert abs(record["delta_exact"]["recall@10"]) < 0.005
    for population, moved in record["delta_separation"].items():
        assert abs(moved) < 0.002, f"separation moved on {population}: {moved}"

    # halfvec at DOUBLE the width is SMALLER on disk than vector at half of it.
    # That is the N9 quantization question answered as a side effect.
    assert arm["storage"]["index_bytes"] < control["storage"]["index_bytes"]
    assert arm["storage"]["table_total_bytes"] < control["storage"]["table_total_bytes"]
