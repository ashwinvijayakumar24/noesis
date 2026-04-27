-- Add insights_metadata JSONB column to projects table.
-- Stores task_id and error_detail for Literature Map analysis tracking.
ALTER TABLE projects ADD COLUMN IF NOT EXISTS insights_metadata jsonb;
