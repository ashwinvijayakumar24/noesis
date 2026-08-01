"""Arm 1 of the embedding lane: does the half of the embedding we throw away matter?

``app/services/rag_ingest.py:316`` calls the OpenAI embeddings API with
``dimensions=1536`` and the comment *"Fixed at 1536 for pgvector index
compatibility"*. ``text-embedding-3-large`` is natively **3072**, and the
truncation is Matryoshka: the first 1,536 components are kept and the rest are
discarded. So half of every vector this system has ever stored was thrown away
for an indexing reason.

**The indexing reason is only half true.** Verified on this database
(pgvector 0.8.6):

===============================  ==========================================
``HNSW on vector(3072)``         ERROR: cannot have more than 2000 dimensions
``HNSW on halfvec(3072)``        OK
``HNSW on halfvec(4000)``        OK
===============================  ==========================================

The comment is correct for ``vector`` and wrong for ``halfvec``. This module
re-embeds the corpus at full width into ``halfvec(3072)``, builds an HNSW cosine
index over it, and measures it against a control re-measured in the same session
-- so the question "do the discarded 1,536 dimensions carry retrievable signal"
gets an answer rather than an argument.

WHAT THIS MODULE WILL NOT DO
    It never writes to ``public.document_chunks``, never re-ingests, and never
    touches ``idx_document_chunks_embedding``. That table is shared with other
    agents on this branch and mutating it has already invalidated a day of
    measurements once (``docs/ENGINEERING_LOG.md``, "The concurrency incident").
    The 3072 arm lives in its own table, created by
    ``scripts/eval/schema/100_local_embedding_arm_3072.sql``, and the chunk-id
    digest of ``document_chunks`` is sampled before *and* after every pass. One
    sample cannot detect a mid-run swap; two can.

WHAT A CORPUS CHANGE IS AND IS NOT
    Re-embedding mints a new corpus identity. The 3072 arm is therefore
    **never** differenced against the historical 0.2195 / 0.2200 lineage -- only
    against the control measured in the same session, over the same chunk ids,
    through the same scoring code. ``config_hash`` includes the embedding
    dimensionality and the vector column type precisely so the two arms cannot
    collide in the sink.

A NULL IS A RESULT
    "The 1,536 dimensions Matryoshka discards carry no retrievable signal on this
    corpus" is a finding, is worth the two dollars it costs to establish, and is
    reported as such rather than as a failed arm.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.eval.retrieval import firststage as fs  # noqa: E402
from scripts.eval.retrieval import metrics as metrics_mod  # noqa: E402
from scripts.eval.retrieval.adapters import EVAL_PROJECT_ID  # noqa: E402
from scripts.eval.retrieval.run_retrieval_eval import config_hash  # noqa: E402

EVAL_DIR = Path(__file__).resolve().parent.parent
SCHEMA_SQL = EVAL_DIR / "schema" / "100_local_embedding_arm_3072.sql"
CACHE_DIR = EVAL_DIR / "cache" / "retrieval_3072"
CHUNK_CACHE = CACHE_DIR / "chunks.npz"
QUERY_CACHE = CACHE_DIR / "queries.json"
RESULTS_PATH = EVAL_DIR / "results" / "embedding_arms.jsonl"

HARNESS_VERSION = "embed_arms/1.0.0"

EMBED_MODEL = "text-embedding-3-large"
EMBED_USD_PER_MTOK = 0.13
NATIVE_DIM = 3072
#: What rag_ingest.py truncates to, and what the shipped index stores.
SHIPPED_DIM = 1536

#: The shipped operating point, held identical across both arms. Only the
#: embedding width and the column type change.
K = 10
CHUNK_OVERSAMPLE = 5
EF_SEARCH = 80

ARM_3072_TABLE = "document_chunks_3072"

#: Metrics reported for both arms. recall@20 is included even though the shipped
#: 50-chunk pool holds a median of 20 documents: it is a property of the arm, and
#: silently dropping the k where the pool runs out would flatter both arms.
ARM_METRICS = ["recall@1", "recall@5", "recall@10", "recall@20", "mrr", "ndcg@10", "map"]
CEILING_KS = [1, 5, 10, 20]


class ArmError(RuntimeError):
    """The arm cannot be measured as configured."""


# ---------------------------------------------------------------------------
# Cost
# ---------------------------------------------------------------------------


def estimate_cost(project_id: str = EVAL_PROJECT_ID) -> dict:
    """Input tokens and dollars to re-embed the corpus at 3072.

    Dimensionality does not change what is billed -- OpenAI charges input tokens
    and returns however many components you ask for -- so this is the same bill
    the corpus already paid once at 1536.
    """
    from scripts.eval import db  # noqa: PLC0415

    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT count(*), sum(length(c.content))
            FROM public.document_chunks c
            JOIN public.documents d ON d.id = c.document_id
            WHERE d.project_id = %s::uuid
            """,
            (project_id,),
        )
        n_chunks, n_chars = cur.fetchone()
    # ~4 chars/token, the standard OpenAI rule of thumb. Scientific prose runs
    # slightly denser, so this is an upper bound on the bill, not a point estimate.
    tokens = int(n_chars) / 4.0
    return {
        "n_chunks": int(n_chunks),
        "n_chars": int(n_chars),
        "est_input_tokens": int(tokens),
        "est_usd": round(tokens / 1e6 * EMBED_USD_PER_MTOK, 4),
    }


