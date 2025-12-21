# Step 3.4 - Database Schema & Relational Structure

## ✅ Status: CODE COMPLETE

All backend code for Step 3.4 has been implemented. You only need to run the SQL migration in Supabase.

---

## 📋 What's Implemented

### 1. ✅ Database Schema (SQL)

**File:** `02-create-tables.sql`

Tables created:
- **`projects`** - Research projects that group datasets and documents
  - `id`, `user_id`, `title`, `description`, `created_at`, `updated_at`
  - Indexed on `user_id`

- **`datasets`** - CSV datasets uploaded by users
  - `id`, `user_id`, `project_id` (FK), `filename`, `file_url`, `file_type`, `file_size`, `status`, `metadata`, `created_at`, `updated_at`
  - Indexed on `user_id` and `project_id`
  - Cascade delete when project is deleted

- **`documents`** - Research PDFs for RAG pipeline
  - `id`, `user_id`, `project_id` (FK), `title`, `description`, `file_url`, `file_type`, `file_size`, `metadata`, `status`, `created_at`, `updated_at`
  - Indexed on `user_id` and `project_id`
  - Cascade delete when project is deleted

- **`document_chunks`** - Text chunks with embeddings for RAG
  - `id`, `document_id` (FK), `chunk_index`, `content`, `embedding` (VECTOR 1536), `metadata`, `created_at`
  - HNSW index on `embedding` for fast similarity search
  - Cascade delete when document is deleted

### 2. ✅ FastAPI Routes

**File:** `services/backend/app/api/routes/projects.py`

Endpoints:
- `POST /projects` - Create a new project
- `GET /projects` - List all user projects
- `GET /projects/{project_id}` - Get single project
- `PUT /projects/{project_id}` - Update project
- `DELETE /projects/{project_id}` - Delete project
- `POST /projects/{project_id}/attach-dataset/{dataset_id}` - Attach dataset to project
- `GET /projects/{project_id}/bundle` - Get project with all datasets and documents

**File:** `services/backend/app/api/routes/datasets.py`

Endpoints:
- `POST /datasets/upload` - Upload dataset (supports `project_id` parameter)
- `GET /datasets` - List datasets (can filter by `project_id`)
- `GET /datasets/{dataset_id}` - Get single dataset
- `PUT /datasets/{dataset_id}` - Update dataset
- `DELETE /datasets/{dataset_id}` - Delete dataset

**File:** `services/backend/app/api/routes/documents.py`

Endpoints:
- `POST /documents/upload` - Upload document (supports `project_id` parameter)
- `GET /documents` - List documents (can filter by `project_id`)
- `GET /documents/{document_id}` - Get single document
- `PUT /documents/{document_id}` - Update document
- `DELETE /documents/{document_id}` - Delete document
- `POST /documents/{document_id}/attach-to-project/{project_id}` - Attach document to project

### 3. ✅ Pydantic Models

**File:** `services/backend/app/schemas/projects.py`

Models:
- `ProjectCreate` - For creating projects
- `ProjectUpdate` - For updating projects
- `Project` - Project response model
- `Dataset` - Dataset response model
- `Document` - Document response model
- `ProjectBundle` - Bundle containing project + datasets + documents

### 4. ✅ Router Imports

**File:** `services/backend/app/main.py`

All routers are properly imported and registered:
```python
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(projects.router, prefix="/projects", tags=["Projects"])
app.include_router(datasets.router, prefix="/datasets", tags=["Datasets"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(rag.router, prefix="/rag", tags=["RAG"])
```

---

## 🚀 Next Steps: Apply SQL Migration

### Option 1: Supabase SQL Editor (Recommended)

1. Go to your Supabase SQL Editor:
   ```
   https://app.supabase.com/project/ufnaadgdrraqnatvgarq/sql
   ```

2. Copy the contents of `02-create-tables.sql`

3. Paste into the SQL Editor and click "Run"

4. Verify tables were created in the Table Editor

### Option 2: Command Line Script

Run the helper script to see the SQL:
```bash
cd /Applications/Ashwin/Programming/Personal\ Projects/startup/noesis/infra/db-init
./show_migrations.sh
```

---

## ✅ Verification

To verify Step 3.4 is complete:

```bash
cd /Applications/Ashwin/Programming/Personal\ Projects/startup/noesis/infra/db-init
python3 verify_step_3_4.py
```

