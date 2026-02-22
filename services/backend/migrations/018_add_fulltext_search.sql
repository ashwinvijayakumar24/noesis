-- ============================================
-- Migration 018: Add Full-Text Search for Hybrid Retrieval
-- Purpose: Enable hybrid search (semantic + keyword) for improved RAG precision
-- Date: 2026-02-20
--
-- Changes:
-- 1. Add tsvector columns for full-text search
-- 2. Create GIN indexes for fast full-text search
-- 3. Add triggers to auto-update tsvector on insert/update
-- 4. Create hybrid search RPC functions (semantic + keyword)
-- ============================================

-- ============================================
-- 1. ADD TSVECTOR COLUMNS
-- ============================================

-- Add tsvector column to document_chunks
ALTER TABLE public.document_chunks
ADD COLUMN IF NOT EXISTS content_tsv tsvector;

-- Add tsvector column to draft_chunks
ALTER TABLE public.draft_chunks
ADD COLUMN IF NOT EXISTS content_tsv tsvector;

COMMENT ON COLUMN public.document_chunks.content_tsv IS 'Full-text search vector for hybrid retrieval (semantic + keyword)';
COMMENT ON COLUMN public.draft_chunks.content_tsv IS 'Full-text search vector for hybrid retrieval (semantic + keyword)';

-- ============================================
-- 2. POPULATE TSVECTOR FOR EXISTING ROWS
-- ============================================

-- Populate tsvector for existing document_chunks
UPDATE public.document_chunks
SET content_tsv = to_tsvector('english', content)
WHERE content_tsv IS NULL;

-- Populate tsvector for existing draft_chunks
UPDATE public.draft_chunks
SET content_tsv = to_tsvector('english', content)
WHERE content_tsv IS NULL;

-- ============================================
-- 3. CREATE GIN INDEXES
-- ============================================

-- GIN index for fast full-text search on document_chunks
CREATE INDEX IF NOT EXISTS idx_document_chunks_fulltext
ON public.document_chunks USING GIN(content_tsv);

-- GIN index for fast full-text search on draft_chunks
CREATE INDEX IF NOT EXISTS idx_draft_chunks_fulltext
ON public.draft_chunks USING GIN(content_tsv);

-- ============================================
-- 4. CREATE TRIGGERS TO AUTO-UPDATE TSVECTOR
-- ============================================

-- Trigger for document_chunks
DROP TRIGGER IF EXISTS tsvector_update_document_chunks ON public.document_chunks;
CREATE TRIGGER tsvector_update_document_chunks
BEFORE INSERT OR UPDATE ON public.document_chunks
FOR EACH ROW EXECUTE FUNCTION
tsvector_update_trigger(content_tsv, 'pg_catalog.english', content);

-- Trigger for draft_chunks
DROP TRIGGER IF EXISTS tsvector_update_draft_chunks ON public.draft_chunks;
CREATE TRIGGER tsvector_update_draft_chunks
BEFORE INSERT OR UPDATE ON public.draft_chunks
FOR EACH ROW EXECUTE FUNCTION
tsvector_update_trigger(content_tsv, 'pg_catalog.english', content);

-- ============================================
-- 5. CREATE HYBRID SEARCH RPC FUNCTION FOR DOCUMENTS
-- ============================================

DROP FUNCTION IF EXISTS hybrid_search_document_chunks(text, vector, uuid, integer, float, float);

