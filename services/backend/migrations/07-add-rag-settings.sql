-- ============================================
-- ADD RAG SETTINGS TO PROJECTS TABLE
-- ============================================
-- This migration adds configurable RAG settings per project

ALTER TABLE projects
ADD COLUMN IF NOT EXISTS rag_settings JSONB DEFAULT jsonb_build_object(
  'chunk_size', 1000,
  'chunk_overlap', 150,
  'embedding_model', 'text-embedding-3-small',
  'max_chunks', 5,
  'similarity_threshold', 0.0
);

-- Add comment for documentation
COMMENT ON COLUMN projects.rag_settings IS 'Per-project RAG configuration: chunk_size (200-2000), chunk_overlap (0-200), embedding_model (text-embedding-3-small/large), max_chunks (1-20), similarity_threshold (0.0-1.0)';

-- Create index for faster access
CREATE INDEX IF NOT EXISTS idx_projects_rag_settings ON projects USING gin (rag_settings);
