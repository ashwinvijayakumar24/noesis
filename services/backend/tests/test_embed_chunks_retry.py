"""`embed_chunks` had no retry at all, so one TPM spike killed a whole ingestion.

Reproduced on a 345-document corpus. OpenAI returned:

    429 ... Rate limit reached for text-embedding-3-large ...
    Limit 1000000, Used 982070, Requested 20872. Please try again in 176ms.

and the run died 264 documents in, having already paid to embed them. The
retry waits the 176ms. `embed_query` in rag_retrieval has carried `@retry_openai`
all along; this path simply never got it.

Batching keeps embedding requests large, so brushing the per-minute token ceiling
is normal operation for a bulk ingest, not an exceptional condition.
"""

import httpx
import pytest
from openai import APIConnectionError, RateLimitError

from app.services import rag_ingest


def _rate_limit_error() -> RateLimitError:
    request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
    response = httpx.Response(429, request=request, json={"error": {"message": "TPM"}})
    return RateLimitError("rate limited", response=response, body=None)


class _FakeEmbeddings:
    """Fails `fail_times` times, then succeeds. Records how often it was called."""

    def __init__(self, fail_times: int, exc: Exception | None = None):
        self.fail_times = fail_times
        self.calls = 0
        self.exc = exc or _rate_limit_error()

    def create(self, **kwargs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise self.exc
        return type("Resp", (), {"data": [f"vec{i}" for i in range(len(kwargs["input"]))]})()


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    """Strip the backoff wait so the suite does not actually sleep for seconds."""
    monkeypatch.setattr(rag_ingest.retry_openai, "sleep", lambda _: None, raising=False)


@pytest.fixture
def _api_key(monkeypatch):
    monkeypatch.setattr(rag_ingest.settings, "OPENAI_API_KEY", "test-key")


class TestEmbedChunksRetry:
    def test_recovers_from_a_transient_rate_limit(self, monkeypatch, _api_key):
        """The exact production failure: one 429, then success."""
        fake = _FakeEmbeddings(fail_times=1)
        monkeypatch.setattr(
            rag_ingest, "get_openai_client", lambda: type("C", (), {"embeddings": fake})()
        )

        result = rag_ingest.embed_chunks(["chunk one", "chunk two"])

        assert len(result) == 2
        assert fake.calls == 2, "should have retried exactly once"

    def test_recovers_from_a_connection_error(self, monkeypatch, _api_key):
        fake = _FakeEmbeddings(
            fail_times=2,
            exc=APIConnectionError(request=httpx.Request("POST", "https://api.openai.com/")),
        )
        monkeypatch.setattr(
            rag_ingest, "get_openai_client", lambda: type("C", (), {"embeddings": fake})()
        )

        assert len(rag_ingest.embed_chunks(["a"])) == 1
        assert fake.calls == 3

    def test_gives_up_after_the_configured_attempts(self, monkeypatch, _api_key):
        """Retrying forever would turn a rate limit into a hang. retry_openai stops
        at 3 attempts; the caller still sees the failure."""
        fake = _FakeEmbeddings(fail_times=99)
        monkeypatch.setattr(
            rag_ingest, "get_openai_client", lambda: type("C", (), {"embeddings": fake})()
        )

        with pytest.raises(Exception):
            rag_ingest.embed_chunks(["a"])
        assert fake.calls == 3

    def test_no_retry_on_a_success(self, monkeypatch, _api_key):
        fake = _FakeEmbeddings(fail_times=0)
        monkeypatch.setattr(
            rag_ingest, "get_openai_client", lambda: type("C", (), {"embeddings": fake})()
        )

        rag_ingest.embed_chunks(["a", "b", "c"])
        assert fake.calls == 1

    def test_still_requires_an_api_key(self, monkeypatch):
        """The guard must fire before any retry machinery, so a misconfiguration
        fails immediately instead of backing off three times first."""
        monkeypatch.setattr(rag_ingest.settings, "OPENAI_API_KEY", "")
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            rag_ingest.embed_chunks(["a"])

    def test_dimensions_are_pinned_to_1536(self, monkeypatch, _api_key):
        """The retry wrapper must not drop the kwargs. 1536 is what the pgvector
        column and its HNSW index are built for."""
        seen = {}

        class _Capture:
            def create(self, **kwargs):
                seen.update(kwargs)
                return type("Resp", (), {"data": ["v"]})()

        monkeypatch.setattr(
            rag_ingest, "get_openai_client", lambda: type("C", (), {"embeddings": _Capture()})()
        )

        rag_ingest.embed_chunks(["a"], model="text-embedding-3-large")

        assert seen["dimensions"] == 1536
        assert seen["model"] == "text-embedding-3-large"
        assert seen["input"] == ["a"]
