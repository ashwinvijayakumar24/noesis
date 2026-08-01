-- 035_revision_task_anchor_columns.sql
-- Adds per-row anchor observability columns to draft_revision_tasks.
--
-- WHY: the honest verbatim-anchor work (June 2026) classifies each task's anchor as
-- verbatim (a real manuscript substring) vs not, and as local (highlightable) vs global
-- (whole-document critique, no single quotable locus). The coverage METRIC is already
-- stored in draft_analysis.analysis_metadata, but persisting per-row lets the frontend
-- highlighter decide which tasks to anchor (local+verbatim) vs render as document-level
-- (global), and gives engineering real per-task observability.
--
-- UNTIL THIS IS APPLIED: app/services/draft_analysis_langgraph.py:_revision_task_row does
-- NOT write these fields (it was reverted after an unapplied-column insert failure,
-- PGRST204). After applying this migration, re-add the two keys to _revision_task_row:
--   "anchor_type": task.get("anchor_type"),
--   "anchor_verbatim": task.get("anchor_verbatim"),

ALTER TABLE draft_revision_tasks
    ADD COLUMN IF NOT EXISTS anchor_type   text    DEFAULT 'local',
    ADD COLUMN IF NOT EXISTS anchor_verbatim boolean DEFAULT NULL;

-- Optional backfill (existing rows predate the classifier; leave NULL/local).
-- No index needed; these are read alongside the row, not filtered on.
