"""First-stage recall: why 6,011 of 6,944 misses were never in the candidate pool.

``RERANK.md`` established that 86.5% of all misses are documents the first stage
never returned, and concluded "the headroom is first-stage recall, not ranking".
This module takes that conclusion apart and measures each of its parts.

The short version of what it finds:

* Ingestion is **not** the cause. Exactly **1** label document has zero chunks in
  the index, accounting for **20 of 6,011** misses. Another 12 documents are
  indexed but never surface for any of the 338 queries (**71** misses). The
  remaining **5,920 (98.5%)** are documents the retriever demonstrably *does*
  return -- for some other query.
* The pool is smaller than the ground truth. ``k * chunk_oversample`` is a count
  of **chunks**, and the 50 chunks max-pool to a median of **20 distinct
  documents** against a median of **25 relevant documents per query**. A perfect
  reranker over that pool tops out at recall@10 = **0.2982**, not the label
  ceiling of 0.5199.
* Depth does not fix it. Holding the query plan fixed and sweeping depth from 120
  to 1,000 chunks -- 42 to 186 distinct documents in the pool -- moves recall@10
  by **exactly 0.0000**. The first stage's document ordering is fully determined
  by the top ~50 chunks; everything deeper scores below the incumbent top 10.

Everything here is on label snapshot ``230c6ea9d9b7e8fd`` (n = 338 scorable
queries, 8,554 relevant judgments) and corpus ``5948c/344d`` /
``8d3edbe3f3b28cdb``. Both are asserted, not assumed: a run on another snapshot
or another corpus raises rather than reporting.

This module **never writes to the database** and never appends to the
append-only results sink. It is a measurement driver.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[3])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.eval.retrieval import contentless as contentless_mod  # noqa: E402
from scripts.eval.retrieval import labels as labels_mod  # noqa: E402
from scripts.eval.retrieval import queries as queries_mod  # noqa: E402
from scripts.eval.retrieval.adapters import (  # noqa: E402
    EVAL_PROJECT_ID,
    db_document_id,
    production_embed_fn,
)

EVAL_DIR = Path(__file__).resolve().parent.parent
SUBCHUNK_CACHE_DIR = EVAL_DIR / "cache" / "retrieval_subchunk_embeddings"

#: The only label snapshot these numbers describe. Three snapshots exist and they
#: are not comparable at all, so this is asserted rather than documented.
SNAPSHOT = "230c6ea9d9b7e8fd"
QUERIES_FINGERPRINT = "1f6c584e8fd6c055"

#: The only corpus these numbers describe. A row count is not a corpus identity
#: -- a restore returned this corpus to 5,948 chunks while replacing 324 chunk
#: ids, and every count-based check passed throughout. See CONTENTLESS.md §3g.
INDEX_DIGEST = "8d3edbe3f3b28cdb"
INDEX_STATE = "5948c/344d"

#: Published control on this corpus (NOT 0.2195, which belongs to the corpus that
#: existed before the re-ingest). `plan: index`, hnsw.ef_search = 80, 50 chunks.
CONTROL_R10 = 0.2200
#: Exact (sequential-scan) k-NN over the whole corpus at any depth >= 120.
EXACT_R10 = 0.2227

#: The production RPC pins this inside its own body (`SET LOCAL hnsw.ef_search = 80`),
#: so a caller-side `SET` does not reach it. Recorded because it bounds the ANN
#: path: the HNSW graph is asked to yield at most 80 candidates per scan.
RPC_EF_SEARCH = 80

#: text-embedding-3-large, $0.13 per 1M input tokens (app.core.llm_budget).
EMBED_MODEL = "text-embedding-3-large"
EMBED_USD_PER_MTOK = 0.13


class SnapshotMismatch(RuntimeError):
    """The labels, queries or corpus are not the ones these numbers describe."""


# ---------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GroundTruth:
    label_set: object
    query_list: list
    qrels: dict[str, set[str]]
    #: {database document id -> label doc id}
    id_map: dict[str, str]
    topic_of: dict[str, str]

    @property
    def n(self) -> int:
        return len(self.qrels)

    @property
    def n_judgments(self) -> int:
        return sum(len(v) for v in self.qrels.values())


def load_ground_truth(strict: bool = True) -> GroundTruth:
    """Labels + queries, with the snapshot asserted."""
    label_set, _ = labels_mod.load_or_build(Path(labels_mod.CORPORA_DIR), use_cache=True)
    query_list = queries_mod.build_query_set(Path(queries_mod.EXPORTS_DIR))
    if strict:
        assert_snapshot(label_set, query_list)
    qrels = {
        qid: set(rels)
        for qid, rels in label_set.qrels(queries_mod.queries_by_topic(query_list)).items()
        if rels
    }
    return GroundTruth(
        label_set=label_set,
        query_list=query_list,
        qrels=qrels,
        id_map={
            db_document_id(d.content_sha256): d.doc_id
            for d in label_set.docs.values()
            if d.content_sha256
        },
        topic_of={q.query_id: q.topic for q in query_list},
    )


def assert_snapshot(label_set, query_list) -> None:
    got_labels = label_set.fingerprint()
    got_queries = queries_mod.fingerprint(query_list)
    if got_labels != SNAPSHOT or got_queries != QUERIES_FINGERPRINT:
        raise SnapshotMismatch(
            f"labels/queries are {got_labels}/{got_queries}, this module describes "
            f"{SNAPSHOT}/{QUERIES_FINGERPRINT}. Ceilings move with the labels, so "
            "every number in FIRSTSTAGE.md would be scaled against the wrong "
            "yardstick. Re-measure rather than re-label."
        )


def index_identity(project_id: str = EVAL_PROJECT_ID) -> dict:
    """Chunk count, document count and a digest over chunk ids.

    The digest, not the count, is the identity: see the module docstring.
    """
    from scripts.eval import db  # noqa: PLC0415 -- no DB needed to import this module

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*), count(DISTINCT c.document_id),
                       md5(string_agg(c.id::text, ',' ORDER BY c.id))
                FROM public.document_chunks c
                JOIN public.documents d ON d.id = c.document_id
                WHERE d.project_id = %s::uuid
                """,
                (project_id,),
            )
            n_chunks, n_docs, digest = cur.fetchone()
    return {
        "index_state": f"{n_chunks}c/{n_docs}d",
        "index_n_chunks": int(n_chunks),
        "index_n_documents": int(n_docs),
        "index_digest": hashlib.sha256((digest or "").encode()).hexdigest()[:16],
    }