# ---------------------------------------------------------------------------
# Embedding at native width
# ---------------------------------------------------------------------------


def _load_backend() -> None:
    """Put ``services/backend`` on the path and its ``.env`` on the environment.

    ``app.core.config`` reads ``env_file=".env"`` relative to the PROCESS cwd, so
    the settings object is empty when the harness runs from anywhere else and the
    embedding call dies with "OPENAI_API_KEY not configured". Same fix as
    ``adapters.production_embed_fn``; existing env vars always win, so a caller's
    ``NOESIS_LLM_MAX_SPEND_USD`` is never overwritten by the file.
    """
    backend = EVAL_DIR.parent.parent / "services" / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    env_path = backend / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def _openai_embed(texts: list[str], dimensions: int) -> list[list[float]]:
    """One embeddings call at an explicit width.

    ``rag_ingest.embed_chunks`` hardcodes ``dimensions=1536`` and is production
    code this lane does not edit, so the client and its retry decorator are
    reused directly rather than the function that pins the width.
    """
    _load_backend()
    from app.services.rag_ingest import get_openai_client, retry_openai  # noqa: PLC0415

    client = get_openai_client()

    @retry_openai
    def _create():
        return client.embeddings.create(model=EMBED_MODEL, input=texts, dimensions=dimensions)

    return [list(d.embedding) for d in _create().data]


def _key_of(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]


