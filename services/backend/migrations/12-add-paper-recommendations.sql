-- Migration: Add paper recommendations table
-- This table stores AI-discovered paper recommendations from external APIs

CREATE TABLE IF NOT EXISTS paper_recommendations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,

  -- Paper metadata
  title TEXT NOT NULL,
  abstract TEXT,
  authors TEXT[], -- Array of author names
  year INTEGER,

  -- External identifiers
  doi TEXT,
  arxiv_id TEXT,
  pubmed_id TEXT,
  semantic_scholar_id TEXT,

  -- Source tracking
  source TEXT NOT NULL, -- 'semantic_scholar', 'arxiv', 'pubmed'

  -- URLs
  paper_url TEXT,
  pdf_url TEXT,

  -- Metadata
  citation_count INTEGER,
  journal_name TEXT,
  publication_type TEXT,
  fields_of_study TEXT[],

  -- Recommendation context
  relevance_score FLOAT, -- 0-1 score
  relevance_reason TEXT, -- Why this paper was recommended
  matched_keywords TEXT[], -- Keywords that matched
  addresses_gaps TEXT[], -- Which research gaps this addresses

  -- User interaction
  status TEXT DEFAULT 'new' CHECK (status IN ('new', 'added', 'dismissed')),

  -- Metadata
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_paper_recommendations_project_id ON paper_recommendations(project_id);
CREATE INDEX IF NOT EXISTS idx_paper_recommendations_user_id ON paper_recommendations(user_id);
CREATE INDEX IF NOT EXISTS idx_paper_recommendations_status ON paper_recommendations(status);
CREATE INDEX IF NOT EXISTS idx_paper_recommendations_source ON paper_recommendations(source);
CREATE INDEX IF NOT EXISTS idx_paper_recommendations_doi ON paper_recommendations(doi);

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_paper_recommendations_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER paper_recommendations_updated_at
  BEFORE UPDATE ON paper_recommendations
  FOR EACH ROW
  EXECUTE FUNCTION update_paper_recommendations_updated_at();
