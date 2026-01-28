-- Migration: Create draft_analysis_checkpoints table
-- Purpose: Store LangGraph workflow checkpoints for draft analysis
-- This enables pause/resume capability and recovery from failures

CREATE TABLE IF NOT EXISTS draft_analysis_checkpoints (
    id TEXT PRIMARY KEY,
    thread_id TEXT NOT NULL,
    checkpoint_data JSONB NOT NULL,
    node_name TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('in_progress', 'completed', 'failed')),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for fast lookup by thread_id (draft_id)
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_id ON draft_analysis_checkpoints(thread_id);

-- Index for sorting by creation time
CREATE INDEX IF NOT EXISTS idx_checkpoints_created_at ON draft_analysis_checkpoints(created_at DESC);

-- Index for filtering by status
CREATE INDEX IF NOT EXISTS idx_checkpoints_status ON draft_analysis_checkpoints(status);

-- Composite index for common query pattern (thread_id + created_at)
CREATE INDEX IF NOT EXISTS idx_checkpoints_thread_created ON draft_analysis_checkpoints(thread_id, created_at DESC);

-- Add comment to table
COMMENT ON TABLE draft_analysis_checkpoints IS 'Stores LangGraph workflow checkpoints for draft analysis. Enables pause/resume and failure recovery.';

COMMENT ON COLUMN draft_analysis_checkpoints.id IS 'Unique checkpoint identifier: {thread_id}_{node_name}_{timestamp}';
COMMENT ON COLUMN draft_analysis_checkpoints.thread_id IS 'Workflow identifier (typically draft_id)';
COMMENT ON COLUMN draft_analysis_checkpoints.checkpoint_data IS 'Serialized DraftAnalysisState as JSON';
COMMENT ON COLUMN draft_analysis_checkpoints.node_name IS 'Name of the node that created this checkpoint';
COMMENT ON COLUMN draft_analysis_checkpoints.status IS 'Workflow status: in_progress, completed, or failed';
COMMENT ON COLUMN draft_analysis_checkpoints.created_at IS 'When this checkpoint was created';
COMMENT ON COLUMN draft_analysis_checkpoints.updated_at IS 'When this checkpoint was last updated';
