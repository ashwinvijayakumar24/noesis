-- 031_reviewer_panel_run_unique.sql
-- Make reviewer panel output identity analysis-run aware.
--
-- Older schemas enforced one reviewer row per draft via
-- reviewer_panel_outputs_draft_id_reviewer_id_key. Atomic analysis publishing
-- needs one reviewer row per draft/run/reviewer so a new run can be staged
-- without colliding with the previous published run.

ALTER TABLE public.reviewer_panel_outputs
    DROP CONSTRAINT IF EXISTS reviewer_panel_outputs_draft_id_reviewer_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS reviewer_panel_outputs_draft_run_reviewer_uidx
    ON public.reviewer_panel_outputs(draft_id, analysis_run_id, reviewer_id)
    WHERE analysis_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_reviewer_panel_outputs_draft_reviewer_visible
    ON public.reviewer_panel_outputs(draft_id, reviewer_id, analysis_run_id)
    WHERE is_published = true;

COMMENT ON INDEX public.reviewer_panel_outputs_draft_run_reviewer_uidx
    IS 'Run-aware reviewer identity prevents reanalysis publish conflicts.';
