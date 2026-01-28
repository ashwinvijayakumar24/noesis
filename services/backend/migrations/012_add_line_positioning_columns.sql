-- Migration: Add line positioning columns for TXT file annotations
-- Purpose: Enable clickable annotations that link claims/feedback/gaps to specific lines in draft text
-- Date: 2025-12-27

-- ============================================
-- Add Line Positioning Columns to draft_claims
-- ============================================

ALTER TABLE public.draft_claims
ADD COLUMN IF NOT EXISTS line_number INTEGER,
ADD COLUMN IF NOT EXISTS char_start INTEGER,
ADD COLUMN IF NOT EXISTS char_end INTEGER,
ADD COLUMN IF NOT EXISTS text_snippet TEXT;

-- ============================================
-- Add Line Positioning Columns to coverage_gaps
-- ============================================

ALTER TABLE public.coverage_gaps
ADD COLUMN IF NOT EXISTS line_number INTEGER,
ADD COLUMN IF NOT EXISTS char_start INTEGER,
ADD COLUMN IF NOT EXISTS char_end INTEGER,
ADD COLUMN IF NOT EXISTS text_snippet TEXT;

-- ============================================
-- Add Line Positioning Columns to reviewer_feedback
-- ============================================

ALTER TABLE public.reviewer_feedback
ADD COLUMN IF NOT EXISTS line_number INTEGER,
ADD COLUMN IF NOT EXISTS char_start INTEGER,
ADD COLUMN IF NOT EXISTS char_end INTEGER,
ADD COLUMN IF NOT EXISTS text_snippet TEXT;

-- ============================================
-- Add Indexes for Line Number Lookups
-- ============================================

CREATE INDEX IF NOT EXISTS idx_draft_claims_line_number ON public.draft_claims(line_number) WHERE line_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_coverage_gaps_line_number ON public.coverage_gaps(line_number) WHERE line_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_line_number ON public.reviewer_feedback(line_number) WHERE line_number IS NOT NULL;

-- ============================================
-- Comments for Documentation
-- ============================================

COMMENT ON COLUMN public.draft_claims.line_number IS 'Line number in TXT file where claim appears (1-indexed)';
COMMENT ON COLUMN public.draft_claims.char_start IS 'Character offset within the line where claim starts';
COMMENT ON COLUMN public.draft_claims.char_end IS 'Character offset within the line where claim ends';
COMMENT ON COLUMN public.draft_claims.text_snippet IS '100-200 char excerpt for fuzzy matching fallback';

COMMENT ON COLUMN public.coverage_gaps.line_number IS 'Line number in TXT file where gap was identified';
COMMENT ON COLUMN public.coverage_gaps.char_start IS 'Character offset within the line';
COMMENT ON COLUMN public.coverage_gaps.char_end IS 'Character offset within the line';
COMMENT ON COLUMN public.coverage_gaps.text_snippet IS '100-200 char excerpt for fuzzy matching fallback';

COMMENT ON COLUMN public.reviewer_feedback.line_number IS 'Line number in TXT file where feedback applies';
COMMENT ON COLUMN public.reviewer_feedback.char_start IS 'Character offset within the line';
COMMENT ON COLUMN public.reviewer_feedback.char_end IS 'Character offset within the line';
COMMENT ON COLUMN public.reviewer_feedback.text_snippet IS '100-200 char excerpt for fuzzy matching fallback';
