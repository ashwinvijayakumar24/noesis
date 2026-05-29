-- 023_draft_revision_tasks.sql
-- Durable canonical action queue for draft analysis.
-- Apply in Supabase SQL editor.

DO $$ BEGIN
    CREATE TYPE feedback_status_enum AS ENUM (
        'new',
        'saved',
        'dismissed'
    );
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS public.draft_revision_tasks (
    id TEXT NOT NULL,
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    source_type TEXT NOT NULL,
    task_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'major', 'minor', 'suggestion')),
    priority TEXT NOT NULL CHECK (priority IN ('high', 'medium', 'low')),
    section TEXT,
    anchor_text TEXT,
    line_number INTEGER,
    char_start INTEGER,
    char_end INTEGER,
    text_snippet TEXT,
    pdf_coordinates JSONB,
    match_confidence REAL CHECK (match_confidence IS NULL OR (match_confidence >= 0 AND match_confidence <= 1)),
    problem TEXT NOT NULL,
    why_it_matters TEXT,
    suggested_action TEXT NOT NULL,
    source_ids JSONB DEFAULT '[]'::jsonb,
    confidence REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    status feedback_status_enum DEFAULT 'new',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (draft_id, id)
);

CREATE INDEX IF NOT EXISTS idx_draft_revision_tasks_draft_id ON public.draft_revision_tasks(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_revision_tasks_status ON public.draft_revision_tasks(status);
CREATE INDEX IF NOT EXISTS idx_draft_revision_tasks_priority ON public.draft_revision_tasks(priority);
CREATE INDEX IF NOT EXISTS idx_draft_revision_tasks_task_type ON public.draft_revision_tasks(task_type);

ALTER TABLE public.draft_revision_tasks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own draft revision tasks"
    ON public.draft_revision_tasks FOR SELECT
    USING (
        draft_id IN (SELECT id FROM public.drafts WHERE user_id = auth.uid())
    );

CREATE POLICY "Users can update own draft revision tasks"
    ON public.draft_revision_tasks FOR UPDATE
    USING (
        draft_id IN (SELECT id FROM public.drafts WHERE user_id = auth.uid())
    )
    WITH CHECK (
        draft_id IN (SELECT id FROM public.drafts WHERE user_id = auth.uid())
    );

CREATE POLICY "Service role can insert draft revision tasks"
    ON public.draft_revision_tasks FOR INSERT
    WITH CHECK (true);

CREATE POLICY "Service role can delete draft revision tasks"
    ON public.draft_revision_tasks FOR DELETE
    USING (true);

COMMENT ON TABLE public.draft_revision_tasks IS 'Canonical deduplicated draft-analysis revision task queue rendered by the frontend.';
COMMENT ON COLUMN public.draft_revision_tasks.id IS 'Stable deterministic task id generated from task content.';
COMMENT ON COLUMN public.draft_revision_tasks.status IS 'Workflow status: new, saved/addressed, or dismissed.';
