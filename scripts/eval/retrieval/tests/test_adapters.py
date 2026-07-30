"""Retriever adapters: determinism, protocol conformance, and lazy DB import."""

import builtins

import pytest

from scripts.eval.retrieval.adapters import (
    DenseRetriever,
    HybridRetriever,
    KeywordRetriever,
    MockRetriever,
    RetrievedDoc,
    Retriever,
    RetrieverUnavailable,
    build_retriever,
)

DOCS = [f"d{i}" for i in range(20)]


def test_mock_conforms_to_protocol():
    assert isinstance(MockRetriever(DOCS), Retriever)


def test_mock_is_deterministic_across_instances():
    a = MockRetriever(DOCS, seed=7).retrieve("scaling laws", 5)
    b = MockRetriever(DOCS, seed=7).retrieve("scaling laws", 5)
    assert [d.doc_id for d in a] == [d.doc_id for d in b]


def test_mock_seed_changes_ordering():
    a = [d.doc_id for d in MockRetriever(DOCS, seed=1).retrieve("q", 10)]
    b = [d.doc_id for d in MockRetriever(DOCS, seed=2).retrieve("q", 10)]
    assert a != b


def test_mock_ordering_is_query_dependent():
    a = [d.doc_id for d in MockRetriever(DOCS, seed=0).retrieve("alpha", 10)]
    b = [d.doc_id for d in MockRetriever(DOCS, seed=0).retrieve("beta", 10)]
    assert a != b


def test_mock_returns_k_results_with_dense_strictly_decreasing_scores():
    out = MockRetriever(DOCS).retrieve("q", 6)
    assert len(out) == 6
    assert [d.rank for d in out] == [1, 2, 3, 4, 5, 6]
    assert all(out[i].score > out[i + 1].score for i in range(len(out) - 1))


def test_mock_k_larger_than_corpus():
    assert len(MockRetriever(["a", "b"]).retrieve("q", 50)) == 2


def test_mock_empty_corpus():
    assert MockRetriever([]).retrieve("q", 5) == []


def test_mock_populates_all_required_fields():
    d = MockRetriever(DOCS).retrieve("q", 1)[0]
    assert isinstance(d, RetrievedDoc)
    assert d.doc_id and d.chunk_id and d.section_id
    assert d.rank == 1 and 0.0 <= d.score <= 1.0


def test_mock_planting_puts_relevant_docs_on_top():
    """A known non-degenerate operating point, so the harness isn't only tested at chance."""
    relevant = ["d3", "d7", "d11", "d15"]
    r = MockRetriever(DOCS, seed=0, relevant_by_query={"q": relevant}, plant_rate=0.5)
    top = [d.doc_id for d in r.retrieve("q", 10)][:2]
    assert set(top) == {"d11", "d15"}  # sorted(relevant)[:2]


def test_mock_plant_rate_zero_plants_nothing():
    r = MockRetriever(DOCS, seed=0, relevant_by_query={"q": DOCS[:4]}, plant_rate=0.0)
    unplanted = MockRetriever(DOCS, seed=0)
    assert [d.doc_id for d in r.retrieve("q", 10)] == [
        d.doc_id for d in unplanted.retrieve("q", 10)
    ]


# ---------------------------------------------------------------------------
# DB-backed adapters: must not import db at module load
# ---------------------------------------------------------------------------


