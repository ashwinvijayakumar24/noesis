-- Migration 011: Shared Paper Cache
-- Global cache of scholarly papers discoverable across all users.
-- Papers are fetched once from external APIs (Semantic Scholar, OpenAlex, arXiv)
-- and reused so every user benefits from prior fetches.
--
-- Run on Supabase BEFORE deploying backend changes.

-- Enable pgvector if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- Create shared_papers table
CREATE TABLE IF NOT EXISTS shared_papers (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

  -- Identifiers (any can be null, at least one should be present)
  doi TEXT UNIQUE,
  arxiv_id TEXT UNIQUE,
  pubmed_id TEXT UNIQUE,
  semantic_scholar_id TEXT UNIQUE,
  openalex_id TEXT UNIQUE,

  -- Core metadata
  title TEXT NOT NULL,
  authors JSONB DEFAULT '[]'::jsonb,  -- List of author name strings
  year INTEGER,
  abstract TEXT,
  journal TEXT,

  -- Open-access PDF
  pdf_url TEXT,           -- Open-access PDF URL (arXiv, Unpaywall, OpenAlex OA)
  full_text TEXT,         -- Extracted text (GROBID-processed or abstract-only)

  -- AI analysis (reused across users)
  analysis JSONB,         -- Our GPT-5.2 analysis (executive_summary, key_findings, etc.)

  -- Embeddings for semantic search (text-embedding-3-small = 1536 dims)
  embedding VECTOR(1536),

  -- Source and usage tracking
  source TEXT NOT NULL DEFAULT 'unknown',  -- 'arxiv'|'pubmed'|'semantic_scholar'|'openalex'|'user_upload'
  download_count INTEGER NOT NULL DEFAULT 0,
  last_accessed TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Indexes
CREATE INDEX IF NOT EXISTS shared_papers_embedding_idx
  ON shared_papers USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE INDEX IF NOT EXISTS shared_papers_doi_idx
  ON shared_papers (doi)
  WHERE doi IS NOT NULL;

CREATE INDEX IF NOT EXISTS shared_papers_arxiv_idx
  ON shared_papers (arxiv_id)
  WHERE arxiv_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS shared_papers_year_idx
  ON shared_papers (year)
  WHERE year IS NOT NULL;

CREATE INDEX IF NOT EXISTS shared_papers_source_idx
  ON shared_papers (source);

-- Full-text search on title and abstract
CREATE INDEX IF NOT EXISTS shared_papers_fts_idx
  ON shared_papers USING gin(to_tsvector('english', coalesce(title, '') || ' ' || coalesce(abstract, '')));

-- Function: search shared_papers by embedding similarity
CREATE OR REPLACE FUNCTION match_shared_papers(
  query_embedding VECTOR(1536),
  match_count INT DEFAULT 10,
  similarity_threshold FLOAT DEFAULT 0.5
)
RETURNS TABLE (
  id UUID,
  title TEXT,
  authors JSONB,
  year INTEGER,
  abstract TEXT,
  journal TEXT,
  doi TEXT,
  pdf_url TEXT,
  source TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    sp.id,
    sp.title,
    sp.authors,
    sp.year,
    sp.abstract,
    sp.journal,
    sp.doi,
    sp.pdf_url,
    sp.source,
    1 - (sp.embedding <=> query_embedding) AS similarity
  FROM shared_papers sp
  WHERE sp.embedding IS NOT NULL
    AND 1 - (sp.embedding <=> query_embedding) > similarity_threshold
  ORDER BY sp.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

-- Trigger: update updated_at on row change
CREATE OR REPLACE FUNCTION update_shared_papers_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER shared_papers_updated_at
  BEFORE UPDATE ON shared_papers
  FOR EACH ROW
  EXECUTE FUNCTION update_shared_papers_updated_at();

-- RLS: shared_papers are readable by all authenticated users, writable by service role only
ALTER TABLE shared_papers ENABLE ROW LEVEL SECURITY;

CREATE POLICY "shared_papers_read_all" ON shared_papers
  FOR SELECT
  USING (true);  -- All authenticated users can read shared papers

-- Note: INSERT/UPDATE/DELETE only via service role key (backend)
