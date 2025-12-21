-- ============================================
-- VECTOR SIMILARITY SEARCH FUNCTION
-- ============================================
-- This function enables efficient semantic search across document chunks
-- using cosine similarity with pgvector

-- Drop existing function to allow return type change
DROP FUNCTION IF EXISTS match_document_chunks(vector, uuid, integer);

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

-- Add comment for documentation
COMMENT ON FUNCTION match_document_chunks IS 'Performs vector similarity search on document chunks within a project using cosine distance';

-- ============================================
-- SINGLE DOCUMENT VECTOR SEARCH FUNCTION
-- ============================================
-- This function searches within a single document only

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

COMMENT ON FUNCTION match_single_document_chunks IS 'Performs vector similarity search on chunks within a single document using cosine distance';