CREATE OR REPLACE FUNCTION hybrid_search_document_chunks(
  query_text TEXT,
  query_embedding VECTOR(1536),
  proj_id UUID,
  match_count INT DEFAULT 20,
  semantic_weight FLOAT DEFAULT 0.7,
  keyword_weight FLOAT DEFAULT 0.3
)
RETURNS TABLE (
  id UUID,
  document_id UUID,
  document_title TEXT,
  chunk_index INTEGER,
  content TEXT,
  semantic_similarity FLOAT,
  keyword_rank FLOAT,
  combined_score FLOAT,
  source_type TEXT,
  metadata JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  WITH semantic_results AS (
    -- Semantic search using pgvector
    SELECT
      dc.id,
      dc.document_id,
      d.title AS document_title,
      dc.chunk_index,
      dc.content,
      dc.metadata,
      (1 - (dc.embedding <=> query_embedding)) AS similarity,
      0.0 AS rank
    FROM document_chunks dc
    INNER JOIN documents d ON dc.document_id = d.id
    WHERE dc.project_id = proj_id
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count
  ),
  keyword_results AS (
    -- Keyword search using PostgreSQL full-text search
    SELECT
      dc.id,
      dc.document_id,
      d.title AS document_title,
      dc.chunk_index,
      dc.content,
      dc.metadata,
      0.0 AS similarity,
      ts_rank(dc.content_tsv, plainto_tsquery('english', query_text)) AS rank
    FROM document_chunks dc
    INNER JOIN documents d ON dc.document_id = d.id
    WHERE dc.project_id = proj_id
      AND dc.content_tsv @@ plainto_tsquery('english', query_text)
    ORDER BY ts_rank(dc.content_tsv, plainto_tsquery('english', query_text)) DESC
    LIMIT match_count
  ),
  combined_results AS (
    -- Combine semantic and keyword results
    SELECT
      COALESCE(s.id, k.id) AS id,
      COALESCE(s.document_id, k.document_id) AS document_id,
      COALESCE(s.document_title, k.document_title) AS document_title,
      COALESCE(s.chunk_index, k.chunk_index) AS chunk_index,
      COALESCE(s.content, k.content) AS content,
      COALESCE(s.metadata, k.metadata) AS metadata,
      COALESCE(s.similarity, 0.0) AS semantic_similarity,
      COALESCE(k.rank, 0.0) AS keyword_rank,
      (COALESCE(s.similarity, 0.0) * semantic_weight +
       COALESCE(k.rank, 0.0) * keyword_weight) AS combined_score
    FROM semantic_results s
    FULL OUTER JOIN keyword_results k ON s.id = k.id
  )
  SELECT
    cr.id,
    cr.document_id,
    cr.document_title,
    cr.chunk_index,
    cr.content,
    cr.semantic_similarity,
    cr.keyword_rank,
    cr.combined_score,
    'literature'::TEXT AS source_type,
    cr.metadata
  FROM combined_results cr
  ORDER BY cr.combined_score DESC
  LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION hybrid_search_document_chunks IS 'Hybrid search combining semantic (pgvector) and keyword (full-text) search for improved RAG precision';

-- ============================================
-- 6. CREATE HYBRID SEARCH RPC FUNCTION FOR DRAFTS
-- ============================================

DROP FUNCTION IF EXISTS hybrid_search_draft_chunks(text, vector, uuid, integer, float, float);

CREATE OR REPLACE FUNCTION hybrid_search_draft_chunks(
  query_text TEXT,
  query_embedding VECTOR(1536),
  proj_id UUID,
  match_count INT DEFAULT 20,
  semantic_weight FLOAT DEFAULT 0.7,
  keyword_weight FLOAT DEFAULT 0.3
)
RETURNS TABLE (
  id UUID,
  draft_id UUID,
  draft_title TEXT,
  chunk_index INTEGER,
  content TEXT,
  semantic_similarity FLOAT,
  keyword_rank FLOAT,
  combined_score FLOAT,
  source_type TEXT,
  metadata JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  WITH semantic_results AS (
    -- Semantic search using pgvector
    SELECT
      dc.id,
      dc.draft_id,
      d.title AS draft_title,
      dc.chunk_index,
      dc.content,
      dc.metadata,
      (1 - (dc.embedding <=> query_embedding)) AS similarity,
      0.0 AS rank
    FROM draft_chunks dc
    INNER JOIN drafts d ON dc.draft_id = d.id
    WHERE dc.project_id = proj_id
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count
  ),
  keyword_results AS (
    -- Keyword search using PostgreSQL full-text search
    SELECT
      dc.id,
      dc.draft_id,
      d.title AS draft_title,
      dc.chunk_index,
      dc.content,
      dc.metadata,
      0.0 AS similarity,
      ts_rank(dc.content_tsv, plainto_tsquery('english', query_text)) AS rank
    FROM draft_chunks dc
    INNER JOIN drafts d ON dc.draft_id = d.id
    WHERE dc.project_id = proj_id
      AND dc.content_tsv @@ plainto_tsquery('english', query_text)
    ORDER BY ts_rank(dc.content_tsv, plainto_tsquery('english', query_text)) DESC
    LIMIT match_count
  ),
  combined_results AS (
    -- Combine semantic and keyword results
    SELECT
      COALESCE(s.id, k.id) AS id,
      COALESCE(s.draft_id, k.draft_id) AS draft_id,
      COALESCE(s.draft_title, k.draft_title) AS draft_title,
      COALESCE(s.chunk_index, k.chunk_index) AS chunk_index,
      COALESCE(s.content, k.content) AS content,
      COALESCE(s.metadata, k.metadata) AS metadata,
      COALESCE(s.similarity, 0.0) AS semantic_similarity,
      COALESCE(k.rank, 0.0) AS keyword_rank,
      (COALESCE(s.similarity, 0.0) * semantic_weight +
       COALESCE(k.rank, 0.0) * keyword_weight) AS combined_score
    FROM semantic_results s
    FULL OUTER JOIN keyword_results k ON s.id = k.id
  )
  SELECT
    cr.id,
    cr.draft_id,
    cr.draft_title,
    cr.chunk_index,
    cr.content,
    cr.semantic_similarity,
    cr.keyword_rank,
    cr.combined_score,
    'draft'::TEXT AS source_type,
    cr.metadata
  FROM combined_results cr
  ORDER BY cr.combined_score DESC
  LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION hybrid_search_draft_chunks IS 'Hybrid search for drafts combining semantic and keyword search';

-- ============================================
-- 7. CREATE UNIFIED HYBRID SEARCH FUNCTION
-- ============================================

DROP FUNCTION IF EXISTS hybrid_search_project_content(text, vector, uuid, integer, boolean, boolean, uuid, float, float);

CREATE OR REPLACE FUNCTION hybrid_search_project_content(
  query_text TEXT,
  query_embedding VECTOR(1536),
  proj_id UUID,
  match_count INT DEFAULT 20,
  include_drafts BOOLEAN DEFAULT TRUE,
  include_literature BOOLEAN DEFAULT TRUE,
  specific_draft_id UUID DEFAULT NULL,
  semantic_weight FLOAT DEFAULT 0.7,
  keyword_weight FLOAT DEFAULT 0.3
)
RETURNS TABLE (
  id UUID,
  source_id UUID,
  source_title TEXT,
  chunk_index INTEGER,
  content TEXT,
  semantic_similarity FLOAT,
  keyword_rank FLOAT,
  combined_score FLOAT,
  source_type TEXT,
  metadata JSONB
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY

  -- Get results from both documents and drafts, then combine
  WITH all_results AS (
    -- Document chunks (if include_literature = true)
    SELECT
      doc_results.id,
      doc_results.document_id AS source_id,
      doc_results.document_title AS source_title,
      doc_results.chunk_index,
      doc_results.content,
      doc_results.semantic_similarity,
      doc_results.keyword_rank,
      doc_results.combined_score,
      doc_results.source_type,
      doc_results.metadata
    FROM hybrid_search_document_chunks(
      query_text,
      query_embedding,
      proj_id,
      match_count,
      semantic_weight,
      keyword_weight
    ) AS doc_results
    WHERE include_literature = TRUE

    UNION ALL

    -- Draft chunks (if include_drafts = true)
    SELECT
      draft_results.id,
      draft_results.draft_id AS source_id,
      draft_results.draft_title AS source_title,
      draft_results.chunk_index,
      draft_results.content,
      draft_results.semantic_similarity,
      draft_results.keyword_rank,
      draft_results.combined_score,
      draft_results.source_type,
      draft_results.metadata
    FROM hybrid_search_draft_chunks(
      query_text,
      query_embedding,
      proj_id,
      match_count,
      semantic_weight,
      keyword_weight
    ) AS draft_results
    WHERE include_drafts = TRUE
      AND (specific_draft_id IS NULL OR draft_results.draft_id = specific_draft_id)
  )

  SELECT
    ar.id,
    ar.source_id,
    ar.source_title,
    ar.chunk_index,
    ar.content,
    ar.semantic_similarity,
    ar.keyword_rank,
    ar.combined_score,
    ar.source_type,
    ar.metadata
  FROM all_results ar
  ORDER BY ar.combined_score DESC
  LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION hybrid_search_project_content IS 'Unified hybrid search across both documents and drafts with configurable inclusion';

-- ============================================
-- 8. VERIFY MIGRATION
-- ============================================

DO $$
DECLARE
    v_doc_chunks_count INTEGER;
    v_draft_chunks_count INTEGER;
    v_doc_tsv_count INTEGER;
    v_draft_tsv_count INTEGER;
BEGIN
    -- Count chunks
    SELECT COUNT(*) INTO v_doc_chunks_count FROM public.document_chunks;
    SELECT COUNT(*) INTO v_draft_chunks_count FROM public.draft_chunks;

    -- Count populated tsvectors
    SELECT COUNT(*) INTO v_doc_tsv_count FROM public.document_chunks WHERE content_tsv IS NOT NULL;
    SELECT COUNT(*) INTO v_draft_tsv_count FROM public.draft_chunks WHERE content_tsv IS NOT NULL;

    RAISE NOTICE 'Migration 018 complete:';
    RAISE NOTICE '- Added content_tsv columns to document_chunks and draft_chunks';
    RAISE NOTICE '- Created GIN indexes for full-text search';
    RAISE NOTICE '- Created triggers for auto-update';
    RAISE NOTICE '- Created 3 hybrid search RPC functions';
    RAISE NOTICE '- Document chunks: % total, % with tsvector', v_doc_chunks_count, v_doc_tsv_count;
    RAISE NOTICE '- Draft chunks: % total, % with tsvector', v_draft_chunks_count, v_draft_tsv_count;
    RAISE NOTICE '- Hybrid search ready: semantic (pgvector) + keyword (full-text)';
END $$;
