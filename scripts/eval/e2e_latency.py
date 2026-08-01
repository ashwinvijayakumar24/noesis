"""The user-visible end-to-end latency of one draft analysis, measured.

Every prior latency number in this repo is a *graph* number. `loadgen/` times
``run_draft_analysis_workflow`` from entry to return and says so in every table
it prints; `node_eval.py` times one node replayed alone. Neither includes
upload, storage, PDF parsing or the publish writes, and the excluded remainder
was believed to be larger than the included part. This module closes that gap:
it starts a stopwatch at the moment a user's file leaves the browser and stops
it at the moment that user's browser could first render results.

What it runs is the production path, not a re-implementation of it:

``drafts.upload_draft``            the real upload route function
``drafts._run_draft_analysis_task`` the exact body the Celery worker executes
``drafts.get_draft_analysis``      the real read the frontend polls

Only three things about them are changed, each one deliberate and each one
recorded in the output record:

1. ``analyze_draft_task.delay`` is replaced by a no-op, and the task body is
   then called inline. A broker hop is not measured; it is reported as an
   excluded stage rather than silently folded into another one.
2. ``limiter.enabled = False``. The 5-uploads-per-minute cap is a policy gate,
   not a latency, and at n>=5 it would truncate the run.
3. ``weasyprint`` is stubbed at import time. It is imported by the PDF-export
   route, needs system libraries this host does not have, and is not on the
   measured path.

Everything writes to a LOCAL Supabase. The module refuses to start if
``SUPABASE_URL`` does not resolve to loopback -- see :func:`assert_local_only`.
That check is not a convenience; production must never see a synthetic draft.

Usage
-----
    cd scripts/eval
    python3 e2e_latency.py --dry-run
    python3 e2e_latency.py --bootstrap          # local schema + bucket + fixtures
    python3 e2e_latency.py --n 3 --yes          # REAL paid GPT-5.2 calls

Results append to ``scripts/eval/results/e2e_latency.jsonl``, keyed by a config
hash that covers the fixture, the parser, the LLM mode and the skip flags.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import platform
import statistics
import sys
import time
import types
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Path bootstrap -- mirrors loadgen/__init__.py so the two harnesses resolve the
# backend package and `trace_report` identically.
# ---------------------------------------------------------------------------
if Path("/app/app").exists():  # pragma: no cover - container-only branch
    REPO_ROOT = Path("/app")
    EVAL_DIR = Path("/app/scripts/eval")
else:
    REPO_ROOT = Path(__file__).resolve().parents[2]
    EVAL_DIR = Path(__file__).resolve().parent
for _p in (str(REPO_ROOT / "services" / "backend"), str(EVAL_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

DEFAULT_RESULTS = EVAL_DIR / "results" / "e2e_latency.jsonl"
DEFAULT_FIXTURE = EVAL_DIR / "openreview" / "ICLR.cc_2024_Conference" / "10eQ4Cfh8p.pdf"

#: The Supabase CLI's published local development credentials. Not a secret --
#: they are printed by `supabase status` on every machine and are identical
#: everywhere. Hard-coded so that a stale production value in
#: services/backend/.env can never be picked up by accident.
LOCAL_SUPABASE_URL = "http://127.0.0.1:54321"
LOCAL_SERVICE_ROLE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImV4cCI6MTk4MzgxMjk5Nn0."
    "EGIM96RAZx35lJzdJsyH-qQwv8Hdp7fsn3W0YpN81IU"
)
LOCAL_DB_URL = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

#: Stages, in the order a user experiences them. `sum(STAGES) == wall_seconds`
#: to within HARNESS_OVERHEAD_TOLERANCE -- asserted by the test module, because
#: a large unexplained residual is a finding and not a rounding error.
STAGES = ("upload_request", "ingest", "graph", "task_tail", "first_read")

#: Stages a user is actually waiting on before results can be rendered. The
#: graph flips `drafts.status` to 'analyzed' as its last act, so `task_tail`
#: (quota + usage bookkeeping) happens after the page could already paint.
VISIBLE_STAGES = ("upload_request", "ingest", "graph", "first_read")

#: Residual (wall - sum of stages) above which the measurement is not trusted.
#: The graph-level harness found node time was 99.5% of graph wall; 1% is the
#: same standard applied one level up.
HARNESS_OVERHEAD_TOLERANCE = 0.01

#: What this harness still does NOT measure. Printed with every result table
#: and stored on every record, in the same spirit as loadgen's EXCLUSION_NOTE.
EXCLUSIONS = (
    "browser -> server network transfer of the PDF (in-process call, no socket)",
    "Celery broker enqueue + worker pickup (task body called inline)",
    "OpenAlex / Unpaywall external source discovery (EVAL_SKIP_EXTERNAL_SOURCE_DISCOVERY=1)",
    "the preliminary-halt gate (EVAL_DISABLE_PRE_REVIEWER_HALT=1)",
    "frontend render time after the JSON arrives",
    "production network latency to Supabase (this runs against LOCAL Supabase)",
)

EXCLUSION_NOTE = (
    "USER-VISIBLE end-to-end latency: upload + storage + PDF parse + 18-node "
    "graph + publish writes + first read. Still excluded: " + "; ".join(EXCLUSIONS)
)


# ---------------------------------------------------------------------------
# Safety
# ---------------------------------------------------------------------------

def assert_local_only(url: str) -> None:
    """Refuse to run against anything but loopback.

    A synthetic draft written to the production project would be
    indistinguishable from a real user's, so this is a hard stop with no
    override flag.
    """
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1", "kong", "host.docker.internal"}:
        raise SystemExit(
            f"REFUSING TO RUN: SUPABASE_URL host is {host!r}, which is not loopback.\n"
            "This harness writes drafts, storage objects and analysis rows. "
            "It runs against local Supabase only."
        )


def configure_environment(*, skip_external: bool = True, parser: str = "docling") -> None:
    """Set every variable the pipeline reads BEFORE the app package is imported.

    ``app.core.supabase_client`` builds its client at import time from
    ``settings``, so a value set afterwards has no effect at all.
    """
    os.environ["SUPABASE_URL"] = LOCAL_SUPABASE_URL
    os.environ["SUPABASE_SERVICE_ROLE_KEY"] = LOCAL_SERVICE_ROLE_KEY
    os.environ["SUPABASE_ANON_KEY"] = LOCAL_SERVICE_ROLE_KEY
    os.environ.setdefault("GROBID_URL", "http://localhost:8070")
    os.environ.setdefault("DOCLING_URL", "http://localhost:5001")
    os.environ["PDF_PARSER"] = parser
    if skip_external:
        # Same two escape hatches the graph-level measurement used, so the
        # `graph` stage here is comparable with the 63.75 s figure.
        os.environ.setdefault("EVAL_SKIP_EXTERNAL_SOURCE_DISCOVERY", "1")
        os.environ.setdefault("EVAL_DISABLE_PRE_REVIEWER_HALT", "1")
    assert_local_only(os.environ["SUPABASE_URL"])

    # weasyprint is imported by the PDF-export route and needs libgobject.
    # Not on the measured path; stubbed rather than installed.
    if "weasyprint" not in sys.modules:
        stub = types.ModuleType("weasyprint")
        stub.HTML = object
        stub.CSS = object
        sys.modules["weasyprint"] = stub


def load_openai_key() -> None:
    """Take OPENAI_API_KEY (and friends) from services/backend/.env.

    Deliberately AFTER :func:`configure_environment`: ``env.load_backend_env``
    never overrides an already-set variable, so the local Supabase values above
    win over whatever the file holds.
    """
    from env import load_backend_env  # scripts/eval/env.py

    load_backend_env()


# ---------------------------------------------------------------------------
# HTTP accounting -- every Supabase call, attributed to the stage that made it
# ---------------------------------------------------------------------------

class _Account:
    """Routes a timing to whichever Clock is currently in flight."""

    def __init__(self, get_clock, which: str):
        self._get_clock = get_clock
        self._which = which

    def record(self, stage: str, dt: float) -> None:
        clock = self._get_clock()
        if clock is not None:
            getattr(clock, self._which).record(stage, dt)


@dataclass
class HttpAccount:
    """Wall time and call count for one class of HTTP traffic, per stage."""

    calls: dict[str, int] = field(default_factory=dict)
    seconds: dict[str, float] = field(default_factory=dict)

    def record(self, stage: str, dt: float) -> None:
        self.calls[stage] = self.calls.get(stage, 0) + 1
        self.seconds[stage] = self.seconds.get(stage, 0.0) + dt

    def to_dict(self) -> dict:
        return {
            "calls": dict(sorted(self.calls.items())),
            "seconds": {k: round(v, 4) for k, v in sorted(self.seconds.items())},
            "total_calls": sum(self.calls.values()),
            "total_seconds": round(sum(self.seconds.values()), 4),
        }


class Clock:
    """Sequential stage timing plus per-stage HTTP attribution.

    Stages never nest and never overlap, which is what makes
    ``sum(stages) ~= wall`` a meaningful check rather than a tautology.
    """

    def __init__(self) -> None:
        self.stage_seconds: dict[str, float] = {}
        self.current: str = "outside"
        self.db = HttpAccount()
        self.storage = HttpAccount()
        self.parse_calls: list[dict] = []
        self.wall_seconds: float = 0.0
        self._wall_t0: float | None = None

    @contextmanager
    def stage(self, name: str):
        prev, self.current = self.current, name
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.stage_seconds[name] = self.stage_seconds.get(name, 0.0) + (
                time.perf_counter() - t0
            )
            self.current = prev

    @contextmanager
    def wall(self):
        self._wall_t0 = time.perf_counter()
        try:
            yield
        finally:
            self.wall_seconds = time.perf_counter() - self._wall_t0

    # -- derived ----------------------------------------------------------
    @property
    def stages_total(self) -> float:
        return sum(self.stage_seconds.get(s, 0.0) for s in STAGES)

    @property
    def residual(self) -> float:
        """wall - sum(stages). Harness overhead, and nothing else should be here."""
        return self.wall_seconds - self.stages_total

    @property
    def visible_total(self) -> float:
        return sum(self.stage_seconds.get(s, 0.0) for s in VISIBLE_STAGES)

    def to_dict(self) -> dict:
        return {
            "stage_seconds": {k: round(self.stage_seconds.get(k, 0.0), 4) for k in STAGES},
            "wall_seconds": round(self.wall_seconds, 4),
            "stages_total_seconds": round(self.stages_total, 4),
            "residual_seconds": round(self.residual, 4),
            "residual_fraction": round(self.residual / self.wall_seconds, 6)
            if self.wall_seconds
            else None,
            "visible_total_seconds": round(self.visible_total, 4),
            "supabase_db_http": self.db.to_dict(),
            "supabase_storage_http": self.storage.to_dict(),
            "pdf_parse_calls": self.parse_calls,
        }


def install_http_hooks(get_clock, supabase_client) -> list[str]:
    """Attach httpx event hooks to every Supabase transport we can reach.

    ``get_clock`` is a callable rather than a Clock so the hooks are installed
    exactly once for the whole session and still attribute each call to the run
    in flight. Installing them per run would stack the handlers and count every
    request once per run already completed.

    Returns the names of the transports actually instrumented, so an
    un-instrumented one shows up as a gap in the record instead of as a zero.
    """
    pending: dict[int, float] = {}
    instrumented: list[str] = []

    def make_hooks(account):
        def on_request(request):
            pending[id(request)] = time.perf_counter()

        def on_response(response):
            t0 = pending.pop(id(response.request), None)
            clock = get_clock()
            if t0 is not None and clock is not None:
                account.record(clock.current, time.perf_counter() - t0)

        return {"request": [on_request], "response": [on_response]}

    targets = [
        ("postgrest", getattr(getattr(supabase_client, "postgrest", None), "session", None), "db"),
        ("storage", getattr(getattr(supabase_client, "storage", None), "session", None), "storage"),
        ("storage_client", getattr(getattr(supabase_client, "storage", None), "_client", None), "storage"),
    ]
    seen: set[int] = set()
    for name, session, which in targets:
        if session is None or not hasattr(session, "event_hooks") or id(session) in seen:
            continue
        seen.add(id(session))
        hooks = make_hooks(_Account(get_clock, which))
        existing = dict(session.event_hooks or {})
        for key, fns in hooks.items():
            existing.setdefault(key, [])
            existing[key] = list(existing[key]) + fns
        session.event_hooks = existing
        instrumented.append(name)
    return instrumented


# ---------------------------------------------------------------------------
# Local bootstrap: schema, storage bucket, user, project
# ---------------------------------------------------------------------------

BOOTSTRAP_SQL_HEADER = """
-- #########################################################################
-- ##  E2E-LOCAL SCHEMA -- NOT PRODUCTION DDL. NEVER APPLY TO PRODUCTION.  ##
-- #########################################################################
--
-- Migrations 001-021 do not exist in this repository; only 022-039 do, and
-- each of those ALTERs tables it assumes already exist. To run the pipeline
-- against a fresh local Postgres the base tables therefore have to be
-- reconstructed, and the only available source of truth for their columns is
-- the application code that reads and writes them.
--
-- CONSEQUENCE, stated plainly: this file is a reconstruction, not a copy. It
-- carries the columns the draft-analysis path touches and no others. Column
-- types are the widest thing that works (mostly TEXT and JSONB) rather than
-- whatever production declares. Constraints, RLS policies, triggers and
-- defaults that production has are absent unless a migration in 022-039
-- creates them. Do not read this file as a description of production.
--
-- Applied by `e2e_latency.py --bootstrap`, followed by migrations 022-039 in
-- order.
"""


def bootstrap_sql() -> str:
    """The base tables, reconstructed from application read/write sites.

    Every column here exists because some line of `app/` writes it, filters on
    it, or orders by it. The provenance for the whole set is a read of
    `routes/drafts.py`, `services/draft_processing.py`,
    `services/draft_analysis_langgraph.py` and `workflows/draft_analysis/`.
    """
    return BOOTSTRAP_SQL_HEADER + """
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS public.projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    insights JSONB,
    insights_status TEXT,
    insights_updated_at TIMESTAMPTZ,
    insights_doc_count INTEGER,
    insights_metadata JSONB,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE,
    title TEXT,
    description TEXT,
    file_url TEXT,
    file_type TEXT,
    file_size BIGINT,
    status TEXT,
    source_type TEXT,
    resolution_status TEXT,
    tags TEXT[],
    metadata JSONB DEFAULT '{}'::jsonb,
    analysis JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    project_id UUID REFERENCES public.projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    file_url TEXT,
    file_type TEXT,
    file_size BIGINT,
    paper_type TEXT DEFAULT 'journal_article',
    citation_style TEXT DEFAULT 'auto',
    status TEXT DEFAULT 'uploaded',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.draft_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    structure JSONB DEFAULT '{}'::jsonb,
    analysis JSONB DEFAULT '{}'::jsonb,
    analysis_metadata JSONB DEFAULT '{}'::jsonb,
    word_count INTEGER,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.draft_claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    claim_text TEXT NOT NULL,
    claim_type TEXT,
    section_location TEXT,
    section_type TEXT,
    importance_score REAL,
    requires_citation BOOLEAN,
    existing_citations JSONB DEFAULT '[]'::jsonb,
    max_similarity REAL,
    supporting_literature JSONB DEFAULT '[]'::jsonb,
    confidence_score NUMERIC,
    match_confidence REAL,
    line_number INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    text_snippet TEXT,
    status TEXT,
    -- NOT NULL DEFAULT false is load-bearing: routes filter .eq("hidden", False)
    -- and nothing ever writes the column, so a NULL hides every claim.
    hidden BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.coverage_gaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    gap_type TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT,
    suggested_papers JSONB DEFAULT '[]'::jsonb,
    reasoning TEXT,
    section_type TEXT,
    line_number INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    text_snippet TEXT,
    status TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.reviewer_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    feedback_type TEXT,
    feedback_text TEXT,
    severity TEXT,
    reviewer_persona TEXT,
    section_reference TEXT,
    section_type TEXT,
    specific_issue TEXT,
    suggestions JSONB DEFAULT '[]'::jsonb,
    source_grounding JSONB,
    target_claim_id UUID,
    target_gap_id UUID,
    line_number INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    text_snippet TEXT,
    match_confidence REAL,
    qa_status TEXT,
    qa_notes JSONB,
    -- never written, but .order("priority") is issued by two list endpoints.
    priority TEXT,
    status TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Referenced by citation_suggestions.suggested_citation_id for a PostgREST
