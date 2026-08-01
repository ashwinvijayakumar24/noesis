"""Ingestion robustness: fabricated page counts, chunk-write atomicity, ceiling visibility.

Three failures found while measuring retrieval, all of which corrupted the
measurement rather than announcing themselves:

1. `get_pdf_page_count` returned 10 when the PDF could not be opened, so a
   document that failed to open was indexed with a chunk geometry chosen by a
   number nobody counted, and looked identical to a real 10-page paper.
2. Chunks were inserted one row per request. A failure at row k left k orphan
   rows behind while the document was marked `failed`, so retrieval scored
   against half a document.
3. MAX_CHUNKS_PER_DOCUMENT silently coarsened chunk geometry on exactly the
   longest documents, and nothing durable recorded that it had fired.

These tests pin the fixes. The Supabase client is faked -- the real write path
is PostgREST over HTTPS and is not exercised here (see the module note in
store_document_chunks for what is and is not guaranteed).
"""

import asyncio
import sys
import types

import fitz
import pytest

from app.services import rag_ingest
from app.services.rag_ingest import (
    UNKNOWN_PAGE_COUNT_FALLBACK,
    ChunkWriteError,
    get_pdf_page_count,
    resolve_page_count_for_tiering,
    store_document_chunks,
)
from app.services.rag_chunking import (
    MAX_CHUNKS_PER_DOCUMENT,
    get_chunking_strategy,
    get_section_aware_chunking_strategy,
)


# ------------------------------------------------------------------ fixtures ---

def _make_pdf(pages: int) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"Page {i + 1}. " + ("lorem ipsum dolor sit amet. " * 20))
    data = doc.tobytes()
    doc.close()
    return data


CORRUPT_PDF = b"%PDF-1.7\nthis is not actually a pdf, the xref table is gone\n"


class _Response:
    def __init__(self, data, count=None):
        self.data = data
        self.count = count


class _FakeTable:
    def __init__(self, store, name):
        self._store = store
        self._name = name
        self._op = None
        self._payload = None
        self._filters = {}
        self._count_mode = None
        self._single = False

    # -- query builders -------------------------------------------------
    def select(self, *_args, **kwargs):
        self._op = "select"
        self._count_mode = kwargs.get("count")
        return self

    def insert(self, payload):
        self._op = "insert"
        self._payload = payload
        return self

    def update(self, payload):
        self._op = "update"
        self._payload = payload
        return self

    def delete(self):
        self._op = "delete"
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def single(self):
        self._single = True
        return self

    # -- execution ------------------------------------------------------
    def execute(self):
        store = self._store
        store.calls.append((self._name, self._op, self._filters.copy(), self._payload))

        if self._name == "documents":
            if self._op == "select":
                # PostgREST returns an object for .single(), a list otherwise.
                if self._single:
                    return _Response(dict(store.document))
                return _Response([dict(store.document)])
            if self._op == "update":
                store.document_updates.append(self._payload)
                store.document.update(self._payload)
                return _Response([dict(store.document)])
            return _Response([])

        if self._name == "document_chunks":
            if self._op == "insert":
                if store.fail_insert:
                    store.insert_attempts.append(self._payload)
                    raise RuntimeError("PostgREST 500: insert failed midway")
                rows = self._payload if isinstance(self._payload, list) else [self._payload]
                store.insert_calls.append(rows)
                store.chunks.extend(rows)
                return _Response(rows)
            if self._op == "delete":
                if store.fail_cleanup_delete and store.fail_insert and store.insert_attempts:
                    raise RuntimeError("PostgREST connection reset during cleanup")
                doc_id = self._filters.get("document_id")
                store.chunks = [c for c in store.chunks if c["document_id"] != doc_id]
                store.delete_calls.append(doc_id)
                return _Response([])
            if self._op == "select":
                doc_id = self._filters.get("document_id")
                matching = [c for c in store.chunks if c["document_id"] == doc_id]
                if store.leftover_after_cleanup is not None:
                    return _Response([{"id": i} for i in range(store.leftover_after_cleanup)],
                                     count=store.leftover_after_cleanup)
                return _Response([{"id": i} for i, _ in enumerate(matching)], count=len(matching))

        return _Response([])


