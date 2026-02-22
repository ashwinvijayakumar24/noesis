-- Migration: Draft Analysis Redesign - Section-Based Navigation & Save/Dismiss Workflow
-- Purpose: Transform draft analysis from flat tabs to section-based, researcher-friendly interface
-- Date: 2026-02-19
--
-- Changes:
-- 1. Add section_type column for section-based navigation (7 standard sections)
-- 2. Add status column for save/dismiss workflow (new/saved/dismissed)
-- 3. Add priority column for reviewer_feedback (derived from severity)
-- 4. Create unified view for efficient section-based queries
-- 5. Create function for feedback count aggregation
-- 6. Add confidence_score column to draft_claims (if not exists)

-- ============================================
-- 1. ADD SECTION_TYPE COLUMN
-- ============================================

-- Define section type enum
DO $$ BEGIN
    CREATE TYPE section_type_enum AS ENUM (
        'abstract',
        'introduction',
        'literature_review',
        'methodology',
        'results',
        'discussion',
        'conclusion',
        'references'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Add section_type to draft_claims
ALTER TABLE public.draft_claims
ADD COLUMN IF NOT EXISTS section_type section_type_enum;

-- Add section_type to coverage_gaps
ALTER TABLE public.coverage_gaps
ADD COLUMN IF NOT EXISTS section_type section_type_enum;

-- Add section_type to reviewer_feedback
ALTER TABLE public.reviewer_feedback
ADD COLUMN IF NOT EXISTS section_type section_type_enum;

-- Create indexes for section_type filtering
CREATE INDEX IF NOT EXISTS idx_draft_claims_section_type ON public.draft_claims(section_type) WHERE section_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_coverage_gaps_section_type ON public.coverage_gaps(section_type) WHERE section_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_section_type ON public.reviewer_feedback(section_type) WHERE section_type IS NOT NULL;

COMMENT ON COLUMN public.draft_claims.section_type IS 'Academic section where claim appears (abstract, introduction, literature_review, methodology, results, discussion, conclusion, references)';
COMMENT ON COLUMN public.coverage_gaps.section_type IS 'Academic section where gap was identified';
COMMENT ON COLUMN public.reviewer_feedback.section_type IS 'Academic section where feedback applies';

-- ============================================
-- 2. ADD STATUS COLUMN FOR SAVE/DISMISS WORKFLOW
-- ============================================

-- Define status enum
DO $$ BEGIN
    CREATE TYPE feedback_status_enum AS ENUM (
        'new',
        'saved',
        'dismissed'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Add status to draft_claims
ALTER TABLE public.draft_claims
ADD COLUMN IF NOT EXISTS status feedback_status_enum DEFAULT 'new';

-- Add status to coverage_gaps
ALTER TABLE public.coverage_gaps
ADD COLUMN IF NOT EXISTS status feedback_status_enum DEFAULT 'new';

-- Add status to reviewer_feedback
ALTER TABLE public.reviewer_feedback
ADD COLUMN IF NOT EXISTS status feedback_status_enum DEFAULT 'new';

-- Create indexes for status filtering
CREATE INDEX IF NOT EXISTS idx_draft_claims_status ON public.draft_claims(status);
CREATE INDEX IF NOT EXISTS idx_coverage_gaps_status ON public.coverage_gaps(status);
CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_status ON public.reviewer_feedback(status);

COMMENT ON COLUMN public.draft_claims.status IS 'Workflow status: new (unreviewed), saved (useful), dismissed (not relevant)';
COMMENT ON COLUMN public.coverage_gaps.status IS 'Workflow status: new (unreviewed), saved (useful), dismissed (not relevant)';
COMMENT ON COLUMN public.reviewer_feedback.status IS 'Workflow status: new (unreviewed), saved (useful), dismissed (not relevant)';

-- ============================================
-- 3. ADD PRIORITY COLUMN TO REVIEWER_FEEDBACK
-- ============================================

-- Define priority enum
DO $$ BEGIN
    CREATE TYPE priority_enum AS ENUM (
        'high',
        'medium',
        'low'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- Add priority to reviewer_feedback
ALTER TABLE public.reviewer_feedback
ADD COLUMN IF NOT EXISTS priority priority_enum DEFAULT 'medium';

-- Create index for priority filtering
CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_priority ON public.reviewer_feedback(priority);

COMMENT ON COLUMN public.reviewer_feedback.priority IS 'Priority level: high (critical/major severity), medium (minor severity), low (suggestion severity)';

-- ============================================
-- 4. ADD CONFIDENCE_SCORE COLUMN TO DRAFT_CLAIMS
-- ============================================

-- Add confidence_score if not exists
ALTER TABLE public.draft_claims
ADD COLUMN IF NOT EXISTS confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1);

-- Add hidden flag for low-confidence claims
ALTER TABLE public.draft_claims
ADD COLUMN IF NOT EXISTS hidden BOOLEAN DEFAULT false;

-- Create index for confidence filtering
CREATE INDEX IF NOT EXISTS idx_draft_claims_confidence ON public.draft_claims(confidence_score DESC) WHERE confidence_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_draft_claims_hidden ON public.draft_claims(hidden) WHERE hidden = false;

COMMENT ON COLUMN public.draft_claims.confidence_score IS 'AI confidence score for claim extraction (0.0 to 1.0)';
COMMENT ON COLUMN public.draft_claims.hidden IS 'True if confidence_score < 0.6 (hidden by default to reduce hallucinations)';

-- ============================================
-- 5. CREATE UNIFIED FEEDBACK VIEW
-- ============================================

-- Drop existing view if it exists
DROP VIEW IF EXISTS public.draft_feedback_unified;

-- Create unified view combining all feedback types
CREATE VIEW public.draft_feedback_unified AS
-- Claims as feedback
SELECT
    'claim' AS feedback_source,
    id,
    draft_id,
    section_type,
    status,
    claim_text AS content,
    claim_type AS category,
    CASE
        WHEN importance_score >= 0.8 THEN 'high'::priority_enum
        WHEN importance_score >= 0.5 THEN 'medium'::priority_enum
        ELSE 'low'::priority_enum
    END AS priority,
    importance_score AS score,
    line_number,
    char_start,
    char_end,
    text_snippet,
    confidence_score,
    hidden,
    requires_citation,
    existing_citations,
    reasoning,
    created_at
FROM public.draft_claims

UNION ALL

-- Coverage gaps as feedback
SELECT
    'gap' AS feedback_source,
    id,
    draft_id,
    section_type,
    status,
    description AS content,
    gap_type AS category,
    priority::priority_enum AS priority,
    NULL AS score,
    line_number,
    char_start,
    char_end,
    text_snippet,
    NULL AS confidence_score,
    false AS hidden,
    false AS requires_citation,
    NULL AS existing_citations,
    reasoning,
    created_at
FROM public.coverage_gaps

UNION ALL

-- Reviewer feedback
SELECT
    'feedback' AS feedback_source,
    id,
    draft_id,
    section_type,
    status,
    feedback_text AS content,
    feedback_type AS category,
    priority,
    impact_score AS score,
    line_number,
    char_start,
    char_end,
    text_snippet,
    NULL AS confidence_score,
    false AS hidden,
    false AS requires_citation,
    NULL AS existing_citations,
    NULL AS reasoning,
    created_at
FROM public.reviewer_feedback;

COMMENT ON VIEW public.draft_feedback_unified IS 'Unified view of all draft feedback (claims, gaps, feedback) for section-based queries';

-- ============================================
-- 6. CREATE FEEDBACK COUNTS FUNCTION
-- ============================================

-- Drop existing function if it exists
DROP FUNCTION IF EXISTS public.get_feedback_counts_by_section(UUID);

-- Create function to get feedback counts grouped by section and status
CREATE OR REPLACE FUNCTION public.get_feedback_counts_by_section(p_draft_id UUID)
RETURNS TABLE (
    section_type section_type_enum,
    status feedback_status_enum,
    feedback_source TEXT,
    count BIGINT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        dfu.section_type,
        dfu.status,
        dfu.feedback_source,
        COUNT(*) AS count
    FROM public.draft_feedback_unified dfu
    WHERE dfu.draft_id = p_draft_id
        AND dfu.section_type IS NOT NULL
        AND dfu.hidden = false  -- Exclude hidden low-confidence claims
    GROUP BY dfu.section_type, dfu.status, dfu.feedback_source
    ORDER BY dfu.section_type, dfu.status, dfu.feedback_source;
END;
$$;

COMMENT ON FUNCTION public.get_feedback_counts_by_section IS 'Returns feedback counts grouped by section, status, and source for navigation badges';

-- ============================================
-- 7. UPDATE RLS POLICIES FOR NEW COLUMNS
-- ============================================

-- No new policies needed - existing policies cover new columns
-- Status and section_type updates use existing UPDATE policies

-- ============================================
-- 8. CREATE COMPOSITE INDEXES FOR COMMON QUERIES
-- ============================================

-- Section-based filtering with status (common query pattern)
CREATE INDEX IF NOT EXISTS idx_draft_claims_section_status ON public.draft_claims(draft_id, section_type, status) WHERE section_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_coverage_gaps_section_status ON public.coverage_gaps(draft_id, section_type, status) WHERE section_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_section_status ON public.reviewer_feedback(draft_id, section_type, status) WHERE section_type IS NOT NULL;

-- Priority-based filtering for reviewer_feedback (HIGH shown first)
CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_priority_order ON public.reviewer_feedback(draft_id, section_type, priority, status);

-- ============================================
-- 9. MIGRATION COMPLETE
-- ============================================

-- Verify migration
DO $$
DECLARE
    v_claims_count INTEGER;
    v_gaps_count INTEGER;
    v_feedback_count INTEGER;
BEGIN
    -- Count existing records
    SELECT COUNT(*) INTO v_claims_count FROM public.draft_claims;
    SELECT COUNT(*) INTO v_gaps_count FROM public.coverage_gaps;
    SELECT COUNT(*) INTO v_feedback_count FROM public.reviewer_feedback;

    RAISE NOTICE 'Migration 016 complete:';
    RAISE NOTICE '- Added section_type, status, priority columns';
    RAISE NOTICE '- Created draft_feedback_unified view';
    RAISE NOTICE '- Created get_feedback_counts_by_section function';
    RAISE NOTICE '- Existing records: % claims, % gaps, % feedback', v_claims_count, v_gaps_count, v_feedback_count;
    RAISE NOTICE '- All existing records have status=new (default)';
    RAISE NOTICE '- Section types will be assigned on first view via auto-migration';
END $$;
