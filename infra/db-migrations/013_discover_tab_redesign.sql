-- Migration 013: Discover Tab Redesign
-- Adds discovery_type, search_query, bib_saved columns to paper_recommendations

ALTER TABLE paper_recommendations
  ADD COLUMN IF NOT EXISTS discovery_type TEXT DEFAULT 'recommended';
  -- 'recommended' (Find Papers button) | 'searched' (search bar)

ALTER TABLE paper_recommendations
  ADD COLUMN IF NOT EXISTS search_query TEXT DEFAULT NULL;

ALTER TABLE paper_recommendations
  ADD COLUMN IF NOT EXISTS bib_saved BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_paper_recs_discovery_type
  ON paper_recommendations(discovery_type, project_id);
