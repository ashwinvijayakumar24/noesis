"""End-to-end sweep against a TINY SYNTHETIC table.

Synthetic on purpose: these tests assert the machinery (one record per
configuration, cleanup actually drops, a failed build is recorded not raised),
not the numbers. Running them against the real corpus would make them slow,
order-dependent, and -- worse -- would create and drop indexes on the table every
other measurement in this repo depends on.

Every test SKIPS when the local pgvector container is unreachable.
"""

from __future__ import annotations

import uuid

import psycopg2.extras
import pytest

from scripts.eval.ann_sweep.grid import BuildConfig, EfSearchConfig
from scripts.eval.ann_sweep.index_ops import (
    build_hnsw_index,
    drop_created_indexes,
    drop_index,
    find_stray_sweep_indexes,
    index_size_bytes,
    snapshot_indexes,
    snapshot_signature,
    verify_restored,
)
from scripts.eval.ann_sweep.search import SearchSpec, index_used, measurement_txn, run_search
from scripts.eval.ann_sweep.sweep import (
    QuerySet,
    corpus_fingerprint,
    probe_planner_choice,
    run_build_sweep,
    run_ef_search_sweep,
    run_exact_baseline,
)

from .conftest import requires_db  # noqa: F401  (imported for the marker)

pytestmark = requires_db

DIM = 16
#: Enough rows that the planner prefers an HNSW index scan over a sequential
#: scan. Below roughly a thousand rows it does not, and every build-sweep record
#: would then be measuring a seq scan while claiming to measure an index.
N_ROWS = 2000
N_DOCS = 40
TABLE = "ann_sweep_test_chunks"


def _vec(seed: int) -> list[float]:
    """Deterministic pseudo-random unit-ish vector. No numpy, no RNG state."""
    import math

    return [math.sin(seed * (i + 1) * 0.7331) for i in range(DIM)]


@pytest.fixture
def synthetic(conn):
    """A throwaway table with its own HNSW index, dropped afterwards."""
    project_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS public.{TABLE} CASCADE")
        cur.execute(
            f"""
            CREATE TABLE public.{TABLE} (
                id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id uuid NOT NULL,
                project_id uuid NOT NULL,
                embedding vector({DIM})
            )
            """
        )
        rows = [
            (str(uuid.UUID(int=i % N_DOCS)), project_id,
             "[" + ",".join(repr(x) for x in _vec(i)) + "]")
            for i in range(N_ROWS)
        ]
        psycopg2.extras.execute_values(
            cur,
            f"INSERT INTO public.{TABLE} (document_id, project_id, embedding) VALUES %s",
            rows,
            template="(%s::uuid, %s::uuid, %s::vector)",
            page_size=500,
        )
        cur.execute(
            f"CREATE INDEX {TABLE}_baseline_hnsw ON public.{TABLE} "
            "USING hnsw (embedding vector_cosine_ops)"
        )
        cur.execute(f"ANALYZE public.{TABLE}")
    conn.commit()

    spec = SearchSpec(table=TABLE, project_id=project_id, join_documents=False)
    yield spec

    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS public.{TABLE} CASCADE")
    conn.commit()


@pytest.fixture
def queries():
    return QuerySet(
        query_ids=[f"q{i}" for i in range(5)],
        embeddings=[_vec(1000 + i) for i in range(5)],
        fingerprint="synthetic",
    )


# ---------------------------------------------------------------------------
# Basic plumbing
# ---------------------------------------------------------------------------


def test_corpus_fingerprint_counts_documents_and_chunks(conn, synthetic):
    fp = corpus_fingerprint(conn, synthetic)
    assert fp.chunks == N_ROWS
    assert fp.documents == N_DOCS
    assert fp.table == TABLE


def test_exact_mode_uses_no_index(conn, synthetic, queries):
    with measurement_txn(conn, synthetic, exact=True):
        from scripts.eval.ann_sweep.search import explain_plan_text

        plan = explain_plan_text(conn, synthetic, queries.embeddings[0], 10)
    assert index_used(plan) is None, plan


def test_measurement_txn_rolls_back_dropped_indexes(conn, synthetic, queries):
    """The production index is never really dropped -- that is the whole trick."""
    before = snapshot_signature(snapshot_indexes(conn, TABLE))
    cfg = BuildConfig(8, 32)
    assert build_hnsw_index(conn, cfg, table=TABLE).ok
    try:
        with measurement_txn(conn, synthetic, keep_index=cfg.index_name):
            names = [i.name for i in snapshot_indexes(conn, TABLE)]
            assert f"{TABLE}_baseline_hnsw" not in names  # dropped inside the txn
            assert cfg.index_name in names
        after = [i.name for i in snapshot_indexes(conn, TABLE)]
        assert f"{TABLE}_baseline_hnsw" in after  # ... and back after rollback
    finally:
        drop_index(conn, cfg.index_name)
    assert snapshot_signature(snapshot_indexes(conn, TABLE)) == before


def test_keep_index_refuses_an_index_that_is_not_there(conn, synthetic):
    with pytest.raises(ValueError, match="Refusing to measure"):
        with measurement_txn(conn, synthetic, keep_index="does_not_exist"):
            pass


