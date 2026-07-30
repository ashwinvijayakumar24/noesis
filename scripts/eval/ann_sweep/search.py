"""The query under measurement, and the two ways it is run.

WHY NOT CALL match_document_chunks DIRECTLY
    That RPC hard-codes ``SET LOCAL hnsw.ef_search = 80`` in its own body, so a
    sweep that calls it measures 80 seven times. db.py says as much in
    ``set_ef_search``'s docstring. This module therefore issues the RPC's body
    verbatim -- same SELECT list, same JOIN, same WHERE, same ORDER BY, same
    LIMIT -- with ef_search under our control. Any drift between the two is a
    bug in this file; ``PRODUCTION_RPC_BODY_NOTE`` records the source.

TWO CLOCKS, ONE OF WHICH IS REPORTED
    Latency is taken from ``EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON)`` ->
    "Execution Time": Postgres' own measure of executing the plan, excluding
    planning and excluding the client round trip. TIMING OFF suppresses per-node
    instrumentation (which on a 2124-row scan costs more than the query) while
    still reporting total execution time.

    A client-side round-trip figure is also available via ``time_search_client``
    and is reported alongside, because on a corpus this small the loopback RTT
    is the same order as the query and a server-side number alone would
    understate what the application actually waits for.
"""

from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass

from .index_ops import droppable_indexes, hnsw_indexes_on_column

#: Provenance for the SQL below. If migration 036 changes, this must change too.
PRODUCTION_RPC_BODY_NOTE = (
    "services/backend/migrations/036_recovered_production_ddl.sql :: "
    "match_document_chunks(vector, uuid, integer)"
)


@dataclass(frozen=True)
class SearchSpec:
    """What to search. Parameterised so tests can point at a synthetic table."""

    table: str = "document_chunks"
    project_id: str = "e7a1c0b0-0000-4000-8000-000000000001"
    schema: str = "public"
    column: str = "embedding"
    #: Production's RPC joins ``documents`` to return a title. It cannot change
    #: the ranking, but it is part of the latency, so it is on by default.
    join_documents: bool = True
    documents_table: str = "documents"

    def sql(self) -> str:
        join = (
            f"INNER JOIN {self.schema}.{self.documents_table} d ON dc.document_id = d.id"
            if self.join_documents
            else ""
        )
        return f"""
            SELECT dc.id::text AS chunk_id,
                   dc.document_id::text AS document_id,
                   1 - (dc.{self.column} <=> %(vec)s::vector) AS similarity
            FROM {self.schema}.{self.table} dc
            {join}
            WHERE dc.project_id = %(pid)s::uuid
            ORDER BY dc.{self.column} <=> %(vec)s::vector
            LIMIT %(k)s
        """


@dataclass(frozen=True)
class Hit:
    chunk_id: str
    document_id: str
    similarity: float


def _vec_literal(embedding) -> str:
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


# ---------------------------------------------------------------------------
# Measurement transaction
# ---------------------------------------------------------------------------