def _hide_db(monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "db" or name.endswith("eval.db") or (fromlist and "db" in fromlist
                                                        and name == "scripts.eval"):
            raise ImportError("no db module")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_dense_retriever_raises_clear_error_when_db_missing(monkeypatch):
    _hide_db(monkeypatch)
    with pytest.raises(RetrieverUnavailable) as exc:
        DenseRetriever(project_id="p1").retrieve("query", 5)
    msg = str(exc.value)
    assert "db.py" in msg                     # says what is missing
    assert "match_document_chunks" in msg     # says what it must expose
    assert "--retriever mock" in msg          # says what to do instead


def test_keyword_retriever_raises_clear_error_when_db_missing(monkeypatch):
    _hide_db(monkeypatch)
    with pytest.raises(RetrieverUnavailable, match="db.py"):
        KeywordRetriever(project_id="p1").retrieve("query", 5)


def test_constructing_db_retrievers_does_not_need_db(monkeypatch):
    """Import is lazy: construction must succeed with no database present."""
    _hide_db(monkeypatch)
    assert DenseRetriever(project_id="p1").name == "dense"
    assert KeywordRetriever(project_id="p1").name == "keyword"


def _fake_db(monkeypatch, **fns):
    """Stand in for scripts/eval/db.py with its real positional signatures:
    match_document_chunks(conn, embedding, project_id, match_count) and
    keyword_search_chunks(conn, project_id, query, match_count).
    """
    import contextlib
    import types

    from scripts.eval.retrieval import adapters as A

    fake = types.ModuleType("db")
    fake.get_connection = lambda **kw: contextlib.nullcontext("CONN")
    for name, fn in fns.items():
        setattr(fake, name, fn)
    monkeypatch.setattr(A, "_load_db_module", lambda: fake)
    return fake


def test_db_retrievers_map_rpc_rows_to_retrieved_docs(monkeypatch):
    _fake_db(
        monkeypatch,
        match_document_chunks=lambda conn, embedding, project_id, match_count: [
            {"id": "c1", "document_id": "docA", "similarity": 0.81, "content": "text"},
            {"id": "c2", "document_id": "docB", "similarity": 0.62, "content": "more"},
        ],
        keyword_search_chunks=lambda conn, project_id, query, match_count: [
            {"chunk_id": "k1", "doc_id": "docC", "rank": 0.33},
        ],
    )

    dense = DenseRetriever(project_id="p1", embed_fn=lambda q: [0.1] * 4).retrieve("q", 2)
    assert [d.doc_id for d in dense] == ["docA", "docB"]
    assert [d.rank for d in dense] == [1, 2]
    assert dense[0].score == pytest.approx(0.81)

    kw = KeywordRetriever(project_id="p1").retrieve("q", 2)
    assert kw[0].doc_id == "docC" and kw[0].score == pytest.approx(0.33)


def test_dense_requires_an_injected_embedder(monkeypatch):
    """The embedding model belongs to the system under test, not to the ruler."""
    _fake_db(monkeypatch, match_document_chunks=lambda *a: [])
    with pytest.raises(RetrieverUnavailable, match="embed_fn"):
        DenseRetriever(project_id="p1").retrieve("q", 5)


def test_db_retrievers_handle_empty_rpc_result(monkeypatch):
    _fake_db(
        monkeypatch,
        match_document_chunks=lambda *a: [],
        keyword_search_chunks=lambda *a: None,
    )
    assert DenseRetriever(project_id="p", embed_fn=lambda q: [0.0]).retrieve("q", 5) == []
    assert KeywordRetriever(project_id="p").retrieve("q", 5) == []


def test_keyword_retriever_does_not_swallow_rpc_errors(monkeypatch):
    """rag_retrieval swallows 42703 and returns []; a broken RPC must fail the eval."""

    def boom(*args):
        raise RuntimeError("column dc.metadata does not exist (42703)")

    _fake_db(monkeypatch, keyword_search_chunks=boom)
    with pytest.raises(RuntimeError, match="42703"):
        KeywordRetriever(project_id="p").retrieve("q", 5)


# ---------------------------------------------------------------------------
# Hybrid stub
# ---------------------------------------------------------------------------


def test_hybrid_is_a_deliberate_stub():
    h = HybridRetriever(MockRetriever(DOCS), MockRetriever(DOCS))
    with pytest.raises(NotImplementedError, match="deliberate stub"):
        h.retrieve("q", 5)


def test_factory():
    assert isinstance(build_retriever("mock", doc_ids=DOCS), MockRetriever)
    assert isinstance(build_retriever("dense", project_id="p"), DenseRetriever)
    with pytest.raises(ValueError, match="Unknown retriever"):
        build_retriever("magic")


# ---------------------------------------------------------------------------
# The document-id join, and the constants it is mirrored from
# ---------------------------------------------------------------------------


def test_db_document_id_matches_the_uuid5_scheme_ingest_writes():
    import uuid

    from scripts.eval.retrieval.adapters import EVAL_DOC_NAMESPACE, db_document_id

    sha = "a" * 64
    assert db_document_id(sha) == str(uuid.uuid5(EVAL_DOC_NAMESPACE, sha))


def test_db_document_id_is_stable_and_content_dependent():
    from scripts.eval.retrieval.adapters import db_document_id

    assert db_document_id("a" * 64) == db_document_id("a" * 64)
    assert db_document_id("a" * 64) != db_document_id("b" * 64)


def test_mirrored_ingest_constants_have_not_drifted():
    """adapters.py copies two constants out of scripts/eval/ingest.py rather than
    importing it (that import pulls in PyMuPDF, tiktoken and the backend app).
    A copy is only safe if drift is detected, so read the source textually."""
    from scripts.eval.retrieval.adapters import (
        EVAL_DOC_NAMESPACE,
        EVAL_PROJECT_ID,
        INGEST_MODULE_PATH,
    )

    if not INGEST_MODULE_PATH.exists():
        pytest.skip("scripts/eval/ingest.py not present")
    source = INGEST_MODULE_PATH.read_text()
    assert f'EVAL_PROJECT_ID = "{EVAL_PROJECT_ID}"' in source
    assert f'EVAL_DOC_NAMESPACE = uuid.UUID("{EVAL_DOC_NAMESPACE}")' in source


def test_degradation_snapshot_never_claims_health_it_did_not_check(monkeypatch):
    from scripts.eval.retrieval import adapters as A

    monkeypatch.setattr(A, "_keyword_degradation_flag", lambda: None)
    snap = A.keyword_degradation_snapshot()
    assert snap["checked"] is False
    assert snap["degraded"] is None          # NOT False
    assert "UNKNOWN" in snap["note"]


def test_degradation_snapshot_reports_a_recorded_failure(monkeypatch):
    from scripts.eval.retrieval import adapters as A

    class _Flag:
        def snapshot(self):
            return {"name": "keyword_search_chunks", "degraded": True,
                    "failure_count": 2, "last_error": "UndefinedColumn: dc.metadata"}

    monkeypatch.setattr(A, "_keyword_degradation_flag", lambda: _Flag())
    snap = A.keyword_degradation_snapshot()
    assert snap["degraded"] is True and snap["checked"] is True
