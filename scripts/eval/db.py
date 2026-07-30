"""Direct psycopg2 access to the LOCAL pgvector Postgres used by the eval harness.

WHY THIS EXISTS
    The application talks to Postgres through the Supabase client (PostgREST over
    HTTPS). That is fine for the product but useless for retrieval experiments:
    every call pays network RTT to Supabase, which swamps the microsecond-scale
    differences a HNSW `ef_search` sweep is trying to measure, and it means the
    sweep would be mutating session GUCs on the production database.

    This module bypasses the app layer entirely and speaks psycopg2 to the local
    `pgvector` container declared in infra/docker-compose.yml, whose schema is a
    faithful copy of production (migrations 036 + 037, plus the local base stubs
    in scripts/eval/schema/000_local_base_stubs.sql).

SETUP
    cd infra && docker compose --profile core up -d pgvector
    docker compose exec -T pgvector psql -U noesis_local -d noesis_eval \\
        < ../scripts/eval/schema/000_local_base_stubs.sql
    docker compose exec -T pgvector psql -U noesis_local -d noesis_eval \\
        < ../services/backend/migrations/036_recovered_production_ddl.sql
    docker compose exec -T pgvector psql -U noesis_local -d noesis_eval \\
        < ../services/backend/migrations/037_fix_keyword_search_chunks.sql

CREDENTIALS
    Read from EVAL_DB_* env vars. The defaults are the throwaway LOCAL-ONLY values
    baked into the compose service and are not credentials for anything real.
    Nothing here is ever read from a .env file.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Sequence

import psycopg2
import psycopg2.extras

# Dimensionality of every embedding column in the recovered production schema
# (OpenAI text-embedding-3-large truncated to 1536). See migration 036.
EMBEDDING_DIM = 1536

# LOCAL DEV ONLY — matches the `pgvector` service in infra/docker-compose.yml.
# Host port is 5433, not 5432, to avoid colliding with a developer-installed
# Postgres. Override any of these via the environment.
DEFAULTS = {
    "host": "localhost",
    "port": "5433",
    "dbname": "noesis_eval",
    "user": "noesis_local",
    "password": "noesis_local_dev_only",
}


def connection_params() -> Dict[str, Any]:
    """Resolve connection parameters from EVAL_DB_* env vars, with local defaults."""
    return {
        "host": os.getenv("EVAL_DB_HOST", DEFAULTS["host"]),
        "port": int(os.getenv("EVAL_DB_PORT", DEFAULTS["port"])),
        "dbname": os.getenv("EVAL_DB_NAME", DEFAULTS["dbname"]),
        "user": os.getenv("EVAL_DB_USER", DEFAULTS["user"]),
        "password": os.getenv("EVAL_DB_PASSWORD", DEFAULTS["password"]),
    }


def format_vector(embedding: Sequence[float]) -> str:
    """Render a Python sequence as a pgvector literal, e.g. '[0.1,0.2]'.

    psycopg2 has no adapter for the `vector` type, so embeddings cross the wire as
    text and are cast server-side with `::vector`.
    """
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


@contextmanager
def get_connection(**overrides: Any) -> Iterator[psycopg2.extensions.connection]:
    """Yield a psycopg2 connection to the local eval database.

    Commits on clean exit, rolls back on exception, always closes.
    """
    params = connection_params()
    params.update(overrides)
    conn = psycopg2.connect(**params)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def set_ef_search(conn: psycopg2.extensions.connection, value: int) -> None:
    """Set the HNSW query-time search breadth for this session.

    Higher `ef_search` explores more of the graph: better recall, slower queries.
    pgvector's session default is 40; production's match_document_chunks and
    match_single_document_chunks override it to 80 via SET LOCAL inside the
    function body, so a sweep that only sets it here will NOT affect those two
    RPCs — call the underlying query directly when sweeping them.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"ef_search must be an int, got {type(value).__name__}")
    with conn.cursor() as cur:
        # hnsw.ef_search is a custom GUC, so it cannot be parameterised with %s in
        # a plain SET. set_config() is the parameterised equivalent.
        cur.execute("SELECT set_config('hnsw.ef_search', %s, false)", (str(value),))


def match_document_chunks(
    conn: psycopg2.extensions.connection,
    embedding: Sequence[float],
    project_id: str,
    match_count: int = 5,
) -> List[Dict[str, Any]]:
    """Call the production RPC match_document_chunks(vector, uuid, integer).

    Returns rows with keys: id, document_id, document_title, chunk_index, content,
    similarity (1 - cosine distance, so higher is better).
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM public.match_document_chunks(%s::vector, %s::uuid, %s)",
            (format_vector(embedding), project_id, match_count),
        )
        return [dict(row) for row in cur.fetchall()]


def keyword_search_chunks(
    conn: psycopg2.extensions.connection,
    project_id: str,
    query: str,
    match_count: int = 20,
) -> List[Dict[str, Any]]:
    """Call the production RPC keyword_search_chunks(uuid, text, integer).

    Returns rows with keys: id, document_id, content, rank. Raises
    psycopg2.errors.UndefinedColumn (SQLSTATE 42703) if migration 037 has not been
    applied — see that migration's header for the bug this covers.
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT * FROM public.keyword_search_chunks(%s::uuid, %s, %s)",
            (project_id, query, match_count),
        )
        return [dict(row) for row in cur.fetchall()]


def healthcheck() -> bool:
    """True if the local eval DB is reachable AND the pgvector extension is installed."""
    try:
        with get_connection(connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
                return cur.fetchone() is not None
    except Exception:
        return False


if __name__ == "__main__":
    params = connection_params()
    print(f"eval db: {params['user']}@{params['host']}:{params['port']}/{params['dbname']}")
    print("healthy" if healthcheck() else "UNREACHABLE (is the pgvector container up?)")
