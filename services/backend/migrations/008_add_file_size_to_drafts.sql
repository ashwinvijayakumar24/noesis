-- Migration: Add file_size column to drafts table
-- Purpose: Store the file size of uploaded drafts for validation and display
-- Date: 2025-12-24

-- Add file_size column to drafts table
ALTER TABLE public.drafts
ADD COLUMN IF NOT EXISTS file_size BIGINT;

-- Add comment for documentation
COMMENT ON COLUMN public.drafts.file_size IS 'Size of the draft file in bytes';

-- Verify the column was added
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'drafts'
  AND column_name = 'file_size';
