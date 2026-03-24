# Next Steps — Post-Launch Priorities

**Date**: March 2026
**Context**: Pre-launch implementation complete (Tracks 1-4). These are the highest-leverage improvements after the launch stabilizes.

---

## ✅ Priority 1: WebSocket Streaming for Real-Time Progress — COMPLETED (March 17, 2026)

**What was built**: `useAnalysisStream` hook connects via WebSocket to `/drafts/{id}/analysis-stream`. `DraftAnalysis.tsx` now reads real progress + step message from the stream instead of the fake `useEstimatedProgress` fallback. The 3s polling loop is retained as a completion safety net.

**Files changed**: `services/frontend/src/pages/DraftAnalysis.tsx` (import + hook call + ProgressIndicator props + stream.complete effect)

---

## ✅ Priority 2: Server-Controlled RAG Chunking (ex-Priority 3) — COMPLETED (March 17, 2026)

**What was done**:
- `rag_retrieval.py`: Removed `rag_settings` DB fetch per retrieval call; hardcoded server defaults (`text-embedding-3-large`, 5 chunks, 0.0 threshold)
- `draft_rag_integration.py`: Removed `rag_settings` DB fetch; replaced with `get_optimal_chunk_params()` adaptive chunking based on estimated page count

**Files changed**: `services/backend/app/services/rag_retrieval.py`, `services/backend/app/services/draft_rag_integration.py`

---

## ✅ Imported References: Abstract Embedding + Literature Tab Split — COMPLETED (March 2026)

**What was built**:
- `embed_imported_document()` in `rag_ingest.py`: embeds title + abstract for BibTeX/Zotero imports into `document_chunks` (one chunk per document, `text-embedding-3-large`)
- Called from `projects.py` (BibTeX import route) and `zotero_service.py` (`import_collection`) after each successful document insert — non-fatal if embedding fails
- Literature tab split into two sections: "Uploaded Papers" (full analysis, `DocumentCard`) and "Imported References" (abstract search only, `ImportedRefCard`)
- New `ImportedRefCard` component: source badge (Zotero/BibTeX), title, authors/year/journal, collapsible abstract snippet, DOI link, "Metadata only" + "Abstract indexed" badges
- Imported references now contribute to RAG search, gap detection, and citation suggestions via abstract embeddings

**Files changed**: `services/backend/app/services/rag_ingest.py`, `services/backend/app/api/routes/projects.py`, `services/backend/app/services/zotero_service.py`, `services/frontend/src/pages/ProjectDetail.tsx`, `services/frontend/src/components/literature/ImportedRefCard.tsx` (new)

---

## Priority 3: Remove User-Adjustable RAG Settings (UI Layer)

**Why**: Users can currently change chunk sizes and overlap in the UI (RAGSettingsModal.tsx). This causes support tickets and is technically unnecessary — users don't know the right values, and our defaults are already optimized.

**What to remove** (backend service layer already done — see ✅ Priority 2 above):
- `services/frontend/src/components/RAGSettingsModal.tsx` — delete entirely
- `services/backend/app/api/routes/rag.py` — remove or lock settings endpoints
- `services/backend/app/api/routes/projects.py` — remove `rag_settings` from project update

**Effort**: 0.5 day (backend already done)

---

## Priority 4: More Paper Sources

**Current**: PubMed, arXiv, Semantic Scholar (paper_discovery_agent.py) + OpenAlex (new)

**Add next**:

### CrossRef (free, comprehensive)
```python
# services/backend/app/services/external_apis/crossref.py
# GET https://api.crossref.org/works?query={query}&rows=10&mailto=contact@noesis.is
# Best for: recent publications, exact DOI lookup, citation counts
```

### IEEE Xplore (engineering/CS focus)
- Requires free API key registration at developer.ieee.org
- Best for: conference papers, IEEE transactions
- Rate limit: 200 req/day (free tier)

### CORE (open access repository aggregator)
- `api.core.ac.uk/v3/search/works?q={query}`
- Requires free API key
- Best for: preprints and OA versions of paywalled papers

### Europe PMC (life sciences)
- `europepmc.org/backend/eupmc/findArticleIds.cgi`
- No auth needed
- Best for: biomedical research (complements PubMed)

**Integration approach**: Add each as a separate module in `app/services/external_apis/` following the OpenAlex pattern. Route through paper_discovery_agent.py which already handles source aggregation and deduplication.

---

## Priority 5: Overleaf Partnership Program

**Background**: See `OVERLEAF_INTEGRATION.md` for full analysis.

**Action items**:
1. Apply to Overleaf's integration partner program: overleaf.com/for/partners
2. Reference Writefull as comparable integration (they got special embed access via partnership)
3. In the interim, the current content script approach works for personal use

**What partnership unlocks**:
- Official Overleaf OAuth: users auth once, extension reads files via API (no DOM parsing)
- Multi-file project access via Overleaf API (vs. current DOM scraping)
- Overleaf marketplace listing → organic discovery from their user base (~10M users)

**Timeline**: Apply now, expect 2-4 week response. Partnership likely requires paid revenue/users.

---

## Priority 6: GPT-5.2-mini for Cheap Tasks

**Why**: Not all analysis steps need full GPT-5.2. Using a smaller model for simple tasks reduces cost by 60-80%.

**Candidates for gpt-5.2-mini**:
- `literature_search_node.py` — query expansion (simple text transformation)
- `claim_analysis.py` — claim categorization (classification, not generation)
- `citation_quality.py` — confidence scoring
- `gap_detection.py` — gap type classification

