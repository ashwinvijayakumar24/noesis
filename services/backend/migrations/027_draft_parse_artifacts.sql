-- Private parser artifact storage for draft anchoring/debugging.
-- Stores compact paragraph snippets and coordinates, not a second full manuscript.

CREATE TABLE IF NOT EXISTS public.draft_parse_artifacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE UNIQUE,
    parser_name TEXT NOT NULL,
    parser_version TEXT,
    parser_metadata JSONB DEFAULT '{}'::jsonb,
    parser_quality_score REAL CHECK (
        parser_quality_score IS NULL OR (parser_quality_score >= 0 AND parser_quality_score <= 1)
    ),
    parser_quality_flags JSONB DEFAULT '[]'::jsonb,
    section_map JSONB DEFAULT '[]'::jsonb,
    anchor_map JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_draft_parse_artifacts_draft_id
    ON public.draft_parse_artifacts(draft_id);

ALTER TABLE public.draft_parse_artifacts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own draft parse artifacts"
    ON public.draft_parse_artifacts FOR SELECT
    USING (
        draft_id IN (SELECT id FROM public.drafts WHERE user_id = auth.uid())
    );

CREATE POLICY "Service role can insert draft parse artifacts"
    ON public.draft_parse_artifacts FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Service role can update draft parse artifacts"
    ON public.draft_parse_artifacts FOR UPDATE
    USING (true)
    WITH CHECK (true);

CREATE POLICY "Service role can delete draft parse artifacts"
    ON public.draft_parse_artifacts FOR DELETE
    USING (true);

COMMENT ON TABLE public.draft_parse_artifacts IS 'Private compact parser output for anchoring and parser-quality debugging.';
