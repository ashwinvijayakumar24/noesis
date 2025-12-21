-- Migration: Add research questions table
-- This table stores AI-generated research questions based on project insights

CREATE TABLE IF NOT EXISTS research_questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  user_id UUID NOT NULL,

  -- Question content
  question TEXT NOT NULL,
  rationale TEXT NOT NULL,
  suggested_methodology TEXT,
  gap_category TEXT, -- 'methodological', 'population', 'theoretical', 'temporal', or NULL

  -- User interaction
  status TEXT DEFAULT 'new' CHECK (status IN ('new', 'exploring', 'answered')),
  notes TEXT,

  -- Metadata
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_research_questions_project_id ON research_questions(project_id);
CREATE INDEX IF NOT EXISTS idx_research_questions_user_id ON research_questions(user_id);
CREATE INDEX IF NOT EXISTS idx_research_questions_status ON research_questions(status);
CREATE INDEX IF NOT EXISTS idx_research_questions_gap_category ON research_questions(gap_category);

-- Add trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_research_questions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_questions_updated_at
  BEFORE UPDATE ON research_questions
  FOR EACH ROW
  EXECUTE FUNCTION update_research_questions_updated_at();
