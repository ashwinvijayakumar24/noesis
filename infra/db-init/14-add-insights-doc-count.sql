-- Add insights_doc_count column to projects table
-- This tracks the number of analyzed documents when insights were last generated
-- Used to detect when insights are stale (new documents added)

ALTER TABLE projects
ADD COLUMN IF NOT EXISTS insights_doc_count INTEGER DEFAULT 0;

-- Add index for better query performance
CREATE INDEX IF NOT EXISTS idx_projects_insights_doc_count
ON projects(insights_doc_count);

COMMENT ON COLUMN projects.insights_doc_count IS 'Number of analyzed documents when insights were last generated';
