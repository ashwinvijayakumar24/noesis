-- Phase 6B: Create project_tags table for tagging and organizing projects
-- This table stores tags assigned to projects

-- ============================================
-- PROJECT_TAGS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS project_tags (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE NOT NULL,
  user_id UUID NOT NULL,
  tag_name TEXT NOT NULL,
  tag_color TEXT NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_project_tags_project_id ON project_tags(project_id);
CREATE INDEX IF NOT EXISTS idx_project_tags_user_id ON project_tags(user_id);
CREATE INDEX IF NOT EXISTS idx_project_tags_tag_name ON project_tags(tag_name);

-- Unique constraint: one tag per project (no duplicates)
CREATE UNIQUE INDEX IF NOT EXISTS idx_project_tags_unique ON project_tags(project_id, tag_name);

-- Comments for documentation
COMMENT ON TABLE project_tags IS 'Tags for organizing and filtering projects';
COMMENT ON COLUMN project_tags.tag_name IS 'Tag name (case-insensitive, stored as lowercase)';
COMMENT ON COLUMN project_tags.tag_color IS 'Tag color from predefined palette (e.g., red-500, blue-500)';
