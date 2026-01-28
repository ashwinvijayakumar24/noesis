-- Migration: Create citation_suggestions table
-- Purpose: Store AI-generated citation suggestions for draft claims
-- Date: 2025-01-XX

-- ============================================
-- Create citation_suggestions Table
-- ============================================

CREATE TABLE IF NOT EXISTS public.citation_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    
    -- Claim Information
    claim_text TEXT NOT NULL,
    section_location TEXT,
    
    -- Suggestion Details
    suggestion_type VARCHAR(100) NOT NULL, -- 'missing_citation', 'weak_citation', 'alternative_source', etc.
    suggested_paper JSONB NOT NULL, -- Paper metadata: title, authors, year, doi, abstract, etc.
    
    -- Scoring
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    relevance_score FLOAT CHECK (relevance_score >= 0 AND relevance_score <= 1),
    priority_score FLOAT CHECK (priority_score >= 0 AND priority_score <= 1),
    impact_level VARCHAR(50), -- 'critical', 'high', 'medium', 'low'
    
    -- Reasoning
    reasoning TEXT,
    
    -- Status
    status VARCHAR(50) DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected', 'dismissed', 'applied')),
    user_feedback TEXT,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_citation_suggestions_draft_id ON public.citation_suggestions(draft_id);
CREATE INDEX IF NOT EXISTS idx_citation_suggestions_user_id ON public.citation_suggestions(user_id);
CREATE INDEX IF NOT EXISTS idx_citation_suggestions_status ON public.citation_suggestions(status);
CREATE INDEX IF NOT EXISTS idx_citation_suggestions_priority ON public.citation_suggestions(priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_citation_suggestions_created ON public.citation_suggestions(created_at DESC);

-- Add comments
COMMENT ON TABLE public.citation_suggestions IS 'AI-generated citation suggestions for draft claims';
COMMENT ON COLUMN public.citation_suggestions.suggested_paper IS 'JSONB object containing paper metadata: title, authors, year, doi, abstract, document_id, etc.';
COMMENT ON COLUMN public.citation_suggestions.suggestion_type IS 'Type of suggestion: missing_citation, weak_citation, alternative_source, recent_work, foundational_work';
COMMENT ON COLUMN public.citation_suggestions.status IS 'User response status: pending, accepted, rejected, dismissed, applied';

