-- Migration 009: Sprint Week 1 Features
-- Date: March 2026
-- Features: Source grounding on feedback, BibTeX import support, free tier quota update

-- ============================================
-- 1. Add source grounding to reviewer_feedback
-- ============================================

ALTER TABLE reviewer_feedback
ADD COLUMN IF NOT EXISTS source_grounding JSONB,
ADD COLUMN IF NOT EXISTS confidence_level TEXT DEFAULT 'medium';

COMMENT ON COLUMN reviewer_feedback.source_grounding IS 'Literature passage that grounded this feedback item: {document_title, excerpt, similarity, chunk_index}';
COMMENT ON COLUMN reviewer_feedback.confidence_level IS 'Feedback confidence based on source grounding similarity: high, medium, low';

-- ============================================
-- 2. Add BibTeX import support to documents
-- ============================================

-- The documents table already has a status column. We add 'imported' as a valid status.
-- BibTeX-imported documents will have:
--   status = 'imported'
--   file_type = 'bibtex_import'
--   file_url = NULL (no PDF)
--   metadata = {import_source: 'bibtex', bibtex_key, entry_type, authors, year, ...}

-- No schema change needed for documents table — all fields already exist.
-- Just documenting the new status values for clarity.

COMMENT ON TABLE documents IS 'Research documents. status values: uploaded, processing, analyzed, failed, imported (BibTeX metadata-only)';

-- ============================================
-- 3. Update default free tier quota limits
-- ============================================

-- Update existing free-tier users to have the new generous beta limits
-- Only update users who are still at the old restrictive defaults (5 docs, 1 draft)
-- This prevents accidentally reducing limits for users who were upgraded

UPDATE user_quotas
SET
    monthly_document_limit = 50,
    monthly_draft_limit = 10,
    monthly_chat_messages_limit = 500,
    updated_at = NOW()
WHERE
    plan_tier = 'free'
    AND monthly_document_limit <= 5
    AND monthly_draft_limit <= 1;

-- ============================================
-- 4. Add index for faster source grounding lookups
-- ============================================

CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_confidence
    ON reviewer_feedback(draft_id, confidence_level);
