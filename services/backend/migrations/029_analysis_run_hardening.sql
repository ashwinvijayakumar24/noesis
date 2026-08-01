-- 029_analysis_run_hardening.sql
-- Hardens draft analysis artifact isolation after atomic run publishing.

-- Existing historical rows are expected to have been backfilled by migration 028.
-- This migration makes new artifact rows run-aware and prevents deterministic
-- task IDs from colliding across reanalysis runs.

-- Best-effort backfill for any artifacts created between migrations 028 and 029.
UPDATE public.draft_revision_tasks rt
SET analysis_run_id = d.active_analysis_run_id
FROM public.drafts d
WHERE rt.draft_id = d.id
  AND rt.analysis_run_id IS NULL
  AND d.active_analysis_run_id IS NOT NULL;

-- Fail before changing constraints if any visible artifact is still missing run
-- ownership. That is a data-integrity incident that should be repaired manually.
DO $$
DECLARE
    bad_count INTEGER;
    duplicate_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO bad_count FROM public.draft_analysis WHERE is_published = true AND analysis_run_id IS NULL;
    IF bad_count > 0 THEN RAISE EXCEPTION 'draft_analysis has % published rows without analysis_run_id', bad_count; END IF;

    SELECT COUNT(*) INTO bad_count FROM public.draft_claims WHERE is_published = true AND analysis_run_id IS NULL;
    IF bad_count > 0 THEN RAISE EXCEPTION 'draft_claims has % published rows without analysis_run_id', bad_count; END IF;

    SELECT COUNT(*) INTO bad_count FROM public.coverage_gaps WHERE is_published = true AND analysis_run_id IS NULL;
    IF bad_count > 0 THEN RAISE EXCEPTION 'coverage_gaps has % published rows without analysis_run_id', bad_count; END IF;

    SELECT COUNT(*) INTO bad_count FROM public.reviewer_feedback WHERE is_published = true AND analysis_run_id IS NULL;
    IF bad_count > 0 THEN RAISE EXCEPTION 'reviewer_feedback has % published rows without analysis_run_id', bad_count; END IF;

    SELECT COUNT(*) INTO bad_count FROM public.reviewer_panel_outputs WHERE is_published = true AND analysis_run_id IS NULL;
    IF bad_count > 0 THEN RAISE EXCEPTION 'reviewer_panel_outputs has % published rows without analysis_run_id', bad_count; END IF;

    SELECT COUNT(*) INTO bad_count FROM public.meta_reviews WHERE is_published = true AND analysis_run_id IS NULL;
    IF bad_count > 0 THEN RAISE EXCEPTION 'meta_reviews has % published rows without analysis_run_id', bad_count; END IF;

    SELECT COUNT(*) INTO bad_count FROM public.citation_suggestions WHERE is_published = true AND analysis_run_id IS NULL;
    IF bad_count > 0 THEN RAISE EXCEPTION 'citation_suggestions has % published rows without analysis_run_id', bad_count; END IF;

    SELECT COUNT(*) INTO bad_count FROM public.draft_revision_tasks WHERE is_published = true AND analysis_run_id IS NULL;
    IF bad_count > 0 THEN RAISE EXCEPTION 'draft_revision_tasks has % published rows without analysis_run_id', bad_count; END IF;

    SELECT COUNT(*) INTO duplicate_count
    FROM (
        SELECT draft_id, analysis_run_id, id
        FROM public.draft_revision_tasks
        WHERE analysis_run_id IS NOT NULL
        GROUP BY draft_id, analysis_run_id, id
        HAVING COUNT(*) > 1
    ) duplicates;
    IF duplicate_count > 0 THEN
        RAISE EXCEPTION 'draft_revision_tasks has % duplicate draft/run/task identities', duplicate_count;
    END IF;
END $$;

DO $$ BEGIN
    ALTER TABLE public.draft_revision_tasks DROP CONSTRAINT IF EXISTS draft_revision_tasks_pkey;
EXCEPTION WHEN undefined_table THEN null;
END $$;

ALTER TABLE public.draft_revision_tasks
    ADD CONSTRAINT draft_revision_tasks_pkey PRIMARY KEY (draft_id, analysis_run_id, id);

CREATE INDEX IF NOT EXISTS idx_draft_revision_tasks_draft_status_visible
    ON public.draft_revision_tasks(draft_id, analysis_run_id, status)
    WHERE is_published = true;

CREATE INDEX IF NOT EXISTS idx_draft_claims_draft_status_visible
    ON public.draft_claims(draft_id, analysis_run_id, status)
    WHERE is_published = true;

CREATE INDEX IF NOT EXISTS idx_coverage_gaps_draft_status_visible
    ON public.coverage_gaps(draft_id, analysis_run_id, status)
    WHERE is_published = true;

CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_draft_status_visible
    ON public.reviewer_feedback(draft_id, analysis_run_id, status)
    WHERE is_published = true;

COMMENT ON CONSTRAINT draft_revision_tasks_pkey ON public.draft_revision_tasks
    IS 'Run-aware task identity prevents deterministic task IDs from colliding across draft reanalysis runs.';
