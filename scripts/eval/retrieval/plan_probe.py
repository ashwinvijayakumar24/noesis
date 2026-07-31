"""Did the vector query actually use the HNSW index?

WHY THIS EXISTS
    docs/MEASUREMENTS.md §Retrieval baseline (superseded) published a row labelled "dense (pgvector HNSW,
    cosine)". It was not measured against HNSW. On the 2124-chunk corpus,
    Postgres' cost model declined ``idx_document_chunks_embedding`` above a
    ``LIMIT`` of roughly 35 and ran an exhaustive ``Seq Scan -> Sort`` instead;
    the harness asks for ``k * chunk_oversample`` = 50 chunks, which is past that
    crossover. The numbers were valid retrieval quality. The label was wrong.

    A label cannot be trusted to stay right, so this module stops relying on one.
    Every dense run now asks Postgres what it *actually* did and stamps the answer
    into the results record as ``plan: "index" | "seqscan"``. Mislabelling a
    sequential scan as HNSW is now a thing you have to work at.

WHY IT ISSUES THE RPC BODY RATHER THAN EXPLAINing THE RPC
    ``match_document_chunks`` is a plpgsql function. ``EXPLAIN`` of a call to it
    reports one ``Function Scan`` node and says nothing about the plan chosen for
    the statement inside. So this module issues the RPC's body verbatim -- same
    SELECT list shape, same INNER JOIN, same WHERE, same ORDER BY, same LIMIT --
    under the same ``hnsw.ef_search`` the function sets for itself, and EXPLAINs
    that. It is a faithful proxy, not the literal statement, and
    ``PRODUCTION_RPC_BODY_NOTE`` records where the original lives so drift is
    traceable. ``test_plan_probe.py`` asserts the two stay in step by reading the
    live function definition when a database is present.

    The EXPLAIN is plan-only (no ANALYZE): it costs a planning pass, not an
    execution, so stamping every query is cheap.
"""

from __future__ import annotations

#: Provenance of SQL below. If migration 036 changes, this must change with it.
PRODUCTION_RPC_BODY_NOTE = (
    "services/backend/migrations/036_recovered_production_ddl.sql :: "
    "match_document_chunks(vector, uuid, integer)"
)

#: ``match_document_chunks`` hard-codes this in its own body (``SET LOCAL
#: hnsw.ef_search = 80``). The probe mirrors it, because ef_search shifts the
#: index scan's estimated cost and therefore moves the crossover.
RPC_EF_SEARCH = 80

#: The name of the HNSW index the dense path is supposed to be using.
DENSE_INDEX_NAME = "idx_document_chunks_embedding"

PLAN_INDEX = "index"
PLAN_SEQSCAN = "seqscan"
#: Different queries in one run planned differently. Never silently collapsed to
#: either of the two, because "half of this arm was HNSW" is its own finding.
PLAN_MIXED = "mixed"
PLAN_UNKNOWN = "unknown"

DENSE_BODY_SQL = """
SELECT dc.id::text AS chunk_id,
       dc.document_id::text AS document_id,
       1 - (dc.embedding <=> %(vec)s::vector) AS similarity
FROM public.document_chunks dc
INNER JOIN public.documents d ON dc.document_id = d.id
WHERE dc.project_id = %(pid)s::uuid
ORDER BY dc.embedding <=> %(vec)s::vector
LIMIT %(k)s
"""


def classify_plan(plan_text: str, index_name: str = DENSE_INDEX_NAME) -> str:
    """``"index"`` if the plan scans ``index_name``, else ``"seqscan"``.

    Deliberately keyed on the specific vector index rather than on the absence of
    the string "Seq Scan": the plan always contains a scan of ``documents`` for
    the join, and at the crossover that one is a Seq Scan in *both* regimes.
    """
    return PLAN_INDEX if f"Index Scan using {index_name}" in plan_text else PLAN_SEQSCAN


def summarise_plans(kinds) -> str:
    """Collapse the per-query plan kinds of a whole run into one field."""
    distinct = set(kinds)
    if not distinct:
        return PLAN_UNKNOWN
    if len(distinct) == 1:
        return distinct.pop()
    return PLAN_MIXED


def explain_plan_text(conn, embedding, project_id: str, limit: int,
                      ef_search: int = RPC_EF_SEARCH) -> str:
    """Raw ``EXPLAIN (COSTS OFF)`` text for the dense query at this depth."""
    vec = "[" + ",".join(repr(float(x)) for x in embedding) + "]"
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('hnsw.ef_search', %s, true)", (str(ef_search),))
        cur.execute(
            "EXPLAIN (COSTS OFF) " + DENSE_BODY_SQL,
            {"vec": vec, "pid": project_id, "k": limit},
        )
        return "\n".join(row[0] for row in cur.fetchall())


def probe_plan(conn, embedding, project_id: str, limit: int,
               ef_search: int = RPC_EF_SEARCH) -> str:
    """``"index"`` or ``"seqscan"`` for the dense query at this depth."""
    return classify_plan(explain_plan_text(conn, embedding, project_id, limit, ef_search))


def find_crossover(conn, embedding, project_id: str, lo: int = 1, hi: int = 512,
                   ef_search: int = RPC_EF_SEARCH) -> tuple[int, int] | None:
    """Largest LIMIT still planned as an index scan, and the first that is not.

    Binary search, valid because the cost curves cross exactly once: an index
    scan has high startup cost and low per-row cost, a sequential scan the
    reverse. Returns ``None`` if the plan never flips inside ``[lo, hi]`` -- which
    is the expected answer on a corpus large enough that the index always wins,
    and must not be reported as a crossover of ``hi``.
    """
    if probe_plan(conn, embedding, project_id, lo, ef_search) != PLAN_INDEX:
        return None  # already sequential at the shallowest depth
    if probe_plan(conn, embedding, project_id, hi, ef_search) == PLAN_INDEX:
        return None  # never flips within the range
    low, high = lo, hi
    while high - low > 1:
        mid = (low + high) // 2
        if probe_plan(conn, embedding, project_id, mid, ef_search) == PLAN_INDEX:
            low = mid
        else:
            high = mid
    return low, high
