-- 025_revision_task_payload_cleanup.sql
-- Adds page-level anchors and source display payloads to durable revision tasks.
-- Apply in Supabase SQL editor.

ALTER TABLE public.draft_revision_tasks
    ADD COLUMN IF NOT EXISTS page_number INTEGER,
    ADD COLUMN IF NOT EXISTS paragraph_index INTEGER,
    ADD COLUMN IF NOT EXISTS suggested_sources JSONB DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_draft_revision_tasks_page_number
    ON public.draft_revision_tasks(draft_id, page_number)
    WHERE page_number IS NOT NULL;

COMMENT ON COLUMN public.draft_revision_tasks.page_number IS 'One-based PDF page number for page-level navigation.';
COMMENT ON COLUMN public.draft_revision_tasks.paragraph_index IS 'Best-effort paragraph index within the matched page or extracted text.';
COMMENT ON COLUMN public.draft_revision_tasks.suggested_sources IS 'Validated citation/source candidates to display on citation-related tasks.';
