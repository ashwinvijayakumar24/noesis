-- Add document-level tags (text array) to documents table
ALTER TABLE documents ADD COLUMN IF NOT EXISTS tags text[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS idx_documents_tags ON documents USING GIN (tags);
