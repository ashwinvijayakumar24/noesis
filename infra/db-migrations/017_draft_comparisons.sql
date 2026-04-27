-- ================================
-- Migration 017: Draft Comparison System
-- Purpose: Compare draft versions side-by-side
-- ================================

CREATE TABLE IF NOT EXISTS draft_comparisons (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    draft_v1_id UUID NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    draft_v2_id UUID NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,

    -- Comparison results
    comparison_result JSONB,
    improvement_score NUMERIC,  -- Overall improvement score (0-100)

    -- Summary stats
    claims_added INTEGER DEFAULT 0,
    claims_removed INTEGER DEFAULT 0,
    claims_improved INTEGER DEFAULT 0,
    claims_worsened INTEGER DEFAULT 0,
    feedback_addressed INTEGER DEFAULT 0,
    gaps_resolved INTEGER DEFAULT 0,

    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_comparisons_project ON draft_comparisons(project_id);
CREATE INDEX IF NOT EXISTS idx_comparisons_user ON draft_comparisons(user_id);
CREATE INDEX IF NOT EXISTS idx_comparisons_drafts ON draft_comparisons(draft_v1_id, draft_v2_id);

-- RLS policies
ALTER TABLE draft_comparisons ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own comparisons"
ON draft_comparisons FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own comparisons"
ON draft_comparisons FOR INSERT
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete their own comparisons"
ON draft_comparisons FOR DELETE
USING (auth.uid() = user_id);
