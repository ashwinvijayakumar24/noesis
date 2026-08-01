"""Index lifecycle: snapshot, build, size, drop, and proof of restoration.

THE SAFETY PROPERTY THIS MODULE EXISTS FOR
    A stray index left on ``document_chunks`` would silently change every later
    measurement in this repo -- and, because index choice is invisible in query
    results, it would change them without anything looking wrong. So:

    * every index this package creates is named with the ``ann_sweep_hnsw_``
      prefix, so a stray is identifiable by name alone;
    * ``snapshot_indexes`` is taken before and after and compared byte for byte;
    * the production index is NEVER dropped outside a transaction that is then
      ROLLED BACK.

THE ROLLBACK TRICK, AND WHY IT IS NECESSARY
    Postgres has no index hints. With two HNSW indexes on the same column and
    the same opclass the planner picks by cost, and their costs are identical,
    so which one gets used is not under our control -- and an unlabelled index
    choice makes the whole build sweep meaningless.

    Postgres DDL is transactional. So each candidate is measured inside:

        BEGIN;
          DROP INDEX <every other hnsw index on this column>;
          -- only the candidate survives; the planner has no choice
          ... run the queries ...
        ROLLBACK;

    The DROPs are never committed, so the production index is intact the whole
    time. Nothing is rebuilt, nothing is at risk if the process dies mid-run:
    an aborted backend rolls its transaction back for us.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from .grid import INDEX_PREFIX, BuildConfig

#: Statement timeout applied to index builds. A pathological configuration on a
#: bigger corpus should fail loudly and be RECORDED, not hang the sweep.
BUILD_TIMEOUT_MS = 15 * 60 * 1000


@dataclass
class IndexInfo:
    name: str
    definition: str

    def to_dict(self) -> dict:
        return {"name": self.name, "definition": self.definition}


@dataclass
class BuildOutcome:
    """Result of attempting to build one index. A failure is data, not an exception."""

    config: BuildConfig
    status: str  # "ok" | "build_failed"
    build_seconds: float | None = None
    index_bytes: int | None = None
    index_size_pretty: str | None = None
    error: str | None = None
    error_class: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == "ok"

    def to_dict(self) -> dict:
        return {
            **self.config.to_dict(),
            "status": self.status,
            "build_seconds": self.build_seconds,
            "index_bytes": self.index_bytes,
            "index_size_pretty": self.index_size_pretty,
            "error": self.error,
            "error_class": self.error_class,
        }


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------


def snapshot_indexes(conn, table: str = "document_chunks", schema: str = "public") -> list[IndexInfo]:
    """Every index on ``table``, name + full definition, sorted by name.

    Compared before and after the sweep. Definitions are included, not just
    names, so a same-named index rebuilt with different reloptions is caught.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT indexname, indexdef FROM pg_indexes "
            "WHERE schemaname = %s AND tablename = %s ORDER BY indexname",
            (schema, table),
        )
        return [IndexInfo(name=r[0], definition=r[1]) for r in cur.fetchall()]


def snapshot_signature(snapshot: list[IndexInfo]) -> list[str]:
    """Flat comparable form of a snapshot."""
    return [f"{i.name} :: {i.definition}" for i in snapshot]


def hnsw_indexes_on_column(
    conn, table: str = "document_chunks", column: str = "embedding", schema: str = "public"
) -> list[str]:
    """Names of every HNSW index whose definition mentions ``column``.

    These are exactly the indexes that must be dropped (inside the throwaway
    transaction) to leave a candidate as the planner's only option.
    """
    out = []
    for info in snapshot_indexes(conn, table, schema):
        d = info.definition.lower()
        if " using hnsw " in d and column.lower() in d:
            out.append(info.name)
    return out


def droppable_indexes(conn, table: str = "document_chunks", schema: str = "public") -> list[str]:
    """Indexes that can be DROPped directly, i.e. not backing a constraint.

    A primary key's index cannot be dropped without dropping the constraint, so
    it is excluded. Everything else is fair game inside the throwaway
    transaction that isolates a candidate index.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT i.relname
            FROM pg_index x
            JOIN pg_class i ON i.oid = x.indexrelid
            JOIN pg_class t ON t.oid = x.indrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = %s AND t.relname = %s
              AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = i.oid)
            ORDER BY i.relname
            """,
            (schema, table),
        )
        return [r[0] for r in cur.fetchall()]