def assert_corpus(identity: dict) -> None:
    if identity.get("index_digest") != INDEX_DIGEST:
        raise SnapshotMismatch(
            f"corpus is {identity.get('index_state')}/{identity.get('index_digest')}, "
            f"this module describes {INDEX_STATE}/{INDEX_DIGEST}. Absolute recalls "
            "are a property of one corpus and of nothing else -- the same arm reads "
            "0.2195 on the pre-restore corpus and 0.2186 on an experimental one."
        )


# ---------------------------------------------------------------------------
# Pools
# ---------------------------------------------------------------------------

#: One document's best chunk score. The relevance unit is `document`, and a
#: document's score is its best chunk's -- max-pooling, matching metrics.pool_to_unit.
Pool = dict[str, dict[str, float]]  # query_id -> {doc_id: best score}


def pool_documents(rows: list[tuple[str | None, str, float]]) -> dict[str, float]:
    best: dict[str, float] = {}
    for doc_id, _chunk_id, score in rows:
        if doc_id is None:
            continue
        if doc_id not in best or score > best[doc_id]:
            best[doc_id] = score
    return best


def rank_documents(best: dict[str, float]) -> list[str]:
    """Descending score, ties broken by doc id -- the same order metrics.truncate uses."""
    return [d for d, _ in sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))]


_KNN_SQL = """
SELECT c.document_id::text, c.id::text, 1 - (c.embedding <=> %s::vector)
FROM public.document_chunks c
WHERE c.project_id = %s::uuid
ORDER BY c.embedding <=> %s::vector
LIMIT %s
"""


