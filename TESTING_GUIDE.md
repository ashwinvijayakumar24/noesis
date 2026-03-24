# Testing Guide — Pre-Launch Feature Verification

**Date**: March 2026
**Covers**: All changes in LAUNCH_CHANGES.md (4 tracks)

---

## Prerequisites

### Environment Setup
```bash
# 1. Run DB migration (REQUIRED before any testing)
# In Supabase SQL editor, run:
infra/db-migrations/011_shared_paper_cache.sql

# 2. Start local containers
cd infra && docker-compose up --build

# 3. Verify services
curl http://localhost:8000/health          # Backend health
curl http://localhost:8070/api/isalive     # GROBID health
open http://localhost:5173                 # Frontend
```

### Test Account Requirements
- A Noesis account with at least one project
- A project with ≥ 3 uploaded and analyzed documents (for literature grounding tests)
- A draft uploaded to that project (for feedback tests)
- Optional: A real Zotero API key (for Zotero integration tests)

---

## Track 1: Analysis Quality

### 1.1 — Evidence-Grounded Reviewer Feedback

**What changed**: Reviewer feedback now includes paper titles and excerpts from your project library in the GPT prompt. Feedback should cite specific papers by name.

**How to test**:

1. Open a project with ≥ 3 uploaded documents
2. Upload a draft (PDF, DOCX, or TXT) via the Drafts panel
3. Wait for analysis to complete (watch progress bar)
4. Open the **Reviewer Feedback** tab in the Draft Analysis view

**Expected results**:
- Feedback items should reference specific paper titles from your library (e.g., "As shown in 'Attention Is All You Need' (Vaswani et al., 2017)...")
- The overall assessment should mention specific methodology, datasets, or findings from your papers
- Feedback should NOT be generic (e.g., "You should cite more literature" with no specifics)

**Regression check** (what NOT to see):
- ❌ Generic phrases like "cite relevant literature" without naming papers
- ❌ All feedback items saying "N/A" for section references
- ❌ Empty `overall_assessment` field

**Backend verification**:
```bash
# Watch backend logs during analysis to confirm literature context is being used
docker logs -f noesis-backend | grep "literature context"
# Expected: "Literature context: 3 papers available for feedback generation"
```

---

### 1.2 — Embedding-Based Coverage Gap Detection

**What changed**: Coverage gaps are now detected by comparing draft section embeddings against your actual project documents (not GPT hallucination). Only sections with cosine similarity < 0.65 to any document chunk are flagged as real gaps.

**How to test**:

1. Use the same project + draft from 1.1
2. Open the **Coverage Gaps** tab in Draft Analysis
3. Check gaps for quality

**Expected results**:
- Gaps should correspond to topics genuinely missing from your library
- Each critical/major gap may include 1-3 **external paper suggestions** with open-access PDF links (e.g., arXiv URLs)
- Gaps that ARE covered in your library should NOT appear

**Verification via API**:
```bash
curl -X GET "http://localhost:8000/api/drafts/{DRAFT_ID}/gaps" \
  -H "Authorization: Bearer {TOKEN}" | python3 -m json.tool
```

**Expected response shape**:
```json
{
  "gaps": [
    {
      "gap_type": "missing_evidence",
      "description": "Section 3 (Methods) has no supporting literature...",
      "severity": "critical",
      "external_paper_suggestions": [
        {
          "title": "...",
          "authors": "...",
          "year": 2024,
          "open_access_url": "https://arxiv.org/pdf/..."
        }
      ]
    }
  ]
}
```

---

### 1.3 — OpenAlex Client Smoke Test

**What changed**: New OpenAlex API client at `app/services/external_apis/openalex.py`.

**Test via Python**:
```bash
docker exec -it noesis-backend python3 -c "
import asyncio
from app.services.external_apis.openalex import search_works, find_open_access_papers_for_gap

async def test():
    # Test basic search
    results = await search_works('transformer attention mechanism', per_page=3)
    print(f'Search returned {len(results)} results')
    if results:
        print(f'First: {results[0][\"title\"]} ({results[0][\"year\"]})')
        print(f'OA URL: {results[0].get(\"open_access_url\", \"none\")}')

    # Test gap papers
    gap_papers = await find_open_access_papers_for_gap('machine learning fairness metrics')
    print(f'Gap papers: {len(gap_papers)} with OA URLs')

asyncio.run(test())
"
```

