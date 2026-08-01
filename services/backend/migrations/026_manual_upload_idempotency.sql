-- Enforce idempotent manual PDF uploads per user/project/content hash.
-- The application writes metadata.file_sha256 before inserting documents.
CREATE UNIQUE INDEX IF NOT EXISTS documents_manual_upload_file_sha256_unique
ON documents (
  user_id,
  COALESCE(project_id::text, 'no_project'),
  ((metadata ->> 'file_sha256'))
)
WHERE source_type = 'manual_upload'
  AND metadata ? 'file_sha256';