def retrieve_pools(
    gt: GroundTruth,
    depth: int,
    plan: str = "index",
    ef_search: int | None = None,
    project_id: str = EVAL_PROJECT_ID,
    embed_fn=None,
) -> tuple[Pool, str]:
    """Retrieve ``depth`` chunks per query with the query plan FORCED.

    The existing depth record tangles pool depth with the planner flipping to a
    sequential scan somewhere above ~103 candidates, so a depth comparison drawn
    from it is partly attributing a planner decision to a retrieval idea. This
    forces the plan with ``enable_seqscan`` / ``enable_indexscan`` and returns the
    plan Postgres actually chose, so the two are separated by construction rather
    than by assertion.

    ``ef_search`` is only meaningful for ``plan="index"``. Note it cannot be used
    to sweep ``match_document_chunks``: that RPC pins ``hnsw.ef_search = 80``
    inside its own body, which is why this issues the k-NN query directly.
    """
    from scripts.eval import db  # noqa: PLC0415

    if plan not in ("index", "seqscan"):
        raise ValueError(f"plan must be 'index' or 'seqscan', got {plan!r}")
    embed_fn = embed_fn or production_embed_fn()

    pools: Pool = {}
    with db.get_connection() as conn:
        with conn.cursor() as cur:
            if plan == "index":
                cur.execute("SET enable_seqscan = off")
                cur.execute(
                    "SELECT set_config('hnsw.ef_search', %s, false)",
                    (str(ef_search or max(RPC_EF_SEARCH, depth)),),
                )
            else:
                cur.execute("SET enable_indexscan = off")
                cur.execute("SET enable_bitmapscan = off")

            probe = db.format_vector(embed_fn(gt.query_list[0].text))
            cur.execute("EXPLAIN " + _KNN_SQL, (probe, project_id, probe, depth))
            plan_text = " ".join(r[0] for r in cur.fetchall())
            observed = "index" if "Index Scan" in plan_text else "seqscan"

            for q in gt.query_list:
                vec = db.format_vector(embed_fn(q.text))
                cur.execute(_KNN_SQL, (vec, project_id, vec, depth))
                pools[q.query_id] = pool_documents(
                    [(gt.id_map.get(r[0]), r[1], float(r[2])) for r in cur.fetchall()]
                )
    return pools, observed


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def recall_ceiling(qrels: dict[str, set[str]], k: int = 10) -> float:
    """``mean(min(k, |rel_q|) / |rel_q|)`` -- recomputed for whatever subset is passed.

    A ceiling never travels across query subsets: carrying one silently rescales
    every arm it touches.
    """
    if not qrels:
        return 0.0
    return sum(min(k, len(r)) / len(r) for r in qrels.values()) / len(qrels)


def pool_oracle(pools: Pool, qrels: dict[str, set[str]], k: int = 10) -> float:
    """The best recall@k any reranker could reach over these pools.

    Reranking is a permutation of a fixed pool, so ``min(k, |pool ∩ rel|) / |rel|``
    is a hard bound on every reranked arm -- and it is the number that says
    whether the reranking lane or the retrieval lane holds the headroom.
    """
    if not qrels:
        return 0.0
    return sum(
        min(k, len(set(pools.get(q, {})) & rels)) / len(rels) for q, rels in qrels.items()
    ) / len(qrels)


def recall_at_k(pools: Pool, qrels: dict[str, set[str]], k: int = 10) -> float:
    if not qrels:
        return 0.0
    total = 0.0
    for q, rels in qrels.items():
        top = set(rank_documents(pools.get(q, {}))[:k])
        total += len(top & rels) / len(rels)
    return total / len(qrels)


def arm_summary(pools: Pool, qrels: dict[str, set[str]], k: int = 10) -> dict:
    sizes = [len(pools.get(q, {})) for q in qrels]
    return {
        "n": len(qrels),
        "recall@%d" % k: round(recall_at_k(pools, qrels, k), 4),
        "ceiling": round(recall_ceiling(qrels, k), 4),
        "pool_oracle@%d" % k: round(pool_oracle(pools, qrels, k), 4),
        "mean_pool_documents": round(statistics.mean(sizes), 2) if sizes else 0.0,
        "median_pool_documents": statistics.median(sizes) if sizes else 0,
    }


# ---------------------------------------------------------------------------
# Step 1: characterise the misses that were never in the pool
# ---------------------------------------------------------------------------


@dataclass
class Characterisation:
    n_queries: int
    n_judgments: int
    hits: int
    retrieval_failures: int
    ranking_failures: int
    #: never ingested -- the document has zero chunks in the index
    never_ingested: int
    never_ingested_docs: list[str]
    #: indexed, but never surfaces for ANY of the 338 queries at this depth
    never_retrieved: int
    never_retrieved_docs: list[str]
    #: Indexed documents that surface for no query at all. A superset of
    #: ``never_retrieved_docs``: most of them are never anybody's reference
    #: either, so they cost nothing. Reported so "3 documents" is not mistaken
    #: for "the index has 3 dark corners".
    dark_documents: int
    #: retrieved for some other query, just not the one that needed it
    retrieved_elsewhere: int
    retrieved_elsewhere_docs: int
    by_topic: dict[str, dict] = field(default_factory=dict)
    contentless: dict[str, dict] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["never_ingested_docs"] = sorted(self.never_ingested_docs)
        d["never_retrieved_docs"] = sorted(self.never_retrieved_docs)
        return d