@contextmanager
def measurement_txn(
    conn,
    spec: SearchSpec,
    ef_search: int | None = None,
    keep_index: str | None = None,
    exact: bool = False,
    force_index_scan: bool = False,
):
    """Open a throwaway transaction configured for one measurement point.

    ``keep_index`` leaves exactly that one HNSW index on the column by DROPping
    every other one -- inside a transaction that ALWAYS rolls back, so nothing
    is really dropped. See index_ops' module docstring for why this is the only
    way to control which index the planner uses.

    ``exact=True`` disables index scans so the ORDER BY falls back to a
    sequential scan + sort: exhaustive nearest neighbour, recall 1.0 by
    definition, the ground truth ANN recall is measured against.

    ``force_index_scan=True`` does the opposite -- ``enable_seqscan = off`` --
    and it exists because of a measured fact about this corpus: at 2124 chunks
    and a LIMIT of 50, Postgres' cost model prefers a sequential scan and
    DECLINES the HNSW index. Without forcing, every "HNSW" measurement here
    would silently be a sequential scan wearing an index's name. Any record
    produced under this flag is stamped ``index_scan_forced: true`` and
    describes the index, NOT what production executes.

    Rolls back unconditionally on exit, including on success. Nothing in this
    package is ever meant to be committed.
    """
    if exact and keep_index is not None:
        raise ValueError("exact=True and keep_index are mutually exclusive: exact search uses no index")
    if exact and force_index_scan:
        raise ValueError("exact=True and force_index_scan=True are contradictory")
    try:
        with conn.cursor() as cur:
            if keep_index is not None:
                present = hnsw_indexes_on_column(conn, spec.table, spec.column, spec.schema)
                if keep_index not in present:
                    raise ValueError(
                        f"keep_index={keep_index!r} is not an HNSW index on "
                        f"{spec.schema}.{spec.table}.{spec.column} (present: {present}). "
                        "Refusing to measure -- the planner would silently use a different index."
                    )
                # Drop EVERY droppable index except the candidate, not just the
                # other HNSW ones. Measured the hard way: with only enable_seqscan
                # off, Postgres reaches for the btree on project_id and feeds a
                # Sort, so the "HNSW" measurement was a btree scan. Leaving the
                # candidate as the sole option is the only way to be sure.
                for name in droppable_indexes(conn, spec.table, spec.schema):
                    if name != keep_index:
                        cur.execute(f'DROP INDEX {spec.schema}."{name}"')
            if exact:
                cur.execute("SET LOCAL enable_indexscan = off")
                cur.execute("SET LOCAL enable_bitmapscan = off")
            if force_index_scan:
                cur.execute("SET LOCAL enable_seqscan = off")
            if ef_search is not None:
                # hnsw.ef_search is a custom GUC: SET cannot be parameterised,
                # set_config can. is_local=true scopes it to this transaction.
                cur.execute("SELECT set_config('hnsw.ef_search', %s, true)", (str(int(ef_search)),))
        yield
    finally:
        conn.rollback()


# ---------------------------------------------------------------------------
# Running and timing
# ---------------------------------------------------------------------------


def run_search(conn, spec: SearchSpec, embedding, k: int) -> list[Hit]:
    params = {"vec": _vec_literal(embedding), "pid": spec.project_id, "k": int(k)}
    with conn.cursor() as cur:
        cur.execute(spec.sql(), params)
        return [Hit(chunk_id=r[0], document_id=r[1], similarity=float(r[2])) for r in cur.fetchall()]


def time_search_server(conn, spec: SearchSpec, embedding, k: int) -> float:
    """One server-side execution time in milliseconds, from EXPLAIN ANALYZE."""
    params = {"vec": _vec_literal(embedding), "pid": spec.project_id, "k": int(k)}
    sql = "EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON) " + spec.sql()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        payload = cur.fetchone()[0]
    plan = json.loads(payload) if isinstance(payload, str) else payload
    return float(plan[0]["Execution Time"])


def time_search_client(conn, spec: SearchSpec, embedding, k: int) -> float:
    """One client-side round trip in milliseconds: execute + fetchall."""
    params = {"vec": _vec_literal(embedding), "pid": spec.project_id, "k": int(k)}
    sql = spec.sql()
    started = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        cur.fetchall()
    return (time.perf_counter() - started) * 1000.0


_VECTOR_LITERAL = re.compile(r"'\[[^\]]{40,}\]'")


def elide_vectors(plan_text: str) -> str:
    """Replace 1536-dim literals in a plan with ``<vector>``.

    A stored plan is evidence about which index ran; the 20 kB of floats inside
    it are not, and they would make the results file unreadable and 100x larger.
    """
    return _VECTOR_LITERAL.sub("'<vector>'", plan_text)


def explain_plan_text(conn, spec: SearchSpec, embedding, k: int) -> str:
    """The plan as text -- used to PROVE which index (or none) was used.

    Without this, "we measured m=32" is an unverified claim about the planner.
    """
    params = {"vec": _vec_literal(embedding), "pid": spec.project_id, "k": int(k)}
    with conn.cursor() as cur:
        cur.execute("EXPLAIN (COSTS OFF) " + spec.sql(), params)
        return elide_vectors("\n".join(r[0] for r in cur.fetchall()))


def index_used(plan_text: str) -> str | None:
    """Extract the index name from an EXPLAIN plan, or None for a sequential scan."""
    for line in plan_text.splitlines():
        stripped = line.strip()
        if "Index Scan using " in stripped:
            after = stripped.split("Index Scan using ", 1)[1]
            return after.split(" on ", 1)[0].strip()
    return None
