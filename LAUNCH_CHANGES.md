# Launch Changes — Pre-Launch Implementation

**Date**: March 2026
**Tracks**: 4 parallel worktrees merged into develop

---

## Track 1: Analysis Quality

### Problem Fixed
The LangGraph workflow retrieved literature from the project library but then discarded it before generating feedback. GPT received only structural metadata — no actual paper text — making feedback feel generic.

### Changes

**`services/backend/app/workflows/draft_analysis/nodes/reviewer_feedback.py`**
- Added `_build_literature_context()` function that collects paper titles + excerpts from `literature_search_results` state
- Updated `REVIEWER_FEEDBACK_PROMPT` to explicitly instruct GPT to cite specific papers by name
- Passes up to 5 deduplicated papers (sorted by similarity score) as grounding context
- Logs whether literature context is available for each analysis run

**`services/backend/app/services/coverage_analysis.py`**
- Added `analyze_coverage_with_embeddings()` function
- Embeds each draft section (title + first 400 chars) and compares against project's document_chunks via pgvector
- Sections with max cosine similarity < 0.65 are identified as real gaps (embedding-detected, not hallucinated)
- For critical/major gaps, queries OpenAlex for open-access external papers (fire-and-forget async)
- Returns gap list with `external_paper_suggestions` containing OA PDF links

**`services/backend/app/services/external_apis/openalex.py`** *(NEW)*
- Free scholarly database client (100K requests/day, no auth needed)
- `search_works(query, per_page, open_access_only)` — search with OA filtering
- `get_work_by_doi(doi)` — fetch specific paper by DOI
- `search_concepts(topic)` — get related academic concepts for query expansion
- `find_open_access_papers_for_gap(gap_description, limit)` — returns only papers with free PDF links
- Includes polite pool header (`mailto=contact@noesis.is`) for better rate limits
- Reconstructs abstracts from OpenAlex inverted index format

---

## Track 2: Paper Extraction & Caching

### Changes

**`infra/db-migrations/011_shared_paper_cache.sql`** *(NEW)*
- Creates `shared_papers` table with `VECTOR(1536)` embedding column
- IVFFlat index for fast cosine similarity search
- Full-text search GIN index on title + abstract
- `match_shared_papers()` RPC function for semantic search
- RLS: readable by all authenticated users, writable only by service role

**`services/backend/app/services/shared_paper_cache.py`** *(NEW)*
- `get_or_fetch_paper(doi, title, arxiv_id)` — checks cache first, then fetches from Semantic Scholar/OpenAlex
- `store_paper(paper_data)` — saves paper with embedding to shared_papers table
- `find_similar_papers(query, limit)` — semantic search over all cached papers via pgvector
- Handles duplicate DOI/arXiv gracefully (no error on re-insert)

**`services/backend/app/services/zotero_service.py`** *(NEW)*
- `validate_api_key(api_key)` — validates Zotero key at api.zotero.org/keys
- `list_collections(api_key, zotero_user_id)` — lists all user collections
- `fetch_collection_items(api_key, zotero_user_id, collection_key, limit)` — paginated item fetch
- `import_collection(...)` — bulk imports Zotero items as document records
- `_fetch_oa_pdf_for_document(doi, document_id)` — background Unpaywall lookup for imported DOIs
- Supports item types: journalArticle, conferencePaper, book, bookSection, thesis, report, preprint

**`services/backend/app/api/routes/zotero.py`** *(NEW)*
- `POST /api/zotero/validate-key` — validate key + return user info
- `POST /api/zotero/libraries` — list collections for a user
- `POST /api/zotero/import` — import collection into a Noesis project

**`services/backend/app/main.py`**
- Registered Zotero router at `/api` prefix

**`services/frontend/src/lib/api.ts`**
- Added `api.zotero.validateKey()`, `api.zotero.getLibraries()`, `api.zotero.importCollection()`

**`services/frontend/src/components/UploadDocumentModal.tsx`**
- Added "Zotero" tab (3 tabs total: Upload PDF, Zotero, BibTeX)
- Zotero tab: API key input → validate → show collections → import
- Two-step flow: validate first (shows username), then select collection and import

---

## Track 3: Overleaf Extension + Research

### Changes