**Expected output**:
```
Search returned 3 results
First: Attention Is All You Need (2017)
OA URL: https://arxiv.org/pdf/...
Gap papers: 1-3 with OA URLs
```

---

## Track 2: Paper Extraction & Caching

### 2.1 — Shared Papers DB Table

**What changed**: New `shared_papers` table in Supabase with pgvector index.

**Verify in Supabase**:
1. Open Supabase dashboard → SQL Editor
2. Run:
```sql
-- Check table exists with correct columns
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'shared_papers'
ORDER BY ordinal_position;

-- Check vector index exists
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'shared_papers';

-- Check RLS policies
SELECT policyname, cmd, qual
FROM pg_policies
WHERE tablename = 'shared_papers';
```

**Expected**:
- Table has columns: `id`, `doi`, `arxiv_id`, `title`, `authors`, `year`, `abstract`, `pdf_url`, `embedding`, `source`, `download_count`, `created_at`, etc.
- Index `shared_papers_embedding_idx` exists with `ivfflat` operator
- RLS policies: `SELECT` for authenticated users, `INSERT/UPDATE` for service role

**Test the RPC function**:
```sql
-- Test match_shared_papers function exists
SELECT routine_name FROM information_schema.routines
WHERE routine_name = 'match_shared_papers';
```

---

### 2.2 — Shared Paper Cache Service

**Test via Python**:
```bash
docker exec -it noesis-backend python3 -c "
import asyncio
from app.services.shared_paper_cache import _normalize_doi, _format_semantic_scholar_paper

# Test DOI normalization
tests = [
    ('https://doi.org/10.1234/test', '10.1234/test'),
    ('http://doi.org/10.1234/test', '10.1234/test'),
    ('10.1234/test', '10.1234/test'),
    (None, None),
    ('', None),
]
for input_, expected in tests:
    result = _normalize_doi(input_)
    status = '✓' if result == expected else '✗'
    print(f'{status} _normalize_doi({input_!r}) = {result!r}')

print('DOI normalization: OK')
"
```

**Expected**: All 5 assertions pass with `✓`.

---

### 2.3 — Zotero API Validation

**Test API endpoint** (requires a real Zotero account):

1. Get your Zotero API key from https://www.zotero.org/settings/keys
2. Get your Zotero User ID from https://www.zotero.org/settings/keys (shown at top)

```bash
curl -X POST "http://localhost:8000/api/zotero/validate-key" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {YOUR_NOESIS_TOKEN}" \
  -d '{"api_key": "YOUR_ZOTERO_KEY", "user_id": "YOUR_ZOTERO_USER_ID"}'
```

**Expected response**:
```json
{
  "valid": true,
  "username": "your_username",
  "user_id": 12345,
  "name": "Your Name"
}
```

**Invalid key test**:
```bash
curl -X POST "http://localhost:8000/api/zotero/validate-key" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {YOUR_NOESIS_TOKEN}" \
  -d '{"api_key": "invalidkey123", "user_id": "12345"}'
```

**Expected**: `{"valid": false, "error": "Invalid API key"}`

---

### 2.4 — Zotero Collection Listing

```bash
curl -X POST "http://localhost:8000/api/zotero/libraries" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer {YOUR_NOESIS_TOKEN}" \
  -d '{"api_key": "YOUR_ZOTERO_KEY", "user_id": "YOUR_ZOTERO_USER_ID"}'
```

**Expected response**:
```json
{
  "collections": [
    {
      "key": "ABC123",
      "name": "Machine Learning Papers",
      "item_count": 45
    }
  ]
}
```

---

### 2.5 — Zotero Import Frontend Flow

**How to test in the UI**:

1. Open any project → click **Add Papers** (or **Upload** button)
2. Click the **Zotero** tab (3rd tab, should be visible)
3. Enter your Zotero User ID and API Key
4. Click **Connect to Zotero**
5. Expected: Shows username confirmation ("Connected as Dr. Smith")
6. Select a collection from the dropdown
7. Click **Import Collection**
8. Expected: Progress indicator, then success message with count