def embed_corpus_3072(
    project_id: str = EVAL_PROJECT_ID,
    allow_spend: bool = False,
    batch: int = 64,
) -> dict:
    """Embed every chunk at 3072 into ``CHUNK_CACHE``, resumable and cached.

    Stored as a float32 ``.npz`` keyed by chunk id rather than JSON: 5,948 x 3072
    floats is ~350 MB of JSON text and 73 MB of float32, and the JSON round-trip
    is the slowest part of the whole arm.
    """
    import numpy as np  # noqa: PLC0415

    from scripts.eval import db  # noqa: PLC0415

    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id::text, c.document_id::text, c.content
            FROM public.document_chunks c
            JOIN public.documents d ON d.id = c.document_id
            WHERE d.project_id = %s::uuid
            ORDER BY c.id
            """,
            (project_id,),
        )
        rows = cur.fetchall()

    have: dict[str, "np.ndarray"] = {}
    if CHUNK_CACHE.exists():
        with np.load(CHUNK_CACHE) as z:
            ids = list(z["ids"])
            mat = z["vectors"]
        have = {str(i): mat[j] for j, i in enumerate(ids)}

    missing = [(cid, content or "") for cid, _doc, content in rows if cid not in have]
    if missing:
        if not allow_spend:
            est = sum(len(t) for _, t in missing) / 4.0 / 1e6 * EMBED_USD_PER_MTOK
            raise ArmError(
                f"{len(missing)} of {len(rows)} chunks are not cached at {NATIVE_DIM}d; "
                f"embedding them costs ~${est:.4f}. Re-run with --allow-spend."
            )
        _load_backend()
        from app.core.llm_budget import record_usage  # noqa: PLC0415

        for i in range(0, len(missing), batch):
            block = missing[i : i + batch]
            vectors = _openai_embed([t for _, t in block], NATIVE_DIM)
            for (cid, _t), vec in zip(block, vectors):
                have[cid] = np.asarray(vec, dtype=np.float32)
            record_usage(
                model=EMBED_MODEL,
                prompt_tokens=max(1, sum(len(t) for _, t in block) // 4),
                label="embed_arms_chunk_3072",
            )
            if (i // batch) % 10 == 0:
                _save_chunk_cache(have)
                print(f"  embedded {min(i + batch, len(missing))}/{len(missing)}", flush=True)
        _save_chunk_cache(have)

    dims = {int(v.shape[0]) for v in have.values()}
    if dims != {NATIVE_DIM}:
        raise ArmError(f"cached chunk vectors have widths {sorted(dims)}, expected {NATIVE_DIM}")
    return {"n_chunks": len(rows), "n_cached": len(have), "n_embedded_this_run": len(missing)}


def _save_chunk_cache(have: dict) -> None:
    import numpy as np  # noqa: PLC0415

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ids = sorted(have)
    np.savez(
        CHUNK_CACHE,
        # Fixed-width unicode, not dtype=object: an object array is a pickle and
        # np.load refuses to read one without allow_pickle=True.
        ids=np.array(ids, dtype="U36"),
        vectors=np.stack([have[i] for i in ids]).astype(np.float32),
    )


def embed_queries_3072(query_list, allow_spend: bool = False, batch: int = 64) -> dict[str, list[float]]:
    """Query vectors at 3072, cached separately from the 1536 query cache.

    A separate file, not a separate key inside the shipped cache: overwriting
    ``retrieval_query_embeddings/text-embedding-3-large.json`` with wider vectors
    would silently break every other arm on this branch that reads it.
    """
    cache: dict[str, list[float]] = {}
    if QUERY_CACHE.exists():
        cache = json.loads(QUERY_CACHE.read_text())

    missing = [q.text for q in query_list if _key_of(q.text) not in cache]
    if missing:
        if not allow_spend:
            est = sum(len(t) for t in missing) / 4.0 / 1e6 * EMBED_USD_PER_MTOK
            raise ArmError(
                f"{len(missing)} queries are not cached at {NATIVE_DIM}d "
                f"(~${est:.4f}). Re-run with --allow-spend."
            )
        _load_backend()
        from app.core.llm_budget import record_usage  # noqa: PLC0415

        for i in range(0, len(missing), batch):
            block = missing[i : i + batch]
            for text, vec in zip(block, _openai_embed(block, NATIVE_DIM)):
                cache[_key_of(text)] = vec
            record_usage(
                model=EMBED_MODEL,
                prompt_tokens=max(1, sum(len(t) for t in block) // 4),
                label="embed_arms_query_3072",
            )
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        QUERY_CACHE.write_text(json.dumps(cache))

    widths = {len(v) for v in cache.values()}
    if widths and widths != {NATIVE_DIM}:
        raise ArmError(f"cached query vectors have widths {sorted(widths)}, expected {NATIVE_DIM}")
    return cache


# ---------------------------------------------------------------------------
# Loading the 3072 arm into its own table
# ---------------------------------------------------------------------------


def load_arm_table(project_id: str = EVAL_PROJECT_ID) -> dict:
    """Create ``document_chunks_3072``, fill it, and build its HNSW index.

    Idempotent: the table is truncated and refilled from the cache, and the index
    is created after the rows so HNSW is built once over the whole set rather
    than incrementally 5,948 times.
    """
    import numpy as np  # noqa: PLC0415
    import psycopg2.extras  # noqa: PLC0415

    from scripts.eval import db  # noqa: PLC0415

    if not CHUNK_CACHE.exists():
        raise ArmError(f"no 3072 chunk cache at {CHUNK_CACHE}; run --mode embed first")
    with np.load(CHUNK_CACHE) as z:
        ids = [str(i) for i in z["ids"]]
        vectors = z["vectors"]

    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id::text, c.document_id::text
            FROM public.document_chunks c
            JOIN public.documents d ON d.id = c.document_id
            WHERE d.project_id = %s::uuid
            """,
            (project_id,),
        )
        parent = dict(cur.fetchall())
        if set(parent) != set(ids):
            raise ArmError(
                f"cache holds {len(ids)} chunk ids and the corpus holds {len(parent)}; "
                "they must be the same chunks or the arms are not comparable. "
                "Delete the cache and re-embed."
            )

        # Split on the statement terminator: psycopg2 will happily run the whole
        # file, but one failing statement then rolls the others back invisibly.
        for stmt in filter(None, (s.strip() for s in SCHEMA_SQL.read_text().split(";"))):
            if stmt.lstrip().startswith("--") and "CREATE" not in stmt.upper():
                continue
            cur.execute(stmt)

        cur.execute(f"DROP INDEX IF EXISTS public.idx_{ARM_3072_TABLE}_embedding")
        cur.execute(f"TRUNCATE public.{ARM_3072_TABLE}")
        psycopg2.extras.execute_values(
            cur,
            f"INSERT INTO public.{ARM_3072_TABLE} (id, document_id, project_id, embedding) "
            "VALUES %s",
            [
                (cid, parent[cid], project_id, db.format_vector(vectors[j]))
                for j, cid in enumerate(ids)
            ],
            template="(%s::uuid, %s::uuid, %s::uuid, %s::halfvec)",
            page_size=200,
        )
        cur.execute(
            f"CREATE INDEX idx_{ARM_3072_TABLE}_embedding ON public.{ARM_3072_TABLE} "
            "USING hnsw (embedding halfvec_cosine_ops)"
        )
        cur.execute(f"ANALYZE public.{ARM_3072_TABLE}")
        cur.execute(f"SELECT count(*), vector_dims(embedding) FROM public.{ARM_3072_TABLE} GROUP BY 2")
        counts = cur.fetchall()

    if len(counts) != 1 or counts[0][1] != NATIVE_DIM:
        raise ArmError(f"loaded table reports {counts}, expected one row at {NATIVE_DIM} dims")
    return {"rows": int(counts[0][0]), "dims": int(counts[0][1])}


