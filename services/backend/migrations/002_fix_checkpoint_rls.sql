-- Migration: Fix RLS for draft_analysis_checkpoints
-- Purpose: Add user_id column and enable Row-Level Security to prevent cross-user data leakage
-- Critical Security Fix: Closes vulnerability where checkpoints could be accessed across users

-- Step 1: Add user_id column to draft_analysis_checkpoints
-- Note: NOT NULL constraint added after backfilling data
ALTER TABLE draft_analysis_checkpoints ADD COLUMN IF NOT EXISTS user_id UUID;

-- Step 2: Backfill user_id from drafts table (if data exists)
-- This ensures existing checkpoints are properly associated with users
UPDATE draft_analysis_checkpoints
SET user_id = drafts.user_id
FROM drafts
WHERE draft_analysis_checkpoints.thread_id = drafts.id::TEXT
  AND draft_analysis_checkpoints.user_id IS NULL;

-- Step 3: Add NOT NULL constraint after backfilling
-- New checkpoints MUST include user_id
ALTER TABLE draft_analysis_checkpoints ALTER COLUMN user_id SET NOT NULL;

-- Step 4: Create index for efficient user-based queries
CREATE INDEX IF NOT EXISTS idx_checkpoints_user_id ON draft_analysis_checkpoints(user_id);

-- Step 5: Create composite index for common query pattern (user_id + thread_id)
CREATE INDEX IF NOT EXISTS idx_checkpoints_user_thread ON draft_analysis_checkpoints(user_id, thread_id);

-- Step 6: Enable Row-Level Security
ALTER TABLE draft_analysis_checkpoints ENABLE ROW LEVEL SECURITY;

-- Step 7: Create RLS policies for user isolation
-- Policy: Users can view only their own checkpoints
CREATE POLICY "Users can view own checkpoints"
  ON draft_analysis_checkpoints FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

-- Policy: Users can insert only their own checkpoints
CREATE POLICY "Users can insert own checkpoints"
  ON draft_analysis_checkpoints FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

-- Policy: Users can update only their own checkpoints
CREATE POLICY "Users can update own checkpoints"
  ON draft_analysis_checkpoints FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id);

-- Policy: Users can delete only their own checkpoints
CREATE POLICY "Users can delete own checkpoints"
  ON draft_analysis_checkpoints FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);

-- Step 8: Add comment explaining the security context
COMMENT ON COLUMN draft_analysis_checkpoints.user_id IS 'User ID for RLS isolation. Ensures checkpoints cannot be accessed across users.';

-- Verification query (run manually after migration):
-- SELECT tablename, rowsecurity FROM pg_tables WHERE tablename = 'draft_analysis_checkpoints';
-- Expected: rowsecurity = true

-- Security test query (run manually as different users):
-- SET request.jwt.claim.sub = 'user-a-uuid';
-- SELECT * FROM draft_analysis_checkpoints WHERE user_id != 'user-a-uuid';
-- Expected: 0 rows (blocked by RLS)
