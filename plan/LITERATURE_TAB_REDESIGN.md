# Literature Tab Redesign

**Branch:** `develop`
**Status:** Implementation complete — awaiting DB migration + container rebuild before testing

---

## What Changed

### Core UX shifts
- Unified paper list replaces the split "Your Papers" / "Imported References" layout
- BibTeX import is now non-blocking — modal stays open showing live resolution progress
- Separate quota pools: 10 PDFs/month and 10 BibTeX refs/month (independent)
- Shared paper cache now consulted before GPT-5.2 calls, reducing redundant API usage

---

## Files Changed

| File | What changed |
|---|---|
| `infra/db-migrations/012_literature_tab_redesign.sql` | **CREATE** — `source_type`, `resolution_status` on `documents`; bib quota columns on `user_quotas` |
| `services/backend/app/services/bibtex_resolution_service.py` | **CREATE** — OA PDF search → download → GROBID → GPT-5.2 → RAG ingest pipeline |
| `services/backend/app/tasks/bibtex_resolution_task.py` | **CREATE** — Celery task wrapper for the resolution service |
| `services/frontend/src/components/literature/PaperCard.tsx` | **CREATE** — Unified card (replaces `DocumentCard` + `ImportedRefCard` in the lit tab) |
| `services/backend/app/services/quota_management.py` | `bib_import` quota type, `count` param on `increment_quota_usage`, 10-doc default, `get_quota_summary()` |
| `services/backend/app/api/routes/projects.py` | BibTeX import: quota check, `source_type`/`resolution_status` set, Celery task submitted; new `GET /{project_id}/bib-resolution-status` endpoint |
| `services/backend/app/api/routes/documents.py` | `source_type='manual_upload'` on upload; shared cache check before GPT; cache write after analysis |
| `services/backend/app/api/routes/auth.py` | New `GET /auth/quota-summary` endpoint |
| `services/backend/app/tasks/__init__.py` | Exports `resolve_bibtex_task` |
| `services/frontend/src/lib/api.ts` | `projects.getBibResolutionStatus()`, `quota.getSummary()` |
| `services/frontend/src/pages/ProjectDetail.tsx` | Unified literature tab: filter pills, sort dropdown, `PaperCard`, polling for resolving entries |
| `services/frontend/src/components/UploadDocumentModal.tsx` | Full redesign: quota bars, BibTeX live resolution panel, Zotero tab redesign |
| `services/backend/tests/test_bibtex_resolution.py` | **CREATE** — 17 unit tests |
| `services/backend/tests/test_quota_management.py` | **CREATE** — 16 unit tests |
| `services/backend/tests/test_shared_cache_integration.py` | **CREATE** — 12 unit tests |

---

## Pre-Testing Checklist

These must be done before testing any of the new behavior:

- [ ] **Run DB migration** on Supabase: `infra/db-migrations/012_literature_tab_redesign.sql`
  - Adds `source_type` and `resolution_status` to `documents`
  - Adds `current_month_bib_refs` and `monthly_bib_refs_limit` to `user_quotas`
- [ ] **Rebuild Docker containers**: `cd infra && docker-compose down && docker-compose up --build`
- [ ] Optionally update `Pricing.tsx` to reflect the new 10 PDFs/month free-tier limit (previously showed 50)

---

## Manual Test Scenarios

### 1. Manual PDF upload
1. Open a project → Literature tab → click "Add Papers"
2. Upload a PDF on the PDF tab
3. Verify card appears in the unified list with a "PDF" source badge
4. Status should animate: `Uploaded → Analyzing → Processed`
5. Click the card → should navigate to document detail page

### 2. Cache hit on duplicate PDF
1. Upload the same PDF (or a paper with the same DOI) twice across two different projects
2. Check backend logs: second upload should log `✓ CACHE HIT for DOI ... — skipping GPT-5.2 call`
3. Second paper should still show full analysis

### 3. BibTeX import — OA PDF found
1. Click "Add Papers" → BibTeX tab
2. Upload a `.bib` file containing an arXiv paper (e.g., BERT, GPT-3)
3. Click "Import & Resolve"
4. Modal should stay open and switch to the resolution panel
5. Entry should progress: `Searching → Found PDF → Analyzing → Processed`
6. Click "Continue to Literature" → paper appears in the list with "BibTeX" source badge and "Processed" status

### 4. BibTeX import — no OA PDF
1. Import a `.bib` entry for a paywalled journal paper (no arXiv version)
2. In the resolution panel, entry should show "No OA PDF — Metadata only"
3. In the literature list, card should show abstract inline and a "BibTeX" badge
4. Card should not be clickable (no full analysis)

### 5. Quota enforcement
1. Import 10 BibTeX entries (using up the free-tier BibTeX pool)
2. Try importing an 11th entry
3. Should get a quota error with a clear message before any records are created
4. PDF uploads should still work (separate pool)

### 6. Filter and sort
1. Literature tab with a mix of PDF and BibTeX documents
2. Click "BibTeX" filter pill → only BibTeX cards shown
3. Click "PDF" → only PDF cards shown
4. Click "All" → everything visible
5. Sort by "By status" → Processed cards should group at top

### 7. Delete
1. Delete a resolved BibTeX document from the literature tab
2. Card disappears from the list
3. Verify in Supabase: `shared_papers` table still has the paper (global cache unaffected)

### 8. Run unit tests
```bash
docker exec noesis-backend python -m pytest tests/test_bibtex_resolution.py tests/test_quota_management.py tests/test_shared_cache_integration.py -v
# Expected: 45 passed
```

---

## New API Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/projects/{project_id}/bib-resolution-status` | Returns per-entry resolution status for BibTeX imports. Polled every 3s by the modal. |
| `GET` | `/auth/quota-summary` | Returns `{pdfs: {used, limit}, bib_refs: {used, limit}, plan_tier, reset_date}` for upload modal display. |

---

## Data Model Changes

### `documents` table (new columns)
| Column | Type | Values |
|---|---|---|
| `source_type` | TEXT | `manual_upload` \| `bibtex_import` \| `zotero_import` \| `discovered` |
| `resolution_status` | TEXT \| NULL | `resolving` \| `resolved` \| `unresolved` \| NULL |

### `user_quotas` table (new columns)
| Column | Type | Default |
|---|---|---|
| `current_month_bib_refs` | INTEGER | 0 |
| `monthly_bib_refs_limit` | INTEGER | 10 |

---

## BibTeX Resolution Flow (backend)

```
import_bibtex endpoint called
  → quota check (bib_import pool)
  → create document records with source_type='bibtex_import', resolution_status='resolving'
  → return immediately (non-blocking)
  → Celery task: resolve_bibtex_task.delay(document_ids, user_id, project_id)

Per entry (bibtex_resolution_service.py):
  1. Check shared_papers by DOI          → cache hit → apply analysis + RAG ingest → 'resolved'
  2. Check shared_papers by title (0.85) → cache hit → apply analysis + RAG ingest → 'resolved'
  3. Search Semantic Scholar / Unpaywall → OA PDF found → download → GROBID → GPT-5.2 → RAG ingest → cache write → 'resolved'
  4. No OA PDF                           → embed title+abstract only → 'unresolved'
```