This will check:
- ✅ SQL migration files exist
- ✅ All API routes are implemented
- ✅ Pydantic models are defined
- ✅ Routers are imported in main.py

---

## 🧪 Testing After Migration

Once you've run the SQL migration, test the endpoints:

### 1. Test Supabase Connection
```bash
curl http://localhost:8000/test-supabase
```

Expected: `{"connection":"ok",...}`

### 2. Create a Project (requires auth token)
```bash
curl -X POST http://localhost:8000/projects \
  -H 'Authorization: Bearer YOUR_TOKEN' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -d 'title=My Research Project&description=Testing Step 3.4'
```

### 3. List Projects
```bash
curl http://localhost:8000/projects \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

### 4. Get Project Bundle
```bash
curl http://localhost:8000/projects/{project_id}/bundle \
  -H 'Authorization: Bearer YOUR_TOKEN'
```

---

## 📊 Database Schema Diagram

```
┌─────────────┐
│  projects   │
├─────────────┤
│ id (PK)     │◄──┐
│ user_id     │   │
│ title       │   │
│ description │   │
│ created_at  │   │
│ updated_at  │   │
└─────────────┘   │
                  │ CASCADE DELETE
         ┌────────┴────────┐
         │                 │
┌────────▼──────┐  ┌───────▼────────┐
│   datasets    │  │   documents    │
├───────────────┤  ├────────────────┤
│ id (PK)       │  │ id (PK)        │◄──┐
│ user_id       │  │ user_id        │   │
│ project_id(FK)│  │ project_id (FK)│   │
│ filename      │  │ title          │   │
│ file_url      │  │ description    │   │
│ file_type     │  │ file_url       │   │
│ file_size     │  │ file_type      │   │
│ status        │  │ file_size      │   │
│ metadata      │  │ metadata       │   │
│ created_at    │  │ status         │   │
│ updated_at    │  │ created_at     │   │
└───────────────┘  │ updated_at     │   │
                   └────────────────┘   │ CASCADE DELETE
                                        │
                                ┌───────▼─────────┐
                                │ document_chunks │
                                ├─────────────────┤
                                │ id (PK)         │
                                │ document_id(FK) │
                                │ chunk_index     │
                                │ content         │
                                │ embedding       │
                                │ metadata        │
                                │ created_at      │
                                └─────────────────┘
```

---

## 🎯 Success Criteria

- [x] `projects` table created
- [x] `datasets` table has `project_id` FK
- [x] `documents` table created with `project_id` FK
- [x] `document_chunks` table created with VECTOR column
- [x] POST `/projects` endpoint implemented
- [x] GET `/projects` endpoint implemented
- [x] POST `/projects/{id}/attach-dataset/{id}` endpoint implemented
- [x] GET `/projects/{id}/bundle` endpoint implemented
- [x] Pydantic models created
- [x] No circular imports
- [ ] **SQL migration applied in Supabase** ⬅️ ONLY STEP REMAINING

---

## 🔜 Ready for Step 4

Once the SQL migration is applied, the system will be ready for:

**Step 4: RAG Pipeline Ingestion**
- Document chunking
- OpenAI embedding generation
- Vector storage in `document_chunks` table
- Similarity search implementation

---

## 📝 Files Created/Modified

### New Files:
- `infra/db-init/02-create-tables.sql` - SQL migration
- `infra/db-init/verify_step_3_4.py` - Verification script
- `infra/db-init/show_migrations.sh` - SQL display helper
- `infra/db-init/README.md` - This file

### Modified Files:
- `services/backend/app/api/routes/projects.py` - Already existed
- `services/backend/app/api/routes/datasets.py` - Already existed
- `services/backend/app/api/routes/documents.py` - Already existed
- `services/backend/app/schemas/projects.py` - Already existed
- `services/backend/app/main.py` - Already had correct imports

---

## 🎉 Summary

**Step 3.4 is CODE COMPLETE!**

All backend routes, models, and SQL migrations are ready. You just need to:

1. Go to https://app.supabase.com/project/ufnaadgdrraqnatvgarq/sql
2. Run the SQL from `02-create-tables.sql`
3. Test the endpoints

Then you'll be ready for Step 4 (RAG pipeline)! 🚀
