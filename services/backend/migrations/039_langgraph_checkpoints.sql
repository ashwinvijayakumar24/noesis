-- 039_langgraph_checkpoints.sql
--
-- Durable LangGraph checkpoint storage for the draft-analysis graph.
--
-- WHY THESE TABLES EXIST
--     Before this migration the graph compiled with no checkpointer at all
--     (`workflow.compile()` bare) and `ainvoke` was called with no thread_id, so a
--     run that died at node 15 of 18 re-executed all 18 and re-paid for every LLM
--     call. The pre-existing `draft_analysis_checkpoints` table is NOT a
--     checkpointer -- it holds two privacy-minimized run-status rows per run and
--     is explicitly non-resumable. It is left untouched.
--
-- SCHEMA SHAPE
--     Column names deliberately mirror the upstream `langgraph-checkpoint-postgres`
--     schema (thread_id / checkpoint_ns / checkpoint_id / parent_checkpoint_id /
--     type / checkpoint / metadata, plus a `checkpoint_writes` sidecar keyed by
--     task_id+idx). That package is NOT installed in this project (it requires
--     psycopg v3, which is also absent -- we have psycopg2 only), so the saver in
--     app/workflows/draft_analysis/checkpoints.py implements LangGraph's own
--     BaseCheckpointSaver protocol over psycopg2 against these tables. Keeping the
--     column names identical means swapping to the upstream saver later is a
--     table rename, not a data migration.
--
--     The tables are prefixed `noesis_lg_` rather than named `checkpoints` /
--     `checkpoint_writes` precisely so that adding the upstream package later can
--     create its own canonical tables side by side without a collision.
--
-- PRIVACY (this is the load-bearing part -- see checkpoints.py MANUSCRIPT_CHANNELS)
--     Manuscript body text is NEVER written to these tables. The saver strips the
--     `draft_content`, `parse_artifact` and `structure` channels from every
--     checkpoint before serialization and records their names in
--     `scrubbed_channels`. Those three channels are already caller-supplied
--     arguments of run_draft_analysis_workflow(), so resume re-supplies them from
--     Supabase Storage / draft_parse_artifacts rather than from this table.
--
--     This matches the invariant the rest of the codebase already enforces:
--       * draft_analysis_langgraph.py and draft_processing.py both write
--         `strip_manuscript_content_from_structure(structure)`, never raw sections.
--       * migration 027 states in its own header that draft_parse_artifacts stores
--         "compact paragraph snippets and coordinates, not a second full manuscript".
--     Derived analysis text (claim_text, feedback_text) IS present in checkpoint
--     rows -- but that same text is already stored durably and un-TTL'd in
--     draft_claims / reviewer_feedback, so a checkpoint row introduces no new
--     class of content. Unlike those tables, checkpoint rows carry a hard TTL and
--     are deleted on successful completion.
--
-- RETENTION
--     `expires_at` is set by the saver (default 24h, NOESIS_CHECKPOINT_TTL_HOURS).
--     Rows are deleted eagerly when a run completes; `expires_at` is the backstop
--     for runs that die without ever reaching the delete, which is exactly the
--     case this feature exists for. Sweep with
--         SELECT public.prune_expired_lg_checkpoints();
--     from pg_cron or the existing Celery beat schedule.

-- ---------------------------------------------------------------------------
-- checkpoints
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.noesis_lg_checkpoints (
    thread_id            TEXT NOT NULL,
    checkpoint_ns        TEXT NOT NULL DEFAULT '',
    checkpoint_id        TEXT NOT NULL,
    parent_checkpoint_id TEXT,
    -- Serializer tag from LangGraph's JsonPlusSerializer (e.g. 'msgpack'), needed
    -- to round-trip the payload back through loads_typed().
    type                 TEXT NOT NULL,
    checkpoint           BYTEA NOT NULL,
    metadata             JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Channels stripped before serialization; the resume path REQUIRES every one
    -- of these to be re-supplied and refuses to run if any is missing, so a
    -- scrubbed checkpoint can never be silently resumed with an empty manuscript.
    scrubbed_channels    JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- SHA-256 of `checkpoint`. Verified on read: a truncated or torn row is
    -- rejected as corrupt instead of being deserialized into partial state.
    payload_sha256       TEXT NOT NULL,
    user_id              UUID,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at           TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);

CREATE INDEX IF NOT EXISTS idx_noesis_lg_checkpoints_thread
    ON public.noesis_lg_checkpoints (thread_id, checkpoint_ns, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_noesis_lg_checkpoints_expires
    ON public.noesis_lg_checkpoints (expires_at);

-- ---------------------------------------------------------------------------
-- checkpoint_writes
--
-- Pending writes from tasks that finished inside a superstep whose checkpoint was
-- not yet committed. Without this table a crash mid-superstep would re-run every
-- task in that superstep, which for the reviewer fan-out means re-paying for all
-- three personas because one of them failed.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS public.noesis_lg_checkpoint_writes (
    thread_id     TEXT NOT NULL,
    checkpoint_ns TEXT NOT NULL DEFAULT '',
    checkpoint_id TEXT NOT NULL,
    task_id       TEXT NOT NULL,
    idx           INTEGER NOT NULL,
    channel       TEXT NOT NULL,
    type          TEXT NOT NULL,
    blob          BYTEA NOT NULL,
    -- Manuscript keys dropped from a dict-valued write before serialization. The
    -- case that forces this to exist is LangGraph's `__start__` channel, whose
    -- single write carries the entire input state -- draft_content included --
    -- as one dict. Scrubbing only whole channels named in MANUSCRIPT_CHANNELS
    -- would leave the full manuscript inside that blob.
    scrubbed_channels JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);

CREATE INDEX IF NOT EXISTS idx_noesis_lg_checkpoint_writes_expires
    ON public.noesis_lg_checkpoint_writes (expires_at);

-- ---------------------------------------------------------------------------
-- RLS
--
-- These tables are only ever touched by the backend over a direct Postgres
-- connection using the service role, never by an end-user JWT through PostgREST.
-- RLS is enabled with no permissive policy so that an accidental anon/authenticated
-- PostgREST exposure reads zero rows rather than another user's in-flight analysis.
-- ---------------------------------------------------------------------------

ALTER TABLE public.noesis_lg_checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.noesis_lg_checkpoint_writes ENABLE ROW LEVEL SECURITY;

-- Guarded because the local eval Postgres (infra/docker-compose.yml pgvector) is a
-- plain Postgres without Supabase's `anon`/`authenticated` roles; an unguarded
-- REVOKE aborts the migration there.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON public.noesis_lg_checkpoints FROM anon;
        REVOKE ALL ON public.noesis_lg_checkpoint_writes FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON public.noesis_lg_checkpoints FROM authenticated;
        REVOKE ALL ON public.noesis_lg_checkpoint_writes FROM authenticated;
    END IF;
END
$$;

-- ---------------------------------------------------------------------------
-- TTL sweep
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.prune_expired_lg_checkpoints()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    removed INTEGER;
BEGIN
    DELETE FROM public.noesis_lg_checkpoint_writes WHERE expires_at < now();
    DELETE FROM public.noesis_lg_checkpoints WHERE expires_at < now();
    GET DIAGNOSTICS removed = ROW_COUNT;
    RETURN removed;
END;
$$;
