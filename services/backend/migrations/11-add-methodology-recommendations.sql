-- Migration: Add methodology recommendations table
-- This table stores AI-generated methodology recommendations for research questions

CREATE TABLE IF NOT EXISTS methodology_recommendations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,

  -- Link to research question (optional - can be for custom questions)
  research_question_id UUID REFERENCES research_questions(id) ON DELETE CASCADE,

  -- Question content (stored for custom questions or reference)
  question TEXT NOT NULL,

  -- Methodology recommendations (JSONB for flexibility)
  recommendations JSONB NOT NULL,
  -- Structure:
  -- {
  --   "primary_methodology": {
  --     "name": "Mixed Methods Study",
  --     "fit_score": 9,
  --     "rationale": "Why this is best...",
  --     "approach": ["Step 1", "Step 2", ...],
  --     "required_resources": ["Resource 1", ...],
  --     "timeline": "6-12 months",
  --     "challenges": ["Challenge 1", ...],
  --     "example_studies": ["Paper title 1", ...]
  --   },
  --   "alternative_methodologies": [
  --     { same structure as primary }
  --   ],
  --   "data_collection": {
  --     "strategy": "Description...",
  --     "sources": ["Source 1", ...],
  --     "tools": ["Tool 1", ...]
  --   },
  --   "analysis_techniques": ["Technique 1", ...],
  --   "validation_approach": "Description..."
  -- }

  -- Metadata
  model TEXT DEFAULT 'gpt-4o',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_methodology_recommendations_project_id ON methodology_recommendations(project_id);
CREATE INDEX IF NOT EXISTS idx_methodology_recommendations_user_id ON methodology_recommendations(user_id);
CREATE INDEX IF NOT EXISTS idx_methodology_recommendations_question_id ON methodology_recommendations(research_question_id);

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_methodology_recommendations_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER methodology_recommendations_updated_at
  BEFORE UPDATE ON methodology_recommendations
  FOR EACH ROW
  EXECUTE FUNCTION update_methodology_recommendations_updated_at();
