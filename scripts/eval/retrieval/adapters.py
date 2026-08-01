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
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .plan_probe import PLAN_UNKNOWN, probe_plan, summarise_plans

EVAL_DIR = Path(__file__).resolve().parent.parent
DB_MODULE_PATH = EVAL_DIR / "db.py"
INGEST_MODULE_PATH = EVAL_DIR / "ingest.py"

# ---------------------------------------------------------------------------
# The doc-id join
# ---------------------------------------------------------------------------
#
# labels.py identifies a document by sha256(pdf_bytes)[:16]. The database
# identifies the same document by uuid5(EVAL_DOC_NAMESPACE, <full sha256 hex>),
# because that is what scripts/eval/ingest.py writes. Those two ids never
# collide, so without an explicit translation every DB-backed run scores 0.0 on
# every metric while looking perfectly healthy -- the exact class of silent
# failure this harness exists to catch.
#
# These two constants MIRROR scripts/eval/ingest.py, which is owned by another
# lane and is not imported here (importing it pulls in PyMuPDF, tiktoken and the
# whole backend app package). test_adapters.py reads that file textually and
# fails if either value drifts.
EVAL_DOC_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")
EVAL_PROJECT_ID = "e7a1c0b0-0000-4000-8000-000000000001"


def db_document_id(content_sha256: str) -> str:
    """The database document id ingest.py assigns to a PDF with this content hash."""
    return str(uuid.uuid5(EVAL_DOC_NAMESPACE, content_sha256))


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

    Every call also asks Postgres which plan it chose at this depth and records
    it, so a run can never again be labelled HNSW when it was an exhaustive scan.
    See ``plan_probe`` for why that is a live question and how it is answered.
    """

    name = "dense"

    def __init__(self, project_id: str, embed_fn=None, name: str | None = None,
                 record_plan: bool = True) -> None:
        super().__init__(project_id, name)
        self.embed_fn = embed_fn
        self.record_plan = record_plan
        #: One entry per retrieve() call: "index" or "seqscan".
        self.plan_kinds: list[str] = []

    def plan_summary(self) -> str:
        """``"index"`` / ``"seqscan"`` / ``"mixed"`` / ``"unknown"`` for the run."""
        if not self.record_plan:
            return PLAN_UNKNOWN
        return summarise_plans(self.plan_kinds)

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
            if self.record_plan:
                self.plan_kinds.append(probe_plan(conn, embedding, self.project_id, k))
            rows = db.match_document_chunks(
                conn, embedding, self.project_id, k
            )
        return self._rows_to_docs(list(rows or []), "similarity")


#: Env flag mirroring ``app.services.rag_retrieval.KEYWORD_SEARCH_V2_ENV``.
KEYWORD_SEARCH_V2_ENV = "KEYWORD_SEARCH_V2"
KEYWORD_RPC_V1 = "keyword_search_chunks"
KEYWORD_RPC_V2 = "keyword_search_chunks_v2"


def keyword_v2_enabled() -> bool:
    """Same parse as the backend's: 1/true/yes/on, default OFF."""
    return (os.getenv(KEYWORD_SEARCH_V2_ENV) or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


class KeywordRetriever(_DBRetriever):
    """Lexical retrieval via ``keyword_search_chunks`` or its v2 sibling.

    v1 builds its tsquery with ``plainto_tsquery``, which ANDs every lemma. The
    queries here are ~20-word manuscript claims, so a chunk had to contain all
    ~20 lemmas: 55 of 59 queries returned zero rows and recall@10 was 0.0026.
    Migration 038 added ``keyword_search_chunks_v2``, which ORs the lemmas and
    ranks with ``ts_rank(..., 1|32)``. See docs/MEASUREMENTS.md §Keyword query formulation.

    Which one runs is chosen exactly the way the application chooses -- the
    ``KEYWORD_SEARCH_V2`` env flag, default off -- so the eval cannot measure a
    code path production is not running. The chosen RPC name is recorded.

    This adapter does NOT swallow errors. ``rag_retrieval.keyword_search`` does,
    which is how the keyword leg of hybrid retrieval returned nothing for the
    entire life of the feature without anyone noticing. A broken RPC must surface
    as a failed eval run, not as a plausible-looking zero.
    """

    name = "keyword"

    def __init__(self, project_id: str, name: str | None = None,
                 use_v2: bool | None = None) -> None:
        super().__init__(project_id, name)
        self.use_v2 = keyword_v2_enabled() if use_v2 is None else bool(use_v2)

    @property
    def rpc_name(self) -> str:
        return KEYWORD_RPC_V2 if self.use_v2 else KEYWORD_RPC_V1

    def retrieve(self, query: str, k: int) -> list[RetrievedDoc]:
        db = _load_db_module()
        with db.get_connection() as conn:
            if self.use_v2:
                # db.py wraps v1 only and is owned by another lane, so v2 is
                # called directly rather than by editing that module.
                import psycopg2.extras  # type: ignore

                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute(
                        f"SELECT * FROM public.{KEYWORD_RPC_V2}(%s::uuid, %s, %s)",
                        (self.project_id, query, k),
                    )
                    rows = [dict(r) for r in cur.fetchall()]
            else:
                rows = db.keyword_search_chunks(conn, self.project_id, query, k)
        return self._rows_to_docs(list(rows or []), "rank")


# ---------------------------------------------------------------------------
# Hybrid -- reciprocal rank fusion
# ---------------------------------------------------------------------------

#: The conventional RRF constant (Cormack, Clarke & Buettcher 2009). It damps the
#: contribution of the very top ranks: at k_rrf = 60, rank 1 scores 1/61 and rank
#: 2 scores 1/62, a 1.6% difference, so a single leg's confident #1 cannot carry
#: the fused list on its own. Small k_rrf sharpens that; large k_rrf flattens
#: towards "appears in both lists" voting. It is swept, not assumed -- see
#: docs/MEASUREMENTS.md §Retrieval baseline 15.
DEFAULT_K_RRF = 60


def rrf_fuse(
    result_lists: list[list[RetrievedDoc]],
    k_rrf: int = DEFAULT_K_RRF,
    limit: int | None = None,
) -> list[RetrievedDoc]:
    """Reciprocal rank fusion: ``score(d) = sum over lists of 1 / (k_rrf + rank)``.

    FUSE BY RANK, NOT BY SCORE. This is the whole reason RRF is the right tool
    here rather than ``hybrid_search``'s ``0.7*similarity + 0.3*keyword_score``:
    ``ts_rank(..., 1|32)`` values in this corpus sit between 0.0038 and 0.0071
    while cosine similarity sits around 0.3-0.6, so a weighted sum gives the
    keyword leg under 1% of the combined total -- technically fused, practically
    ignored. RRF consumes order and is immune to the scale mismatch by
    construction.

    FUSED AT DOCUMENT LEVEL. A document's rank within a leg is the rank of its
    best-ranked chunk. The alternative -- fusing chunk ids -- looks more natural
    but is measurably weaker for this harness: the relevance unit is *document*
    (docs/EVAL_GUIDE.md §Relevance §2), and if the dense leg's evidence for a document is chunk A
    while the keyword leg's is chunk B, chunk-level fusion gives that document no
    agreement bonus at all, which is exactly the evidence fusion exists to
    combine. The returned list therefore carries one entry per document, with the
    best contributing chunk attached for inspection.

    Ranks come from each ``RetrievedDoc.rank`` (1-based), not from list position,
    so a caller that has already filtered a list does not silently re-rank it.
    Ties are broken by ``doc_id`` so the output is deterministic.
    """
    if k_rrf <= 0:
        raise ValueError(f"k_rrf must be positive, got {k_rrf}")

    scores: dict[str, float] = {}
    best: dict[str, RetrievedDoc] = {}
    for results in result_lists:
        best_rank_in_list: dict[str, RetrievedDoc] = {}
        for r in results:
            prev = best_rank_in_list.get(r.doc_id)
            if prev is None or r.rank < prev.rank:
                best_rank_in_list[r.doc_id] = r
        for doc_id, r in best_rank_in_list.items():
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k_rrf + r.rank)
            held = best.get(doc_id)
            if held is None or r.rank < held.rank:
                best[doc_id] = r

    ordered = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if limit is not None:
        ordered = ordered[:limit]

    out: list[RetrievedDoc] = []
    for i, (doc_id, score) in enumerate(ordered, start=1):
        src = best[doc_id]
        out.append(RetrievedDoc(
            doc_id=doc_id,
            chunk_id=src.chunk_id,
            score=score,
            rank=i,
            section_id=src.section_id,
            text=src.text,
        ))
    return out