# ---------------------------------------------------------------------------
# Retrieval, identical for both arms except the table and the cast
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArmSpec:
    name: str
    table: str
    column_type: str
    dimensions: int
    opclass: str
    #: None means "read the vectors already in the shipped index".
    query_vectors: dict[str, list[float]] | None


def _knn_sql(table: str, column_type: str) -> str:
    return f"""
SELECT c.document_id::text, c.id::text, 1 - (c.embedding <=> %s::{column_type})
FROM public.{table} c
WHERE c.project_id = %s::uuid
ORDER BY c.embedding <=> %s::{column_type}
LIMIT %s
"""


def retrieve_arm(
    gt,
    spec: ArmSpec,
    embed_fn,
    depth: int,
    ef_search: int = EF_SEARCH,
    project_id: str = EVAL_PROJECT_ID,
) -> dict:
    """Retrieve ``depth`` chunks per query and time each one.

    The plan is FORCED to an index scan and the plan Postgres actually chose is
    returned alongside. A plan flip is not an embedding result, and the only way
    to say that is to record which plan ran.
    """
    from scripts.eval import db  # noqa: PLC0415

    sql = _knn_sql(spec.table, spec.column_type)
    pools: fs.Pool = {}
    latencies: list[float] = []

    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute("SET enable_seqscan = off")
        cur.execute("SELECT set_config('hnsw.ef_search', %s, false)", (str(ef_search),))

        probe = db.format_vector(embed_fn(gt.query_list[0].text))
        cur.execute("EXPLAIN " + sql, (probe, project_id, probe, depth))
        plan_text = " ".join(r[0] for r in cur.fetchall())
        observed = "index" if "Index Scan" in plan_text else "seqscan"

        for q in gt.query_list:
            vec = db.format_vector(embed_fn(q.text))
            t0 = time.perf_counter()
            cur.execute(sql, (vec, project_id, vec, depth))
            rows = cur.fetchall()
            latencies.append((time.perf_counter() - t0) * 1000.0)
            pools[q.query_id] = fs.pool_documents(
                [(gt.id_map.get(r[0]), r[1], float(r[2])) for r in rows]
            )

    latencies.sort()
    return {
        "pools": pools,
        "plan_observed": observed,
        "latency_ms": {
            "p50": round(statistics.median(latencies), 3),
            "p90": round(latencies[int(len(latencies) * 0.9)], 3),
            "mean": round(statistics.mean(latencies), 3),
            "n": len(latencies),
        },
    }


def storage_stats(table: str, index: str) -> dict:
    """Index and heap size, with TOAST counted.

    A 1536-dim ``vector`` row is 6 KB and lives in TOAST, so ``pg_relation_size``
    on the heap reads ~2 MB and says nothing. ``pg_total_relation_size`` is the
    number that answers "what does this arm cost on disk".
    """
    from scripts.eval import db  # noqa: PLC0415

    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT pg_relation_size(%s), pg_total_relation_size(%s)", (index, f"public.{table}")
        )
        idx_bytes, total_bytes = cur.fetchone()
    return {
        "index_bytes": int(idx_bytes),
        "index_mb": round(int(idx_bytes) / 1024 / 1024, 2),
        "table_total_bytes": int(total_bytes),
        "table_total_mb": round(int(total_bytes) / 1024 / 1024, 2),
    }


# ---------------------------------------------------------------------------
# The separation diagnostic
# ---------------------------------------------------------------------------


#: The chunk depth ``FIRSTSTAGE.md``'s separation figure was computed over.
#: Its populations -- 7,346 relevant and 55,562 irrelevant document scores over
#: 338 queries -- average 186 documents per query, which is the x100 exact arm's
#: pool, not the whole 344-document corpus. Reproducing that population is the
#: only way this session's control can be checked against the published 0.0593.
PUBLISHED_SEPARATION_DEPTH = 1000


