# Apply SQL Migrations to Supabase

## Quick Start

Go to your Supabase SQL Editor and run these migrations in order:

**Supabase SQL Editor:** https://app.supabase.com/project/ufnaadgdrraqnatvgarq/sql

---

## Migration 1: Enable pgvector

```sql
CREATE EXTENSION IF NOT EXISTS "pgvector";
```

---

## Migration 2: Create Tables

```sql
-- 1. PROJECTS TABLE
CREATE TABLE IF NOT EXISTS projects (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);

-- 2. DATASETS TABLE
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
CREATE INDEX IF NOT EXISTS idx_datasets_user_id ON datasets(user_id);
CREATE INDEX IF NOT EXISTS idx_datasets_project_id ON datasets(project_id);

-- 3. DOCUMENTS TABLE
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
CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_project_id ON documents(project_id);

-- 4. DOCUMENT_CHUNKS TABLE (for RAG)
CREATE TABLE IF NOT EXISTS document_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  embedding VECTOR(1536),
  metadata JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_document_chunks_document_id ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_project_id ON document_chunks(project_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
ON document_chunks USING hnsw (embedding vector_cosine_ops);
```

---

## Migration 3: Create Vector Search Function

```sql
CREATE OR REPLACE FUNCTION match_document_chunks(
  query_embedding VECTOR(1536),
  proj_id UUID,
  match_count INT DEFAULT 5
)
RETURNS TABLE (
  id UUID,
  document_id UUID,
  chunk_index INTEGER,
  content TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    document_chunks.id,
    document_chunks.document_id,
    document_chunks.chunk_index,
    document_chunks.content,
    1 - (document_chunks.embedding <=> query_embedding) AS similarity
  FROM document_chunks
  WHERE document_chunks.project_id = proj_id
  ORDER BY document_chunks.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;
```

---

## Verification

After running all migrations, verify they worked:

### Check Tables
In the Supabase Table Editor, you should see:
- `projects`
- `datasets`
- `documents`
- `document_chunks`

### Check Function
Run this query to test the vector search function:
```sql
SELECT * FROM match_document_chunks(
  ARRAY[0.1, 0.2, ...]::vector(1536),  -- dummy embedding
  'some-uuid'::uuid,
  5
);
```

It should return an empty result set (no error) if the function exists.

### Check Indexes
```sql
SELECT tablename, indexname
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

You should see indexes like:
- `idx_projects_user_id`
- `idx_datasets_user_id`
- `idx_datasets_project_id`
- `idx_documents_user_id`
- `idx_documents_project_id`
- `idx_document_chunks_document_id`
- `idx_document_chunks_project_id`
- `idx_document_chunks_embedding`

---

## Next Steps

Once migrations are complete:

1. **Test the backend:**
   ```bash
   curl http://localhost:8000/test-supabase
   ```

2. **Upload a test document:**
   - Create a project
   - Upload a PDF
   - Trigger RAG ingestion
   - Query the RAG endpoint

3. **Monitor logs:**
   ```bash
   cd infra
   docker compose logs -f backend
   ```

---

## Troubleshooting

### Error: "extension 'vector' does not exist"
Make sure you ran Migration 1 first.

### Error: "relation 'projects' does not exist"
Run Migration 2.

### Error: "function match_document_chunks does not exist"
Run Migration 3.

### Check Migration Status
```sql
-- Check if pgvector is enabled
SELECT * FROM pg_extension WHERE extname = 'vector';

-- Check if tables exist
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
ORDER BY table_name;

-- Check if function exists
SELECT routine_name
FROM information_schema.routines
WHERE routine_schema = 'public'
AND routine_name = 'match_document_chunks';
```

---

## Complete Migration Script

If you want to run everything at once:

```sql
-- Migration 1: Enable pgvector
CREATE EXTENSION IF NOT EXISTS "pgvector";

-- Migration 2: Create tables (see above)
-- ... (copy full SQL from Migration 2)

-- Migration 3: Create vector search function (see above)
-- ... (copy full SQL from Migration 3)
```

---

**After completing migrations, you're ready to use the RAG pipeline!** 🚀
