"""The keyword leg of hybrid search must fail audibly, not silently.

`keyword_search` wraps its RPC in a broad `except` and returns `[]` so that a
missing RPC degrades hybrid retrieval to semantic-only instead of failing the
whole draft analysis. That fallback is correct. What was wrong is that it was
*silent*: `keyword_search_chunks` raised

    ERROR: 42703: column dc.metadata does not exist

on every call in production -- the RPC selected a column `document_chunks` does
not have -- and the handler turned that hard failure into a plausible empty
list. `hybrid_search` then fused 0.7*semantic + 0.3*nothing and reported
success. Nobody noticed for the life of the feature.

Migration 037 fixes the RPC. These tests cover the thing that outlives the fix:
the next schema drift must be visible.
"""

import logging

import pytest

from app.services import rag_retrieval
from app.services.rag_retrieval import KEYWORD_SEARCH_DEGRADED, keyword_search


PROJECT_ID = "00000000-0000-0000-0000-000000000000"


class _Response:
    def __init__(self, data):
        self.data = data


class _FakeSupabase:
    """Stands in for the Supabase client. `rpc()` returns an object whose
    `execute()` either yields rows or raises."""

    def __init__(self, *, rows=None, raises=None):
        self._rows = rows
        self._raises = raises
        self.calls = []

    def rpc(self, name, params):
        self.calls.append((name, params))
        outer = self

        class _Query:
            def execute(self):
                if outer._raises is not None:
                    raise outer._raises
                return _Response(outer._rows)

        return _Query()


@pytest.fixture(autouse=True)
def _reset_flag():
    KEYWORD_SEARCH_DEGRADED.clear()
    yield
    KEYWORD_SEARCH_DEGRADED.clear()


class TestSuccessPath:
    def test_returns_rows_and_leaves_flag_clear(self, monkeypatch):
        rows = [{"id": "a", "rank": 0.9}, {"id": "b", "rank": 0.2}]
        monkeypatch.setattr(rag_retrieval, "supabase", _FakeSupabase(rows=rows))

        assert keyword_search(PROJECT_ID, "attention mechanisms") == rows
        assert KEYWORD_SEARCH_DEGRADED.degraded is False

    def test_empty_result_is_not_degradation(self, monkeypatch):
        """A query that legitimately matches nothing is not a failure. This is
        the distinction the old code destroyed: it made 'no matches' and 'the
        RPC is broken' indistinguishable."""
        monkeypatch.setattr(rag_retrieval, "supabase", _FakeSupabase(rows=[]))

        assert keyword_search(PROJECT_ID, "nonexistent term") == []
        assert KEYWORD_SEARCH_DEGRADED.degraded is False

    def test_success_clears_a_previous_failure(self, monkeypatch):
        """The flag reflects current state, so a transient failure does not
        pin it on forever."""
        monkeypatch.setattr(
            rag_retrieval, "supabase", _FakeSupabase(raises=RuntimeError("boom"))
        )
        keyword_search(PROJECT_ID, "q")
        assert KEYWORD_SEARCH_DEGRADED.degraded is True

        monkeypatch.setattr(rag_retrieval, "supabase", _FakeSupabase(rows=[{"id": "a"}]))
        keyword_search(PROJECT_ID, "q")
        assert KEYWORD_SEARCH_DEGRADED.degraded is False


class TestFailurePath:
    def test_still_degrades_rather_than_raising(self, monkeypatch):
        """The fallback behavior is deliberately unchanged -- a broken keyword
        leg must not fail an entire draft analysis."""
        monkeypatch.setattr(
            rag_retrieval, "supabase", _FakeSupabase(raises=RuntimeError("42703"))
        )
        assert keyword_search(PROJECT_ID, "q") == []

    def test_the_original_42703_is_recorded(self, monkeypatch):
        """The exact production failure, as verified against the live database."""
        exc = RuntimeError('column dc.metadata does not exist')
        monkeypatch.setattr(rag_retrieval, "supabase", _FakeSupabase(raises=exc))

        keyword_search(PROJECT_ID, "q")

        snap = KEYWORD_SEARCH_DEGRADED.snapshot()
        assert snap["degraded"] is True
        assert snap["failure_count"] == 1
        assert "dc.metadata" in snap["last_error"]
        assert "RuntimeError" in snap["last_error"]

    def test_logs_at_error_level_with_traceback(self, monkeypatch, caplog):
        monkeypatch.setattr(
            rag_retrieval, "supabase", _FakeSupabase(raises=RuntimeError("boom"))
        )

        with caplog.at_level(logging.ERROR, logger=rag_retrieval.__name__):
            keyword_search(PROJECT_ID, "q")

        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert errors, "a swallowed RPC failure must reach the log at ERROR"
        assert errors[0].exc_info is not None, "traceback must be preserved"
        assert "keyword_search_chunks" in errors[0].getMessage()

    def test_repeated_failures_accumulate(self, monkeypatch):
        monkeypatch.setattr(
            rag_retrieval, "supabase", _FakeSupabase(raises=RuntimeError("boom"))
        )
        for _ in range(3):
            keyword_search(PROJECT_ID, "q")

        assert KEYWORD_SEARCH_DEGRADED.snapshot()["failure_count"] == 3


class TestFlagIsQueryable:
    def test_snapshot_shape(self, monkeypatch):
        """An eval harness must be able to assert on this without scraping logs --
        nothing reads logs during a measurement run."""
        monkeypatch.setattr(rag_retrieval, "supabase", _FakeSupabase(rows=[]))
        keyword_search(PROJECT_ID, "q")

        snap = KEYWORD_SEARCH_DEGRADED.snapshot()
        assert set(snap) == {"name", "degraded", "failure_count", "last_error"}
        assert snap["name"] == "keyword_search_chunks"
        assert snap["last_error"] is None

    def test_thread_safe_counting(self, monkeypatch):
        import threading

        monkeypatch.setattr(
            rag_retrieval, "supabase", _FakeSupabase(raises=RuntimeError("boom"))
        )
        barrier = threading.Barrier(10)

        def worker():
            barrier.wait()
            for _ in range(20):
                keyword_search(PROJECT_ID, "q")

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert KEYWORD_SEARCH_DEGRADED.snapshot()["failure_count"] == 200
