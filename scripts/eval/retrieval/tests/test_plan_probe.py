"""The plan field: is it recorded, and is it right?

The point of this file is that docs/MEASUREMENTS.md §Retrieval baseline (superseded) published a row called
"dense (pgvector HNSW, cosine)" that was measured against an exhaustive
sequential scan. Nothing detected it because nothing asked Postgres. These tests
make the asking non-optional.

The DB-backed tests skip cleanly without a local pgvector, so the file is green
on a laptop with no database.
"""

import pytest

from scripts.eval.retrieval.adapters import DenseRetriever, MockRetriever
from scripts.eval.retrieval.plan_probe import (
    DENSE_BODY_SQL,
    DENSE_INDEX_NAME,
    PLAN_INDEX,
    PLAN_MIXED,
    PLAN_SEQSCAN,
    PLAN_UNKNOWN,
    classify_plan,
    find_crossover,
    probe_plan,
    summarise_plans,
)

INDEX_PLAN = """Limit
  ->  Nested Loop
        ->  Index Scan using idx_document_chunks_embedding on document_chunks dc
              Order By: (embedding <=> '[...]'::vector)
        ->  Index Only Scan using documents_pkey on documents d
"""

SEQ_PLAN = """Limit
  ->  Sort
        Sort Key: ((dc.embedding <=> '[...]'::vector))
        ->  Hash Join
              ->  Seq Scan on document_chunks dc
              ->  Hash
                    ->  Seq Scan on documents d
"""


def test_classify_index_and_seqscan():
    assert classify_plan(INDEX_PLAN) == PLAN_INDEX
    assert classify_plan(SEQ_PLAN) == PLAN_SEQSCAN


def test_classify_keys_on_the_vector_index_not_on_the_absence_of_seq_scan():
    """The index-scan plan ALSO contains a scan of `documents`.

    A naive "no 'Seq Scan' anywhere" rule would call the real index plan a
    sequential scan whenever the join side happens to be scanned -- which is what
    Postgres does at some depths. Only the vector index decides the question.
    """
    mixed = INDEX_PLAN.replace("Index Only Scan using documents_pkey", "Seq Scan")
    assert "Seq Scan" in mixed
    assert classify_plan(mixed) == PLAN_INDEX


def test_summarise_plans():
    assert summarise_plans([]) == PLAN_UNKNOWN
    assert summarise_plans([PLAN_INDEX, PLAN_INDEX]) == PLAN_INDEX
    assert summarise_plans([PLAN_SEQSCAN]) == PLAN_SEQSCAN
    # Never collapsed to a majority: "half this arm was HNSW" is its own finding.
    assert summarise_plans([PLAN_INDEX, PLAN_SEQSCAN]) == PLAN_MIXED


def test_dense_retriever_records_a_plan_per_query(monkeypatch):
    import contextlib
    import types

    from scripts.eval.retrieval import adapters as A

    fake = types.ModuleType("db")
    fake.get_connection = lambda **kw: contextlib.nullcontext("CONN")
    fake.match_document_chunks = lambda conn, e, p, k: [
        {"id": "c1", "document_id": "d1", "similarity": 0.5}
    ]
    monkeypatch.setattr(A, "_load_db_module", lambda: fake)
    monkeypatch.setattr(A, "probe_plan", lambda conn, emb, pid, k: (
        PLAN_INDEX if k <= 100 else PLAN_SEQSCAN
    ))

    r = DenseRetriever(project_id="p", embed_fn=lambda q: [0.0])
    r.retrieve("a", 50)
    r.retrieve("b", 50)
    assert r.plan_kinds == [PLAN_INDEX, PLAN_INDEX]
    assert r.plan_summary() == PLAN_INDEX

    r.retrieve("c", 200)
    assert r.plan_summary() == PLAN_MIXED


def test_plan_is_unknown_when_probing_is_off():
    r = DenseRetriever(project_id="p", embed_fn=lambda q: [0.0], record_plan=False)
    assert r.plan_summary() == PLAN_UNKNOWN


def test_retriever_without_a_probe_reports_unknown():
    """A mock has no plan. It must say "unknown", not "index"."""
    assert not hasattr(MockRetriever([]), "plan_summary")


# ---------------------------------------------------------------------------
# Against the live database
# ---------------------------------------------------------------------------


def _conn_or_skip():
    try:
        from scripts.eval import db
    except ImportError:  # pragma: no cover
        pytest.skip("scripts/eval/db.py unavailable")
    if not db.healthcheck():
        pytest.skip("local pgvector not reachable")
    return db


PID = "e7a1c0b0-0000-4000-8000-000000000001"


def _an_embedding():
    import json
    from pathlib import Path

    path = (Path(__file__).resolve().parents[2] / "cache" / "ann_sweep_embeddings"
            / "text-embedding-3-large.json")
    if not path.exists():
        pytest.skip("no cached query embedding")
    return next(iter(json.loads(path.read_text()).values()))


def test_probe_reports_index_shallow_and_seqscan_deep():
    db = _conn_or_skip()
    emb = _an_embedding()
    with db.get_connection() as conn:
        assert probe_plan(conn, emb, PID, 10) == PLAN_INDEX
        assert probe_plan(conn, emb, PID, 500) == PLAN_SEQSCAN


def test_crossover_is_found_and_is_a_real_boundary():
    db = _conn_or_skip()
    emb = _an_embedding()
    with db.get_connection() as conn:
        found = find_crossover(conn, emb, PID, lo=1, hi=1024)
        assert found is not None
        last_index, first_seq = found
        assert first_seq == last_index + 1
        assert probe_plan(conn, emb, PID, last_index) == PLAN_INDEX
        assert probe_plan(conn, emb, PID, first_seq) == PLAN_SEQSCAN


def test_probe_sql_matches_the_deployed_rpc_body():
    """Drift guard: the probe EXPLAINs a copy of the RPC's body, because EXPLAIN
    of a plpgsql call reports one Function Scan and hides the real plan."""
    db = _conn_or_skip()
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_get_functiondef(p.oid) FROM pg_proc p "
                "JOIN pg_namespace n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'public' AND p.proname = 'match_document_chunks'"
            )
            row = cur.fetchone()
    if not row:
        pytest.skip("match_document_chunks not deployed")
    body = " ".join(row[0].split()).lower()
    probe = " ".join(DENSE_BODY_SQL.split()).lower()
    # Same shape: same join, same filter column, same ordering expression.
    assert "inner join documents" in body
    assert "inner join public.documents" in probe
    assert "order by document_chunks.embedding <=> query_embedding" in body
    assert "order by dc.embedding <=>" in probe
    assert "set local hnsw.ef_search = 80" in body


def test_the_hnsw_index_the_probe_looks_for_actually_exists():
    db = _conn_or_skip()
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT indexdef FROM pg_indexes WHERE indexname = %s",
                        (DENSE_INDEX_NAME,))
            row = cur.fetchone()
    assert row is not None, f"{DENSE_INDEX_NAME} is missing; every plan would be a seqscan"
    assert "hnsw" in row[0].lower()
