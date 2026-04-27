-- Migration 015: Literature Map recommendation context
-- Adds deterministic recommendation-to-gap/conflict mapping metadata.

ALTER TABLE paper_recommendations
  ADD COLUMN IF NOT EXISTS recommendation_context JSONB DEFAULT '{}'::jsonb;

UPDATE paper_recommendations
SET recommendation_context = '{}'::jsonb
WHERE recommendation_context IS NULL;

CREATE INDEX IF NOT EXISTS idx_paper_recommendations_context
  ON paper_recommendations
  USING GIN (recommendation_context);
