-- 033_align_citation_style_check.sql
-- Fix: drafts uploads 500 with "drafts_citation_style_check" violation.
-- The drafts.citation_style CHECK constraint was stale — it only allowed
-- apa/ieee/mla/chicago, but the API accepts (and DEFAULTS to) 'auto', and also
-- offers acs/vancouver/other. Every upload using the default style failed.
-- This realigns the constraint with the application's VALID_CITATION_STYLES
-- (app/api/routes/drafts.py). NULL stays allowed (= unspecified / auto-detect).
-- Apply in the Supabase SQL editor.

ALTER TABLE public.drafts
    DROP CONSTRAINT IF EXISTS drafts_citation_style_check;

ALTER TABLE public.drafts
    ADD CONSTRAINT drafts_citation_style_check
    CHECK (
        citation_style IS NULL
        OR citation_style IN (
            'auto', 'acs', 'apa', 'mla', 'chicago', 'ieee', 'vancouver', 'other'
        )
    );
