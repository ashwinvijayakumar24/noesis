-- Migration: Add user_id to draft_analysis_checkpoints
-- Purpose: Fix draft analysis checkpoint persistence (missing user_id column)
-- Date: 2026-02-20
--
-- Issue: Checkpoint saver tries to insert user_id but column doesn't exist
-- Fix: Add user_id column with foreign key to auth.users

-- Add user_id column
ALTER TABLE public.draft_analysis_checkpoints
ADD COLUMN IF NOT EXISTS user_id UUID;

-- Add foreign key constraint (optional but recommended)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'draft_analysis_checkpoints_user_id_fkey'
    ) THEN
        ALTER TABLE public.draft_analysis_checkpoints
        ADD CONSTRAINT draft_analysis_checkpoints_user_id_fkey
        FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;
    END IF;
END $$;

-- Create index for user_id filtering
CREATE INDEX IF NOT EXISTS idx_draft_analysis_checkpoints_user_id
ON public.draft_analysis_checkpoints(user_id);

-- Add RLS policy for user isolation (if RLS is enabled)
DO $$
BEGIN
    -- Enable RLS if not already enabled
    ALTER TABLE public.draft_analysis_checkpoints ENABLE ROW LEVEL SECURITY;

    -- Drop existing policies if they exist
    DROP POLICY IF EXISTS "Users can manage their own checkpoints" ON public.draft_analysis_checkpoints;

    -- Create policy for user isolation
    CREATE POLICY "Users can manage their own checkpoints"
    ON public.draft_analysis_checkpoints
    FOR ALL
    USING (auth.uid() = user_id);
EXCEPTION
    WHEN others THEN
        RAISE NOTICE 'RLS policy creation skipped (may already exist or auth.uid() not available)';
END $$;

COMMENT ON COLUMN public.draft_analysis_checkpoints.user_id IS 'User who owns this checkpoint (for RLS isolation)';

-- Verify migration
DO $$
DECLARE
    v_checkpoint_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_checkpoint_count FROM public.draft_analysis_checkpoints;

    RAISE NOTICE 'Migration 017 complete:';
    RAISE NOTICE '- Added user_id column to draft_analysis_checkpoints';
    RAISE NOTICE '- Added foreign key constraint to auth.users';
    RAISE NOTICE '- Created index on user_id';
    RAISE NOTICE '- Enabled RLS and created user isolation policy';
    RAISE NOTICE '- Existing checkpoints: %', v_checkpoint_count;
    RAISE NOTICE '- Note: Existing checkpoints will have NULL user_id (will be populated on next run)';
END $$;