**`OVERLEAF_INTEGRATION.md`** *(NEW)*
- Technical feasibility analysis
- ToS analysis (safe for current use case — similar to Writefull)
- Multi-file support architecture and trade-offs
- Real-time suggestions requirements (needs GPT-5-mini for cost control)
- Zotero Connector integration via port 23119
- Overleaf partnership program path
- Risk table with mitigations
- Prioritized fixes roadmap

**`services/extension/content/overleaf.js`**
- Added `extractAllProjectFiles()` — reads file names from Overleaf file tree DOM
- Added `parseInputReferences()` — parses `\input{}` / `\include{}` / `\subfile{}` from active content
- Added `buildContentPayload()` — combines content + multi-file metadata
- Added `setButtonState(state)` — proper loading/success/error states (no more `alert()`)
- Multi-file projects include `file_count`, `referenced_files`, `unread_files` in payload
- Content script now handles `TRIGGER_ANALYZE` message from sidebar
- Sends `SHOW_ERROR` message to sidebar instead of `alert()`
- Sends `MULTI_FILE_WARNING` when project has unread referenced files

**`services/extension/sidebar/sidebar.js`**
- Added `errorMessage` and `multiFileWarning` state fields
- Renders non-blocking error panel (with dismiss button) instead of alert
- Shows multi-file warning (amber) during processing state
- Added `chrome.runtime.onMessage` listener for `SHOW_ERROR`, `MULTI_FILE_WARNING`, `SHOW_LOGIN_PROMPT`

---

## Track 4: Testing & CI/CD

### Changes

**`services/backend/tests/test_analysis_quality.py`** *(NEW)*
- 10 unit tests for OpenAlex client, reviewer feedback node, coverage analysis
- Tests: abstract reconstruction, paper formatting, search (mock), timeout handling, literature context building, deduplication, citation strength categorization, gap prioritization

**`services/backend/tests/test_paper_discovery.py`** *(NEW)*
- 9 unit tests for shared paper cache, Zotero service, BibTeX import
- Tests: DOI normalization, Semantic Scholar formatting, cache hit/miss, Zotero item conversion (journal articles, notes filtered, no title filtered), API key validation, BibTeX parsing

**`services/backend/tests/test_e2e_workflows.py`** *(NEW)*
- 6 end-to-end workflow tests with mocked dependencies
- Tests: state schema, feedback with literature context (verifies GPT receives paper names), feedback cache skip, gap detection with no data, missing_evidence gap creation, literature search with no claims

**`.github/workflows/ci.yml`**
- Added `pytest-cov` for coverage reporting with `--cov-fail-under=50` threshold
- Added Codecov upload step
- Added `security` job: `pip-audit` dependency vulnerability scan
- Coverage reporting to codecov.io with `flags: backend`

---

## Database Migration Required

**Run on Supabase before deploying**:
```bash
# In Supabase SQL editor, run:
infra/db-migrations/011_shared_paper_cache.sql
```

---

## Files Changed Summary

| File | Change Type | Track |
|------|-------------|-------|
| `app/services/external_apis/openalex.py` | NEW | 1 |
| `app/workflows/draft_analysis/nodes/reviewer_feedback.py` | MODIFIED | 1 |
| `app/services/coverage_analysis.py` | MODIFIED | 1 |
| `infra/db-migrations/011_shared_paper_cache.sql` | NEW | 2 |
| `app/services/shared_paper_cache.py` | NEW | 2 |
| `app/services/zotero_service.py` | NEW | 2 |
| `app/api/routes/zotero.py` | NEW | 2 |
| `app/main.py` | MODIFIED | 2 |
| `frontend/src/lib/api.ts` | MODIFIED | 2 |
| `frontend/src/components/UploadDocumentModal.tsx` | MODIFIED | 2 |
| `OVERLEAF_INTEGRATION.md` | NEW | 3 |
| `extension/content/overleaf.js` | MODIFIED | 3 |
| `extension/sidebar/sidebar.js` | MODIFIED | 3 |
| `tests/test_analysis_quality.py` | NEW | 4 |
| `tests/test_paper_discovery.py` | NEW | 4 |
| `tests/test_e2e_workflows.py` | NEW | 4 |
| `.github/workflows/ci.yml` | MODIFIED | 4 |