class _FakeStorageBucket:
    def __init__(self, store):
        self._store = store

    def download(self, _path):
        return self._store.file_bytes


class _FakeStorage:
    def __init__(self, store):
        self._store = store

    def from_(self, _bucket):
        return _FakeStorageBucket(self._store)


class FakeSupabase:
    """Minimal stand-in for the Supabase client used by rag_ingest."""

    def __init__(self, file_bytes=b"", document=None):
        self.file_bytes = file_bytes
        self.document = document or {
            "id": "doc-1",
            "file_url": "https://x/storage/v1/object/public/documents/user-1/paper.pdf",
            "user_id": "user-1",
            "status": "uploaded",
            "metadata": {},
        }
        self.chunks = []
        self.insert_calls = []
        self.insert_attempts = []
        self.delete_calls = []
        self.document_updates = []
        self.calls = []
        self.fail_insert = False
        self.fail_cleanup_delete = False
        self.leftover_after_cleanup = None
        self.storage = _FakeStorage(self)

    def table(self, name):
        return _FakeTable(self, name)


class _FakeEmbedding:
    def __init__(self, index):
        self.embedding = [float(index)] * 1536


@pytest.fixture
def fake_supabase(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(rag_ingest, "supabase", fake)
    return fake


def _stub_pipeline(monkeypatch, sections=None, full_text="Some extracted body text. " * 200):
    async def _fake_extract(_bytes):
        return {
            "full_text": full_text,
            "title": "A Paper",
            "authors": [],
            "abstract": "",
            "sections": sections or [],
            "references": [],
            "metadata": {},
        }

    monkeypatch.setattr(rag_ingest, "extract_structured_data_from_pdf", _fake_extract)

    # ingest_document auto-triggers the Celery analysis task at the end. Without a
    # stub, .delay() spends ~19s failing to reach Redis before the error is
    # swallowed. Stub the module so the tests measure ingestion, not a broker timeout.
    fake_tasks = types.ModuleType("app.tasks.document_analysis")
    fake_tasks.analyze_document_task = types.SimpleNamespace(
        delay=lambda *a, **kw: types.SimpleNamespace(id="task-stub")
    )
    monkeypatch.setitem(sys.modules, "app.tasks.document_analysis", fake_tasks)

    monkeypatch.setattr(
        rag_ingest,
        "embed_chunks",
        lambda chunks, model=None: [_FakeEmbedding(i) for i in range(len(chunks))],
    )


# ------------------------------------------------- bug 1: page count honesty ---

def test_corrupt_pdf_no_longer_fabricates_a_page_count():
    """The old code returned 10 here -- an unmeasured number that then chose the
    chunking tier. It must now report that it does not know."""
    assert get_pdf_page_count(CORRUPT_PDF) is None


def test_empty_bytes_also_report_unknown():
    assert get_pdf_page_count(b"") is None


def test_real_ten_page_pdf_still_returns_ten():
    assert get_pdf_page_count(_make_pdf(10)) == 10


def test_a_real_ten_page_pdf_is_distinguishable_from_a_failure():
    """Same page_count, different provenance. This is the whole point of the fix."""
    real = resolve_page_count_for_tiering(_make_pdf(10))
    broken = resolve_page_count_for_tiering(CORRUPT_PDF)

    assert real == (10, True)
    assert broken == (UNKNOWN_PAGE_COUNT_FALLBACK, False)
    assert real[0] == broken[0]  # the number alone tells you nothing
    assert real[1] != broken[1]  # the flag does


def test_other_page_counts_are_reported_exactly():
    assert get_pdf_page_count(_make_pdf(3)) == 3
    assert resolve_page_count_for_tiering(_make_pdf(42)) == (42, True)


def test_a_readable_pdf_does_not_crash_ingestion_when_page_count_fails(fake_supabase, monkeypatch):
    """Failing to open with PyMuPDF must not be fatal: GROBID parses PDFs PyMuPDF
    refuses, and ingestion of such a document succeeds today."""
    fake_supabase.file_bytes = CORRUPT_PDF
    _stub_pipeline(monkeypatch)

    result = asyncio.run(rag_ingest.ingest_document("doc-1", "proj-1"))

    assert result["page_count"] == UNKNOWN_PAGE_COUNT_FALLBACK
    assert result["page_count_measured"] is False


def test_unmeasured_page_count_is_recorded_on_the_document(fake_supabase, monkeypatch):
    fake_supabase.file_bytes = CORRUPT_PDF
    _stub_pipeline(monkeypatch)

    asyncio.run(rag_ingest.ingest_document("doc-1", "proj-1"))

    metadata = fake_supabase.document_updates[-1]["metadata"]
    assert metadata["page_count"] == UNKNOWN_PAGE_COUNT_FALLBACK
    assert metadata["page_count_measured"] is False


def test_measured_page_count_is_recorded_on_the_document(fake_supabase, monkeypatch):
    fake_supabase.file_bytes = _make_pdf(10)
    _stub_pipeline(monkeypatch)

    asyncio.run(rag_ingest.ingest_document("doc-1", "proj-1"))

    metadata = fake_supabase.document_updates[-1]["metadata"]
    assert metadata["page_count"] == 10
    assert metadata["page_count_measured"] is True


# ----------------------------------------------- bug 2: chunk write atomicity ---

def _rows(document_id="doc-1", n=5):
    return [
        {
            "document_id": document_id,
            "project_id": "proj-1",
            "chunk_index": i,
            "content": f"chunk {i}",
            "embedding": [0.0] * 1536,
        }
        for i in range(n)
    ]


def test_all_chunks_are_written_in_a_single_request(fake_supabase):
    """One request == one SQL INSERT == one implicit transaction. The old loop
    issued one request per row, which is where partial writes came from."""
    store_document_chunks("doc-1", _rows(n=37))

    assert len(fake_supabase.insert_calls) == 1
    assert len(fake_supabase.insert_calls[0]) == 37
    assert len(fake_supabase.chunks) == 37


def test_prior_chunks_are_cleared_first_so_retries_do_not_duplicate(fake_supabase):
    store_document_chunks("doc-1", _rows(n=4))
    store_document_chunks("doc-1", _rows(n=4))

    assert len(fake_supabase.chunks) == 4
    assert fake_supabase.delete_calls == ["doc-1", "doc-1"]


def test_a_failed_insert_leaves_no_orphan_chunks(fake_supabase):
    fake_supabase.fail_insert = True

    with pytest.raises(ChunkWriteError) as excinfo:
        store_document_chunks("doc-1", _rows(n=20))

    assert fake_supabase.chunks == []
    assert excinfo.value.orphans_possible is False


def test_cleanup_is_verified_not_assumed(fake_supabase):
    """If rows survive the compensating delete, the error must admit it rather
    than reporting a clean failure."""
    fake_supabase.fail_insert = True
    fake_supabase.leftover_after_cleanup = 12

    with pytest.raises(ChunkWriteError) as excinfo:
        store_document_chunks("doc-1", _rows(n=20))

    assert excinfo.value.orphans_possible is True


def test_when_cleanup_itself_fails_orphans_are_reported_as_possible(fake_supabase):
    fake_supabase.fail_insert = True
    fake_supabase.fail_cleanup_delete = True

    with pytest.raises(ChunkWriteError) as excinfo:
        store_document_chunks("doc-1", _rows(n=20))

    assert excinfo.value.orphans_possible is True


def test_ingest_records_the_orphan_state_on_the_failed_document(fake_supabase, monkeypatch):
    fake_supabase.file_bytes = _make_pdf(5)
    _stub_pipeline(monkeypatch)
    fake_supabase.fail_insert = True

    with pytest.raises(ChunkWriteError):
        asyncio.run(rag_ingest.ingest_document("doc-1", "proj-1"))

    failure_update = fake_supabase.document_updates[-1]
    assert failure_update["status"] == "failed"
    assert failure_update["metadata"]["orphan_chunks_possible"] is False
    assert failure_update["metadata"]["chunks_cleaned_up"] is True


def test_ingest_records_undetermined_cleanup_when_orphans_may_remain(fake_supabase, monkeypatch):
    fake_supabase.file_bytes = _make_pdf(5)
    _stub_pipeline(monkeypatch)
    fake_supabase.fail_insert = True
    fake_supabase.leftover_after_cleanup = 7

    with pytest.raises(ChunkWriteError):
        asyncio.run(rag_ingest.ingest_document("doc-1", "proj-1"))

    metadata = fake_supabase.document_updates[-1]["metadata"]
    assert metadata["orphan_chunks_possible"] is True
    assert metadata["chunks_cleaned_up"] is False


def test_successful_ingest_stores_every_chunk_exactly_once(fake_supabase, monkeypatch):
    fake_supabase.file_bytes = _make_pdf(5)
    _stub_pipeline(monkeypatch)

    result = asyncio.run(rag_ingest.ingest_document("doc-1", "proj-1"))

    assert len(fake_supabase.chunks) == result["num_chunks"]
    assert [c["chunk_index"] for c in fake_supabase.chunks] == list(range(result["num_chunks"]))


# ------------------------------------------------ bug 3: ceiling is now visible ---

def test_ceiling_metadata_records_original_and_adjusted_geometry():
    """A 200k-token document under the SHORT tier would be 199 chunks; the
    ceiling coarsens it to fit 50. Every number in that sentence is now stored."""
    strategy = get_chunking_strategy(page_count=5, total_tokens=200_000)
    ceiling = strategy["cost_ceiling"]

    assert ceiling["applied"] is True
    assert ceiling["trigger"] == "estimated_tokens"
    assert ceiling["max_chunks"] == MAX_CHUNKS_PER_DOCUMENT
    assert ceiling["original_chunk_size"] == 1200
    assert ceiling["original_overlap"] == 200
    assert ceiling["adjusted_chunk_size"] > ceiling["original_chunk_size"]
    assert ceiling["adjusted_chunk_size"] == strategy["chunk_size"]
    assert ceiling["adjusted_overlap"] == strategy["overlap"]
    assert ceiling["chunks_before_ceiling"] > MAX_CHUNKS_PER_DOCUMENT
    assert ceiling["chunks_after_ceiling"] == strategy["estimated_chunks"]
    # NOT asserted: chunks_after_ceiling <= MAX_CHUNKS_PER_DOCUMENT. It is 57 for
    # this document. apply_cost_ceiling solves for chunk_size using the ORIGINAL
    # overlap, then scales overlap up proportionally to the new chunk_size, which
    # shrinks the stride the solution assumed -- so the ceiling routinely
    # overshoots its own limit. Pre-existing behaviour, deliberately left alone
    # (changing it would move the committed retrieval baseline); recorded here so
    # the record's numbers are not mistaken for a guarantee.
    assert ceiling["chunks_after_ceiling"] < ceiling["chunks_before_ceiling"]
    assert ceiling["chunks_avoided"] == (
        ceiling["chunks_before_ceiling"] - ceiling["chunks_after_ceiling"]
    )


def test_document_under_the_ceiling_records_no_adjustment():
    strategy = get_chunking_strategy(page_count=12, total_tokens=8000)
    ceiling = strategy["cost_ceiling"]

    assert ceiling["applied"] is False
    assert ceiling["trigger"] is None
    assert ceiling["original_chunk_size"] == ceiling["adjusted_chunk_size"] == 1600
    assert ceiling["original_overlap"] == ceiling["adjusted_overlap"] == 250
    assert ceiling["chunks_before_ceiling"] == ceiling["chunks_after_ceiling"]
    assert ceiling["chunks_avoided"] == 0


def test_section_aware_path_records_the_ceiling_too():
    sections = [
        {"title": f"Section {i}", "content": "A sentence about the method. " * 400,
         "type": "other"}
        for i in range(12)
    ]
    strategy = get_section_aware_chunking_strategy(
        sections=sections, page_count=40, total_tokens=120_000
    )
    ceiling = strategy["cost_ceiling"]

    assert ceiling["applied"] is True
    assert ceiling["trigger"] in ("estimated_tokens", "actual_section_chunks")
    assert ceiling["adjusted_chunk_size"] == strategy["chunk_size"]
    assert ceiling["chunks_before_ceiling"] >= ceiling["chunks_after_ceiling"]


def test_section_aware_short_document_records_no_adjustment():
    sections = [{"title": "Intro", "content": "Short body. " * 20, "type": "introduction"}]
    strategy = get_section_aware_chunking_strategy(
        sections=sections, page_count=6, total_tokens=500
    )

    assert strategy["cost_ceiling"]["applied"] is False
    assert strategy["cost_ceiling"]["chunks_avoided"] == 0


def test_ingest_persists_the_ceiling_record(fake_supabase, monkeypatch):
    fake_supabase.file_bytes = _make_pdf(4)
    # ~120k tokens of body text: comfortably over the 50-chunk ceiling.
    _stub_pipeline(monkeypatch, full_text="lorem ipsum dolor sit amet consectetur " * 20_000)

    result = asyncio.run(rag_ingest.ingest_document("doc-1", "proj-1"))

    persisted = fake_supabase.document_updates[-1]["metadata"]["adaptive_chunking"]["cost_ceiling"]
    assert persisted["applied"] is True
    assert persisted["original_chunk_size"] == 1200
    assert persisted["adjusted_chunk_size"] > 1200
    assert persisted["chunks_before_ceiling"] > MAX_CHUNKS_PER_DOCUMENT
    assert result["adaptive_chunking"]["cost_ceiling"] == persisted


# --------------------------------------- unchanged behaviour for normal docs ---

@pytest.mark.parametrize(
    "page_count,total_tokens,expected",
    [
        (5, 6_000, {"tier": "SHORT", "chunk_size": 1200, "overlap": 200}),
        (20, 12_000, {"tier": "MEDIUM", "chunk_size": 1600, "overlap": 250}),
        (60, 40_000, {"tier": "LONG", "chunk_size": 2000, "overlap": 300}),
    ],
)
def test_chunk_geometry_for_normal_documents_is_unchanged(page_count, total_tokens, expected):
    """The ceiling record is additive: documents that never hit the ceiling must
    be chunked exactly as before, or the committed retrieval baseline is void."""
    strategy = get_chunking_strategy(page_count=page_count, total_tokens=total_tokens)

    assert strategy["tier"] == expected["tier"]
    assert strategy["chunk_size"] == expected["chunk_size"]
    assert strategy["overlap"] == expected["overlap"]
    assert strategy["was_adjusted"] is False


def test_existing_strategy_keys_are_all_still_present():
    strategy = get_chunking_strategy(page_count=12, total_tokens=8000)
    for key in ("chunk_size", "overlap", "tier", "max_chunks", "was_adjusted", "estimated_chunks"):
        assert key in strategy


def test_normal_ingest_still_reports_the_same_shape(fake_supabase, monkeypatch):
    fake_supabase.file_bytes = _make_pdf(8)
    _stub_pipeline(monkeypatch)

    result = asyncio.run(rag_ingest.ingest_document("doc-1", "proj-1"))

    assert result["message"] == "Document successfully ingested and embedded"
    assert result["adaptive_chunking"]["tier"] == "SHORT"
    assert result["adaptive_chunking"]["chunk_size"] == 1200
    assert result["adaptive_chunking"]["cost_ceiling_applied"] is False
    assert fake_supabase.document["status"] == "ready"
