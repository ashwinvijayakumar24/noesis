"""Retriever adapters behind one protocol.

The point of this module is decoupling: the harness is built, tested and runnable
against ``MockRetriever`` with no database and no network, while the DB-backed
retrievers are wired to ``scripts/eval/db.py``, which is owned by another lane.

That module is imported **lazily, inside the method** -- never at import time --
so the absence of a database never breaks collection, and its absence produces
one clear actionable error instead of an ImportError at import time.

The RPC wrappers there take an open psycopg2 connection first:
``match_document_chunks(conn, embedding, project_id, match_count)`` and
``keyword_search_chunks(conn, project_id, query, match_count)``. This module owns
connection lifetime; it does not own embedding (see ``DenseRetriever``).
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

EVAL_DIR = Path(__file__).resolve().parent.parent
DB_MODULE_PATH = EVAL_DIR / "db.py"


@dataclass(frozen=True)
class RetrievedDoc:
    """One retrieval result.

    ``rank`` is 1-based. ``doc_id`` must be joinable to ``labels.CorpusDoc.doc_id``
    for scoring; see ``docs_by_key`` for the filename-based join used until the
    ingestion path stores content hashes.
    """

    doc_id: str
    chunk_id: str
    score: float
    rank: int
    section_id: str | None = None
    text: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@runtime_checkable
class Retriever(Protocol):
    """The one interface the harness scores against."""

    name: str

    def retrieve(self, query: str, k: int) -> list[RetrievedDoc]:
        ...


class RetrieverUnavailable(RuntimeError):
    """Raised when a retriever's backing dependency is not present."""


# ---------------------------------------------------------------------------
# Mock -- deterministic, no DB, no network
# ---------------------------------------------------------------------------


