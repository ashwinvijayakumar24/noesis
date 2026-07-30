-- 036_recovered_production_ddl.sql
-- DOCUMENTATION OF PRODUCTION REALITY — recovered by live introspection on 2026-07-30.
--
-- WHY THIS FILE EXISTS: the entire vector/retrieval layer (chunk tables, HNSW + GIN
-- indexes, and the similarity RPCs) was never checked into version control. It was
-- created by hand in the Supabase SQL editor and existed ONLY in production. See
-- 034_document_domain.sql lines 7-9, which explicitly admits this ("defined directly in
-- Supabase (not tracked in this repo)"). This migration checks those objects in as a
-- documentation-of-record so the repo finally contains its own retrieval layer, and so a
-- fresh local Postgres can reproduce production.
--
-- Source: PostgreSQL 17.6 (Supabase), production, 2026-07-30. Column lists come from
-- information_schema, index definitions verbatim from pg_indexes, and the six functions
-- verbatim from pg_get_functiondef.
--
-- RETRIEVAL FACTS worth recording:
--   * Embeddings are vector(1536) (OpenAI text-embedding-3-large @ 1536 dims).
--   * Vector indexes are HNSW with vector_cosine_ops. No explicit m / ef_construction is
--     specified, so production runs on pgvector DEFAULTS: m = 16, ef_construction = 64.
--   * Distance operator is `<=>` (cosine distance). Similarity is returned as
--     `1 - (embedding <=> query_embedding)`, i.e. bounded to [0, 1] for non-negative
--     cosine similarity.
--   * Query-time `hnsw.ef_search` is set to 80 INSIDE two of the RPCs
--     (match_document_chunks, match_single_document_chunks) via SET LOCAL. The other four
--     functions do not touch ef_search and therefore run at the session default (40).
--
-- KNOWN PRODUCTION BUG reproduced faithfully below: `keyword_search_chunks` references a
-- `document_chunks.metadata` column that does not exist. See the marked comment block
-- above function 4. It is deliberately NOT fixed here.
--
-- Idempotent: safe to apply to production (no-ops) or to a fresh local Postgres.
-- Apply in the Supabase SQL editor, or `psql -f` locally.
--
-- CAVEAT: the introspection captured columns, indexes and functions. Foreign keys, RLS
-- policies, grants and triggers on these tables were NOT captured and are therefore NOT
-- reproduced here. This file is a retrieval-layer record, not a full schema dump.

-- ---------------------------------------------------------------------------
-- 1. Extension
-- ---------------------------------------------------------------------------

CREATE EXTENSION IF NOT EXISTS vector;

-- ---------------------------------------------------------------------------
-- 2. Tables
-- ---------------------------------------------------------------------------

-- Literature chunks: one row per chunk of an uploaded/resolved source document.
CREATE TABLE IF NOT EXISTS public.document_chunks (
    id               uuid        NOT NULL DEFAULT gen_random_uuid(),
    document_id      uuid        NULL,
    project_id       uuid        NULL,
    chunk_index      integer     NOT NULL,
    content          text        NOT NULL,
    embedding        vector(1536) NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    content_tsvector tsvector    NULL,
    CONSTRAINT document_chunks_pkey PRIMARY KEY (id)
);
-- NOTE: there is NO `metadata` column on document_chunks in production. This is not an
-- omission in this file — see the bug block above function 4.

-- Manuscript chunks: one row per chunk of a user's own draft.
CREATE TABLE IF NOT EXISTS public.draft_chunks (
    id                  uuid        NOT NULL DEFAULT gen_random_uuid(),
    draft_id            uuid        NOT NULL,
    project_id          uuid        NOT NULL,
    chunk_text          text        NOT NULL,
    chunk_index         integer     NOT NULL,
    section_name        text        NULL,
    embedding           vector(1536) NULL,
    created_at          timestamptz NULL DEFAULT now(),
    chunk_text_tsvector tsvector    NULL,
    CONSTRAINT draft_chunks_pkey PRIMARY KEY (id)
);

-- Extracted claims per source document (used by find_similar_claims / contradiction work).
CREATE TABLE IF NOT EXISTS public.document_claims (
    id                      uuid         NOT NULL DEFAULT gen_random_uuid(),
    document_id             uuid         NOT NULL,
    project_id              uuid         NOT NULL,
    claim_text              text         NOT NULL,
    claim_type              varchar      NOT NULL,
    section_title           varchar      NULL,
    section_type            varchar      NULL,
    page_number             integer      NULL,
    importance_score        numeric      NULL,
    confidence_score        numeric      NULL,
    supports_primary_thesis boolean      NULL DEFAULT false,
    embedding               vector(1536) NULL,
    created_at              timestamptz  NULL DEFAULT now(),
    updated_at              timestamptz  NULL DEFAULT now(),
    CONSTRAINT document_claims_pkey PRIMARY KEY (id)
);

-- ---------------------------------------------------------------------------
-- 3. Indexes (verbatim from pg_indexes, minus the pkey indexes which are declared
--    as PRIMARY KEY constraints above)
-- ---------------------------------------------------------------------------

CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id
    ON public.document_chunks USING btree (document_id);

CREATE INDEX IF NOT EXISTS idx_document_chunks_project_id
    ON public.document_chunks USING btree (project_id);

-- HNSW, cosine, pgvector defaults (m=16, ef_construction=64).
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
    ON public.document_chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_document_chunks_fts
    ON public.document_chunks USING gin (content_tsvector);

CREATE INDEX IF NOT EXISTS idx_draft_chunks_draft_id
    ON public.draft_chunks USING btree (draft_id);

CREATE INDEX IF NOT EXISTS idx_draft_chunks_project_id
    ON public.draft_chunks USING btree (project_id);

-- HNSW, cosine, pgvector defaults (m=16, ef_construction=64).
CREATE INDEX IF NOT EXISTS idx_draft_chunks_embedding
    ON public.draft_chunks USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_draft_chunks_fts
    ON public.draft_chunks USING gin (chunk_text_tsvector);

-- NOTE: production has NO index on document_claims.embedding. find_similar_claims
-- therefore does a sequential scan with exact cosine distance. Recorded, not changed.

-- ---------------------------------------------------------------------------
-- 4. Functions (verbatim pg_get_functiondef output, six total)
-- ---------------------------------------------------------------------------

-- (1) Project-scoped semantic search over literature chunks. Sets ef_search = 80.
CREATE OR REPLACE FUNCTION public.match_document_chunks(query_embedding vector, proj_id uuid, match_count integer DEFAULT 5)
RETURNS TABLE(id uuid, document_id uuid, document_title text, chunk_index integer, content text, similarity double precision)
LANGUAGE plpgsql
AS $function$
BEGIN
  SET LOCAL hnsw.ef_search = 80;
  RETURN QUERY
  SELECT
    document_chunks.id,
    document_chunks.document_id,
    documents.title AS document_title,
    document_chunks.chunk_index,
    document_chunks.content,
    1 - (document_chunks.embedding <=> query_embedding) AS similarity
  FROM document_chunks
  INNER JOIN documents ON document_chunks.document_id = documents.id
  WHERE document_chunks.project_id = proj_id
  ORDER BY document_chunks.embedding <=> query_embedding
  LIMIT match_count;
END;
$function$;

-- (2) Same, scoped to a single document. Sets ef_search = 80.
CREATE OR REPLACE FUNCTION public.match_single_document_chunks(query_embedding vector, doc_id uuid, match_count integer DEFAULT 5)
RETURNS TABLE(id uuid, document_id uuid, document_title text, chunk_index integer, content text, similarity double precision)
LANGUAGE plpgsql
AS $function$
BEGIN
  SET LOCAL hnsw.ef_search = 80;
  RETURN QUERY
  SELECT
    document_chunks.id,
    document_chunks.document_id,
    documents.title AS document_title,
    document_chunks.chunk_index,
    document_chunks.content,
    1 - (document_chunks.embedding <=> query_embedding) AS similarity
  FROM document_chunks
  INNER JOIN documents ON document_chunks.document_id = documents.id
  WHERE document_chunks.document_id = doc_id
  ORDER BY document_chunks.embedding <=> query_embedding
  LIMIT match_count;
END;
$function$;

-- (3) Unified semantic search across literature chunks AND draft chunks.
--     Does NOT set ef_search (runs at the session default of 40).
CREATE OR REPLACE FUNCTION public.match_project_content(query_embedding vector, filter_project_id uuid, match_threshold double precision DEFAULT 0.0, match_count integer DEFAULT 5, include_drafts boolean DEFAULT true, filter_draft_id uuid DEFAULT NULL::uuid)
RETURNS TABLE(id uuid, content text, similarity double precision, source_type text, source_id uuid, source_title text, metadata jsonb)
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT * FROM (
        SELECT
            dc.id,
            dc.content,
            1 - (dc.embedding <=> query_embedding) as similarity,
            'literature'::text as source_type,
            d.id as source_id,
            d.title as source_title,
            jsonb_build_object('chunk_index', dc.chunk_index, 'document_id', d.id) as metadata
        FROM document_chunks dc
        JOIN documents d ON dc.document_id = d.id
        WHERE d.project_id = filter_project_id
            AND 1 - (dc.embedding <=> query_embedding) > match_threshold

        UNION ALL

        SELECT
            drc.id,
            drc.chunk_text as content,
            1 - (drc.embedding <=> query_embedding) as similarity,
            'draft'::text as source_type,
            dr.id as source_id,
            dr.title as source_title,
            jsonb_build_object('chunk_index', drc.chunk_index, 'draft_id', dr.id) as metadata
        FROM draft_chunks drc
        JOIN drafts dr ON drc.draft_id = dr.id
        WHERE include_drafts = true
            AND dr.project_id = filter_project_id
            AND (filter_draft_id IS NULL OR dr.id = filter_draft_id)
            AND 1 - (drc.embedding <=> query_embedding) > match_threshold
    ) combined_results
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$function$;

-- ###########################################################################
-- ##  KNOWN PRODUCTION BUG — REPRODUCED AS-IS, DO NOT FIX IN THIS FILE     ##
-- ###########################################################################
--
-- `keyword_search_chunks` below selects `dc.metadata`, but public.document_chunks HAS NO
-- `metadata` COLUMN (see the table definition above — verified against live production on
-- 2026-07-30). Calling the function raises:
--
--     ERROR: 42703: column dc.metadata does not exist
--
-- CONSEQUENCE: the keyword leg of hybrid search has ALWAYS returned zero results in
-- production. app/services/rag_retrieval.py lines 382-385 wrap the RPC call in a bare
-- `except` whose comment reads "Some deployed schemas only have vector search RPCs", so
-- the error is silently swallowed and `keyword_results = []`. Therefore `hybrid_search`
-- (rag_retrieval.py:413-502) has been PURE SEMANTIC SEARCH the entire time, despite
-- claiming to fuse 0.7 * semantic + 0.3 * keyword at lines 486-489.
--
-- The fix is deliberately DEFERRED to migration 037 so that this file remains a faithful
-- record of production as of 2026-07-30. The point of this file is fidelity, not repair.
--
-- ###########################################################################

-- (4) BROKEN IN PRODUCTION — see the block above. Keyword (FTS) search over literature
--     chunks. Does NOT set ef_search (irrelevant; this leg is GIN, not HNSW).
CREATE OR REPLACE FUNCTION public.keyword_search_chunks(proj_id uuid, search_query text, match_count integer DEFAULT 20)
RETURNS TABLE(id uuid, document_id uuid, content text, metadata jsonb, rank real)
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        dc.id,
        dc.document_id,
        dc.content,
        dc.metadata,
        ts_rank(dc.content_tsvector, plainto_tsquery('english', search_query)) as rank
    FROM document_chunks dc
    WHERE dc.project_id = proj_id
      AND dc.content_tsvector @@ plainto_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_count;
END;
$function$;

-- (5) Keyword (FTS) search over draft chunks. This one is correct — draft_chunks has
--     every column it selects.
CREATE OR REPLACE FUNCTION public.keyword_search_draft_chunks(proj_id uuid, search_query text, match_count integer DEFAULT 20)
RETURNS TABLE(id uuid, draft_id uuid, chunk_text text, section_name text, rank real)
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        dc.id,
        dc.draft_id,
        dc.chunk_text,
        dc.section_name,
        ts_rank(dc.chunk_text_tsvector, plainto_tsquery('english', search_query)) as rank
    FROM draft_chunks dc
    WHERE dc.project_id = proj_id
      AND dc.chunk_text_tsvector @@ plainto_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_count;
END;
$function$;

-- (6) Cross-document near-duplicate / agreement search over extracted claims.
--     Similarity is rounded to 3 decimals and returned as numeric (not double precision).
--     No HNSW index exists on document_claims.embedding — this is a sequential scan.
CREATE OR REPLACE FUNCTION public.find_similar_claims(query_embedding vector, similarity_threshold numeric DEFAULT 0.7, max_results integer DEFAULT 10, exclude_document_id uuid DEFAULT NULL::uuid)
RETURNS TABLE(claim_id uuid, document_id uuid, claim_text text, similarity_score numeric)
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        dc.id,
        dc.document_id,
        dc.claim_text,
        ROUND((1 - (dc.embedding <=> query_embedding))::NUMERIC, 3) as similarity
    FROM document_claims dc
    WHERE (exclude_document_id IS NULL OR dc.document_id != exclude_document_id)
        AND (1 - (dc.embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY dc.embedding <=> query_embedding ASC
    LIMIT max_results;
END;
$function$;