class HybridRetriever:
    """RRF over a dense leg and a lexical leg.

    Both legs are asked for the SAME depth the harness asked this retriever for,
    so the fusion sees each leg at the operating point that leg's own arm was
    measured at, and the comparison is like for like.

    Per-leg row counts are kept in ``leg_health``. A fusion whose keyword leg
    contributed nothing is dense wearing hybrid's name; the run verdict in
    ``run_retrieval_eval`` reads this and invalidates such a run rather than
    reporting it as a fusion result.
    """

    name = "hybrid"

    def __init__(self, dense: Retriever, keyword: Retriever,
                 k_rrf: int = DEFAULT_K_RRF) -> None:
        self.dense = dense
        self.keyword = keyword
        self.k_rrf = k_rrf
        self.leg_health = {"dense_rows": 0, "keyword_rows": 0,
                           "dense_empty_queries": 0, "keyword_empty_queries": 0}

    def plan_summary(self) -> str:
        probe = getattr(self.dense, "plan_summary", None)
        return probe() if callable(probe) else PLAN_UNKNOWN

    def retrieve(self, query: str, k: int) -> list[RetrievedDoc]:
        dense_hits = self.dense.retrieve(query, k)
        keyword_hits = self.keyword.retrieve(query, k)
        self.leg_health["dense_rows"] += len(dense_hits)
        self.leg_health["keyword_rows"] += len(keyword_hits)
        if not dense_hits:
            self.leg_health["dense_empty_queries"] += 1
        if not keyword_hits:
            self.leg_health["keyword_empty_queries"] += 1
        return rrf_fuse([dense_hits, keyword_hits], k_rrf=self.k_rrf, limit=k)