class MockRetriever:
    """Deterministic seeded retriever for tests and end-to-end smoke runs.

    Scores each corpus document by a hash of ``(seed, query, doc_id)``, so results
    are stable across processes and machines (Python's ``hash()`` is not, hence
    sha256). Optionally plants a fraction of each query's true relevant documents
    at the top, so the harness can be exercised at a known, non-degenerate
    operating point rather than at pure chance.
    """

    def __init__(
        self,
        doc_ids: list[str],
        seed: int = 0,
        relevant_by_query: dict[str, list[str]] | None = None,
        plant_rate: float = 0.0,
        name: str = "mock",
    ) -> None:
        self.doc_ids = list(doc_ids)
        self.seed = seed
        self.relevant_by_query = relevant_by_query or {}
        self.plant_rate = plant_rate
        self.name = name

    def _score(self, query: str, doc_id: str) -> float:
        digest = hashlib.sha256(f"{self.seed}\0{query}\0{doc_id}".encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") / float(1 << 64)

    def retrieve(self, query: str, k: int) -> list[RetrievedDoc]:
        planted: list[str] = []
        if self.plant_rate > 0:
            relevant = self.relevant_by_query.get(query, [])
            n_plant = int(len(relevant) * self.plant_rate)
            planted = sorted(relevant)[:n_plant]

        ranked = sorted(
            (d for d in self.doc_ids if d not in planted),
            key=lambda d: (-self._score(query, d), d),
        )
        ordered = planted + ranked

        out: list[RetrievedDoc] = []
        for i, doc_id in enumerate(ordered[:k], start=1):
            out.append(
                RetrievedDoc(
                    doc_id=doc_id,
                    chunk_id=f"{doc_id}::c0",
                    # Strictly decreasing so the run order is unambiguous to ranx.
                    score=round(1.0 - (i - 1) / max(k, 1) * 0.5, 6),
                    rank=i,
                    section_id=f"{doc_id}::s0",
                )
            )
        return out


# ---------------------------------------------------------------------------
# DB-backed -- lazy import of scripts/eval/db.py
# ---------------------------------------------------------------------------


def _load_db_module():
    """Import ``scripts/eval/db.py`` lazily with an actionable error."""
    try:
        from scripts.eval import db  # type: ignore
        return db
    except ImportError:
        pass
    try:
        import db  # type: ignore  # when run from within scripts/eval
        return db
    except ImportError:
        pass
    raise RetrieverUnavailable(
        f"Database access module not found (expected at {DB_MODULE_PATH}).\n"
        "DenseRetriever and KeywordRetriever require it; it is owned by the lane "
        "standing up the eval database.\n"
        "Fix: ensure scripts/eval/db.py exists and exposes match_document_chunks() "
        "and keyword_search_chunks(), then re-run. To run the harness without a "
        "database, use --retriever mock."
    )


class _DBRetriever:
    """Shared plumbing for DB-backed retrievers.

    Signatures follow ``scripts/eval/db.py``: both RPC wrappers take an open
    psycopg2 connection as their first argument, so this class owns connection
    lifetime and the subclasses own the query.
    """

    name = ""

    def __init__(self, project_id: str, name: str | None = None) -> None:
        self.project_id = project_id
        if name:
            self.name = name

    @staticmethod
    def _rows_to_docs(rows: list[dict], score_key: str) -> list[RetrievedDoc]:
        out: list[RetrievedDoc] = []
        for i, row in enumerate(rows, start=1):
            out.append(
                RetrievedDoc(
                    doc_id=str(row.get("document_id") or row.get("doc_id") or ""),
                    chunk_id=str(row.get("id") or row.get("chunk_id") or f"row{i}"),
                    score=float(row.get(score_key) or 0.0),
                    rank=i,
                    section_id=row.get("section_id"),
                    text=row.get("content") or row.get("chunk_text"),
                )
            )
        return out


class DenseRetriever(_DBRetriever):
    """Vector retrieval via the ``match_document_chunks`` RPC.

    ``embed_fn`` is injected rather than chosen here: the embedding model is a
    property of the system under test, not of the ruler. Passing the retriever a
    different embedder is exactly how an embedding swap gets measured.
    """

    name = "dense"

    def __init__(self, project_id: str, embed_fn=None, name: str | None = None) -> None:
        super().__init__(project_id, name)
        self.embed_fn = embed_fn

    def retrieve(self, query: str, k: int) -> list[RetrievedDoc]:
        db = _load_db_module()
        if self.embed_fn is None:
            raise RetrieverUnavailable(
                "DenseRetriever needs an embed_fn (str -> list[float]). "
                "scripts/eval/db.py speaks to Postgres but does not embed. "
                "Pass DenseRetriever(project_id=..., embed_fn=...) with the same "
                "embedding model the index was built with, or use --retriever mock."
            )
        embedding = self.embed_fn(query)
        with db.get_connection() as conn:
            rows = db.match_document_chunks(
                conn, embedding, self.project_id, k
            )
        return self._rows_to_docs(list(rows or []), "similarity")


class KeywordRetriever(_DBRetriever):
    """Lexical retrieval via the ``keyword_search_chunks`` RPC.

    DEPENDENCY: this RPC is broken in production -- it selects a ``dc.metadata``
    column that does not exist, raising Postgres ``42703`` -- and is being fixed
    in migration 037 by another lane. Worse, ``rag_retrieval.keyword_search``
    swallows the exception and returns ``[]``, so in production hybrid retrieval
    has been silently degrading to dense-only. This adapter targets the FIXED
    signature and does NOT swallow errors: a broken RPC must surface as a failed
    eval run, not as a plausible-looking zero.
    """

    name = "keyword"

    def retrieve(self, query: str, k: int) -> list[RetrievedDoc]:
        db = _load_db_module()
        with db.get_connection() as conn:
            rows = db.keyword_search_chunks(conn, self.project_id, query, k)
        return self._rows_to_docs(list(rows or []), "rank")


# ---------------------------------------------------------------------------
# Hybrid -- INTENTIONALLY UNIMPLEMENTED
# ---------------------------------------------------------------------------


class HybridRetriever:
    """STUB. Fusion of dense + keyword is deliberately not implemented.

    Implementing RRF (or any fusion) now would pre-empt the measurement this lane
    exists to enable. The correct order is: land the ruler, measure dense and
    keyword separately on it, then implement fusion and show it beats both. A
    fusion built before the baseline exists cannot be shown to have helped.

    Slot for the future implementation:
        retrieve() -> run dense(k*m) and keyword(k*m), fuse, truncate to k.
    """

    name = "hybrid"

    def __init__(self, dense: Retriever, keyword: Retriever, k_rrf: int = 60) -> None:
        self.dense = dense
        self.keyword = keyword
        self.k_rrf = k_rrf

    def retrieve(self, query: str, k: int) -> list[RetrievedDoc]:
        raise NotImplementedError(
            "HybridRetriever is a deliberate stub. Fusion (RRF) is a later build: "
            "measure dense and keyword separately on this harness first so the "
            "fusion has a baseline to beat."
        )


def build_retriever(name: str, **kwargs) -> Retriever:
    """Factory used by the CLI."""
    if name == "mock":
        return MockRetriever(**kwargs)
    if name == "dense":
        return DenseRetriever(**kwargs)
    if name == "keyword":
        return KeywordRetriever(**kwargs)
    if name == "hybrid":
        return HybridRetriever(**kwargs)
    raise ValueError(f"Unknown retriever '{name}'. Choose: mock, dense, keyword, hybrid.")