def _stats(values) -> dict:
    return {
        "n": len(values),
        "mean": round(float(statistics.mean(values)), 4) if len(values) else None,
        "sd": round(float(statistics.pstdev(values)), 4) if len(values) > 1 else None,
    }


def _gap(rel: dict, irr: dict) -> dict:
    gap = None
    if rel["mean"] is not None and irr["mean"] is not None:
        gap = rel["mean"] - irr["mean"]
    pooled_sd = None
    if rel["sd"] is not None and irr["sd"] is not None:
        pooled_sd = round(((rel["sd"] ** 2 + irr["sd"] ** 2) / 2) ** 0.5, 4)
    return {
        "relevant": rel,
        "irrelevant": irr,
        "gap": round(gap, 4) if gap is not None else None,
        "pooled_sd": pooled_sd,
        # The number the finding is stated in: a gap under one sigma is a weak
        # encoder, and a gap that does not move is an encoder that did not change.
        "gap_in_sd": round(gap / pooled_sd, 3) if gap is not None and pooled_sd else None,
    }


def separation(gt, doc_vectors, doc_index: dict[str, int], embed_fn) -> dict:
    """Mean max-pooled cosine of a query against its relevant docs vs the rest.

    This is the mechanism, not a summary statistic. ``FIRSTSTAGE.md`` measured
    0.4415 relevant against 0.3821 irrelevant -- a gap of 0.0593 against standard
    deviations near 0.07, which is **under one sigma** and is the whole reason
    this arm exists. If the wider embedding moves recall without moving this, the
    recall move is not an embedding effect and should be distrusted.

    Two populations are returned, because a separation figure is meaningless
    without saying which documents were in the denominator:

    ``whole_corpus``
        every one of the 344 documents scored against every query, exactly, in
        memory. No index, no depth limit -- a property of the vectors alone.
    ``pool_depth_1000``
        only the documents surfacing in a 1,000-chunk pool, which is the
        population ``FIRSTSTAGE.md`` published. Truncating the pool discards the
        low-scoring irrelevant tail, which raises the irrelevant mean and
        *shrinks* the gap -- so the two populations give different numbers for
        the same vectors and must never be compared across.
    """
    import numpy as np  # noqa: PLC0415

    mat = doc_vectors  # a _MaxPooled: `mat @ v` yields one max-pooled score per document
    order = np.array(sorted(doc_index, key=lambda d: doc_index[d]))

    whole = {"rel": [], "irr": []}
    pooled = {"rel": [], "irr": []}
    for q in gt.query_list:
        rels = gt.qrels.get(q.query_id)
        if not rels:
            continue
        v = np.asarray(embed_fn(q.text), dtype=np.float32)
        v /= np.linalg.norm(v)
        sims = mat @ v
        is_rel = np.isin(order, list(rels))
        whole["rel"].extend(sims[is_rel].tolist())
        whole["irr"].extend(sims[~is_rel].tolist())

        in_pool = mat.documents_in_top_chunks(v, PUBLISHED_SEPARATION_DEPTH)
        pooled["rel"].extend(sims[is_rel & in_pool].tolist())
        pooled["irr"].extend(sims[~is_rel & in_pool].tolist())

    return {
        "whole_corpus": _gap(_stats(whole["rel"]), _stats(whole["irr"])),
        f"pool_depth_{PUBLISHED_SEPARATION_DEPTH}": _gap(
            _stats(pooled["rel"]), _stats(pooled["irr"])
        ),
    }


def doc_matrix_1536(gt, project_id: str = EVAL_PROJECT_ID):
    """Max-pool-ready L2-normalised document matrix from the shipped index.

    READ ONLY. This is the control's side of the separation diagnostic and it is
    the only place this module reads ``document_chunks``' vectors at all.
    """
    import numpy as np  # noqa: PLC0415

    from scripts.eval import db  # noqa: PLC0415

    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id::text, c.document_id::text, c.embedding::text
            FROM public.document_chunks c
            JOIN public.documents d ON d.id = c.document_id
            WHERE d.project_id = %s::uuid
            ORDER BY c.id
            """,
            (project_id,),
        )
        rows = cur.fetchall()
    vecs = np.array([np.fromstring(r[2][1:-1], sep=",") for r in rows], dtype=np.float32)
    return _pool_chunks_to_docs(gt, [r[1] for r in rows], vecs)


def doc_matrix_3072(gt, project_id: str = EVAL_PROJECT_ID):
    """The same, from the 3072 cache. Never reads the arm table."""
    import numpy as np  # noqa: PLC0415

    from scripts.eval import db  # noqa: PLC0415

    with np.load(CHUNK_CACHE) as z:
        ids = [str(i) for i in z["ids"]]
        vecs = z["vectors"]
    with db.get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT c.id::text, c.document_id::text
            FROM public.document_chunks c
            JOIN public.documents d ON d.id = c.document_id
            WHERE d.project_id = %s::uuid
            """,
            (project_id,),
        )
        parent = dict(cur.fetchall())
    return _pool_chunks_to_docs(gt, [parent[i] for i in ids], vecs)