# ---------------------------------------------------------------------------
# Degradation flag -- app.services.rag_retrieval.KEYWORD_SEARCH_DEGRADED
# ---------------------------------------------------------------------------


#: What a run reports when the backend module is not importable. Deliberately
#: NOT ``degraded: False``: "we could not check" and "we checked and it is fine"
#: are different claims and must not be confused in a results record.
UNKNOWN_DEGRADATION = {
    "name": "keyword_search_chunks",
    "degraded": None,
    "failure_count": None,
    "last_error": None,
    "checked": False,
    "note": "app.services.rag_retrieval not importable; degradation state UNKNOWN",
}


def _keyword_degradation_flag():
    """Return ``KEYWORD_SEARCH_DEGRADED`` or None if the backend is unavailable.

    Imported lazily and by path so the harness still collects and runs against
    MockRetriever on a machine with no backend dependencies installed.
    """
    import sys

    backend = EVAL_DIR.parent.parent / "services" / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    try:
        from app.services.rag_retrieval import KEYWORD_SEARCH_DEGRADED  # type: ignore
        return KEYWORD_SEARCH_DEGRADED
    except Exception:
        return None


def keyword_degradation_snapshot() -> dict:
    """Current state of the keyword-search degradation flag.

    ``rag_retrieval.keyword_search`` swallows RPC failures and returns ``[]``,
    which is how the keyword leg of hybrid retrieval silently returned nothing
    for the entire life of the feature. A run that completes with this flag set
    has produced a plausible zero, not a measurement, and must say so.
    """
    flag = _keyword_degradation_flag()
    if flag is None:
        return dict(UNKNOWN_DEGRADATION)
    snap = flag.snapshot()
    snap["checked"] = True
    return snap


