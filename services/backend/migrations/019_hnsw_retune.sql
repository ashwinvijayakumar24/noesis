-- 019_hnsw_retune.sql
-- Migrate document_claims from IVFFLAT → HNSW (matches document_chunks, draft_chunks)
-- Also tune ef_search=80 inside the vector search functions.
-- Run during off-hours — CREATE INDEX is not yet concurrent for HNSW in pgvector.

-- Step 1: drop old IVFFLAT index
DROP INDEX IF EXISTS idx_document_claims_embedding;

-- Step 2: create HNSW with tuned parameters
-- m=24 (denser graph → better recall at cost of ~50% more memory)
-- ef_construction=128 (more candidates during build → better index quality)
CREATE INDEX idx_document_claims_embedding_hnsw ON document_claims
USING hnsw (embedding vector_cosine_ops)
WITH (m = 24, ef_construction = 128);

-- Step 3: retune match_document_chunks to set ef_search before each query
-- ef_search=80 raises recall ~3-5% vs default 40, adds ~15ms per query
CREATE OR REPLACE FUNCTION match_document_chunks(
  query_embedding VECTOR(1536),
  proj_id UUID,
  match_count INT DEFAULT 5
)
RETURNS TABLE (
  id UUID,
  document_id UUID,
  document_title TEXT,
  chunk_index INTEGER,
  content TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
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
$$;

-- Step 4: same ef_search tune on the single-document variant
CREATE OR REPLACE FUNCTION match_single_document_chunks(
  query_embedding VECTOR(1536),
  doc_id UUID,
  match_count INT DEFAULT 5
)
RETURNS TABLE (
  id UUID,
  document_id UUID,
  document_title TEXT,
  chunk_index INTEGER,
  content TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
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
$$;