**Verify documents created**:
```bash
curl "http://localhost:8000/api/projects/{PROJECT_ID}/documents" \
  -H "Authorization: Bearer {TOKEN}" | python3 -c "
import json, sys
docs = json.load(sys.stdin)
imported = [d for d in docs.get('documents', []) if d.get('status') == 'imported']
print(f'Imported documents: {len(imported)}')
for d in imported[:3]:
    print(f'  - {d[\"title\"]}')
"
```

---

### 2.6 — BibTeX Import with DOI

The existing BibTeX import should now attempt Unpaywall PDF fetches for entries with DOIs.

```bash
# Create a test BibTeX file
cat > /tmp/test.bib << 'EOF'
@article{vaswani2017attention,
  title={Attention Is All You Need},
  author={Vaswani, Ashish and Shazeer, Noam},
  journal={NeurIPS},
  year={2017},
  doi={10.48550/arXiv.1706.03762}
}
@article{devlin2019bert,
  title={BERT: Pre-training of Deep Bidirectional Transformers for Language Understanding},
  author={Devlin, Jacob and Chang, Ming-Wei},
  journal={NAACL},
  year={2019},
  doi={10.18653/v1/N19-1423}
}
EOF

# Import via API
curl -X POST "http://localhost:8000/api/projects/{PROJECT_ID}/import-bibtex" \
  -H "Authorization: Bearer {TOKEN}" \
  -F "file=@/tmp/test.bib"
```

**Expected response**:
```json
{
  "imported": 2,
  "skipped": 0,
  "errors": []
}
```

---

## Track 3: Overleaf Extension

### 3.1 — Extension Installation Check

1. Open Chrome → `chrome://extensions`
2. Enable **Developer mode** (top right)
3. Click **Load unpacked** → select `services/extension/`
4. Verify extension appears with correct name and version

---

### 3.2 — Single-File Overleaf Analysis

1. Open a single-file LaTeX project on Overleaf (overleaf.com)
2. Click the Noesis extension icon
3. Log in if prompted
4. Click **Analyze Draft**

**Expected**:
- Button shows loading state (not disabled immediately)
- Sidebar shows "Processing..." state
- Analysis completes and shows feedback in sidebar
- No `alert()` dialogs appear — errors shown in sidebar panel

---

### 3.3 — Multi-File Warning

1. Open a multi-file LaTeX project on Overleaf (one with `\input{chapter1}` references)
2. Click **Analyze Draft** in the Noesis sidebar

**Expected**:
- Amber warning banner appears: "This project has X referenced files that couldn't be read..."
- Analysis proceeds with the content that was accessible
- Warning is dismissable (× button)

**Verify file metadata in payload** (check browser network tab):
- Request to `/api/drafts/upload` should include:
  ```json
  {
    "is_multi_file": true,
    "file_count": 4,
    "referenced_files": ["chapter1.tex", "chapter2.tex"],
    "unread_files": ["chapter1.tex"]
  }
  ```

---

### 3.4 — Error Handling (No Alert)

1. Disconnect from the internet (or use DevTools to block requests to `localhost:8000`)
2. Try to analyze a draft from Overleaf

**Expected**:
- Red error panel appears in sidebar with message (not `alert()`)
- Error panel has a **×** dismiss button
- Button returns to ready state after error

---

## Track 4: CI/CD Pipeline

### 4.1 — Run Backend Tests Locally

```bash
cd services/backend

# Install test dependencies
pip install pytest-cov pytest-asyncio

# Run all tests with coverage
python -m pytest tests/ -v --tb=short \
  --cov=app \
  --cov-report=term-missing \
  --cov-fail-under=50

# Expected: All tests pass, coverage ≥ 50%
```

**Expected output**:
```
tests/test_analysis_quality.py::TestOpenAlexClient::test_reconstruct_abstract_basic PASSED
tests/test_analysis_quality.py::TestOpenAlexClient::test_reconstruct_abstract_none PASSED
...
tests/test_e2e_workflows.py::TestDraftAnalysisState::test_state_schema_imports PASSED
...
======================== 25 passed in X.XXs ========================
TOTAL coverage: 52%
```

