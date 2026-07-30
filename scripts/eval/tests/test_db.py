"""Integration tests for scripts/eval/db.py against the local pgvector container.

These require the container from infra/docker-compose.yml with migrations
000_local_base_stubs.sql + 036 + 037 applied:

    cd infra && docker compose --profile core up -d pgvector

Every test SKIPS (does not fail) when the DB is unreachable, so the suite is
green on a machine with no Docker.
"""

import importlib.util
import sys
import uuid
from pathlib import Path

import pytest


def _load_eval_db():
    module_path = Path(__file__).resolve().parents[1] / "db.py"
    spec = importlib.util.spec_from_file_location("eval_db_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["eval_db_for_tests"] = module
    spec.loader.exec_module(module)
    return module


eval_db = _load_eval_db()
psycopg2 = eval_db.psycopg2

DB_UP = eval_db.healthcheck()

requires_db = pytest.mark.skipif(
    not DB_UP,
    reason="local pgvector unreachable; run `cd infra && docker compose --profile core up -d pgvector`",
)


def _unit_vector(index, dim=eval_db.EMBEDDING_DIM):
    """One-hot vector — cosine distance between two distinct one-hots is exactly 1.0."""
    vec = [0.0] * dim
    vec[index] = 1.0
    return vec


@pytest.fixture
def conn():
    with eval_db.get_connection() as connection:
        yield connection


@pytest.fixture
def seeded_project(conn):
    """Insert one document with three orthogonal chunk embeddings; clean up after."""
    project_id = str(uuid.uuid4())
    document_id = str(uuid.uuid4())
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO documents (id, title, project_id) VALUES (%s, %s, %s)",
            (document_id, "Attention Is All You Need", project_id),
        )
        for chunk_index in range(3):
            cur.execute(
                """
                INSERT INTO document_chunks
                    (document_id, project_id, chunk_index, content, embedding, content_tsvector)
                VALUES (%s, %s, %s, %s, %s::vector, to_tsvector('english', %s))
                """,
                (
                    document_id,
                    project_id,
                    chunk_index,
                    f"chunk about transformer architecture number {chunk_index}",
                    eval_db.format_vector(_unit_vector(chunk_index)),
                    f"chunk about transformer architecture number {chunk_index}",
                ),
            )
    conn.commit()

    yield {"project_id": project_id, "document_id": document_id}

    with conn.cursor() as cur:
        cur.execute("DELETE FROM document_chunks WHERE project_id = %s", (project_id,))
        cur.execute("DELETE FROM documents WHERE id = %s", (document_id,))
    conn.commit()


# --------------------------------------------------------------------------
# healthcheck
# --------------------------------------------------------------------------

@requires_db
def test_healthcheck_true_when_db_up():
    assert eval_db.healthcheck() is True


def test_healthcheck_false_on_bad_host(monkeypatch):
    """healthcheck swallows connection errors rather than raising. Runs without Docker."""
    monkeypatch.setenv("EVAL_DB_HOST", "127.0.0.1")
    monkeypatch.setenv("EVAL_DB_PORT", "1")  # nothing listens here
    assert eval_db.healthcheck() is False


def test_format_vector_shape():
    """Pure unit test — no DB required."""
    assert eval_db.format_vector([1.0, 0.0, -0.5]) == "[1.0,0.0,-0.5]"


# --------------------------------------------------------------------------
# vector round trip
# --------------------------------------------------------------------------

@requires_db
def test_vector_roundtrip_and_similarity_ranking(conn, seeded_project):
    """A 1536-dim vector survives the round trip; the closest chunk ranks first."""
    query = _unit_vector(1)  # exactly equal to chunk_index 1's embedding
    rows = eval_db.match_document_chunks(
        conn, query, seeded_project["project_id"], match_count=3
    )

    assert len(rows) == 3
    assert rows[0]["chunk_index"] == 1, "identical vector must rank first"
    assert rows[0]["document_title"] == "Attention Is All You Need"

    for row in rows:
        assert 0.0 <= row["similarity"] <= 1.0, row["similarity"]

    # Descending similarity, and the exact match is 1.0 (cosine distance 0).
    similarities = [row["similarity"] for row in rows]
    assert similarities == sorted(similarities, reverse=True)
    assert similarities[0] == pytest.approx(1.0, abs=1e-6)
    # Orthogonal one-hots -> cosine distance 1.0 -> similarity 0.0.
    assert similarities[1] == pytest.approx(0.0, abs=1e-6)


@requires_db
def test_stored_embedding_has_full_dimension(conn, seeded_project):
    with conn.cursor() as cur:
        cur.execute(
            "SELECT vector_dims(embedding) FROM document_chunks WHERE project_id = %s LIMIT 1",
            (seeded_project["project_id"],),
        )
        assert cur.fetchone()[0] == eval_db.EMBEDDING_DIM


@requires_db
def test_wrong_dimension_vector_is_rejected(conn, seeded_project):
    """The vector(1536) column must refuse a 3-dim embedding."""
    with pytest.raises(psycopg2.Error) as excinfo:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO document_chunks
                    (document_id, project_id, chunk_index, content, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
                """,
                (
                    seeded_project["document_id"],
                    seeded_project["project_id"],
                    99,
                    "too short",
                    eval_db.format_vector([1.0, 0.0, 0.0]),
                ),
            )
    assert "dimensions" in str(excinfo.value).lower()
    conn.rollback()


# --------------------------------------------------------------------------
# ef_search
# --------------------------------------------------------------------------

@requires_db
@pytest.mark.parametrize("value", [10, 40, 200])
def test_set_ef_search_takes_effect(conn, value):
    eval_db.set_ef_search(conn, value)
    with conn.cursor() as cur:
        cur.execute("SHOW hnsw.ef_search")
        assert cur.fetchone()[0] == str(value)


@requires_db
def test_set_ef_search_rejects_non_int(conn):
    """Guards the GUC against string interpolation of arbitrary text."""
    with pytest.raises(TypeError):
        eval_db.set_ef_search(conn, "80; DROP TABLE document_chunks")


# --------------------------------------------------------------------------
# keyword_search_chunks — regression test for the production 42703 bug
# --------------------------------------------------------------------------

@requires_db
def test_keyword_search_chunks_does_not_raise_42703(conn, seeded_project):
    """REGRESSION: before migration 037 this raised

        ERROR: 42703: column dc.metadata does not exist

    because keyword_search_chunks selected document_chunks.metadata, a column that
    does not exist. rag_retrieval.py swallowed it in a bare `except`, so the keyword
    leg of hybrid_search silently returned zero rows in production forever.
    """
    rows = eval_db.keyword_search_chunks(
        conn, seeded_project["project_id"], "transformer architecture", match_count=10
    )
    assert rows, "seeded chunks should match the FTS query"
    assert set(rows[0]) == {"id", "document_id", "content", "rank"}
    assert "metadata" not in rows[0], "037 removed metadata from the return type"
    assert all(row["rank"] >= 0 for row in rows)


@requires_db
def test_keyword_search_chunks_empty_project_returns_empty(conn):
    """No match must be a clean empty result set, not an error."""
    rows = eval_db.keyword_search_chunks(conn, str(uuid.uuid4()), "transformer", 5)
    assert rows == []


@requires_db
def test_keyword_search_chunks_signature_has_no_metadata(conn):
    """Assert against the catalog, so the test fails even if no rows come back."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT pg_get_function_result(p.oid)
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.proname = 'keyword_search_chunks'
            """
        )
        result_type = cur.fetchone()[0]
    assert "metadata" not in result_type, result_type
    assert "rank real" in result_type, result_type
