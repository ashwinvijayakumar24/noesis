-- ================================
-- Migration 002: Full-Text Search for Hybrid RAG
-- Purpose: Add PostgreSQL FTS capabilities for keyword search
-- ================================

-- Add tsvector column for full-text search on document_chunks
ALTER TABLE document_chunks
ADD COLUMN IF NOT EXISTS content_tsvector tsvector;

-- Update existing rows with tsvector
UPDATE document_chunks
SET content_tsvector = to_tsvector('english', content);

-- Create GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_document_chunks_fts
ON document_chunks USING GIN(content_tsvector);

-- Create trigger to auto-update tsvector on insert/update
CREATE OR REPLACE FUNCTION update_document_chunks_tsvector()
RETURNS trigger AS $$
BEGIN
    NEW.content_tsvector := to_tsvector('english', NEW.content);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS tsvector_update ON document_chunks;
CREATE TRIGGER tsvector_update
BEFORE INSERT OR UPDATE ON document_chunks
FOR EACH ROW EXECUTE FUNCTION update_document_chunks_tsvector();

-- Same for draft_chunks (uses chunk_text instead of content)
DO $$
BEGIN
    IF EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'draft_chunks') THEN
        -- Add tsvector column
        ALTER TABLE draft_chunks ADD COLUMN IF NOT EXISTS chunk_text_tsvector tsvector;

        -- Update existing rows (draft_chunks uses chunk_text, not content)
        UPDATE draft_chunks SET chunk_text_tsvector = to_tsvector('english', chunk_text);

        -- Create index
        CREATE INDEX IF NOT EXISTS idx_draft_chunks_fts ON draft_chunks USING GIN(chunk_text_tsvector);

        -- Create trigger function
        CREATE OR REPLACE FUNCTION update_draft_chunks_tsvector()
        RETURNS trigger AS $func$
        BEGIN
            NEW.chunk_text_tsvector := to_tsvector('english', NEW.chunk_text);
            RETURN NEW;
        END;
        $func$ LANGUAGE plpgsql;

        -- Create trigger
        DROP TRIGGER IF EXISTS draft_tsvector_update ON draft_chunks;
        CREATE TRIGGER draft_tsvector_update
        BEFORE INSERT OR UPDATE ON draft_chunks
        FOR EACH ROW EXECUTE FUNCTION update_draft_chunks_tsvector();
    END IF;
END $$;

-- ================================
-- Keyword Search Function
-- ================================

CREATE OR REPLACE FUNCTION keyword_search_chunks(
    proj_id UUID,
    search_query TEXT,
    match_count INTEGER DEFAULT 20
)
RETURNS TABLE (
    id UUID,
    document_id UUID,
    content TEXT,
    metadata JSONB,
    rank REAL
) AS $$
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
$$ LANGUAGE plpgsql;

-- Keyword search function for draft chunks
CREATE OR REPLACE FUNCTION keyword_search_draft_chunks(
    proj_id UUID,
    search_query TEXT,
    match_count INTEGER DEFAULT 20
)
RETURNS TABLE (
    id UUID,
    draft_id UUID,
    chunk_text TEXT,
    section_name TEXT,
    rank REAL
) AS $$
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
$$ LANGUAGE plpgsql;
