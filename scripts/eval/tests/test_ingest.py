"""Tests for scripts/eval/ingest.py.

Two rules, both load-bearing:

1. NO TEST EVER CALLS OPENAI. `ingest.embed_chunks` is monkeypatched in every
   test that could reach it, and the dry-run test asserts the mock was never
   touched.
2. Database tests SKIP (never fail) when the local pgvector container is down,
   matching tests/test_db.py, so the suite stays green on a machine with no
   Docker:

       cd infra && docker compose --profile core up -d pgvector
"""

import hashlib
import json
import sys
import uuid
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import fitz  # noqa: E402
import tiktoken  # noqa: E402

import db as eval_db  # noqa: E402
import ingest  # noqa: E402

from app.core.llm_budget import LLMCallBlocked  # noqa: E402

DB_UP = eval_db.healthcheck()

requires_db = pytest.mark.skipif(
    not DB_UP,
    reason="local pgvector unreachable; run `cd infra && docker compose --profile core up -d pgvector`",
)


# --------------------------------------------------------------------------
# Fixtures / helpers
# --------------------------------------------------------------------------

_WORDS = (
    "transformer attention retrieval embedding corpus gradient inference latency "
    "ablation baseline hypothesis dataset annotation calibration recall precision "
    "microglia neuron synapse cortex protein receptor pathway assay cohort"
).split()


def make_text(seed: int, sentences: int = 400) -> str:
    """Deterministic prose. Distinct per seed so documents do not collide by hash."""
    out = []
    for i in range(sentences):
        picks = [_WORDS[(seed * 7 + i * 3 + j) % len(_WORDS)] for j in range(12)]
        out.append(f"Study {seed}-{i} reports that {' '.join(picks)} was observed.")
    return " ".join(out)


LINES_PER_PAGE = 80
CHARS_PER_LINE = 95


def _wrap(text: str) -> list:
    lines, current = [], ""
    for word in text.split():
        if len(current) + len(word) + 1 > CHARS_PER_LINE:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines


def write_pdf(path: Path, text: str) -> Path:
    """Write a real, text-layer PDF, one line at a time so nothing is silently dropped.

    insert_textbox returns -1 and writes NOTHING when the text overflows the box,
    which produces a PDF with no text layer and a confusing test failure. Placing
    lines explicitly avoids that failure mode entirely.
    """
    doc = fitz.open()
    lines = _wrap(text)
    for start in range(0, len(lines), LINES_PER_PAGE):
        page = doc.new_page()
        for offset, line in enumerate(lines[start : start + LINES_PER_PAGE]):
            page.insert_text((40, 50 + offset * 9), line, fontsize=8)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    doc.close()
    return path


class FakeEmbedding:
    def __init__(self, vector):
        self.embedding = vector