def test_search_returns_at_most_k_rows(conn, synthetic, queries):
    with measurement_txn(conn, synthetic, ef_search=40):
        rows = run_search(conn, synthetic, queries.embeddings[0], 7)
    assert len(rows) == 7
    assert all(r.chunk_id for r in rows)
    # Similarity is 1 - cosine distance, so it must be non-increasing down the list.
    sims = [r.similarity for r in rows]
    assert sims == sorted(sims, reverse=True)


# ---------------------------------------------------------------------------
# One record per configuration
# ---------------------------------------------------------------------------


def test_ef_search_sweep_produces_one_record_per_configuration(conn, synthetic, queries, tmp_path):
    path = tmp_path / "r.jsonl"
    configs = [EfSearchConfig(10), EfSearchConfig(40), EfSearchConfig(80)]
    out = run_ef_search_sweep(
        conn, synthetic, queries, corpus_fingerprint(conn, synthetic), configs,
        k=10, repetitions=1, warmup=0, results_path=path,
    )
    assert len(out.records) == len(configs)
    assert [r["params"]["ef_search"] for r in out.records] == [10, 40, 80]
    assert all(r["status"] == "ok" for r in out.records)
    assert len(path.read_text().splitlines()) == len(configs)


def test_ef_search_sweep_records_carry_latency_with_its_method(conn, synthetic, queries):
    out = run_ef_search_sweep(
        conn, synthetic, queries, corpus_fingerprint(conn, synthetic),
        [EfSearchConfig(40)], k=10, repetitions=2, warmup=1, results_path=None,
    )
    rec = out.records[0]
    lat = rec["latency_server_ms"]
    assert lat["n_samples"] == len(queries) * 2
    assert lat["n_repetitions"] == 2
    assert lat["n_warmup_discarded"] == len(queries)
    assert lat["p50_ms"] <= lat["p95_ms"]
    assert "p99" not in rec["latency_method"].replace("no p99", "")


def test_exact_baseline_is_the_ground_truth_and_ann_recall_is_relative_to_it(
    conn, synthetic, queries
):
    corpus = corpus_fingerprint(conn, synthetic)
    exact_ids, exact_rec = run_exact_baseline(
        conn, synthetic, queries, corpus, k=10, repetitions=1, warmup=0, results_path=None
    )
    assert exact_rec["plan_index_used"] is None
    assert set(exact_ids) == set(queries.query_ids)

    out = run_ef_search_sweep(
        conn, synthetic, queries, corpus, [EfSearchConfig(320)],
        exact_chunk_ids=exact_ids, k=10, repetitions=1, warmup=0, results_path=None,
    )
    ann = out.records[0]["ann_recall_vs_exact"]
    assert 0.0 <= ann["recall@10"] <= 1.0
    # A generous ef_search on 400 rows should find essentially everything.
    assert ann["recall@10"] > 0.9


def test_build_sweep_produces_one_record_per_configuration(conn, synthetic, queries, tmp_path):
    path = tmp_path / "r.jsonl"
    configs = [BuildConfig(4, 16), BuildConfig(8, 32)]
    out = run_build_sweep(
        conn, synthetic, queries, corpus_fingerprint(conn, synthetic), configs,
        k=10, ef_search=40, repetitions=1, warmup=0, results_path=path,
    )
    assert len(out.records) == 2
    assert [(r["params"]["m"], r["params"]["ef_construction"]) for r in out.records] == [(4, 16), (8, 32)]
    assert all(r["status"] == "ok" for r in out.records), [r.get("error") for r in out.records]
    assert all(r["build"]["build_seconds"] > 0 for r in out.records)
    assert all(r["build"]["index_bytes"] > 0 for r in out.records)
    assert len(path.read_text().splitlines()) == 2


def test_build_sweep_measures_the_index_it_built_not_another_one(conn, synthetic, queries):
    out = run_build_sweep(
        conn, synthetic, queries, corpus_fingerprint(conn, synthetic), [BuildConfig(8, 32)],
        k=10, ef_search=40, repetitions=1, warmup=0, results_path=None,
    )
    assert out.records[0]["plan_index_used"] == "ann_sweep_hnsw_m8_efc32"
    assert out.records[0]["index_scan_forced"] is True


def test_forcing_the_index_scan_is_recorded_on_the_record(conn, synthetic, queries):
    """A forced plan describes the index, not what production executes. A record
    that does not say which of the two it is cannot be quoted either way."""
    corpus = corpus_fingerprint(conn, synthetic)
    free = run_ef_search_sweep(
        conn, synthetic, queries, corpus, [EfSearchConfig(80)],
        k=10, force_index_scan=False, repetitions=1, warmup=0, results_path=None,
    ).records[0]
    forced = run_ef_search_sweep(
        conn, synthetic, queries, corpus, [EfSearchConfig(80)],
        k=10, force_index_scan=True, repetitions=1, warmup=0, results_path=None,
    ).records[0]
    assert free["index_scan_forced"] is False
    assert forced["index_scan_forced"] is True
    assert forced["plan_index_used"] is not None


