-- 037_fix_keyword_search_chunks.sql
-- FIX FOR A LIVE PRODUCTION BUG recorded in 036_recovered_production_ddl.sql.
--
-- THE BUG
--   public.keyword_search_chunks selected `dc.metadata` from public.document_chunks,
--   but document_chunks HAS NO `metadata` column (verified against live production on
--   2026-07-30; see the table definition in 036). plpgsql resolves the query when the
--   RETURN QUERY statement first executes, so every single call raised:
--
--       ERROR: 42703: column dc.metadata does not exist
--
--   Reproduced locally against pgvector/pgvector:pg17 with 036 applied:
--       SELECT * FROM keyword_search_chunks('<uuid>', 'transformer', 5);
--       ERROR:  column dc.metadata does not exist
--       LINE 5:         dc.metadata,
--       CONTEXT: PL/pgSQL function keyword_search_chunks(uuid,text,integer) line 3
--
-- THE IMPACT
--   app/services/rag_retrieval.py::keyword_search (lines ~372-385) wraps the RPC call
--   in a bare `except` that returns [] with the comment "Some deployed schemas only
--   have vector search RPCs". So the 42703 was swallowed silently and the keyword leg
--   of hybrid_search (rag_retrieval.py:413-502) has ALWAYS returned ZERO ROWS in
--   production. hybrid_search advertises a 0.7 * semantic + 0.3 * keyword fusion
--   (lines 486-489); with keyword_results always empty, every keyword_score is 0.0 and
--   the ranking has been pure semantic search, scaled by 0.7, for the entire life of
--   the feature. This migration is what makes the keyword leg return rows at all.
--
-- WHY `CREATE OR REPLACE` IS NOT ENOUGH — WHY THE DROP IS REQUIRED
--   The fix removes `metadata jsonb` from the RETURNS TABLE signature. PostgreSQL
--   treats RETURNS TABLE columns as part of the function's result type and refuses to
--   change them in place:
--       ERROR: 42P13: cannot change return type of existing function
--       HINT:  Use DROP FUNCTION keyword_search_chunks(uuid,text,integer) first.
--   Argument types are unchanged (uuid, text, integer), so the DROP targets that exact
--   signature and cannot accidentally remove an unrelated overload.
--
-- WHY NOT KEEP A SYNTHETIC `metadata` COLUMN
--   Considered and rejected. Padding the return type with a fabricated jsonb (e.g.
--   jsonb_build_object('chunk_index', dc.chunk_index)) would preserve a shape no caller
--   ever consumed and would invent data that does not exist in the table. Callers should
--   depend on real columns instead.
--
-- CALLER IMPACT: NONE. The only caller in the repo is
--   app/services/rag_retrieval.py::keyword_search, which returns `response.data`
--   verbatim to hybrid_search. hybrid_search reads exactly two keys off each keyword
--   row — chunk.get("id") (line ~469) and chunk.get("rank") (line ~477) — both of which
--   this function still returns. Nothing in the repo reads `metadata` off a
--   keyword_search_chunks row (grep for keyword_search_chunks: one hit, rag_retrieval.py:374).
--   No application change is required by this migration. rag_retrieval.py is deliberately
--   NOT touched here; the bare `except` there stays as a safety net, but it should stop
--   firing once this is applied.
--
-- Idempotent: DROP ... IF EXISTS followed by CREATE OR REPLACE. Safe to re-run.
-- Apply after 036. Apply in the Supabase SQL editor, or `psql -f` locally.

DROP FUNCTION IF EXISTS public.keyword_search_chunks(uuid, text, integer);

CREATE OR REPLACE FUNCTION public.keyword_search_chunks(proj_id uuid, search_query text, match_count integer DEFAULT 20)
RETURNS TABLE(id uuid, document_id uuid, content text, rank real)
LANGUAGE plpgsql
AS $function$
BEGIN
    RETURN QUERY
    SELECT
        dc.id,
        dc.document_id,
        dc.content,
        ts_rank(dc.content_tsvector, plainto_tsquery('english', search_query)) as rank
    FROM document_chunks dc
    WHERE dc.project_id = proj_id
      AND dc.content_tsvector @@ plainto_tsquery('english', search_query)
    ORDER BY rank DESC
    LIMIT match_count;
END;
$function$;
