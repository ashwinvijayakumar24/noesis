-- Migration: Draft analysis v2
-- Adds structured analysis storage, reviewer personas, and draft context fields.

ALTER TABLE public.draft_analysis
  ADD COLUMN IF NOT EXISTS analysis JSONB DEFAULT '{}'::jsonb;

ALTER TABLE public.reviewer_feedback
  ADD COLUMN IF NOT EXISTS reviewer_persona TEXT DEFAULT 'reviewer_2';

ALTER TABLE public.drafts
  ADD COLUMN IF NOT EXISTS paper_type TEXT DEFAULT 'journal_article';

ALTER TABLE public.drafts
  ADD COLUMN IF NOT EXISTS citation_style TEXT DEFAULT 'apa';

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'reviewer_feedback_reviewer_persona_check'
  ) THEN
    ALTER TABLE public.reviewer_feedback
      ADD CONSTRAINT reviewer_feedback_reviewer_persona_check
      CHECK (reviewer_persona IN ('reviewer_1', 'reviewer_2'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'drafts_paper_type_check'
  ) THEN
    ALTER TABLE public.drafts
      ADD CONSTRAINT drafts_paper_type_check
      CHECK (paper_type IN ('journal_article', 'conference_paper', 'thesis', 'dissertation', 'preprint'));
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'drafts_citation_style_check'
  ) THEN
    ALTER TABLE public.drafts
      ADD CONSTRAINT drafts_citation_style_check
      CHECK (citation_style IN ('apa', 'mla', 'chicago', 'ieee', 'vancouver', 'other'));
  END IF;
END $$;

COMMENT ON COLUMN public.draft_analysis.analysis IS 'Structured draft-analysis payloads such as stage 1 editing feedback.';
COMMENT ON COLUMN public.reviewer_feedback.reviewer_persona IS 'Reviewer voice for feedback rows: reviewer_1 strengths or reviewer_2 critiques.';
COMMENT ON COLUMN public.drafts.paper_type IS 'Draft context selected before upload to tune analysis expectations.';
COMMENT ON COLUMN public.drafts.citation_style IS 'Citation style selected before upload to tune editing checks.';