def test_planner_choice_probe_reports_one_row_per_k_and_changes_nothing(conn, synthetic, queries):
    before = snapshot_signature(snapshot_indexes(conn, TABLE))
    rec = probe_planner_choice(
        conn, synthetic, queries, corpus_fingerprint(conn, synthetic),
        k_values=(1, 10, 50), results_path=None,
    )
    assert [r["k"] for r in rec["planner_choice_by_k"]] == [1, 10, 50]
    assert set(rec["plans"]) == {"1", "10", "50"}
    assert snapshot_signature(snapshot_indexes(conn, TABLE)) == before


def test_stored_plans_do_not_contain_raw_embedding_literals(conn, synthetic, queries):
    """A 1536-float literal per plan would make the results file unreadable and
    is not evidence about anything."""
    out = run_ef_search_sweep(
        conn, synthetic, queries, corpus_fingerprint(conn, synthetic), [EfSearchConfig(40)],
        k=10, repetitions=1, warmup=0, results_path=None,
    )
    plan = out.records[0]["plan"]
    assert "'<vector>'" in plan
    assert len(plan) < 2000


# ---------------------------------------------------------------------------
# Failure is recorded, not raised
# ---------------------------------------------------------------------------


def test_unbuildable_configuration_is_recorded_and_the_sweep_continues(
    conn, synthetic, queries, tmp_path
):
    """m=1 is below pgvector's minimum. Losing the other points of a grid
    because point 1 was invalid would be an own goal."""
    path = tmp_path / "r.jsonl"
    configs = [BuildConfig(1, 64), BuildConfig(8, 32)]
    out = run_build_sweep(
        conn, synthetic, queries, corpus_fingerprint(conn, synthetic), configs,
        k=10, ef_search=40, repetitions=1, warmup=0, results_path=path,
    )
    assert len(out.records) == 2
    failed, ok = out.records
    assert failed["status"] == "build_failed"
    assert failed["error"]
    assert failed["build"]["status"] == "build_failed"
    assert failed["latency_server_ms"] is None
    assert ok["status"] == "ok"
    assert len(path.read_text().splitlines()) == 2


def test_failed_build_leaves_the_connection_usable(conn, synthetic):
    outcome = build_hnsw_index(conn, BuildConfig(1, 64), table=TABLE)
    assert not outcome.ok
    # A poisoned transaction would make this raise InFailedSqlTransaction.
    assert corpus_fingerprint(conn, synthetic).chunks == N_ROWS


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def test_build_sweep_drops_each_index_after_measuring_it(conn, synthetic, queries):
    before = snapshot_signature(snapshot_indexes(conn, TABLE))
    out = run_build_sweep(
        conn, synthetic, queries, corpus_fingerprint(conn, synthetic),
        [BuildConfig(4, 16), BuildConfig(8, 32)],
        k=10, ef_search=40, repetitions=1, warmup=0, results_path=None,
    )
    assert out.created_indexes == []
    assert find_stray_sweep_indexes(conn, TABLE) == []
    assert snapshot_signature(snapshot_indexes(conn, TABLE)) == before


def test_drop_created_indexes_actually_drops_what_it_created(conn, synthetic):
    cfg = BuildConfig(8, 32)
    assert build_hnsw_index(conn, cfg, table=TABLE).ok
    assert cfg.index_name in [i.name for i in snapshot_indexes(conn, TABLE)]
    assert index_size_bytes(conn, cfg.index_name) > 0

    dropped = drop_created_indexes(conn, [cfg.index_name])
    assert dropped == [cfg.index_name]
    assert cfg.index_name not in [i.name for i in snapshot_indexes(conn, TABLE)]
    assert index_size_bytes(conn, cfg.index_name) is None
    # Idempotent: dropping again reports nothing was there.
    assert drop_created_indexes(conn, [cfg.index_name]) == []


def test_verify_restored_detects_a_stray(conn, synthetic):
    before = snapshot_indexes(conn, TABLE)
    cfg = BuildConfig(8, 32)
    assert build_hnsw_index(conn, cfg, table=TABLE).ok
    try:
        report = verify_restored(conn, before, TABLE)
        assert report.restored is False
        assert cfg.index_name in report.strays
        assert cfg.index_name in report.to_dict()["added"][0]
    finally:
        drop_index(conn, cfg.index_name)
    assert verify_restored(conn, before, TABLE).restored is True


def test_verify_restored_compares_definitions_not_just_names(conn, synthetic):
    """A same-named index rebuilt with different reloptions is NOT the same index."""
    before = snapshot_indexes(conn, TABLE)
    with conn.cursor() as cur:
        cur.execute(f"DROP INDEX public.{TABLE}_baseline_hnsw")
        cur.execute(
            f"CREATE INDEX {TABLE}_baseline_hnsw ON public.{TABLE} "
            "USING hnsw (embedding vector_cosine_ops) WITH (m = 8, ef_construction = 32)"
        )
    conn.commit()
    report = verify_restored(conn, before, TABLE)
    assert report.restored is False
    assert report.strays == []  # names match; only the definition drifted
