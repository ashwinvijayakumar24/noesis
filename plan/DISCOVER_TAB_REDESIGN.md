# Discover Tab Redesign — Implementation Record

**Date:** March 21, 2026
**Branch:** develop
**Status:** Complete — pending DB migration on Supabase

---

## Overview

Replaced the split Discover tab (PaperRecommendations + PaperDiscoveryModal) with a single unified experience. Users can find papers via context-based generation or free-text search. All results live in a persistent pool (max 20). Any paper can be saved to the Literature tab where the full AI pipeline runs (GROBID → GPT-5.2 → RAG embed).

---

## Files Changed

### New Files

| File | Description |
|---|---|
| `infra/db-migrations/013_discover_tab_redesign.sql` | Adds `discovery_type`, `search_query`, `bib_saved` columns to `paper_recommendations`; adds composite index |

### Modified Files

| File | Change |
|---|---|
| `services/backend/app/api/routes/paper_recommendations.py` | Full rewrite — new Redis quota helpers, updated `generate` endpoint, new `search` + `save-discovered` + `quota-status` endpoints |
| `services/backend/app/services/paper_recommendations.py` | Appended `search_papers_by_query()` function |
| `services/frontend/src/components/DiscoverTab/index.tsx` | Full rewrite (52 → 644 lines) — unified UI, inline `DiscoverPaperCard`, quota indicators, 3 empty states |
| `services/frontend/src/lib/api.ts` | Added `api.discover.*` namespace (6 methods) |
| `services/frontend/src/pages/ProjectDetail.tsx` | Pass `documentCount={documents.length}` prop to `DiscoverTab` |

### Deleted Files

| File | Reason |
|---|---|
| `services/frontend/src/components/PaperDiscoveryModal.tsx` | Replaced by inline search bar in DiscoverTab |

---

## Database Migration

**File:** `infra/db-migrations/013_discover_tab_redesign.sql`

```sql
ALTER TABLE paper_recommendations
  ADD COLUMN IF NOT EXISTS discovery_type TEXT DEFAULT 'recommended';

ALTER TABLE paper_recommendations
  ADD COLUMN IF NOT EXISTS search_query TEXT DEFAULT NULL;

ALTER TABLE paper_recommendations
  ADD COLUMN IF NOT EXISTS bib_saved BOOLEAN DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_paper_recs_discovery_type
  ON paper_recommendations(discovery_type, project_id);
```

**Must be run manually on Supabase before the new endpoints work.**

---

## Backend Changes

### New Redis quota keys

| Key | Limit | Resets |
|---|---|---|
| `daily_discover_refresh:{user_id}:{date}` | 1/day | 25h TTL |
| `daily_discovery:{user_id}:{date}` | 3/day | 25h TTL (reused from paper discovery) |
| `daily_bib_save:{user_id}:{date}` | 3/day | 25h TTL |

All quota checks fail open (Redis errors are logged but do not block the request).

### Updated endpoint: `POST /paper-recommendations/projects/{project_id}/generate`

- Enforces 1x/day Redis quota (`daily_discover_refresh`)
- Counts existing recs; hard-deletes the oldest `N` rows if `existing + 5 > 20`
- Calls `generate_paper_recommendations(..., limit=5)` (was limit=20)
- Inserts with `discovery_type='recommended'`, `search_query=NULL`, `bib_saved=False`
- Returns `total_held` in response

### New endpoint: `POST /paper-recommendations/projects/{project_id}/search`

```
Body: { "query": string }
```

- Enforces 3x/day Redis quota (`daily_discovery`)
- Same rolling-pool eviction as generate (hard-delete oldest if cap exceeded)
- Calls `search_papers_by_query(query, limit=5)` — new service function
- Deduplicates results against existing recs in the project (by DOI / arXiv ID / normalized title)
- Inserts with `discovery_type='searched'`, `search_query=query`, `bib_saved=False`

### New endpoint: `POST /paper-recommendations/projects/{project_id}/save-discovered/{recommendation_id}`

- Verifies rec ownership; returns 409 if `bib_saved=True` already
- Checks `daily_bib_save` Redis quota (3/day)
- Checks monthly `bib_import` quota via `quota_management.check_quota()`
- Inserts a `documents` row with `source_type='bibtex_import'`, `resolution_status='resolving'`
- Fires `resolve_bibtex_task.delay([doc_id], user_id, project_id)` Celery task
- Sets `bib_saved=True` on the recommendation row
- Increments both Redis daily counter and monthly quota