def reset_keyword_degradation() -> None:
    """Clear the flag before a run so it reflects THIS run, not process history."""
    flag = _keyword_degradation_flag()
    if flag is not None:
        flag.clear()


# ---------------------------------------------------------------------------
# Query embedding
# ---------------------------------------------------------------------------


#: Query embeddings persist here between runs. Four arms over the same query set
#: would otherwise pay for the same 338 embeddings four times, and -- worse --
#: would each get a *slightly* different vector, since the API is not bit-stable
#: across calls. A cached vector makes the arms comparable, not just cheaper.
QUERY_EMBED_CACHE_DIR = EVAL_DIR / "cache" / "retrieval_query_embeddings"


def production_embed_fn(model: str = "text-embedding-3-large", use_cache: bool = True):
    """An ``embed_fn`` using the SAME production call the index was built with.

    scripts/eval/ingest.py embeds chunks with
    ``app.services.rag_ingest.embed_chunks(..., model="text-embedding-3-large")``
    at 1536 dimensions. Querying a vector index with a different embedding model
    than it was built with produces numbers that look like a bad retriever and
    are actually a bad ruler, so this reuses that exact function rather than
    re-deriving one.
    """
    import os
    import sys

    backend = EVAL_DIR.parent.parent / "services" / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    # app.core.config reads env_file=".env" relative to the PROCESS cwd, so the
    # settings object is empty when the harness runs from anywhere else and the
    # embedding call dies with "OPENAI_API_KEY not configured". Same fix as
    # scripts/eval/ingest.py:_load_backend_env. Existing env vars always win.
    env_path = backend / ".env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip().strip('"').strip("'")

    import json

    from app.core.llm_budget import check_llm_allowed, record_usage  # type: ignore
    from app.services.rag_ingest import embed_chunks  # type: ignore

    cache_path = QUERY_EMBED_CACHE_DIR / f"{model}.json"
    cache: dict[str, list[float]] = {}
    if use_cache and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text())
        except (json.JSONDecodeError, OSError):
            cache = {}
    dirty = False

    def key_of(query: str) -> str:
        return hashlib.sha256(query.encode("utf-8")).hexdigest()[:24]

    def flush() -> None:
        nonlocal dirty
        if use_cache and dirty:
            QUERY_EMBED_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache))
            dirty = False

    def embed(query: str) -> list[float]:
        nonlocal dirty
        key = key_of(query)
        if key in cache:
            return cache[key]
        check_llm_allowed("retrieval_eval_query_embed")
        vector = list(embed_chunks([query], model=model)[0].embedding)
        record_usage(model=model, prompt_tokens=max(1, len(query) // 4),
                     label="retrieval_eval_query_embed")
        cache[key] = vector
        dirty = True
        if len(cache) % 25 == 0:  # survive an interrupted run
            flush()
        return vector

    embed.flush = flush  # type: ignore[attr-defined]
    embed.cache = cache  # type: ignore[attr-defined]
    return embed


def build_retriever(name: str, **kwargs) -> Retriever:
    """Factory used by the CLI."""
    if name == "mock":
        return MockRetriever(**kwargs)
    if name == "dense":
        return DenseRetriever(**kwargs)
    if name == "keyword":
        return KeywordRetriever(**kwargs)
    if name == "hybrid":
        if "dense" not in kwargs:
            # Build both legs from a project id + embedder, so the CLI does not
            # have to know how a leg is wired.
            project_id = kwargs.pop("project_id")
            embed_fn = kwargs.pop("embed_fn", None)
            use_v2 = kwargs.pop("use_v2", None)
            kwargs["dense"] = DenseRetriever(project_id=project_id, embed_fn=embed_fn)
            kwargs["keyword"] = KeywordRetriever(project_id=project_id, use_v2=use_v2)
        return HybridRetriever(**kwargs)
    raise ValueError(f"Unknown retriever '{name}'. Choose: mock, dense, keyword, hybrid.")
