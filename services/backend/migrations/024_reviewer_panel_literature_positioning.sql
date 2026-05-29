-- 024_reviewer_panel_literature_positioning.sql
-- Allow the consolidated Literature & Positioning reviewer to persist.
-- Apply in Supabase SQL editor.

ALTER TABLE public.reviewer_panel_outputs
    DROP CONSTRAINT IF EXISTS reviewer_panel_outputs_reviewer_id_check;

ALTER TABLE public.reviewer_panel_outputs
    ADD CONSTRAINT reviewer_panel_outputs_reviewer_id_check
    CHECK (reviewer_id IN (
        'methodology',
        'literature_positioning',
        'clarity',
        -- Legacy rows retained for old analyses and rollback compatibility.
        'novelty',
        'coverage'
    ));