### New endpoint: `GET /paper-recommendations/projects/{project_id}/quota-status`

Returns current daily/monthly usage for all three quota types plus `total_held` and `max_pool`.

### New service function: `search_papers_by_query(query, limit=5)`

Located in `services/backend/app/services/paper_recommendations.py`.

1. Queries Semantic Scholar (up to 10 results)
2. Supplements with arXiv if fewer than 5 results
3. Deduplicates via existing `_deduplicate_papers()`
4. Scores via existing `_score_papers()` using query tokens as keywords
5. Returns top `limit` sorted by `relevance_score` descending

---

## Frontend Changes

### DiscoverTab rewrite (`DiscoverTab/index.tsx`)

**Layout:**
```
Header: "Discover" + subtitle | "{N} / 20 papers" badge (amber ≥16, red =20)
Action row: [Find Papers for My Project] + [search bar 🔍]
Paper list: DiscoverPaperCard × N
Empty state (context-aware)
```

**DiscoverPaperCard (inline component):**
- Source badge: SS (indigo) / arXiv (violet) / PM (emerald)
- Title (2-line clamp), author line, relevance bar (recommended only), abstract preview
- Action buttons: View Paper, PDF (green if OA, gray + disabled tooltip if none), Save to Literature
- "Saved ✓" state after save; dismiss X (hard delete)

**Empty states:**
1. `documentCount === 0`: BookOpenIcon — "Start discovering papers"
2. `documentCount > 0`, `papers.length === 0`: MagnifyingGlassIcon — "Ready to explore"
3. Loading: 3 pulse skeleton cards

**Quota indicators:**
- "Find Papers" button disabled + tooltip when quota used or no docs uploaded
- Search usage counter below input when `search_used >= 1`
- Save button disabled with tooltip when `bib_save_used >= 3`
- Pool badge turns amber at 16, red at 20

**Error handling:** 429 responses map to specific user-friendly toast messages per endpoint.

### API client additions (`api.ts`)

```typescript
api.discover.list(token, projectId)
api.discover.findForProject(token, projectId)
api.discover.search(token, projectId, query)
api.discover.saveToLiterature(token, projectId, recommendationId)
api.discover.dismiss(token, recommendationId)
api.discover.getQuotaStatus(token, projectId)
```

### ProjectDetail.tsx

Changed `<DiscoverTab projectId={projectId} />` to `<DiscoverTab projectId={projectId} documentCount={documents.length} />` so the "Find Papers" button can be disabled when no documents exist.

---

## Quota Summary (Free Tier, Beta)

| Quota | Limit | Enforcement |
|---|---|---|
| Max papers held at once | 20 | App logic at generate/search time |
| Papers per generation/search | 5 | Enforced in endpoint |
| Save to Literature | 3/day | Redis: `daily_bib_save:{user_id}:{date}` |
| "Find Papers" button | 1/day | Redis: `daily_discover_refresh:{user_id}:{date}` |
| Search bar queries | 3/day | Redis: `daily_discovery:{user_id}:{date}` |

---

## Verification Checklist

- [ ] Run migration 013 on Supabase
- [ ] Rebuild containers: `cd infra && docker-compose down && docker-compose up --build`
- [ ] 0 docs: "Find Papers" disabled; search bar active; correct empty state shown
- [ ] ≥1 doc, 0 papers: "Find Papers" enabled; "Ready to explore" empty state
- [ ] Find Papers: click → 5 cards; click again same day → button disabled
- [ ] Search: type query → 5 cards, no relevance bar on cards
- [ ] Pool cap: at 20 papers, new generate/search deletes 5 oldest, adds 5 new
- [ ] PDF button: arXiv paper → green + active; no OA PDF → gray + tooltip
- [ ] Save: click → "Saved ✓"; Literature tab shows paper with "Resolving..." badge
- [ ] 4th save/day: clear toast error, button disabled
- [ ] Dismiss: card removed, DB record deleted
- [ ] PaperDiscoveryModal: no modal anywhere in Discover UI