def indexed_document_ids(gt: GroundTruth, project_id: str = EVAL_PROJECT_ID) -> set[str]:
    """Label doc ids that have at least one chunk in the index."""
    from scripts.eval import db  # noqa: PLC0415

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT c.document_id::text
                FROM public.document_chunks c
                JOIN public.documents d ON d.id = c.document_id
                WHERE d.project_id = %s::uuid
                """,
                (project_id,),
            )
            db_ids = [r[0] for r in cur.fetchall()]
    return {gt.id_map[i] for i in db_ids if i in gt.id_map}


def characterise(
    gt: GroundTruth,
    pools: Pool,
    indexed: set[str],
    k: int = 10,
) -> Characterisation:
    """Split every ``retrieval_failure`` into its three possible causes.

    "Never in the pool" is one bucket in ``metrics.attribute_failures`` and three
    different problems: a document that was never ingested is an ingestion bug, a
    document that never surfaces for anything is an embedding or extraction
    problem, and a document that surfaces for other queries is a *ranking*
    problem that the depth limit disguised as a retrieval one. They call for
    completely different fixes, so reporting them as one number is what made
    "the headroom is first-stage recall" look like a single lever.
    """
    all_label_docs = set(gt.label_set.docs)
    never_ingested_docs = all_label_docs - indexed
    ever_pooled: set[str] = set()
    for best in pools.values():
        ever_pooled |= set(best)
    never_retrieved_docs = indexed - ever_pooled

    hits = ranking = 0
    a = b = c = 0
    a_docs: set[str] = set()
    b_docs: set[str] = set()
    c_docs: set[str] = set()
    per_topic: dict[str, Counter] = {}

    for qid, rels in gt.qrels.items():
        best = pools.get(qid, {})
        top = set(rank_documents(best)[:k])
        topic = gt.topic_of.get(qid, "?")
        bucket = per_topic.setdefault(topic, Counter())
        for doc_id in rels:
            bucket["judgments"] += 1
            if doc_id in top:
                hits += 1
                bucket["hits"] += 1
            elif doc_id in best:
                ranking += 1
                bucket["ranking_failure"] += 1
            elif doc_id in never_ingested_docs:
                a += 1
                a_docs.add(doc_id)
                bucket["never_ingested"] += 1
            elif doc_id in never_retrieved_docs:
                b += 1
                b_docs.add(doc_id)
                bucket["never_retrieved"] += 1
            else:
                c += 1
                c_docs.add(doc_id)
                bucket["retrieved_elsewhere"] += 1

    by_topic = {}
    for topic, bucket in sorted(per_topic.items()):
        j = bucket["judgments"]
        rf = bucket["never_ingested"] + bucket["never_retrieved"] + bucket["retrieved_elsewhere"]
        by_topic[topic] = {
            "judgments": j,
            "retrieval_failure": rf,
            "retrieval_failure_rate": round(rf / j, 3) if j else 0.0,
            "ranking_failure": bucket["ranking_failure"],
            "hits": bucket["hits"],
        }

    return Characterisation(
        n_queries=gt.n,
        n_judgments=gt.n_judgments,
        hits=hits,
        retrieval_failures=a + b + c,
        ranking_failures=ranking,
        never_ingested=a,
        never_ingested_docs=sorted(a_docs),
        never_retrieved=b,
        never_retrieved_docs=sorted(b_docs),
        retrieved_elsewhere=c,
        retrieved_elsewhere_docs=len(c_docs),
        dark_documents=len(never_retrieved_docs),
        by_topic=by_topic,
        contentless=contentless_breakdown(gt, pools, k),
    )


def contentless_breakdown(gt: GroundTruth, pools: Pool, k: int = 10) -> dict:
    """The same failure split over the contentless / servable halves.

    A contentless query cannot surface anything specific, so if that population
    drove the 6,011 it would show up here as a far higher retrieval-failure rate.
    Reporting it separately is what stops "contentless claims" and "pool too
    small" being counted as two causes of the same misses.
    """
    servable, contentless = contentless_mod.partition(gt.query_list)
    halves = {
        "servable": {q.query_id for q in servable},
        "contentless": {q.query_id for q in contentless},
    }
    out = {}
    for name, ids in halves.items():
        sub = {q: r for q, r in gt.qrels.items() if q in ids}
        if not sub:
            continue
        rf = 0
        judgments = 0
        for qid, rels in sub.items():
            best = pools.get(qid, {})
            top = set(rank_documents(best)[:k])
            for doc_id in rels:
                judgments += 1
                if doc_id not in top and doc_id not in best:
                    rf += 1
        summary = arm_summary(pools, sub, k)
        summary.update(
            judgments=judgments,
            retrieval_failure=rf,
            retrieval_failure_rate=round(rf / judgments, 3) if judgments else 0.0,
        )
        summary["fraction_of_pool_oracle"] = (
            round(summary[f"recall@{k}"] / summary[f"pool_oracle@{k}"], 3)
            if summary[f"pool_oracle@{k}"]
            else None
        )
        out[name] = summary
    return out


# ---------------------------------------------------------------------------
# Step 2 H2: chunk granularity, measured without touching the index
# ---------------------------------------------------------------------------


def split_text(text: str, n_parts: int) -> list[str]:
    """Split into ``n_parts`` contiguous pieces on whitespace boundaries.

    Contiguous and non-overlapping so the arm costs the same number of input
    tokens as the corpus already contains: granularity is the only variable, and
    an overlap would make the comparison partly about seeing more text.
    """
    if n_parts <= 1:
        return [text]
    words = text.split()
    if len(words) < n_parts:
        return [text]
    size = len(words) / n_parts
    parts = []
    for i in range(n_parts):
        lo = int(round(i * size))
        hi = int(round((i + 1) * size)) if i < n_parts - 1 else len(words)
        piece = " ".join(words[lo:hi]).strip()
        if piece:
            parts.append(piece)
    return parts or [text]


def _cache_path(n_parts: int) -> Path:
    return SUBCHUNK_CACHE_DIR / f"{EMBED_MODEL}.split{n_parts}.json"


def estimate_subchunk_cost(project_id: str = EVAL_PROJECT_ID) -> dict:
    """Input tokens and dollars for re-embedding the corpus at finer granularity.

    Splitting is contiguous, so the token count is the corpus's own count
    regardless of ``n_parts``; only the number of API rows changes.
    """
    from scripts.eval import db  # noqa: PLC0415

    with db.get_connection() as conn:
        with conn.cursor() as cur:
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
    # ~4 chars/token is the standard OpenAI rule of thumb; English scientific
    # prose runs slightly denser, so this is an upper bound on the bill.
    tokens = int(n_chars) / 4.0
    return {
        "n_chunks": int(n_chunks),
        "n_chars": int(n_chars),
        "est_input_tokens": int(tokens),
        "est_usd": round(tokens / 1e6 * EMBED_USD_PER_MTOK, 4),
    }


def subchunk_arm(
    gt: GroundTruth,
    n_parts: int,
    k: int = 10,
    project_id: str = EVAL_PROJECT_ID,
    allow_spend: bool = False,
) -> dict:
    """Re-embed every chunk in ``n_parts`` pieces and re-score, entirely in memory.

    **Nothing is written to the database.** The eval database is shared and a
    re-ingest mints new chunk ids, which has already invalidated a day of
    measurements on this branch once. Scoring the finer index in process keeps
    the corpus identity ``8d3edbe3f3b28cdb`` intact for every other agent.

    The control is the same in-memory exact max-pool over the *existing* chunk
    embeddings, so the two arms differ in granularity and in nothing else -- not
    in depth, not in plan, not in the scoring code.
    """
    import numpy as np  # noqa: PLC0415

    from scripts.eval import db  # noqa: PLC0415

    # Built first because it is also what loads services/backend/.env onto the
    # environment; the embedding call below dies without OPENAI_API_KEY.
    embed_fn = production_embed_fn()

    with db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id::text, c.document_id::text, c.content, c.embedding::text
                FROM public.document_chunks c
                JOIN public.documents d ON d.id = c.document_id
                WHERE d.project_id = %s::uuid
                ORDER BY c.id
                """,
                (project_id,),
            )
            rows = cur.fetchall()

    parent_doc = [gt.id_map.get(r[1]) for r in rows]
    parent_vecs = np.array(
        [np.fromstring(r[3][1:-1], sep=",") for r in rows], dtype=np.float32
    )

    pieces: list[tuple[str | None, str]] = []
    for (chunk_id, db_doc, content, _emb), doc_id in zip(rows, parent_doc):
        for j, piece in enumerate(split_text(content or "", n_parts)):
            pieces.append((doc_id, piece))

    cache_path = _cache_path(n_parts)
    cache: dict[str, list[float]] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())

    def key_of(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]

    missing = [t for _, t in pieces if key_of(t) not in cache]
    if missing:
        if not allow_spend:
            est = sum(len(t) for t in missing) / 4.0 / 1e6 * EMBED_USD_PER_MTOK
            raise RuntimeError(
                f"{len(missing)} sub-chunks are not cached; embedding them costs "
                f"~${est:.4f}. Re-run with --allow-spend to authorise it."
            )
        sys.path.insert(0, str(EVAL_DIR.parent.parent / "services" / "backend"))
        from app.core.llm_budget import record_usage  # noqa: PLC0415
        from app.services.rag_ingest import embed_chunks  # noqa: PLC0415

        batch = 128
        for i in range(0, len(missing), batch):
            block = missing[i : i + batch]
            vectors = embed_chunks(block, model=EMBED_MODEL)
            for text, vec in zip(block, vectors):
                cache[key_of(text)] = [float(x) for x in vec.embedding]
            record_usage(
                model=EMBED_MODEL,
                prompt_tokens=max(1, sum(len(t) for t in block) // 4),
                label="firststage_subchunk_embed",
            )
            if (i // batch) % 10 == 0:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(cache))
                print(f"  embedded {min(i + batch, len(missing))}/{len(missing)}", flush=True)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache))

    docs = sorted({d for d in parent_doc if d})
    col = {d: i for i, d in enumerate(docs)}
    doc_order = np.array(docs)

    child_doc = np.array([col[d] for d, _ in pieces if d is not None])
    child_vecs = np.array(
        [cache[key_of(t)] for d, t in pieces if d is not None], dtype=np.float32
    )
    child_vecs /= np.linalg.norm(child_vecs, axis=1, keepdims=True)

    keep = np.array([d is not None for d in parent_doc])
    pv = parent_vecs[keep]
    pv /= np.linalg.norm(pv, axis=1, keepdims=True)
    pcol = np.array([col[d] for d in parent_doc if d is not None])

    def score(vecs, cols) -> Pool:
        pools: Pool = {}
        for q in gt.query_list:
            if q.query_id not in gt.qrels:
                continue
            v = np.array(embed_fn(q.text), dtype=np.float32)
            v /= np.linalg.norm(v)
            sims = vecs @ v
            per_doc = np.full(len(docs), -2.0, dtype=np.float32)
            np.maximum.at(per_doc, cols, sims)
            pools[q.query_id] = {
                doc_order[i]: float(per_doc[i]) for i in np.nonzero(per_doc > -2.0)[0]
            }
        return pools

    control = arm_summary(score(pv, pcol), gt.qrels, k)
    fine = arm_summary(score(child_vecs, child_doc), gt.qrels, k)
    return {
        "n_parts": n_parts,
        "n_parent_chunks": int(keep.sum()),
        "n_sub_chunks": int(len(child_doc)),
        "control_exact_full_corpus": control,
        "subchunk_exact_full_corpus": fine,
        "delta_recall": round(fine[f"recall@{k}"] - control[f"recall@{k}"], 4),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

DEPTH_SWEEP = [
    ("index x5   (ef 80, as shipped)", "index", 50, 80),
    ("index x12  (ef 80)", "index", 120, 80),
    ("index x25  (ef 300)", "index", 250, 300),
    ("index x50  (ef 600)", "index", 500, 600),
    ("exact x5", "seqscan", 50, None),
    ("exact x12", "seqscan", 120, None),
    ("exact x25", "seqscan", 250, None),
    ("exact x50", "seqscan", 500, None),
    ("exact x100", "seqscan", 1000, None),
    # The whole corpus as the pool. Not a proposal -- it is the arm that decides
    # whether "never in the pool" is a property of retrieval or of the depth
    # limit, by removing the depth limit entirely.
    ("exact WHOLE CORPUS", "seqscan", 6000, None),
]


def reachability(gt: GroundTruth, pools: Pool, k: int = 10) -> dict:
    """Can ANY claim in a manuscript rank its own cited reference into the top k?

    Every query inherits its manuscript's *entire* resolved reference list, so a
    claim about method X is scored against the 24 references it has nothing to do
    with. This separates "the retriever cannot find this document" from "this
    particular claim does not point at it" -- and only the first is a retrieval
    problem. The unit is the distinct ``(topic, cited document)`` pair, so a
    document cited by a 55-query manuscript counts once, not 55 times.
    """
    by_topic: dict[str, list[str]] = {}
    for q in gt.query_list:
        if q.query_id in gt.qrels:
            by_topic.setdefault(q.topic, []).append(q.query_id)

    best_ranks: list[int] = []
    per_query_ranks: list[int] = []
    for qids in by_topic.values():
        rels = gt.qrels[qids[0]]
        best: dict[str, int] = {}
        for qid in qids:
            for i, doc_id in enumerate(rank_documents(pools.get(qid, {})), 1):
                if doc_id in rels:
                    per_query_ranks.append(i)
                    if doc_id not in best or i < best[doc_id]:
                        best[doc_id] = i
        best_ranks.extend(best.values())

    def pct(values: list[int], p: float) -> int:
        return sorted(values)[int(len(values) * p)] if values else 0

    return {
        "n_topic_document_pairs": len(best_ranks),
        "n_query_document_pairs": len(per_query_ranks),
        "best_of_topic_rank": {f"p{int(p*100)}": pct(best_ranks, p)
                               for p in (0.25, 0.5, 0.75, 0.9)},
        "per_query_rank": {f"p{int(p*100)}": pct(per_query_ranks, p)
                           for p in (0.25, 0.5, 0.75, 0.9)},
        f"reachable_in_top{k}_by_some_claim": sum(1 for r in best_ranks if r <= k),
        f"reachable_in_top{k}_rate": (
            round(sum(1 for r in best_ranks if r <= k) / len(best_ranks), 3)
            if best_ranks else None
        ),
        f"per_query_top{k}_rate": (
            round(sum(1 for r in per_query_ranks if r <= k) / len(per_query_ranks), 3)
            if per_query_ranks else None
        ),
    }


def _print_characterisation(ch: Characterisation, arm: dict) -> None:
    rf = ch.retrieval_failures or 1
    print("\n" + "=" * 72)
    print("  FIRST-STAGE CHARACTERISATION")
    print("=" * 72)
    print(f"  n queries              : {ch.n_queries}")
    print(f"  relevant judgments     : {ch.n_judgments}")
    print(f"  hits@10                : {ch.hits}")
    print(f"  retrieval_failure      : {ch.retrieval_failures}")
    print(f"  ranking_failure        : {ch.ranking_failures}")
    print("\n  -- the retrieval failures, split by cause --------------------------")
    print(f"  never ingested         : {ch.never_ingested:>6}  ({ch.never_ingested / rf:6.2%})"
          f"  {len(ch.never_ingested_docs)} document(s)")
    print(f"  indexed, never pooled  : {ch.never_retrieved:>6}  ({ch.never_retrieved / rf:6.2%})"
          f"  {len(ch.never_retrieved_docs)} cited of {ch.dark_documents} dark document(s)")
    print(f"  pooled for OTHER query : {ch.retrieved_elsewhere:>6}  "
          f"({ch.retrieved_elsewhere / rf:6.2%})  {ch.retrieved_elsewhere_docs} documents")
    print("\n  -- pool capacity ---------------------------------------------------")
    print(f"  median documents in pool : {arm['median_pool_documents']}")
    print(f"  recall@10                : {arm['recall@10']:.4f}")
    print(f"  pool oracle@10           : {arm['pool_oracle@10']:.4f}   "
          f"(best any reranker can reach)")
    print(f"  label ceiling@10         : {arm['ceiling']:.4f}")
    print("\n  -- by topic (retrieval-failure rate) -------------------------------")
    for topic, row in sorted(ch.by_topic.items(), key=lambda kv: -kv[1]["retrieval_failure_rate"]):
        print(f"  {topic}  {row['retrieval_failure']:>5}/{row['judgments']:<5} "
              f"{row['retrieval_failure_rate']:.3f}")
    print("\n  -- contentless interaction -----------------------------------------")
    for name, row in ch.contentless.items():
        print(f"  {name:<12} n={row['n']:<4} rf_rate={row['retrieval_failure_rate']:.3f} "
              f"R@10={row['recall@10']:.4f} ceiling={row['ceiling']:.4f} "
              f"oracle={row['pool_oracle@10']:.4f} "
              f"({row['fraction_of_pool_oracle']:.1%} of oracle)")
    print("=" * 72)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--mode", default="characterise",
                    choices=["characterise", "depth", "subchunk", "cost", "reachability"])
    ap.add_argument("--k", type=int, default=10)
    ap.add_argument("--depth", type=int, default=50)
    ap.add_argument("--n-parts", type=int, default=3)
    ap.add_argument("--allow-spend", action="store_true")
    ap.add_argument("--project-id", default=EVAL_PROJECT_ID)
    ap.add_argument("--json", action="store_true", help="Emit the record as JSON")
    args = ap.parse_args(argv)

    os.environ.setdefault("NOESIS_LLM_KILL_SWITCH", "1" if not args.allow_spend else "0")

    gt = load_ground_truth()
    before = index_identity(args.project_id)
    assert_corpus(before)
    print(f"[firststage] labels {SNAPSHOT} · corpus {before['index_state']}/"
          f"{before['index_digest']} · n={gt.n} · judgments={gt.n_judgments}")

    out: dict = {"snapshot": SNAPSHOT, "index": before, "mode": args.mode}

    if args.mode == "cost":
        out["estimate"] = estimate_subchunk_cost(args.project_id)
        print(json.dumps(out["estimate"], indent=2))
    elif args.mode == "characterise":
        pools, plan = retrieve_pools(gt, args.depth, "index", RPC_EF_SEARCH, args.project_id)
        ch = characterise(gt, pools, indexed_document_ids(gt, args.project_id), args.k)
        arm = arm_summary(pools, gt.qrels, args.k)
        out["plan"] = plan
        out["arm"] = arm
        out["characterisation"] = ch.to_dict()
        _print_characterisation(ch, arm)
    elif args.mode == "depth":
        rows = []
        print(f"\n  {'arm':<32}{'plan':<9}{'depth':>6}{'R@10':>9}{'oracle@10':>11}{'pooldocs':>10}")
        for label, plan, depth, ef in DEPTH_SWEEP:
            pools, observed = retrieve_pools(gt, depth, plan, ef, args.project_id)
            s = arm_summary(pools, gt.qrels, args.k)
            rows.append({"arm": label, "plan_requested": plan, "plan_observed": observed,
                         "depth": depth, "ef_search": ef, **s})
            print(f"  {label:<32}{observed:<9}{depth:>6}{s[f'recall@{args.k}']:>9.4f}"
                  f"{s[f'pool_oracle@{args.k}']:>11.4f}{s['mean_pool_documents']:>10.2f}")
        out["depth_sweep"] = rows
    elif args.mode == "reachability":
        pools, plan = retrieve_pools(gt, 6000, "seqscan", None, args.project_id)
        ch = characterise(gt, pools, indexed_document_ids(gt, args.project_id), args.k)
        out["plan"] = plan
        out["whole_corpus_pool"] = arm_summary(pools, gt.qrels, args.k)
        out["whole_corpus_failures"] = {
            "retrieval_failure": ch.retrieval_failures,
            "ranking_failure": ch.ranking_failures,
            "hits": ch.hits,
        }
        out["recall_curve"] = {
            f"recall@{kk}": {
                "measured": round(recall_at_k(pools, gt.qrels, kk), 4),
                "ceiling": round(recall_ceiling(gt.qrels, kk), 4),
            }
            for kk in (1, 5, 10, 20, 50, 100)
        }
        out["reachability"] = reachability(gt, pools, args.k)
        print(json.dumps({kk: out[kk] for kk in
                          ("whole_corpus_pool", "whole_corpus_failures",
                           "recall_curve", "reachability")}, indent=2))
    elif args.mode == "subchunk":
        out["subchunk"] = subchunk_arm(gt, args.n_parts, args.k, args.project_id,
                                       allow_spend=args.allow_spend)
        print(json.dumps(out["subchunk"], indent=2))
        # Asserted, not assumed. `unpriced_calls` is reported too: a spend figure
        # with unpriced calls behind it is a floor, not a total.
        try:
            sys.path.insert(0, str(EVAL_DIR.parent.parent / "services" / "backend"))
            from app.core.llm_budget import total_spend_usd, unpriced_calls  # noqa: PLC0415

            out["spend_usd"] = round(total_spend_usd(), 5)
            out["unpriced_calls"] = unpriced_calls()
            print(f"[firststage] spend this process: ${out['spend_usd']:.5f}  "
                  f"unpriced_calls={out['unpriced_calls']}")
        except Exception as exc:  # noqa: BLE001
            print(f"[firststage] spend UNKNOWN ({type(exc).__name__}: {exc})")

    after = index_identity(args.project_id)
    if before["index_digest"] != after["index_digest"]:
        raise SnapshotMismatch(
            "the corpus changed while this run was in flight: "
            f"{before['index_state']}/{before['index_digest']} -> "
            f"{after['index_state']}/{after['index_digest']}. One fingerprint cannot "
            "detect a mid-run swap; two can. Re-run."
        )
    if args.json:
        print(json.dumps(out, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
