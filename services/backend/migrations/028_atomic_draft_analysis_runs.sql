-- 028_atomic_draft_analysis_runs.sql
-- Run-isolated draft analysis publishing.
-- Apply in Supabase SQL editor before deploying the backend changes.

DO $$ BEGIN
    CREATE TYPE public.draft_analysis_run_status AS ENUM (
        'running',
        'rerouted',
        'failed',
        'passed',
        'published'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS public.draft_analysis_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    status public.draft_analysis_run_status NOT NULL DEFAULT 'running',
    attempt_number INTEGER NOT NULL DEFAULT 1,
    forced_route TEXT,
    manuscript_profile JSONB DEFAULT '{}'::jsonb,
    quality_gate_results JSONB DEFAULT '{}'::jsonb,
    source_safety_metrics JSONB DEFAULT '{}'::jsonb,
    failure_reason TEXT,
    reroute_from TEXT,
    reroute_to TEXT,
    started_at TIMESTAMPTZ DEFAULT now(),
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE public.drafts
    ADD COLUMN IF NOT EXISTS active_analysis_run_id UUID REFERENCES public.draft_analysis_runs(id) ON DELETE SET NULL;

ALTER TABLE public.draft_analysis
    ADD COLUMN IF NOT EXISTS analysis_run_id UUID REFERENCES public.draft_analysis_runs(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.draft_claims
    ADD COLUMN IF NOT EXISTS analysis_run_id UUID REFERENCES public.draft_analysis_runs(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.coverage_gaps
    ADD COLUMN IF NOT EXISTS analysis_run_id UUID REFERENCES public.draft_analysis_runs(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.reviewer_feedback
    ADD COLUMN IF NOT EXISTS analysis_run_id UUID REFERENCES public.draft_analysis_runs(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.reviewer_panel_outputs
    ADD COLUMN IF NOT EXISTS analysis_run_id UUID REFERENCES public.draft_analysis_runs(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.meta_reviews
    ADD COLUMN IF NOT EXISTS analysis_run_id UUID REFERENCES public.draft_analysis_runs(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.citation_suggestions
    ADD COLUMN IF NOT EXISTS analysis_run_id UUID REFERENCES public.draft_analysis_runs(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT false;

ALTER TABLE public.draft_revision_tasks
    ADD COLUMN IF NOT EXISTS analysis_run_id UUID REFERENCES public.draft_analysis_runs(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS is_published BOOLEAN NOT NULL DEFAULT false;

-- Backfill existing analyzed drafts into a published legacy run so the new
-- active-run filters do not hide pre-migration analysis output.
WITH legacy_runs AS (
    INSERT INTO public.draft_analysis_runs (
        draft_id,
        user_id,
        project_id,
        status,
        attempt_number,
        manuscript_profile,
        quality_gate_results,
        source_safety_metrics,
        started_at,
        completed_at,
        created_at,
        updated_at
    )
    SELECT
        d.id,
        d.user_id,
        d.project_id,
        'published'::public.draft_analysis_run_status,
        1,
        COALESCE(da.analysis_metadata->'manuscript_profile', '{}'::jsonb),
        '{"legacy_backfill": true}'::jsonb,
        '{}'::jsonb,
        COALESCE(da.created_at, d.updated_at, d.created_at, now()),
        now(),
        now(),
        now()
    FROM public.drafts d
    JOIN public.draft_analysis da ON da.draft_id = d.id
    WHERE d.status = 'analyzed'
      AND d.active_analysis_run_id IS NULL
    RETURNING id, draft_id
)
UPDATE public.drafts d
SET active_analysis_run_id = legacy_runs.id
FROM legacy_runs
WHERE d.id = legacy_runs.draft_id;

UPDATE public.draft_analysis da
SET analysis_run_id = d.active_analysis_run_id,
    is_published = true
FROM public.drafts d
WHERE da.draft_id = d.id
  AND d.active_analysis_run_id IS NOT NULL
  AND da.analysis_run_id IS NULL;

UPDATE public.draft_claims dc
SET analysis_run_id = d.active_analysis_run_id,
    is_published = true
FROM public.drafts d
WHERE dc.draft_id = d.id
  AND d.active_analysis_run_id IS NOT NULL
  AND dc.analysis_run_id IS NULL;

UPDATE public.coverage_gaps cg
SET analysis_run_id = d.active_analysis_run_id,
    is_published = true
FROM public.drafts d
WHERE cg.draft_id = d.id
  AND d.active_analysis_run_id IS NOT NULL
  AND cg.analysis_run_id IS NULL;

UPDATE public.reviewer_feedback rf
SET analysis_run_id = d.active_analysis_run_id,
    is_published = true
FROM public.drafts d
WHERE rf.draft_id = d.id
  AND d.active_analysis_run_id IS NOT NULL
  AND rf.analysis_run_id IS NULL;

UPDATE public.reviewer_panel_outputs rpo
SET analysis_run_id = d.active_analysis_run_id,
    is_published = true
FROM public.drafts d
WHERE rpo.draft_id = d.id
  AND d.active_analysis_run_id IS NOT NULL
  AND rpo.analysis_run_id IS NULL;

UPDATE public.meta_reviews mr
SET analysis_run_id = d.active_analysis_run_id,
    is_published = true
FROM public.drafts d
WHERE mr.draft_id = d.id
  AND d.active_analysis_run_id IS NOT NULL
  AND mr.analysis_run_id IS NULL;

UPDATE public.citation_suggestions cs
SET analysis_run_id = d.active_analysis_run_id,
    is_published = true
FROM public.drafts d
WHERE cs.draft_id = d.id
  AND d.active_analysis_run_id IS NOT NULL
  AND cs.analysis_run_id IS NULL;

UPDATE public.draft_revision_tasks drt
SET analysis_run_id = d.active_analysis_run_id,
    is_published = true
FROM public.drafts d
WHERE drt.draft_id = d.id
  AND d.active_analysis_run_id IS NOT NULL
  AND drt.analysis_run_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_draft_analysis_runs_draft_id
    ON public.draft_analysis_runs(draft_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_drafts_active_analysis_run_id
    ON public.drafts(active_analysis_run_id)
    WHERE active_analysis_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_draft_analysis_run_visible
    ON public.draft_analysis(draft_id, analysis_run_id)
    WHERE is_published = true;

CREATE INDEX IF NOT EXISTS idx_draft_claims_run_visible
    ON public.draft_claims(draft_id, analysis_run_id)
    WHERE is_published = true;

CREATE INDEX IF NOT EXISTS idx_coverage_gaps_run_visible
    ON public.coverage_gaps(draft_id, analysis_run_id)
    WHERE is_published = true;

CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_run_visible
    ON public.reviewer_feedback(draft_id, analysis_run_id)
    WHERE is_published = true;

CREATE INDEX IF NOT EXISTS idx_reviewer_panel_outputs_run_visible
    ON public.reviewer_panel_outputs(draft_id, analysis_run_id)
    WHERE is_published = true;

CREATE INDEX IF NOT EXISTS idx_meta_reviews_run_visible
    ON public.meta_reviews(draft_id, analysis_run_id)
    WHERE is_published = true;

CREATE INDEX IF NOT EXISTS idx_citation_suggestions_run_visible
    ON public.citation_suggestions(draft_id, analysis_run_id)
    WHERE is_published = true;

CREATE INDEX IF NOT EXISTS idx_draft_revision_tasks_run_visible
    ON public.draft_revision_tasks(draft_id, analysis_run_id)
    WHERE is_published = true;

ALTER TABLE public.draft_analysis_runs ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'draft_analysis_runs'
          AND policyname = 'Users can read own draft analysis runs'
    ) THEN
        CREATE POLICY "Users can read own draft analysis runs"
            ON public.draft_analysis_runs FOR SELECT
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'draft_analysis_runs'
          AND policyname = 'Service role can insert draft analysis runs'
    ) THEN
        CREATE POLICY "Service role can insert draft analysis runs"
            ON public.draft_analysis_runs FOR INSERT
            WITH CHECK (true);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'draft_analysis_runs'
          AND policyname = 'Service role can update draft analysis runs'
    ) THEN
        CREATE POLICY "Service role can update draft analysis runs"
            ON public.draft_analysis_runs FOR UPDATE
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE schemaname = 'public'
          AND tablename = 'draft_analysis_runs'
          AND policyname = 'Service role can delete draft analysis runs'
    ) THEN
        CREATE POLICY "Service role can delete draft analysis runs"
            ON public.draft_analysis_runs FOR DELETE
            USING (true);
    END IF;
END $$;

COMMENT ON TABLE public.draft_analysis_runs IS 'Internal run records for gated draft analysis attempts.';
COMMENT ON COLUMN public.drafts.active_analysis_run_id IS 'Only artifacts from this published analysis run should be shown to users.';
COMMENT ON COLUMN public.draft_analysis.is_published IS 'False for staged or failed analysis artifacts.';
