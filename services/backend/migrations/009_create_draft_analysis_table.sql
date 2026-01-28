-- Migration: Create draft_analysis table
-- Purpose: Store structural analysis results for research drafts
-- Date: 2025-12-24

-- ============================================
-- Create draft_analysis Table
-- ============================================

CREATE TABLE IF NOT EXISTS public.draft_analysis (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,

    -- Analysis Results
    structure JSONB NOT NULL,  -- Document structure (sections, metadata)
    word_count INTEGER NOT NULL,

    -- Processing Metadata
    analysis_metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================
-- Indexes for Performance
-- ============================================

-- Index on draft_id for quick lookups
CREATE INDEX IF NOT EXISTS idx_draft_analysis_draft_id
ON public.draft_analysis(draft_id);

-- Index on created_at for sorting
CREATE INDEX IF NOT EXISTS idx_draft_analysis_created_at
ON public.draft_analysis(created_at DESC);

-- ============================================
-- Row Level Security (RLS)
-- ============================================

-- Enable RLS
ALTER TABLE public.draft_analysis ENABLE ROW LEVEL SECURITY;

-- Policy: Users can view analysis for their own drafts
CREATE POLICY "Users can view their own draft analysis"
ON public.draft_analysis
FOR SELECT
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.drafts
        WHERE drafts.id = draft_analysis.draft_id
        AND drafts.user_id = auth.uid()
    )
);

-- Policy: System can insert analysis (via service role)
CREATE POLICY "System can insert draft analysis"
ON public.draft_analysis
FOR INSERT
TO authenticated
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.drafts
        WHERE drafts.id = draft_analysis.draft_id
        AND drafts.user_id = auth.uid()
    )
);

-- Policy: System can update analysis
CREATE POLICY "System can update draft analysis"
ON public.draft_analysis
FOR UPDATE
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.drafts
        WHERE drafts.id = draft_analysis.draft_id
        AND drafts.user_id = auth.uid()
    )
)
WITH CHECK (
    EXISTS (
        SELECT 1 FROM public.drafts
        WHERE drafts.id = draft_analysis.draft_id
        AND drafts.user_id = auth.uid()
    )
);

-- Policy: Users can delete their own draft analysis
CREATE POLICY "Users can delete their own draft analysis"
ON public.draft_analysis
FOR DELETE
TO authenticated
USING (
    EXISTS (
        SELECT 1 FROM public.drafts
        WHERE drafts.id = draft_analysis.draft_id
        AND drafts.user_id = auth.uid()
    )
);

-- ============================================
-- Comments for Documentation
-- ============================================

COMMENT ON TABLE public.draft_analysis IS 'Stores structural analysis results for research drafts';
COMMENT ON COLUMN public.draft_analysis.structure IS 'Document structure including sections and metadata';
COMMENT ON COLUMN public.draft_analysis.word_count IS 'Total word count of the draft';
COMMENT ON COLUMN public.draft_analysis.analysis_metadata IS 'Processing metadata including model used, GROBID data, etc.';

-- ============================================
-- Verification
-- ============================================

-- Verify table was created
SELECT
    table_name,
    column_name,
    data_type,
    is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'draft_analysis'
ORDER BY ordinal_position;

-- Verify RLS policies
SELECT
    schemaname,
    tablename,
    policyname,
    permissive,
    roles,
    cmd
FROM pg_policies
WHERE tablename = 'draft_analysis'
ORDER BY policyname;