**Keep on GPT-5.2**:
- `reviewer_feedback.py` — the flagship feature, quality matters most here
- `document_analysis.py` — deep paper analysis needs the full model
- `coverage_analysis.py` — nuanced academic judgment

**Estimated savings**: ~40% cost reduction per draft analysis

**Implementation**: Change `model="gpt-5.2"` → `model="gpt-5.2-mini"` in the appropriate service files. No other API changes needed (same endpoint, same `max_completion_tokens` parameter).

---

## Priority 7: Overleaf Real-Time Suggestions

**Background**: Currently the extension does a single synchronous POST when the user clicks "Analyze Draft". Real-time suggestions (feedback as you type) would be more useful but require:

1. **Cost control**: At $0.01-0.05 per analysis, real-time triggering on every keystroke is not viable. Need a debounced "paragraph-complete" trigger.
2. **GPT-5.2-mini**: Even debounced, use the cheaper model for incremental suggestions.
3. **WebSocket streaming from backend**: The analysis result streams in via WebSocket (Priority 1 prerequisite).
4. **Selective analysis**: Only re-analyze the changed section, not the full draft.

**Effort**: 1-2 weeks after WebSocket streaming is implemented.

---

## Priority 8: Embedding Cache for Shared Papers

**Why**: When multiple users analyze drafts with similar claims, we re-embed the same query text repeatedly. Adding a Redis embedding cache for shared paper lookups would reduce OpenAI embedding API calls.

**Pattern already exists**: `services/embedding_cache.py` (Redis-backed, 7-day TTL) is already in use for document analysis. Extend it to `shared_paper_cache.py` queries.

```python
# In shared_paper_cache.py → find_similar_papers()
cached = await embedding_cache.get(f"query:{query_hash}")
if cached:
    return cached
# ... embed, search, return, cache
```

**Effort**: 1-2 hours (just wire existing cache service into shared_paper_cache.py)

---

## Priority 9: Analytics for Launch Metrics

**Current**: Analytics dashboard tracks MAU, DAU, activation, retention (Feb 2026 implementation).

**Add for launch tracking**:
- **Feature adoption**: % of users who use Zotero import (vs. BibTeX vs. PDF upload)
- **Feedback quality signal**: Track if users click "thumbs up/down" on reviewer feedback items
- **Gap engagement**: Track if users click external paper suggestion links (OpenAlex OA links)
- **Overleaf extension installs**: Track extension install count via Chrome Web Store Developer API

**Implement as new analytics events** in `services/analytics_service.py`:
```python
EVENT_ZOTERO_IMPORT = "zotero_import"
EVENT_FEEDBACK_REACTION = "feedback_reaction"  # thumbs up/down
EVENT_EXTERNAL_PAPER_CLICK = "external_paper_click"
```

---

## Priority 10: GROBID Full-Text for Shared Papers

**Why**: Currently, shared_paper_cache.py stores metadata + abstract only. Full-text extraction would enable much richer evidence quotes in reviewer feedback.

**Flow**:
1. When a paper has an `open_access_url` (PDF link), download it
2. Run through GROBID (already deployed in infra): `http://grobid:8070/api/processFulltextDocument`
3. Parse TEI XML → extract structured sections
4. Store `full_text` in `shared_papers.full_text` column
5. Use full-text passages (not just abstract) in `_build_literature_context()`

**Effort**: 2-3 days (download + GROBID processing pipeline for shared papers)

**Impact**: Highest potential quality improvement. Reviewer feedback quotes could include actual methodology details, not just abstract sentences.

---

## Quick Wins (< 2 hours each)

| Task | File | What |
|------|------|------|
| Cache OpenAlex responses | `external_apis/openalex.py` | Add 1-hour Redis cache for `search_works()` results |
| Add Zotero to analytics | `analytics_service.py` | Track `zotero_import` events |
| Extension version badge | `extension/manifest.json` | Bump version to 1.1.0 after multi-file support |
| Shared papers count endpoint | `api/routes/projects.py` | `GET /projects/{id}/library-stats` (total papers cached) |
| OpenAlex in paper discovery | `paper_discovery_agent.py` | Add OpenAlex as 4th source alongside PubMed/arXiv/Semantic Scholar |

---

## Technical Debt to Address

1. **Remove `max_tokens` fallback** in any older files that might still use it — run `grep -r "max_tokens" services/backend/` to audit
2. **pytest-asyncio mode**: Tests using `async def` without `@pytest.mark.asyncio` will start raising warnings in newer pytest-asyncio versions → add `asyncio_mode = "auto"` to `pytest.ini`
3. **Zotero rate limiting**: The `/api/zotero/import` endpoint uses `slowapi` at 5/minute but `zotero_service.py` itself has no internal rate limiting for the Zotero API — add `asyncio.sleep(0.2)` between item fetches in `fetch_collection_items()`
4. **`shared_papers` index tuning**: The IVFFlat index uses default `lists=100`. Once the table has > 10K rows, re-run `SET ivfflat.probes = 10` for better recall.

---

## Database Migrations Queue

| Migration | File | When |
|-----------|------|------|
| ✅ Shared papers table | `011_shared_paper_cache.sql` | BEFORE deploy |
| Pending: Feedback reactions table | `012_feedback_reactions.sql` | After Priority 9 |
| Pending: Full-text column index | `013_shared_papers_fts.sql` | After Priority 10 |