def deterministic_vector(text: str, dim: int = ingest.EMBEDDING_DIMENSIONS):
    """A unit-ish vector derived from the content, so identical text -> identical vector."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vector = [0.0] * dim
    # A handful of non-zero components is enough to make cosine ranking meaningful
    # while keeping distinct chunks well separated.
    for i in range(8):
        index = int.from_bytes(digest[i * 2 : i * 2 + 2], "big") % dim
        vector[index] += 1.0
    if not any(vector):
        vector[0] = 1.0
    return vector


@pytest.fixture(autouse=True)
def _neutral_guard_env(monkeypatch):
    """Clear the LLM guardrail env vars for every test in this module.

    These tests mock the embedder, so no call ever leaves the process -- but
    ``ingest`` calls ``check_llm_allowed()`` before embedding, which reads the
    environment at call time. Without this, running the suite under an ambient
    ``NOESIS_LLM_KILL_SWITCH=1`` (entirely reasonable for a CI job that wants a
    hard spend guarantee) fails six tests that spend nothing. A mocked test must
    not depend on ambient env.

    The two tests that assert the guardrails DO fire set the vars themselves via
    monkeypatch, which still wins over this fixture.
    """
    for name in ("NOESIS_LLM_KILL_SWITCH", "EVAL_REPLAY_ONLY",
                 "NOESIS_LLM_MAX_SPEND_USD", "NOESIS_LLM_MAX_CALLS"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake_embedder(monkeypatch):
    """Replace the production embedding call. Records every invocation."""
    calls = []

    def _embed(chunks, model=ingest.EMBEDDING_MODEL):
        calls.append({"chunks": list(chunks), "model": model})
        return [FakeEmbedding(deterministic_vector(c)) for c in chunks]

    monkeypatch.setattr(ingest, "embed_chunks", _embed)
    return calls


@pytest.fixture
def corpus(tmp_path):
    """A two-document corpus plus per-test manifest/state paths and a fresh project."""
    corpora = tmp_path / "corpora" / "unit"
    write_pdf(corpora / "alpha.pdf", make_text(1))
    write_pdf(corpora / "beta.pdf", make_text(2))
    return {
        "dir": tmp_path / "corpora",
        "corpus_dir": corpora,
        "manifest": tmp_path / "ingest_manifest.jsonl",
        "state": tmp_path / "ingest_state.json",
        "project_id": str(uuid.uuid4()),
    }


@pytest.fixture
def cleanup_project():
    """Delete everything written under the project ids handed out to a test."""
    project_ids = []
    yield project_ids
    if not DB_UP:
        return
    with eval_db.get_connection() as conn:
        with conn.cursor() as cur:
            for project_id in project_ids:
                cur.execute("DELETE FROM document_chunks WHERE project_id = %s::uuid", (project_id,))
                cur.execute("DELETE FROM documents WHERE project_id = %s::uuid", (project_id,))


def run(corpus, **kwargs):
    return ingest.run_ingest(
        corpora_dir=corpus["dir"],
        project_id=corpus["project_id"],
        manifest_path=corpus["manifest"],
        state_path=corpus["state"],
        verbose=False,
        **kwargs,
    )


def read_manifest(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


# --------------------------------------------------------------------------
# Chunking — pure, no DB, no network
# --------------------------------------------------------------------------


def test_chunking_matches_production_strategy_and_covers_source():
    """Chunk count follows the production tier math; chunks cover the whole source."""
    enc = tiktoken.get_encoding("cl100k_base")
    text = make_text(9, sentences=600)
    total_tokens = len(enc.encode(text))

    chunks, strategy = ingest.chunk_document_text(text, page_count=5)

    # SHORT tier (1-10 pages) per rag_chunking.CHUNKING_TIERS.
    assert strategy["tier"] == "SHORT"
    assert strategy["chunk_size"] == 1200
    assert strategy["overlap"] == 200

    # Expected count from the production estimator, not a hand-rolled formula.
    from app.services.rag_chunking import calculate_estimated_chunks

    expected = calculate_estimated_chunks(total_tokens, 1200, 200)
    assert len(chunks) == expected
    assert len(chunks) <= strategy["max_chunks"]

    # Coverage: every source word survives somewhere in the chunk set, and the
    # boundaries line up with the source boundaries.
    joined = " ".join(chunks)
    assert set(text.split()) <= set(joined.split())
    assert text.startswith(chunks[0][:200])
    assert text.rstrip().endswith(chunks[-1].rstrip()[-200:])


def test_document_id_is_content_addressed(tmp_path):
    """Same bytes -> same id anywhere; different bytes -> different id."""
    a = write_pdf(tmp_path / "a.pdf", make_text(3))
    b = tmp_path / "copy_of_a.pdf"
    b.write_bytes(a.read_bytes())
    c = write_pdf(tmp_path / "c.pdf", make_text(4))

    assert ingest.plan_document(a).doc_id == ingest.plan_document(b).doc_id
    assert ingest.plan_document(a).doc_id != ingest.plan_document(c).doc_id


def test_fingerprint_changes_with_chunker_settings(tmp_path, monkeypatch):
    """The splitter arm is part of the cache key, so switching arms forces a re-embed."""
    pdf = write_pdf(tmp_path / "a.pdf", make_text(5))
    monkeypatch.setenv("CHUNKING_SPLITTER", "pysbd")
    pysbd_fp = ingest.plan_document(pdf).fingerprint()
    monkeypatch.setenv("CHUNKING_SPLITTER", "legacy")
    legacy_fp = ingest.plan_document(pdf).fingerprint()
    assert pysbd_fp != legacy_fp


# --------------------------------------------------------------------------
# Guardrails
# --------------------------------------------------------------------------


def test_dry_run_makes_zero_embedding_calls(corpus, fake_embedder):
    summary = ingest.run_ingest(
        corpora_dir=corpus["dir"],
        project_id=corpus["project_id"],
        manifest_path=corpus["manifest"],
        state_path=corpus["state"],
        dry_run=True,
        verbose=False,
    )
    assert fake_embedder == [], "dry run must not call the embedding API"
    assert summary["documents_found"] == 2
    assert summary["chunks_pending"] > 0
    assert summary["tokens_pending"] > 0
    assert "estimated_cost" in summary
    assert not corpus["manifest"].exists(), "dry run must not write the manifest"


def test_format_cost_handles_unknown_pricing(monkeypatch):
    """llm_budget leaves unknown prices as None; a dollar figure must never be faked."""
    monkeypatch.setattr(ingest, "estimate_usd", lambda *a, **k: None)
    assert "unknown" in ingest.format_cost(1_000_000)


@requires_db
def test_kill_switch_blocks_a_real_run(corpus, fake_embedder, cleanup_project, monkeypatch):
    cleanup_project.append(corpus["project_id"])
    monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
    with pytest.raises(LLMCallBlocked) as excinfo:
        run(corpus)
    assert "NOESIS_LLM_KILL_SWITCH" in str(excinfo.value)
    assert fake_embedder == []


@requires_db
def test_replay_only_blocks_a_real_run(corpus, fake_embedder, cleanup_project, monkeypatch):
    cleanup_project.append(corpus["project_id"])
    monkeypatch.setenv("EVAL_REPLAY_ONLY", "1")
    with pytest.raises(LLMCallBlocked):
        run(corpus)
    assert fake_embedder == []


# --------------------------------------------------------------------------
# Database behaviour
# --------------------------------------------------------------------------


@requires_db
def test_ingest_writes_chunks_and_is_idempotent(corpus, fake_embedder, cleanup_project):
    cleanup_project.append(corpus["project_id"])

    first = run(corpus)
    assert first["documents_ingested"] == 2
    assert first["chunks_inserted"] > 0

    with eval_db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM document_chunks WHERE project_id = %s::uuid",
            (corpus["project_id"],),
        )
        rows_after_first = cur.fetchone()[0]
        cur.execute(
            "SELECT DISTINCT document_id FROM document_chunks WHERE project_id = %s::uuid",
            (corpus["project_id"],),
        )
        ids_after_first = sorted(str(r[0]) for r in cur.fetchall())

    assert rows_after_first == first["chunks_inserted"]

    calls_after_first = len(fake_embedder)
    second = run(corpus)

    assert second["documents_ingested"] == 0
    assert second["documents_skipped"] == 2
    assert second["chunks_inserted"] == 0
    assert len(fake_embedder) == calls_after_first, "re-run must not re-embed"

    with eval_db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM document_chunks WHERE project_id = %s::uuid",
            (corpus["project_id"],),
        )
        assert cur.fetchone()[0] == rows_after_first, "re-run must not duplicate rows"
        cur.execute(
            "SELECT DISTINCT document_id FROM document_chunks WHERE project_id = %s::uuid",
            (corpus["project_id"],),
        )
        assert sorted(str(r[0]) for r in cur.fetchall()) == ids_after_first


@requires_db
def test_adding_one_document_embeds_only_that_document(corpus, fake_embedder, cleanup_project):
    cleanup_project.append(corpus["project_id"])
    run(corpus)
    calls_after_first = len(fake_embedder)

    new_pdf = write_pdf(corpus["corpus_dir"] / "gamma.pdf", make_text(42))
    expected_doc_id = ingest.plan_document(new_pdf).doc_id

    summary = run(corpus)

    assert summary["documents_ingested"] == 1
    assert summary["documents_skipped"] == 2
    assert len(fake_embedder) == calls_after_first + 1, "exactly one new embedding call"

    with eval_db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM document_chunks WHERE project_id = %s::uuid AND document_id = %s::uuid",
            (corpus["project_id"], expected_doc_id),
        )
        assert cur.fetchone()[0] == summary["chunks_inserted"]


@requires_db
def test_vector_roundtrip_and_cosine_ranking(corpus, fake_embedder, cleanup_project):
    """1536-dim vectors survive the round trip and rank by cosine similarity in [0,1]."""
    cleanup_project.append(corpus["project_id"])
    run(corpus)

    target_chunk = fake_embedder[0]["chunks"][0]
    query = deterministic_vector(target_chunk)

    with eval_db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT vector_dims(embedding) FROM document_chunks WHERE project_id = %s::uuid LIMIT 1",
                (corpus["project_id"],),
            )
            assert cur.fetchone()[0] == ingest.EMBEDDING_DIMENSIONS

        rows = eval_db.match_document_chunks(conn, query, corpus["project_id"], match_count=5)

    assert rows
    assert rows[0]["content"] == target_chunk, "the identical vector must rank first"
    assert rows[0]["similarity"] == pytest.approx(1.0, abs=1e-6)
    similarities = [r["similarity"] for r in rows]
    assert similarities == sorted(similarities, reverse=True)
    assert all(0.0 <= s <= 1.0 for s in similarities)


@requires_db
def test_changed_chunker_settings_replace_rather_than_duplicate(
    corpus, fake_embedder, cleanup_project, monkeypatch
):
    """A settings change must evict the old chunks, not stack a second copy on top."""
    cleanup_project.append(corpus["project_id"])
    monkeypatch.setenv("CHUNKING_SPLITTER", "pysbd")
    run(corpus)

    doc_ids_before = set(ingest.load_state(corpus["state"]))

    monkeypatch.setenv("CHUNKING_SPLITTER", "legacy")
    second = run(corpus)

    assert second["documents_ingested"] == 2
    assert set(ingest.load_state(corpus["state"])) == doc_ids_before, "doc ids are content-addressed"

    with eval_db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) FROM document_chunks WHERE project_id = %s::uuid",
            (corpus["project_id"],),
        )
        assert cur.fetchone()[0] == second["chunks_inserted"]


# --------------------------------------------------------------------------
# Manifest
# --------------------------------------------------------------------------

REQUIRED_MANIFEST_FIELDS = {
    "source_path",
    "doc_id",
    "extractor",
    "page_count",
    "chunk_count",
    "token_count",
    "embedding_model",
    "embedding_dimensions",
    "chunking_splitter",
    "tier",
    "chunk_size",
    "chunk_overlap",
}


@requires_db
def test_manifest_has_required_fields_and_is_append_only(corpus, fake_embedder, cleanup_project):
    cleanup_project.append(corpus["project_id"])

    run(corpus)
    first_records = read_manifest(corpus["manifest"])
    assert len(first_records) == 2
    for record in first_records:
        assert REQUIRED_MANIFEST_FIELDS <= set(record), REQUIRED_MANIFEST_FIELDS - set(record)
        assert record["extractor"] == "pymupdf"
        assert record["embedding_model"] == "text-embedding-3-large"
        assert record["embedding_dimensions"] == 1536
        assert record["chunking_splitter"] in {"pysbd", "legacy"}
        assert record["tier"] in {"SHORT", "MEDIUM", "LONG"}
        assert record["chunk_size"] > 0 and record["chunk_overlap"] > 0
        assert record["action"] == "ingested"

    run(corpus)
    second_records = read_manifest(corpus["manifest"])
    assert len(second_records) == 4, "second run appends; it must not truncate"
    assert second_records[:2] == first_records, "earlier records are never rewritten"
    assert all(r["action"] == "skipped" for r in second_records[2:])


# --------------------------------------------------------------------------
# Bad input
# --------------------------------------------------------------------------


def test_corrupt_pdf_is_planned_as_an_error_not_an_exception(tmp_path):
    bad = tmp_path / "corrupt.pdf"
    bad.write_bytes(b"%PDF-1.4 this is not actually a pdf")
    plan = ingest.plan_document(bad)
    assert plan.error is not None
    assert plan.ok is False


def test_pdf_with_no_text_layer_is_rejected(tmp_path):
    """A scanned-image PDF has pages but no extractable text; it must not be embedded."""
    doc = fitz.open()
    doc.new_page()
    doc.new_page()
    scanned = tmp_path / "scanned.pdf"
    doc.save(str(scanned))
    doc.close()

    plan = ingest.plan_document(scanned)
    assert plan.ok is False
    assert "no text layer" in plan.error


@requires_db
def test_corrupt_pdf_is_skipped_and_recorded_not_fatal(corpus, fake_embedder, cleanup_project):
    cleanup_project.append(corpus["project_id"])
    (corpus["corpus_dir"] / "corrupt.pdf").write_bytes(b"%PDF-1.4 broken")

    summary = run(corpus)

    assert summary["documents_ingested"] == 2, "the good documents still land"
    assert summary["documents_failed"] == 1
    assert summary["failures"][0]["source_path"].endswith("corrupt.pdf")

    records = read_manifest(corpus["manifest"])
    failed = [r for r in records if r["action"] == "failed"]
    assert len(failed) == 1
    assert failed[0]["error"]
    assert failed[0]["chunk_count"] == 0