def _pool_chunks_to_docs(gt, db_doc_ids: list[str], vecs):
    """Chunk vectors -> one row per document, holding the chunk-level max.

    The relevance unit is document and a document's score is its best chunk's, so
    the diagnostic must max-pool the same way the retriever does. Returned as
    (per-chunk normalised matrix, document index) and pooled by the caller --
    max over cosine, not cosine of the mean, which would be a different quantity.
    """
    import numpy as np  # noqa: PLC0415

    labels = [gt.id_map.get(d) for d in db_doc_ids]
    keep = np.array([lab is not None for lab in labels])
    vecs = np.asarray(vecs, dtype=np.float32)[keep]
    vecs = vecs / np.linalg.norm(vecs, axis=1, keepdims=True)
    kept = [lab for lab in labels if lab is not None]
    docs = sorted(set(kept))
    index = {d: i for i, d in enumerate(docs)}
    cols = np.array([index[d] for d in kept])
    return _MaxPooled(vecs, cols, len(docs)), index


class _MaxPooled:
    """A chunk matrix that behaves like a document matrix under ``@``."""

    def __init__(self, vecs, cols, n_docs: int) -> None:
        self.vecs = vecs
        self.cols = cols
        self.n_docs = n_docs

    def __matmul__(self, v):
        import numpy as np  # noqa: PLC0415

        sims = self.vecs @ v
        out = np.full(self.n_docs, -2.0, dtype=np.float32)
        np.maximum.at(out, self.cols, sims)
        return out

    def documents_in_top_chunks(self, v, depth: int):
        """Boolean mask over documents: which appear in the top ``depth`` CHUNKS.

        Depth counts chunks and the relevance unit is documents, which is exactly
        the mismatch FIRSTSTAGE §1.2 measured -- so this cannot be replaced by
        "the top ``depth`` documents" without changing the population.
        """
        import numpy as np  # noqa: PLC0415

        sims = self.vecs @ v
        top = np.argpartition(-sims, min(depth, len(sims) - 1))[:depth]
        mask = np.zeros(self.n_docs, dtype=bool)
        mask[self.cols[top]] = True
        return mask


# ---------------------------------------------------------------------------
# Scoring one arm end to end
# ---------------------------------------------------------------------------


def exact_pools(gt, doc_vectors, doc_index: dict[str, int], embed_fn) -> fs.Pool:
    """Score every query against every document exactly, in memory.

    The ANN arm and the exact arm answer different questions and this module
    reports both, because at this corpus size the HNSW approximation is the same
    size as the effect being measured. ``FIRSTSTAGE.md`` §2.1 put a number on it:
    the shipped ef-80 index reads 0.2199 where the identical 50-chunk pool scored
    exactly reads 0.2210, so **0.0010-0.0030 of any recall difference between two
    indexes can be graph luck rather than vectors**. Two HNSW graphs built over
    different vectors are not the same graph, so an ANN-only comparison cannot
    separate "the wider embedding ranks better" from "this graph got luckier".
    Exact scoring removes the graph from the comparison entirely.
    """
    import numpy as np  # noqa: PLC0415

    order = np.array(sorted(doc_index, key=lambda d: doc_index[d]))
    pools: fs.Pool = {}
    for q in gt.query_list:
        if q.query_id not in gt.qrels:
            continue
        v = np.asarray(embed_fn(q.text), dtype=np.float32)
        v /= np.linalg.norm(v)
        sims = doc_vectors @ v
        pools[q.query_id] = {
            order[i]: float(sims[i]) for i in np.nonzero(sims > -2.0)[0]
        }
    return pools


def score_arm(gt, pools: fs.Pool, k: int = K) -> dict:
    """ranx metrics + recomputed ceilings for exactly this query set.

    Ceilings are recomputed here rather than carried: a ceiling that travels
    across query subsets silently rescales every arm it touches.
    """
    qrels_dict = {q: {d: 1 for d in rels} for q, rels in gt.qrels.items()}
    run = {q: dict(pools.get(q, {})) for q in qrels_dict}
    measured = metrics_mod.compute_metrics(qrels_dict, run, ARM_METRICS)
    ceilings = metrics_mod.recall_ceilings(qrels_dict, CEILING_KS)
    return {
        "n": len(qrels_dict),
        "n_judgments": sum(len(v) for v in qrels_dict.values()),
        "metrics": {m: round(v, 4) for m, v in measured.items()},
        "ceilings": {m: round(v, 4) for m, v in ceilings.items()},
        "percent_of_attainable": {
            m: (round(v / ceilings[m], 4) if ceilings.get(m) else None)
            for m, v in measured.items()
            if m in ceilings
        },
        "pool_oracle@%d" % k: round(fs.pool_oracle(pools, gt.qrels, k), 4),
        "mean_pool_documents": round(
            statistics.mean([len(pools.get(q, {})) for q in gt.qrels]), 2
        ),
    }