def index_size_bytes(conn, name: str, schema: str = "public") -> int | None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_relation_size(to_regclass(%s))", (f"{schema}.{name}",))
        row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else None


def pretty_size(nbytes: int | None) -> str | None:
    if nbytes is None:
        return None
    for unit in ("B", "kB", "MB", "GB"):
        if nbytes < 1024 or unit == "GB":
            return f"{nbytes:.0f} {unit}" if unit == "B" else f"{nbytes:.1f} {unit}"
        nbytes /= 1024.0
    return None


def find_stray_sweep_indexes(conn, table: str = "document_chunks", schema: str = "public") -> list[str]:
    """Any ``ann_sweep_hnsw_*`` index still on the table. Should always be empty."""
    return [i.name for i in snapshot_indexes(conn, table, schema) if i.name.startswith(INDEX_PREFIX)]


# ---------------------------------------------------------------------------
# Build / drop
# ---------------------------------------------------------------------------


def build_hnsw_index(
    conn,
    config: BuildConfig,
    table: str = "document_chunks",
    column: str = "embedding",
    opclass: str = "vector_cosine_ops",
    schema: str = "public",
) -> BuildOutcome:
    """Create one candidate HNSW index and time it. Never raises on a build error.

    A configuration the database refuses is a RESULT ("this point is not
    reachable"), and losing the other 11 points of a grid because point 3 was
    invalid would be an own goal. The error text is captured verbatim.

    Timing note: wall clock around CREATE INDEX, client-side. Index build is
    seconds-scale and dominated by server CPU, so the loopback round trip is
    noise here -- unlike query latency, where it is not.
    """
    name = config.index_name
    # Reloptions are integers validated by grid.py; they are interpolated rather
    # than bound because Postgres does not accept parameters in a WITH (...)
    # storage-parameter clause. int() is the injection guard.
    m = int(config.m)
    efc = int(config.ef_construction)
    ddl = (
        f'CREATE INDEX "{name}" ON {schema}.{table} '
        f"USING hnsw ({column} {opclass}) WITH (m = {m}, ef_construction = {efc})"
    )

    started = time.perf_counter()
    try:
        with conn.cursor() as cur:
            cur.execute("SET statement_timeout = %s", (BUILD_TIMEOUT_MS,))
            cur.execute(ddl)
        conn.commit()
    except Exception as exc:  # psycopg2.Error and anything else the server throws
        conn.rollback()
        return BuildOutcome(
            config=config,
            status="build_failed",
            error=str(exc).strip(),
            error_class=type(exc).__name__,
        )
    elapsed = time.perf_counter() - started

    nbytes = index_size_bytes(conn, name, schema)
    conn.commit()
    return BuildOutcome(
        config=config,
        status="ok",
        build_seconds=round(elapsed, 4),
        index_bytes=nbytes,
        index_size_pretty=pretty_size(nbytes),
    )


def drop_index(conn, name: str, schema: str = "public") -> bool:
    """Drop one index if it exists. Returns True if it was there beforehand."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", (f"{schema}.{name}",))
        existed = bool(cur.fetchone()[0])
        if existed:
            cur.execute(f'DROP INDEX IF EXISTS {schema}."{name}"')
    conn.commit()
    return existed


def drop_created_indexes(conn, names: list[str], schema: str = "public") -> list[str]:
    """Drop every index this sweep created. Returns the ones actually dropped."""
    dropped = []
    for name in names:
        if drop_index(conn, name, schema):
            dropped.append(name)
    return dropped


@dataclass
class RestorationReport:
    """Proof, or disproof, that the table is exactly as it was found."""

    before: list[str]
    after: list[str]
    strays: list[str] = field(default_factory=list)

    @property
    def restored(self) -> bool:
        return self.before == self.after and not self.strays

    def to_dict(self) -> dict[str, Any]:
        return {
            "restored": self.restored,
            "indexes_before": self.before,
            "indexes_after": self.after,
            "strays": self.strays,
            "added": [x for x in self.after if x not in self.before],
            "removed": [x for x in self.before if x not in self.after],
        }


def verify_restored(
    conn, before: list[IndexInfo], table: str = "document_chunks", schema: str = "public"
) -> RestorationReport:
    after = snapshot_indexes(conn, table, schema)
    return RestorationReport(
        before=snapshot_signature(before),
        after=snapshot_signature(after),
        strays=find_stray_sweep_indexes(conn, table, schema),
    )
