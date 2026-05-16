-- 021_reviewer_panel.sql
-- Peer review panel tables: per-reviewer structured outputs + meta-review
-- Apply in Supabase SQL editor.

-- Per-reviewer structured outputs (4 rows per draft analysis)
CREATE TABLE IF NOT EXISTS reviewer_panel_outputs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES drafts(id) ON DELETE CASCADE,
    reviewer_id TEXT NOT NULL CHECK (reviewer_id IN ('novelty','methodology','coverage','clarity')),
    summary TEXT,
    strengths JSONB DEFAULT '[]',
    weaknesses JSONB DEFAULT '[]',
    questions_to_authors JSONB DEFAULT '[]',
    limitations_to_address JSONB DEFAULT '[]',
    rating INT CHECK (rating BETWEEN 1 AND 10),
    confidence INT CHECK (confidence BETWEEN 1 AND 5),
    recommendation TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE (draft_id, reviewer_id)
);

-- Meta-review / area chair output (1 row per draft analysis)
CREATE TABLE IF NOT EXISTS meta_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES drafts(id) ON DELETE CASCADE UNIQUE,
    overall_recommendation TEXT,
    decision_rationale TEXT,
    must_address JSONB DEFAULT '[]',
    nice_to_address JSONB DEFAULT '[]',
    consensus_strengths JSONB DEFAULT '[]',
    consensus_weaknesses JSONB DEFAULT '[]',
    reviewer_agreement_level TEXT,
    score_summary JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- reviewer_id column on existing reviewer_feedback for panel source tracking
ALTER TABLE reviewer_feedback
    ADD COLUMN IF NOT EXISTS reviewer_id TEXT DEFAULT 'legacy';

-- Indexes
CREATE INDEX IF NOT EXISTS idx_reviewer_panel_outputs_draft_id ON reviewer_panel_outputs(draft_id);
CREATE INDEX IF NOT EXISTS idx_meta_reviews_draft_id ON meta_reviews(draft_id);

-- RLS
ALTER TABLE reviewer_panel_outputs ENABLE ROW LEVEL SECURITY;
ALTER TABLE meta_reviews ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own reviewer panel outputs"
    ON reviewer_panel_outputs FOR SELECT
    USING (
        draft_id IN (SELECT id FROM drafts WHERE user_id = auth.uid())
    );

CREATE POLICY "Service role can write reviewer panel outputs"
    ON reviewer_panel_outputs FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Service role can delete reviewer panel outputs"
    ON reviewer_panel_outputs FOR DELETE
    USING (true);

CREATE POLICY "Users can read own meta reviews"
    ON meta_reviews FOR SELECT
    USING (
        draft_id IN (SELECT id FROM drafts WHERE user_id = auth.uid())
    );

CREATE POLICY "Service role can write meta reviews"
    ON meta_reviews FOR INSERT
    WITH CHECK (true);
