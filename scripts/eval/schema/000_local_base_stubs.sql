-- ###########################################################################
-- ##  EVAL-LOCAL STUBS — NOT PRODUCTION SCHEMA. NEVER APPLY TO PRODUCTION. ##
-- ###########################################################################
--
-- WHAT THIS IS: the minimum `documents` and `drafts` tables needed so that the
-- RPCs in services/backend/migrations/036_recovered_production_ddl.sql can be
-- CREATEd on a FRESH local Postgres.
--
-- WHY IT EXISTS: 036 is a documentation-of-record of production's retrieval
-- layer. It assumes migrations 001-035 already ran, so it never declares
-- `documents` or `drafts` — but three of its functions join against them:
--   * match_document_chunks         -> JOIN documents
--   * match_single_document_chunks  -> JOIN documents
--   * match_project_content         -> JOIN documents, JOIN drafts
-- plpgsql function bodies are parsed at CREATE time in PostgreSQL, so without
-- these tables 036 fails with `relation "documents" does not exist`.
--
-- WHY IT IS NOT IN A MIGRATION: putting local scaffolding into the
-- services/backend/migrations/ sequence would make a production-facing
-- migration file lie about the production schema. These stubs are a local
-- test fixture, so they live under the eval harness.
--
-- THE REAL `documents` / `drafts` TABLES HAVE MANY MORE COLUMNS. Only the
-- columns the recovered RPCs actually reference are reproduced here:
-- `id` (join key), `title` (selected as document_title / source_title), and
-- `project_id` (filter in match_project_content). Do not treat this file as a
-- description of production. If you need real columns, read migrations 001-035.
--
-- APPLY ORDER on a fresh local DB:
--   1. scripts/eval/schema/000_local_base_stubs.sql   <- this file
--   2. services/backend/migrations/036_recovered_production_ddl.sql
--   3. services/backend/migrations/037_fix_keyword_search_chunks.sql
--
-- Idempotent.

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid() on non-Supabase PG

CREATE TABLE IF NOT EXISTS public.documents (
    id         uuid NOT NULL DEFAULT gen_random_uuid(),
    title      text NULL,
    project_id uuid NULL,
    CONSTRAINT documents_pkey PRIMARY KEY (id)
);

CREATE TABLE IF NOT EXISTS public.drafts (
    id         uuid NOT NULL DEFAULT gen_random_uuid(),
    title      text NULL,
    project_id uuid NULL,
    CONSTRAINT drafts_pkey PRIMARY KEY (id)
);