def arm_config(spec: ArmSpec, gt, corpus: dict, depth: int) -> dict:
    """Everything that makes two arms incomparable, and nothing that does not.

    ``embed_dimensions`` and ``vector_column_type`` are in here by requirement:
    two arms over the same chunk ids with the same labels differ in nothing else,
    so without them the sink would key both to one hash and the second would look
    like run-to-run variance on the first.
    """
    return {
        "harness_version": HARNESS_VERSION,
        "arm": spec.name,
        "relevance_unit": metrics_mod.UNIT_DOCUMENT,
        "retriever": "dense",
        "embed_model": EMBED_MODEL,
        "embed_dimensions": spec.dimensions,
        "vector_column_type": spec.column_type,
        "vector_table": spec.table,
        "index_type": "hnsw",
        "index_opclass": spec.opclass,
        "hnsw_ef_search": EF_SEARCH,
        "k": K,
        "chunk_oversample": CHUNK_OVERSAMPLE,
        "depth": depth,
        "metrics": sorted(ARM_METRICS),
        "labels_fingerprint": fs.SNAPSHOT,
        "queries_fingerprint": fs.QUERIES_FINGERPRINT,
        "index_state": corpus["index_state"],
        "chunk_id_digest": corpus["index_digest"],
    }


def append_result(record: dict, path: Path = RESULTS_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:  # "a" -- append only, never rewrite
        fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    return path


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def run_arms(
    allow_spend: bool = False,
    project_id: str = EVAL_PROJECT_ID,
    with_separation: bool = True,
    write: bool = True,
) -> dict:
    """Measure control and 3072 arm in one session, over one corpus, and record both."""
    from scripts.eval.retrieval.adapters import production_embed_fn  # noqa: PLC0415

    gt = fs.load_ground_truth()
    before = fs.index_identity(project_id)
    fs.assert_corpus(before)
    print(
        f"[embed_arms] labels {fs.SNAPSHOT} · document_chunks "
        f"{before['index_state']}/{before['index_digest']} · n={gt.n}"
    )

    depth = K * CHUNK_OVERSAMPLE
    embed_1536 = production_embed_fn(EMBED_MODEL)
    q3072 = embed_queries_3072(gt.query_list, allow_spend=allow_spend)

    def embed_3072(text: str) -> list[float]:
        key = _key_of(text)
        if key not in q3072:
            raise ArmError("a query is missing from the 3072 cache; run --mode embed")
        return q3072[key]

    specs = [
        ArmSpec("control_1536_vector", "document_chunks", "vector", SHIPPED_DIM,
                "vector_cosine_ops", None),
        ArmSpec("native_3072_halfvec", ARM_3072_TABLE, "halfvec", NATIVE_DIM,
                "halfvec_cosine_ops", q3072),
    ]
    embedders = {specs[0].name: embed_1536, specs[1].name: embed_3072}
    index_names = {
        "document_chunks": "public.idx_document_chunks_embedding",
        ARM_3072_TABLE: f"public.idx_{ARM_3072_TABLE}_embedding",
    }

    arms = []
    for spec in specs:
        out = retrieve_arm(gt, spec, embedders[spec.name], depth, EF_SEARCH, project_id)
        rec = {
            **score_arm(gt, out["pools"], K),
            "plan_observed": out["plan_observed"],
            "latency_ms": out["latency_ms"],
            "storage": storage_stats(spec.table, index_names[spec.table]),
        }
        cfg = arm_config(spec, gt, before, depth)
        rec["config"] = cfg
        rec["config_hash"] = config_hash(cfg)
        rec["arm"] = spec.name
        arms.append(rec)
        print(
            f"  {spec.name:<22} plan={out['plan_observed']:<8} "
            f"R@10={rec['metrics']['recall@10']:.4f} "
            f"ceiling={rec['ceilings']['recall@10']:.4f} n={rec['n']} "
            f"p50={out['latency_ms']['p50']:.2f}ms idx={rec['storage']['index_mb']}MB"
        )

    if arms[0]["config_hash"] == arms[1]["config_hash"]:
        raise ArmError(
            "the two arms hashed to the same config_hash. They differ in embedding "
            "width and column type, so a collision means the hash is not keyed on "
            "the thing that changed and the sink would read them as one arm."
        )

    if with_separation:
        for spec, rec in zip(specs, arms):
            mat, index = (
                doc_matrix_1536(gt, project_id)
                if spec.dimensions == SHIPPED_DIM
                else doc_matrix_3072(gt, project_id)
            )
            rec["separation"] = separation(gt, mat, index, embedders[spec.name])
            rec["exact_whole_corpus"] = score_arm(
                gt, exact_pools(gt, mat, index, embedders[spec.name]), K
            )
            print(
                f"  {spec.name:<22} EXACT whole-corpus "
                f"R@10={rec['exact_whole_corpus']['metrics']['recall@10']:.4f} "
                f"(no HNSW graph in the comparison)"
            )
            for pop, s in rec["separation"].items():
                print(
                    f"  {spec.name:<22} separation[{pop}] rel={s['relevant']['mean']} "
                    f"irr={s['irrelevant']['mean']} gap={s['gap']} "
                    f"({s['gap_in_sd']} sd, n={s['relevant']['n']}/{s['irrelevant']['n']})"
                )

    after = fs.index_identity(project_id)
    if before["index_digest"] != after["index_digest"]:
        raise fs.SnapshotMismatch(
            "document_chunks changed while this run was in flight: "
            f"{before['index_digest']} -> {after['index_digest']}. Another agent "
            "mutated the shared corpus; the control is void. Re-run."
        )

    control, arm = arms
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "harness_version": HARNESS_VERSION,
        "document_chunks_digest_before": before["index_digest"],
        "document_chunks_digest_after": after["index_digest"],
        "arms": arms,
        "delta": {
            m: round(arm["metrics"][m] - control["metrics"][m], 4) for m in ARM_METRICS
        },
        # The delta that has no HNSW graph in it. Reported alongside rather than
        # instead of the ANN delta: the ANN number is what production would ship
        # and the exact number is what the embedding actually did.
        "delta_exact": (
            {
                m: round(
                    arm["exact_whole_corpus"]["metrics"][m]
                    - control["exact_whole_corpus"]["metrics"][m],
                    4,
                )
                for m in ARM_METRICS
            }
            if "exact_whole_corpus" in arm and "exact_whole_corpus" in control
            else None
        ),
        "delta_separation": (
            {
                pop: round(arm["separation"][pop]["gap"] - control["separation"][pop]["gap"], 4)
                for pop in arm["separation"]
            }
            if "separation" in arm and "separation" in control
            else None
        ),
        # Stated explicitly so no reader has to infer it: the delta above is
        # against the control measured in THIS session, never against the
        # historical 0.2195 / 0.2200 lineage, which describes a different corpus.
        "delta_basis": "same-session control, same chunk ids, same labels",
        "n": control["n"],
    }
    try:
        _load_backend()
        from app.core.llm_budget import total_spend_usd, unpriced_calls  # noqa: PLC0415

        record["spend_usd"] = round(total_spend_usd(), 5)
        record["unpriced_calls"] = unpriced_calls()
    except Exception as exc:  # noqa: BLE001
        record["spend_usd"] = None
        record["spend_error"] = f"{type(exc).__name__}: {exc}"

    if write:
        path = append_result(record)
        print(f"[embed_arms] APPENDED -> {path}")
    return record


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", default="run", choices=["cost", "embed", "load", "run"])
    ap.add_argument("--allow-spend", action="store_true")
    ap.add_argument("--no-separation", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="measure but do not append")
    ap.add_argument("--project-id", default=EVAL_PROJECT_ID)
    args = ap.parse_args(argv)

    os.environ.setdefault("NOESIS_LLM_KILL_SWITCH", "0" if args.allow_spend else "1")

    if args.mode == "cost":
        print(json.dumps(estimate_cost(args.project_id), indent=2))
        return 0
    if args.mode == "embed":
        gt = fs.load_ground_truth()
        print(json.dumps(embed_corpus_3072(args.project_id, args.allow_spend), indent=2))
        embed_queries_3072(gt.query_list, args.allow_spend)
        print(f"queries cached at {NATIVE_DIM}d: {QUERY_CACHE}")
        return 0
    if args.mode == "load":
        print(json.dumps(load_arm_table(args.project_id), indent=2))
        return 0

    record = run_arms(
        allow_spend=args.allow_spend,
        project_id=args.project_id,
        with_separation=not args.no_separation,
        write=not args.dry_run,
    )
    print(json.dumps({k: v for k, v in record.items() if k != "arms"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