---

### 4.2 — Run Specific Test Files

```bash
# Analysis quality tests only
python -m pytest tests/test_analysis_quality.py -v

# Paper discovery tests only
python -m pytest tests/test_paper_discovery.py -v

# E2E workflow tests only
python -m pytest tests/test_e2e_workflows.py -v
```

---

### 4.3 — Security Scan

```bash
cd services/backend

pip install pip-audit
pip-audit -r requirements.txt --format=json --output=audit.json

# Check results
python3 -c "
import json
with open('audit.json') as f:
    data = json.load(f)
vulns = data.get('vulnerabilities', []) if isinstance(data, dict) else data
if vulns:
    print(f'⚠ Found {len(vulns)} vulnerabilities')
    for v in vulns[:5]:
        print(f'  - {v.get(\"name\", \"\")} {v.get(\"version\", \"\")}')
else:
    print('✓ No known vulnerabilities found')
"
```

---

### 4.4 — CI Pipeline on GitHub

1. Push to `develop` branch (or open a PR)
2. Check GitHub Actions: `.github/workflows/ci.yml`

**Expected jobs to pass**:
- `backend` — pytest with ≥50% coverage threshold
- `security` — pip-audit scan (informational, won't fail CI)
- `frontend` — lint + type check + build

**Check coverage upload**:
- If Codecov is configured, coverage badge should update
- Go to codecov.io to verify the `backend` flag uploaded

---

## Full Integration Test (Happy Path)

This simulates the core user workflow end-to-end:

```bash
# 1. Create a project
PROJECT_ID=$(curl -s -X POST "http://localhost:8000/api/projects" \
  -H "Authorization: Bearer {TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Project", "description": "Integration test"}' | python3 -c "import json,sys; print(json.load(sys.stdin)['id'])")

echo "Project: $PROJECT_ID"

# 2. Upload a paper PDF
curl -X POST "http://localhost:8000/api/projects/$PROJECT_ID/documents" \
  -H "Authorization: Bearer {TOKEN}" \
  -F "file=@/path/to/test-paper.pdf"

# 3. Wait for analysis (poll status)
sleep 30
curl "http://localhost:8000/api/projects/$PROJECT_ID/documents" \
  -H "Authorization: Bearer {TOKEN}" | python3 -c "
import json,sys
docs = json.load(sys.stdin)
for d in docs.get('documents', []):
    print(f'{d[\"title\"]}: {d[\"status\"]}')
"

# 4. Upload a draft
curl -X POST "http://localhost:8000/api/projects/$PROJECT_ID/drafts" \
  -H "Authorization: Bearer {TOKEN}" \
  -F "file=@/path/to/test-draft.pdf" \
  -F "title=Test Draft"

# 5. Check draft analysis for evidence-grounded feedback
sleep 60  # Allow analysis to complete
curl "http://localhost:8000/api/projects/$PROJECT_ID/drafts" \
  -H "Authorization: Bearer {TOKEN}" | python3 -c "
import json,sys
data = json.load(sys.stdin)
for d in data.get('drafts', []):
    print(f'{d[\"title\"]}: {d[\"status\"]}')
"
```

---

## Troubleshooting

### "Literature context: 0 papers" in logs
- Check that your project has documents in **analyzed** status (not just uploaded)
- Check that document_chunks exist: Query `document_chunks` table in Supabase for your project_id

### Zotero "Invalid API key" on a valid key
- Verify you're using the API key (long hex string from Zotero settings), NOT your password
- Check the User ID matches the key owner (shown at top of zotero.org/settings/keys)

### OpenAlex returns empty results
- Check outbound network from Docker container: `docker exec noesis-backend curl https://api.openalex.org/works?search=test`
- If blocked: API calls will gracefully return `[]` (no crash)

### CI coverage below 50%
- Run locally to see which modules are uncovered: `--cov-report=term-missing`
- Most likely: new service files have 0% coverage
- Add simple import tests to bring baseline up

### Extension "TRIGGER_ANALYZE" not received
- Check that sidebar.js is loaded in the extension context
- In Chrome DevTools → Sources → Content Scripts, verify overleaf.js is injected
- Check `chrome.runtime.sendMessage` calls are reaching the background script

---

## Verification Checklist

- [ ] Draft analysis feedback cites specific papers by name from project library
- [ ] Coverage gaps include 2-3 open-access external paper links (OpenAlex)
- [ ] `shared_papers` table exists in Supabase with correct vector index
- [ ] Zotero API key validation returns user info for valid key
- [ ] Zotero import creates document records in the correct project
- [ ] BibTeX import with DOI attempts Unpaywall PDF fetch (check logs)
- [ ] Extension shows multi-file warning (not alert) when referenced files exist
- [ ] Extension shows error panel (not alert) on analysis failure
- [ ] `python -m pytest tests/ --cov-fail-under=50` passes
- [ ] GitHub Actions CI passes on `develop` push

---

## Post-Launch Priorities: Verification

### WebSocket Progress (Priority 1)

**How to test**:
1. Upload a new draft or open one still in `processing` status
2. Watch the progress screen in `DraftAnalysis.tsx`

**Expected**:
- Progress label cycles through real step names (not always "Analyzing Draft"):
  - "Analyzing draft structure..." → "Extracting research claims..." → "Searching literature..." → "Detecting coverage gaps..." → "Generating reviewer feedback..."
- Progress bar uses real increments (10%, 25%, 35%, 50%, 65%, 75%, 88%, 96%, 100%) rather than a smooth asymptotic curve

**Browser DevTools verification**:
1. Open DevTools → Network tab → filter by **WS**
2. Start a draft analysis
3. Expected: A WebSocket connection to `ws://localhost:8000/drafts/{id}/analysis-stream` appears
4. Click the connection → Messages tab → should show JSON frames with `progress`, `step`, `message` fields

**Fallback check**:
- If WebSocket is unavailable (stream.progress stays 0), the `useEstimatedProgress(180)` fallback kicks in automatically — progress bar still advances, just without real step names

---

### Server-Controlled RAG Chunking (Priority 2 / ex-Priority 3)

**Log verification**:
```bash
# Should return ZERO matches (no more rag_settings DB reads)
docker logs noesis-backend | grep "rag_settings"

# Should show page estimate + tier on every draft RAG ingestion
docker logs noesis-backend | grep "Adaptive draft chunking"
# Example: "Adaptive draft chunking — est. pages: 12, chunk_size: 1600, overlap: 250"
```

**Chunk count verification**:
- Upload a ~5-page draft → expect 5-15 chunks (SHORT tier: 1200 tokens each)
- Upload a ~35-page draft → expect more chunks with `chunk_size=2000` (LONG tier)

**Supabase verification** (check chunks were created):
```sql
SELECT draft_id, COUNT(*) as chunk_count
FROM draft_chunks
GROUP BY draft_id
ORDER BY chunk_count DESC
LIMIT 5;
```

---

## Automated Test Run Results — March 17, 2026

**Tested by**: Claude Code (automated)
**Date**: March 17, 2026

### Results Summary

| Test | Status | Notes |
|------|--------|-------|
| Docker containers healthy | PASS | backend, celery-worker, frontend, grobid, redis all running |
| pytest suite (28 tests) | PASS | 28 passed, 7 skipped (async tests need plugin), 0 failed |
| pytest coverage threshold (50%) | FAIL (expected) | 5.87% full-app coverage — see notes below |
| Security scan (pip-audit) | WARNING | 42 vulnerabilities in 13 packages — informational only |
| OpenAlex client | PASS | Returned 3 results, first result had arXiv OA URL |
| Shared paper cache (DOI normalization) | PASS | All 5 normalization cases passed |
| Adaptive chunking assertions | PASS | SHORT/MEDIUM/LONG tiers correct (1200/1600/2000 tokens) |
| rag_settings DB reads eliminated | PASS | Zero matches in backend logs |
| Service imports smoke test | PASS | All 5 services imported cleanly |
| Backend health endpoint | PASS | `{"status": "ok"}` |
| Platform stats endpoint | PASS | Returns valid JSON stats object |

### Issues Found and Fixed

Two bugs were found and fixed during this test run:

**Bug 1: `literature_search.py` — `supabase` imported inside function body (not patchable)**
- **File**: `services/backend/app/workflows/draft_analysis/nodes/literature_search.py`
- **Problem**: `from app.core.supabase_client import supabase` was inside `literature_search_node()` function body, making it impossible for tests to patch `app.workflows.draft_analysis.nodes.literature_search.supabase`. This caused `TestLiteratureSearchNode::test_search_returns_empty_when_no_documents` to fail with `AttributeError: module does not have the attribute 'supabase'`.
- **Fix**: Moved `from app.core.supabase_client import supabase` to module-level imports and removed the duplicate local import inside the function.

**Bug 2: `test_rag_optimization.py` — standalone integration script collected as pytest tests**
- **File**: `services/backend/tests/test_rag_optimization.py`
- **Problem**: This file is a standalone integration script (meant to be run with `python test_rag_optimization.py --project-id ... --user-id ...`), not a pytest test file. Pytest was collecting it and trying to run `test_hybrid_search(project_id)` and `test_integration_layer(project_id, user_id)` as pytest tests, treating `project_id` and `user_id` as fixture names. This caused two `ERROR` entries and 5 spurious `SKIPPED` entries.
- **Fix**: Created `services/backend/conftest.py` with `collect_ignore = ["tests/test_rag_optimization.py"]` to exclude the standalone script from pytest collection.

### Coverage Note

The `--cov-fail-under=50` threshold fails (5.87% total coverage) because the codebase has grown to 11,205 lines across 90+ modules, but the automated test suite only covers specific workflow nodes and key service functions. The **tested modules themselves** have good coverage (reviewer_feedback: 84%, gap_detection: 63%, state: 100%, draft_analysis_state: 100%). The gap is that most routes, services, and tasks have 0% automated test coverage — they require either live Supabase + OpenAI connections or a full integration test environment.

This is a known limitation documented in the TESTING_GUIDE. To meet the 50% threshold in CI, coverage would need to be scoped to `--cov=app.workflows` only (tested modules), or the threshold would need to be lowered to reflect the current test scope.

### Security Vulnerabilities Found (pip-audit)

42 total vulnerabilities in 13 packages. All are informational — CI is configured not to fail on these. Key packages needing upgrades:

| Package | Current | Issue |
|---------|---------|-------|
| python-jose | 3.3.0 | CVE-2024-33664 (JWT bomb DoS), CVE-2024-33663 (algorithm confusion) — fix: upgrade to 3.4.0 |
| langgraph | 0.2.64 | CVE-2026-28277 (msgpack deserialization RCE) — fix: upgrade to latest |
| langgraph-checkpoint | 2.1.2 | CVE-2025-64439, CVE-2026-27794 (RCE via checkpoint cache) — fix: upgrade to 3.0+ |
| langchain-core | 0.3.63 | CVE-2025-65106 (template injection), CVE-2025-68664 (serialization injection) |
| aiohttp | 3.11.11 | 9 vulnerabilities including request smuggling (CVE-2025-53643) |
| pypdf | 5.1.0 | 15 vulnerabilities (PDF parsing DoS/crashes) |
| starlette | 0.41.3 | CVE-2025-54121 (multipart DoS), CVE-2025-62727 (Range header DoS) |
| ecdsa | 0.19.1 | CVE-2024-23342 (Minerva timing attack) |
| sentry-sdk | 1.40.0 | CVE-2024-40647 (env var exposure) |

### Requires Manual Testing (Frontend/Browser)

- Track 1.1: Evidence-grounded reviewer feedback (needs real draft analysis)
- Track 1.2: Coverage gap quality check (needs project with documents)
- Track 2.1: Shared papers DB table (needs Supabase dashboard access)
- Track 2.3–2.5: Zotero integration (needs real Zotero account)
- Track 2.6: BibTeX import with DOI (needs API token)
- Track 3.1–3.4: Overleaf extension (needs browser + Overleaf)
- Track 4.4: CI pipeline (needs GitHub push)
- Post-Launch Priority 1: WebSocket DevTools verification (needs browser + active analysis)