-- embed. Nothing on the measured path inserts into it.
CREATE TABLE IF NOT EXISTS public.citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    project_id UUID,
    document_id UUID,
    citation_text TEXT,
    citation_key TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.citation_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    claim_text TEXT,
    section_location TEXT,
    suggestion_type TEXT,
    suggested_paper JSONB,
    suggested_citation_id UUID REFERENCES public.citations(id) ON DELETE SET NULL,
    confidence_score REAL,
    relevance_score REAL,
    priority_score REAL,
    impact_level TEXT,
    reasoning TEXT,
    status TEXT DEFAULT 'pending',
    user_feedback TEXT,
    responded_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.reviewer_panel_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL,
    summary TEXT,
    strengths JSONB DEFAULT '[]'::jsonb,
    weaknesses JSONB DEFAULT '[]'::jsonb,
    questions_to_authors JSONB DEFAULT '[]'::jsonb,
    limitations_to_address JSONB DEFAULT '[]'::jsonb,
    rating INTEGER,
    confidence INTEGER,
    recommendation TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.meta_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    overall_recommendation TEXT,
    decision_rationale TEXT,
    must_address JSONB DEFAULT '[]'::jsonb,
    nice_to_address JSONB DEFAULT '[]'::jsonb,
    consensus_strengths JSONB DEFAULT '[]'::jsonb,
    consensus_weaknesses JSONB DEFAULT '[]'::jsonb,
    reviewer_agreement_level TEXT,
    score_summary JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.paper_recommendations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID,
    user_id UUID,
    discovery_type TEXT,
    search_query TEXT,
    bib_saved BOOLEAN DEFAULT false,
    status TEXT,
    title TEXT NOT NULL,
    abstract TEXT,
    authors JSONB DEFAULT '[]'::jsonb,
    year INTEGER,
    doi TEXT,
    arxiv_id TEXT,
    pubmed_id TEXT,
    semantic_scholar_id TEXT,
    source TEXT,
    paper_url TEXT,
    pdf_url TEXT,
    citation_count INTEGER,
    journal_name TEXT,
    publication_type TEXT,
    fields_of_study JSONB DEFAULT '[]'::jsonb,
    relevance_score REAL,
    relevance_reason TEXT,
    matched_keywords JSONB DEFAULT '[]'::jsonb,
    addresses_gaps JSONB DEFAULT '[]'::jsonb,
    recommendation_context JSONB,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.draft_comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_v1_id UUID,
    draft_v2_id UUID,
    comparison_result JSONB DEFAULT '{}'::jsonb,
    improvement_score NUMERIC,
    feedback_addressed INTEGER,
    gaps_resolved INTEGER,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.user_feedback_on_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID REFERENCES public.drafts(id) ON DELETE CASCADE,
    feedback_id UUID,
    user_id UUID,
    user_action TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    -- the one literal on_conflict= on this path.
    UNIQUE (draft_id, feedback_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.draft_analysis_checkpoints (
    id TEXT PRIMARY KEY,
    thread_id TEXT,
    checkpoint_data TEXT,
    node_name TEXT,
    status TEXT,
    user_id UUID,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.usage_tracking (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID,
    project_id UUID,
    draft_id UUID,
    operation_type TEXT,
    model TEXT,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    cost NUMERIC,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.user_quotas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE,
    plan TEXT DEFAULT 'free',
    drafts_analyzed INTEGER DEFAULT 0,
    documents_uploaded INTEGER DEFAULT 0,
    bibtex_refs_resolved INTEGER DEFAULT 0,
    period_start TIMESTAMPTZ DEFAULT now(),
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);
"""


def post_migration_sql() -> str:
    """RPCs the pipeline calls that no migration defines. Applied AFTER 022-039
    because `match_draft_chunks` reads `draft_chunks`, which migration 036
    creates."""
    return """
-- Three RPCs the pipeline calls that no migration in this repo defines. Their
-- production bodies are unknown, so these are minimal local stand-ins, present
-- only so a PostgREST 404 does not change the shape of the measured path.
-- They are NOT a reconstruction of production behaviour.
CREATE OR REPLACE FUNCTION public.increment_quota_field(user_id_param UUID, field_name TEXT)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO public.user_quotas (user_id) VALUES (user_id_param)
        ON CONFLICT (user_id) DO NOTHING;
    IF field_name = 'draft' THEN
        UPDATE public.user_quotas SET drafts_analyzed = COALESCE(drafts_analyzed, 0) + 1
            WHERE user_id = user_id_param;
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.reset_quota_if_needed(user_id_param UUID)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO public.user_quotas (user_id) VALUES (user_id_param)
        ON CONFLICT (user_id) DO NOTHING;
END;
$$;

CREATE OR REPLACE FUNCTION public.match_draft_chunks(
    query_embedding vector, p_draft_id UUID, match_count INTEGER DEFAULT 5)
RETURNS TABLE (id UUID, chunk_text TEXT, section_name TEXT, similarity FLOAT)
LANGUAGE sql STABLE AS $$
    SELECT dc.id, dc.chunk_text, dc.section_name,
           1 - (dc.embedding <=> query_embedding) AS similarity
    FROM public.draft_chunks dc
    WHERE dc.draft_id = p_draft_id AND dc.embedding IS NOT NULL
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
$$;
"""


def apply_bootstrap(verbose: bool = True) -> list[str]:
    """Apply the local base schema, then migrations 022-039, via `docker exec`.

    `psql` is not assumed to exist on the host; the local Supabase database
    container always has it.
    """
    import subprocess
    import tempfile

    applied: list[str] = []
    container = "supabase_db_noesis"

    def run_sql(name: str, sql: str) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".sql", delete=False) as fh:
            fh.write(sql)
            path = fh.name
        try:
            proc = subprocess.run(
                ["docker", "exec", "-i", container, "psql", "-v", "ON_ERROR_STOP=1",
                 "-U", "postgres", "-d", "postgres", "-q"],
                stdin=open(path, "rb"),
                capture_output=True,
                text=True,
            )
        finally:
            os.unlink(path)
        if proc.returncode != 0:
            # Several of 022-039 create RLS policies without an IF NOT EXISTS
            # guard, so a second bootstrap on an already-migrated database
            # fails on the policy rather than on anything meaningful. That one
            # error is reported and skipped; every other error still stops.
            if "already exists" in proc.stderr:
                applied.append(f"{name} (skipped: already applied)")
                if verbose:
                    print(f"  skipped {name} -- already applied")
                return
            raise SystemExit(f"bootstrap failed applying {name}:\n{proc.stderr[-4000:]}")
        applied.append(name)
        if verbose:
            print(f"  applied {name}")

    run_sql("e2e_local_base", bootstrap_sql())
    run_sql("000_local_base_stubs.sql", (EVAL_DIR / "schema" / "000_local_base_stubs.sql").read_text())
    mig_dir = REPO_ROOT / "services" / "backend" / "migrations"
    for path in sorted(mig_dir.glob("*.sql")):
        run_sql(path.name, path.read_text())
    run_sql("e2e_local_rpcs", post_migration_sql())
    return applied


def ensure_storage_bucket(supabase_client, name: str = "drafts") -> None:
    try:
        supabase_client.storage.create_bucket(name, options={"public": True})
    except Exception:
        pass  # already exists


def ensure_fixtures(supabase_client) -> tuple[str, str]:
    """A stable local user + project to hang the synthetic drafts off.

    Deterministic UUIDs so repeated runs reuse the same rows rather than
    accumulating a new project per run.
    """
    user_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "noesis-e2e-latency-user"))
    project_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "noesis-e2e-latency-project"))
    existing = supabase_client.table("projects").select("id").eq("id", project_id).execute()
    if not existing.data:
        supabase_client.table("projects").insert({
            "id": project_id,
            "user_id": user_id,
            "title": "e2e-latency",
            "description": "Synthetic project for scripts/eval/e2e_latency.py. Local only.",
        }).execute()
    return user_id, project_id


# ---------------------------------------------------------------------------
# One run
# ---------------------------------------------------------------------------

@dataclass
class RunRecord:
    index: int
    ok: bool
    warmup: bool = False
    draft_id: str | None = None
    clock: dict = field(default_factory=dict)
    error: str | None = None
    llm: dict = field(default_factory=dict)
    detail: dict = field(default_factory=dict)


class Harness:
    """Holds the imported app modules and the patches, so a run is cheap."""

    def __init__(self, fixture: Path, user_id: str, project_id: str):
        self.fixture = fixture
        self.pdf_bytes = fixture.read_bytes()
        self.user_id = user_id
        self.project_id = project_id

        import app.api.routes.drafts as drafts_mod
        import app.services.draft_processing as processing_mod
        import app.services.draft_analysis_langgraph as langgraph_mod
        from app.core.security_middleware import limiter

        self.drafts = drafts_mod
        self.processing = processing_mod
        self.langgraph = langgraph_mod

        # (2) rate limiting is a policy gate, not a latency.
        limiter.enabled = False

        # (4) `progress_tracking.REDIS_URL` is hard-coded to the compose
        #     hostname `redis`, which does not resolve off the compose network.
        #     Left unpatched, every progress publish spends a DNS failure and
        #     a connect timeout inside the measured path -- an artefact of
        #     running on the host, not something a production user pays. Only
        #     the hostname changes.
        import app.services.progress_tracking as progress_mod
        progress_mod.REDIS_URL = os.environ.get(
            "E2E_REDIS_URL", "redis://localhost:6379/0"
        )

        # (1) no broker: the task body is called inline, and the hop it
        #     replaces is declared in EXCLUSIONS rather than counted as zero.
        import app.tasks.draft_analysis as task_mod
        self._real_delay = task_mod.analyze_draft_task.delay
        task_mod.analyze_draft_task.delay = lambda *a, **k: types.SimpleNamespace(id="inline")

    # -- instrumentation wrappers ----------------------------------------
    def install_timers(self, clock: Clock) -> None:
        """Wrap three functions with stopwatches. No behaviour changes."""
        processing, drafts, langgraph = self.processing, self.drafts, self.langgraph

        if not hasattr(processing, "_e2e_real_extract_text"):
            processing._e2e_real_extract_text = processing.extract_text

        real_extract = processing._e2e_real_extract_text

        async def timed_extract_text(file_bytes, file_type):
            t0 = time.perf_counter()
            out = await real_extract(file_bytes, file_type)
            clock.parse_calls.append({
                "stage": clock.current,
                "seconds": round(time.perf_counter() - t0, 4),
                "chars": len((out or {}).get("full_text") or ""),
                "sections": len((out or {}).get("sections") or []),
                "references": len((out or {}).get("references") or []),
            })
            return out

        processing.extract_text = timed_extract_text

        if not hasattr(drafts, "_e2e_real_ingest_draft"):
            drafts._e2e_real_ingest_draft = drafts.ingest_draft
        real_ingest = drafts._e2e_real_ingest_draft

        async def timed_ingest(draft_id, project_id):
            with clock.stage("ingest"):
                return await real_ingest(draft_id, project_id)

        drafts.ingest_draft = timed_ingest

        if not hasattr(langgraph, "_e2e_real_analyze"):
            langgraph._e2e_real_analyze = langgraph.analyze_draft_with_langgraph
        real_graph = langgraph._e2e_real_analyze

        async def timed_graph(*a, **k):
            with clock.stage("graph"):
                return await real_graph(*a, **k)

        langgraph.analyze_draft_with_langgraph = timed_graph

    # -- the run ----------------------------------------------------------
    def run_once(self, index: int, clock: Clock) -> RunRecord:
        from fastapi.datastructures import UploadFile
        from starlette.datastructures import Headers
        import io

        draft_id = None
        try:
            with clock.wall():
                # 1. upload: validation (which parses the PDF once), storage
                #    write, drafts insert. The real route function.
                with clock.stage("upload_request"):
                    upload = UploadFile(
                        file=io.BytesIO(self.pdf_bytes),
                        filename=f"{self.fixture.stem}_e2e{index}.pdf",
                        headers=Headers({"content-type": "application/pdf"}),
                    )
                    resp = asyncio.run(self.drafts.upload_draft(
                        request=None,
                        file=upload,
                        project_id=self.project_id,
                        title=f"e2e-{self.fixture.stem}-{index}",
                        paper_type="journal_article",
                        citation_style="auto",
                        user_id=self.user_id,
                    ))
                    draft_id = resp["draft"]["id"]

                # 2 + 3. the exact body the Celery worker runs. `ingest` and
                #        `graph` time themselves through the wrappers above;
                #        whatever is left is the task's own bookkeeping tail.
                t_task = time.perf_counter()
                self.drafts._run_draft_analysis_task(draft_id, self.project_id)
                task_wall = time.perf_counter() - t_task
                clock.stage_seconds["task_tail"] = max(
                    0.0,
                    task_wall
                    - clock.stage_seconds.get("ingest", 0.0)
                    - clock.stage_seconds.get("graph", 0.0),
                )

                # 4. the read the frontend makes once status flips to analyzed.
                with clock.stage("first_read"):
                    payload = self.drafts.get_draft_analysis(
                        draft_id=draft_id, user_id=self.user_id, debug=False
                    )

            detail = {
                "chars": clock.parse_calls[-1]["chars"] if clock.parse_calls else None,
                "analysis_status": (payload or {}).get("status"),
                "reviewer_feedback_items": len((payload or {}).get("reviewer_feedback") or []),
            }
            return RunRecord(index=index, ok=True, draft_id=draft_id,
                             clock=clock.to_dict(), detail=detail)
        except Exception as exc:  # a failed run is recorded, never averaged in
            return RunRecord(index=index, ok=False, draft_id=draft_id,
                             clock=clock.to_dict(),
                             error=f"{type(exc).__name__}: {exc}"[:600])

    def restore(self) -> None:
        import app.tasks.draft_analysis as task_mod
        task_mod.analyze_draft_task.delay = self._real_delay


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def summarize(records: list[RunRecord]) -> dict:
    """Per-stage p50/mean over successful runs, with n on every row.

    Percentiles come from ``trace_report.metrics.percentiles`` so the n-floor
    that refuses a p95 below n=20 is literally the same code the graph-level
    harness uses.
    """
    from trace_report.metrics import percentiles

    measured = [r for r in records if not r.warmup]
    ok = [r for r in measured if r.ok]
    out: dict = {
        "n_offered": len(records),
        "n_warmup_discarded": len(records) - len(measured),
        "n_runs": len(measured),
        "n_ok": len(ok),
        "n_failed": len(measured) - len(ok),
    }

    def dist(values: list[float]) -> dict:
        return percentiles(values).to_dict()

    stage_rows = {}
    for stage in STAGES:
        vals = [r.clock["stage_seconds"].get(stage, 0.0) for r in ok]
        stage_rows[stage] = dist(vals)
    out["stages"] = stage_rows
    out["wall"] = dist([r.clock["wall_seconds"] for r in ok])
    out["visible_total"] = dist([r.clock["visible_total_seconds"] for r in ok])
    out["residual"] = dist([r.clock["residual_seconds"] for r in ok])
    out["residual_fraction_max"] = (
        max((abs(r.clock["residual_fraction"] or 0.0) for r in ok), default=None)
    )
    out["supabase_db_seconds"] = dist(
        [r.clock["supabase_db_http"]["total_seconds"] for r in ok]
    )
    out["supabase_storage_seconds"] = dist(
        [r.clock["supabase_storage_http"]["total_seconds"] for r in ok]
    )
    parse_totals = [
        sum(c["seconds"] for c in r.clock["pdf_parse_calls"]) for r in ok
    ]
    out["pdf_parse_seconds"] = dist(parse_totals)
    out["pdf_parse_calls_per_run"] = (
        statistics.fmean([len(r.clock["pdf_parse_calls"]) for r in ok]) if ok else None
    )
    if len(ok) >= 2:
        vals = [r.clock["visible_total_seconds"] for r in ok]
        mean = statistics.fmean(vals)
        sd = statistics.stdev(vals)
        out["visible_total_cv"] = round(sd / mean, 4) if mean else None
        out["visible_total_sd"] = round(sd, 4)
    return out


def config_hash(cfg: dict) -> str:
    blob = json.dumps(cfg, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:12]


def build_config(args, fixture: Path) -> dict:
    """Everything that could move a number. Two runs sharing this hash are
    comparable; two that do not, are not."""
    return {
        "harness": "e2e_latency",
        "harness_version": 1,
        "fixture": fixture.name,
        "fixture_bytes": fixture.stat().st_size,
        "pdf_parser": args.parser,
        "llm": "real",
        "supabase": "local",
        "skip_external_source_discovery": True,
        "disable_pre_reviewer_halt": True,
        "stages": list(STAGES),
        "python": platform.python_version(),
        "platform": f"{platform.system()}-{platform.machine()}",
    }


def append_results(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:  # append-only, always
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def render_table(summary: dict) -> str:
    rows = ["| stage | n | p50 (s) | mean (s) | min | max |", "|---|---|---|---|---|---|"]

    def fmt(v):
        return f"{v:,.2f}" if isinstance(v, (int, float)) else "—"

    for stage in STAGES:
        d = summary["stages"][stage]
        rows.append(
            f"| `{stage}` | {d['n']} | {fmt(d.get('p50'))} | {fmt(d.get('mean'))} "
            f"| {fmt(d.get('min'))} | {fmt(d.get('max'))} |"
        )
    for label, key in (("**to first visible**", "visible_total"), ("wall (incl. tail)", "wall")):
        d = summary[key]
        rows.append(
            f"| {label} | {d['n']} | {fmt(d.get('p50'))} | {fmt(d.get('mean'))} "
            f"| {fmt(d.get('min'))} | {fmt(d.get('max'))} |"
        )
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="e2e_latency",
        description="User-visible end-to-end latency of one draft analysis. LOCAL Supabase only.",
    )
    p.add_argument("--n", type=int, default=3, help="complete runs to measure")
    p.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    p.add_argument("--parser", choices=["docling", "grobid"], default="grobid",
                   help="production compose defaults to docling; grobid is the "
                        "default HERE because docling-serve-cpu and grobid cannot "
                        "both fit in this host's 7.65 GiB Docker allocation "
                        "alongside local Supabase -- see E2E_LATENCY.md")
    p.add_argument("--warmup", type=int, default=1,
                   help="leading runs discarded from every statistic; the parser "
                        "loads its models on first use and that cost is a cold "
                        "start, not a user-visible latency")
    p.add_argument("--max-calls", type=int, default=120,
                   help="NOESIS_LLM_MAX_CALLS ceiling")
    p.add_argument("--max-spend", type=float, default=4.0,
                   help="NOESIS_LLM_MAX_SPEND_USD ceiling")
    p.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    p.add_argument("--bootstrap", action="store_true",
                   help="apply the local schema + bucket + fixtures, then exit")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--yes", action="store_true", help="confirm REAL paid LLM calls")
    args = p.parse_args(argv)

    fixture = args.fixture if args.fixture.is_absolute() else (EVAL_DIR / args.fixture)
    if not fixture.is_file():
        raise SystemExit(f"fixture not found: {fixture}")

    cfg = build_config(args, fixture)
    cfg_hash = config_hash(cfg)

    if args.dry_run:
        print("DRY RUN -- no import of the app package, no call, no write.")
        print(EXCLUSION_NOTE)
        print(f"fixture: {fixture}  ({fixture.stat().st_size:,} bytes)")
        print(f"runs: {args.n}   parser: {args.parser}   cfg={cfg_hash}")
        print(f"LLM calls: ~{args.n * 9}-{args.n * 15} (8-9/graph run, no-corpus, plus stage-1 editing)")
        print(f"est. spend: ${args.n * 0.13:.2f}-${args.n * 0.20:.2f}  "
              f"(graph measured $0.1374/run; stage-1 editing extra)")
        print(f"ceilings: {args.max_calls} calls / ${args.max_spend:.2f}")
        return 0

    # Ceilings before ANY app import, so llm_budget reads them at call time.
    os.environ["NOESIS_LLM_MAX_CALLS"] = str(args.max_calls)
    os.environ["NOESIS_LLM_MAX_SPEND_USD"] = str(args.max_spend)
    configure_environment(parser=args.parser)
    load_openai_key()
    assert_local_only(os.environ["SUPABASE_URL"])

    from app.core.supabase_client import supabase

    if args.bootstrap:
        print("bootstrapping LOCAL schema (never production):")
        apply_bootstrap()
        ensure_storage_bucket(supabase)
        user_id, project_id = ensure_fixtures(supabase)
        print(f"  bucket 'drafts' ready; user={user_id} project={project_id}")
        return 0

    if not args.yes:
        print("This makes REAL paid GPT-5.2 calls. Pass --yes to confirm.", file=sys.stderr)
        return 2

    ensure_storage_bucket(supabase)
    user_id, project_id = ensure_fixtures(supabase)

    harness = Harness(fixture, user_id, project_id)
    from app.core.llm_budget import totals

    spend_before = totals()
    records: list[RunRecord] = []
    active: dict[str, Clock | None] = {"clock": None}
    transports = install_http_hooks(lambda: active["clock"], supabase)
    total_runs = args.warmup + args.n
    try:
        for i in range(total_runs):
            warm = i < args.warmup
            clock = Clock()
            active["clock"] = clock
            harness.install_timers(clock)
            label = "WARMUP (discarded)" if warm else f"run {i - args.warmup + 1}/{args.n}"
            print(f"\n>>> {label}", flush=True)
            t0 = time.perf_counter()
            rec = harness.run_once(i, clock)
            rec.warmup = warm
            before = spend_before if i == 0 else records[-1].llm.get("_cum", spend_before)
            cum = totals()
            rec.llm = {
                "_cum": cum,
                "calls": cum["calls"] - before["calls"],
                "estimated_usd": round(cum["estimated_usd"] - before["estimated_usd"], 6),
                "prompt_tokens": cum["prompt_tokens"] - before["prompt_tokens"],
                "completion_tokens": cum["completion_tokens"] - before["completion_tokens"],
            }
            records.append(rec)
            status = "ok" if rec.ok else f"FAILED {rec.error}"
            print(f"    {time.perf_counter() - t0:,.1f}s  {status}", flush=True)
    finally:
        harness.restore()

    for r in records:
        r.llm.pop("_cum", None)
    spend_after = totals()
    summary = summarize(records)

    run_id = uuid.uuid4().hex[:12]
    record = {
        "record_type": "e2e_latency",
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": cfg,
        "config_hash": cfg_hash,
        "exclusions": list(EXCLUSIONS),
        "exclusion_note": EXCLUSION_NOTE,
        "harness_overhead_tolerance": HARNESS_OVERHEAD_TOLERANCE,
        "instrumented_transports": transports,
        "summary": summary,
        "runs": [
            {"index": r.index, "ok": r.ok, "warmup": r.warmup, "draft_id": r.draft_id,
             "error": r.error, "llm": r.llm, "detail": r.detail, **r.clock}
            for r in records
        ],
        "spend": {
            "calls": spend_after["calls"] - spend_before["calls"],
            "estimated_usd": round(
                spend_after["estimated_usd"] - spend_before["estimated_usd"], 6
            ),
            "prompt_tokens": spend_after["prompt_tokens"] - spend_before["prompt_tokens"],
            "completion_tokens": spend_after["completion_tokens"] - spend_before["completion_tokens"],
            "unpriced_calls": spend_after.get("unpriced_calls"),
            "ceiling_calls": args.max_calls,
            "ceiling_usd": args.max_spend,
        },
    }
    append_results(args.results, record)

    print("\n" + "=" * 92)
    print(f"RUN {run_id}  cfg={cfg_hash}  n={summary['n_ok']} ok / {summary['n_failed']} failed")
    print(EXCLUSION_NOTE)
    print("=" * 92)
    print(render_table(summary))
    print(f"\nresidual (wall - sum of stages), max over runs: "
          f"{summary['residual_fraction_max']!r}  tolerance {HARNESS_OVERHEAD_TOLERANCE}")
    print(f"spend: ${record['spend']['estimated_usd']:.4f} over "
          f"{record['spend']['calls']} calls (ceiling ${args.max_spend:.2f})")
    print(f"appended 1 record to {args.results}")
    return 0 if summary["n_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
