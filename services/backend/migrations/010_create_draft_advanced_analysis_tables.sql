-- Migration: Create draft advanced analysis tables
-- Purpose: Tables for claims, coverage gaps, and reviewer feedback
-- Date: 2025-12-25

-- ============================================
-- Create draft_claims Table
-- ============================================

CREATE TABLE IF NOT EXISTS public.draft_claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,

    -- Claim Details
    claim_text TEXT NOT NULL,
    claim_type VARCHAR(50) NOT NULL CHECK (claim_type IN ('empirical', 'theoretical', 'methodological')),
    section_location TEXT,
    importance_score FLOAT CHECK (importance_score >= 0 AND importance_score <= 1),

    -- Citation Information
    requires_citation BOOLEAN DEFAULT false,
    existing_citations JSONB DEFAULT '[]'::jsonb,

    -- Metadata
    reasoning TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- Create coverage_gaps Table
-- ============================================

CREATE TABLE IF NOT EXISTS public.coverage_gaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,

    -- Gap Details
    gap_type VARCHAR(100) NOT NULL,
    description TEXT NOT NULL,
    priority VARCHAR(20) CHECK (priority IN ('high', 'medium', 'low')),

    -- Suggestions
    suggested_papers JSONB DEFAULT '[]'::jsonb,
    reasoning TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- Create reviewer_feedback Table
-- ============================================

CREATE TABLE IF NOT EXISTS public.reviewer_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,

    -- Feedback Details
    feedback_type VARCHAR(100) NOT NULL,
    feedback_text TEXT NOT NULL,
    severity VARCHAR(20) CHECK (severity IN ('critical', 'major', 'minor', 'suggestion')),
    section_reference TEXT,

    -- Additional Context
    impact_score FLOAT,
    suggestions JSONB DEFAULT '[]'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- Indexes for Performance
-- ============================================

-- draft_claims indexes
CREATE INDEX IF NOT EXISTS idx_draft_claims_draft_id ON public.draft_claims(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_claims_type ON public.draft_claims(claim_type);
CREATE INDEX IF NOT EXISTS idx_draft_claims_importance ON public.draft_claims(importance_score DESC);

-- coverage_gaps indexes
CREATE INDEX IF NOT EXISTS idx_coverage_gaps_draft_id ON public.coverage_gaps(draft_id);
CREATE INDEX IF NOT EXISTS idx_coverage_gaps_priority ON public.coverage_gaps(priority);

-- reviewer_feedback indexes
CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_draft_id ON public.reviewer_feedback(draft_id);
CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_severity ON public.reviewer_feedback(severity);

-- ============================================
-- Row Level Security (RLS)
-- ============================================

-- Enable RLS on all tables
ALTER TABLE public.draft_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.coverage_gaps ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.reviewer_feedback ENABLE ROW LEVEL SECURITY;

-- Policies for draft_claims
CREATE POLICY "Users can view their own draft claims"
ON public.draft_claims FOR SELECT TO authenticated
USING (EXISTS (SELECT 1 FROM public.drafts WHERE drafts.id = draft_claims.draft_id AND drafts.user_id = auth.uid()));

CREATE POLICY "System can insert draft claims"
ON public.draft_claims FOR INSERT TO authenticated
WITH CHECK (EXISTS (SELECT 1 FROM public.drafts WHERE drafts.id = draft_claims.draft_id AND drafts.user_id = auth.uid()));

CREATE POLICY "Users can delete their own draft claims"
ON public.draft_claims FOR DELETE TO authenticated
USING (EXISTS (SELECT 1 FROM public.drafts WHERE drafts.id = draft_claims.draft_id AND drafts.user_id = auth.uid()));

-- Policies for coverage_gaps
CREATE POLICY "Users can view their own coverage gaps"
ON public.coverage_gaps FOR SELECT TO authenticated
USING (EXISTS (SELECT 1 FROM public.drafts WHERE drafts.id = coverage_gaps.draft_id AND drafts.user_id = auth.uid()));

CREATE POLICY "System can insert coverage gaps"
ON public.coverage_gaps FOR INSERT TO authenticated
WITH CHECK (EXISTS (SELECT 1 FROM public.drafts WHERE drafts.id = coverage_gaps.draft_id AND drafts.user_id = auth.uid()));

CREATE POLICY "Users can delete their own coverage gaps"
ON public.coverage_gaps FOR DELETE TO authenticated
USING (EXISTS (SELECT 1 FROM public.drafts WHERE drafts.id = coverage_gaps.draft_id AND drafts.user_id = auth.uid()));

-- Policies for reviewer_feedback
CREATE POLICY "Users can view their own reviewer feedback"
ON public.reviewer_feedback FOR SELECT TO authenticated
USING (EXISTS (SELECT 1 FROM public.drafts WHERE drafts.id = reviewer_feedback.draft_id AND drafts.user_id = auth.uid()));

CREATE POLICY "System can insert reviewer feedback"
ON public.reviewer_feedback FOR INSERT TO authenticated
WITH CHECK (EXISTS (SELECT 1 FROM public.drafts WHERE drafts.id = reviewer_feedback.draft_id AND drafts.user_id = auth.uid()));

CREATE POLICY "Users can delete their own reviewer feedback"
ON public.reviewer_feedback FOR DELETE TO authenticated
USING (EXISTS (SELECT 1 FROM public.drafts WHERE drafts.id = reviewer_feedback.draft_id AND drafts.user_id = auth.uid()));

-- ============================================
-- Comments for Documentation
-- ============================================

COMMENT ON TABLE public.draft_claims IS 'Stores extracted claims from research drafts';
COMMENT ON TABLE public.coverage_gaps IS 'Stores identified coverage gaps in research drafts';
COMMENT ON TABLE public.reviewer_feedback IS 'Stores expert reviewer-style feedback for drafts';
