-- Make meta reviews versioned by analysis run instead of draft-global.
-- This allows reanalysis to publish a fresh meta review without colliding with
-- a previous published run for the same draft.

ALTER TABLE public.meta_reviews
  DROP CONSTRAINT IF EXISTS meta_reviews_draft_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS meta_reviews_draft_run_unique
  ON public.meta_reviews (draft_id, analysis_run_id)
  WHERE analysis_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS meta_reviews_active_lookup_idx
  ON public.meta_reviews (draft_id, analysis_run_id)
  WHERE is_published = true;

COMMENT ON INDEX public.meta_reviews_draft_run_unique IS
  'Allows one meta review per draft analysis run; replaces legacy draft-only uniqueness.';
