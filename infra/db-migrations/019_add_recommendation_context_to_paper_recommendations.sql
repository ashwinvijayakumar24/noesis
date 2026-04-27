-- Add recommendation_context JSONB column to paper_recommendations table.
-- Stores gap_titles and conflict_topics for grouping recommendations in the Literature Map.
ALTER TABLE paper_recommendations ADD COLUMN IF NOT EXISTS recommendation_context jsonb;
