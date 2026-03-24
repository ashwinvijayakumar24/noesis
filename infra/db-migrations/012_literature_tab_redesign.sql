-- ============================================================
-- Migration 012: Literature Tab Redesign
--
-- Changes:
--   1. Add source_type to documents (manual_upload | bibtex_import | zotero_import | discovered)
--   2. Add resolution_status to documents (resolving | resolved | unresolved | NULL)
--   3. Add separate BibTeX quota columns to user_quotas
--   4. Create index on source_type for filter queries
--   5. Backfill existing rows
-- ============================================================

-- 1. Add source_type column to documents
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS source_type TEXT DEFAULT 'manual_upload';

-- 2. Add resolution_status column to documents
ALTER TABLE documents
  ADD COLUMN IF NOT EXISTS resolution_status TEXT DEFAULT NULL;

-- 3. Backfill source_type from file_type / metadata
UPDATE documents
  SET source_type = 'bibtex_import'
  WHERE file_type = 'bibtex_import'
    AND (source_type IS NULL OR source_type = 'manual_upload');

UPDATE documents
  SET source_type = 'zotero_import'
  WHERE metadata->>'import_source' = 'zotero'
    AND (source_type IS NULL OR source_type = 'manual_upload');

-- 4. Backfill resolution_status for existing bibtex/zotero imports
--    (treat them all as 'unresolved' since we never ran the resolver)
UPDATE documents
  SET resolution_status = 'unresolved'
  WHERE source_type IN ('bibtex_import', 'zotero_import')
    AND resolution_status IS NULL;

-- 5. Add BibTeX quota columns to user_quotas
ALTER TABLE user_quotas
  ADD COLUMN IF NOT EXISTS current_month_bib_refs INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS monthly_bib_refs_limit INTEGER DEFAULT 10;

-- 6. Index for efficient literature tab filter queries
CREATE INDEX IF NOT EXISTS idx_documents_source_type
  ON documents(source_type, project_id);

-- 7. Index for resolution_status polling queries
CREATE INDEX IF NOT EXISTS idx_documents_resolution_status
  ON documents(resolution_status, project_id)
  WHERE resolution_status IS NOT NULL;

-- Done
