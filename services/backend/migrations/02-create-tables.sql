-- Step 3.4: Create relational structure for projects, datasets, and documents
-- This migration creates the required tables for the Noesis research workspace

-- ============================================
-- 1. PROJECTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create index on user_id for faster queries
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);

-- ============================================
-- 2. DATASETS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS datasets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  filename TEXT NOT NULL,
  file_url TEXT NOT NULL,
  file_type TEXT NOT NULL,
  file_size INTEGER,
  status TEXT DEFAULT 'uploaded',
  metadata JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_datasets_user_id ON datasets(user_id);
CREATE INDEX IF NOT EXISTS idx_datasets_project_id ON datasets(project_id);

-- ============================================
-- 3. DOCUMENTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT,
  description TEXT,
  file_url TEXT NOT NULL,
  file_type TEXT NOT NULL,
  file_size INTEGER,
  metadata JSONB,
  status TEXT DEFAULT 'uploaded',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);

-- ============================================
-- 4. DOCUMENT_CHUNKS TABLE (for RAG pipeline)
-- ============================================
CREATE TABLE IF NOT EXISTS document_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  embedding VECTOR(1536),  -- Fixed at 1536 dimensions (native for small model, reduced for large model)
  metadata JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_project_id ON document_chunks(project_id);

-- Create vector similarity search index using HNSW (Hierarchical Navigable Small World)
-- This significantly speeds up nearest neighbor searches
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
ON document_chunks
USING hnsw (embedding vector_cosine_ops);

-- ============================================
-- COMMENTS FOR DOCUMENTATION
-- ============================================
COMMENT ON TABLE projects IS 'Research projects that contain datasets and documents';
COMMENT ON TABLE datasets IS 'CSV datasets uploaded by users for analysis';
COMMENT ON TABLE documents IS 'Research PDFs for RAG pipeline ingestion';
COMMENT ON TABLE document_chunks IS 'Text chunks extracted from documents with embeddings for RAG retrieval';

COMMENT ON COLUMN document_chunks.embedding IS 'OpenAI embedding vector (1536 dimensions - native for small model, reduced for large model)';
COMMENT ON COLUMN document_chunks.chunk_index IS 'Sequential position of this chunk within the parent document';
