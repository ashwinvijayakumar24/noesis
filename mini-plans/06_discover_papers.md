# 06 — Discover Papers

**Scope:** Paper discovery agent, save/dismiss flow, dedup, pagination, cross-population with insights/draft.
**Source:** `arch_plan.md` §6, §9.7, §9.8.

---

## Your Intent
Agent searches web APIs + Google → returns 30 candidates → shows 5 to user at a time → user saves to literature (goes through BibTeX resolver) or deletes/requests more. Requires ≥1 uploaded doc to access. Populates from insights/draft if those ran first.

## Current Tech
- Service: `services/backend/app/services/paper_discovery_agent.py:1-497`. **LangGraph StateGraph** workflow.
- Route: `services/backend/app/api/routes/paper_discovery.py:90`.
- Frontend: `services/frontend/src/components/DiscoverTab/index.tsx`.
- Quota: Redis `daily_discovery:{user_id}:{date}`, Free 10/day, Pro/Team 999/day. TTL 90000s (~25h).

## How It Works
```
POST /projects/{id}/discover-papers
  ↓
_check_discovery_quota()  → Redis INCR; 403 if over
  ↓
LangGraph workflow:
  parallel_nodes:
    - PubMed (E-utilities XML)
    - arXiv (Atom feed)
    - Semantic Scholar (JSON)
  ↓
  merge + deduplicate (by DOI / arXiv ID / title)
  ↓
  sort by year desc, truncate to 10
  ↓
  for each paper: Unpaywall → openAccessPdf.url
  ↓
  for each PDF: download → GROBID → chunk → embed → create documents row
  ↓
  return 10 papers
```

## Value to Researchers
Literature search is tedious. Discovery turns "I have a topic" into "I have a starting corpus." If it finds novel, relevant papers, this is a wedge competing with ResearchRabbit/Connected Papers.

## What's Working
- ✅ Three-source search with dedup.
- ✅ Unpaywall integration for open-access PDF downloading.
- ✅ Full GROBID processing for auto-added papers.
- ✅ LangGraph workflow structure (clean, resumable).

## Problems

### 6a. Returns 10, not 5
`max_papers=10` hardcoded (`paper_discovery_agent.py:455`). Your notes say "returns 5 papers to the user." Easy tweak if 5 is canonical.

### 6b. Discovered papers bypass BibTeX resolver
- Discovery adds the paper as a full document directly, counting against the `monthly_document_limit`, not the `monthly_bib_refs_limit`.
- Your spec: "save to literature...counts as a literature upload and goes through the .bib import process."
- Reality: discovery auto-processes all 10 results *without user consent*, which is actually worse — it uploads papers the user hasn't approved yet.

**Two decisions to make:**
1. Should discovery auto-process, or just return metadata and let the user click "save"?
2. When the user clicks save, should that count against PDF quota (keeping the PDF) or BibTeX quota (saving a reference)?

**Cleanest model:** discovery returns metadata + previews only → "Save to library" button triggers the BibTeX-resolution pipeline (which tries for PDF, falls back to abstract) → counts against PDF quota if PDF found, BibTeX quota otherwise.

### 6c. No deletion tracking → same paper re-suggested
- If user clicks "not interested," it's re-suggested on the next discovery run. No `discovery_dismissals` table.

**Your question answered:** *"Should papers be auto-processed even if user doesn't save?"*
→ **No.** Auto-processing commits DB rows (documents + chunks) and burns OpenAI embedding budget on papers the user may reject.

**Better design:** lightweight `discovered_papers` (id, project_id, metadata, status: 'shown' | 'saved' | 'dismissed') table. Only promote to `documents` on save.

### 6d. No "more" / pagination
User gets 10 once, then has to click discover again, which wastes a quota credit and re-runs the whole workflow (new API calls, new dedup). Cache the full candidate set (the 30 you mention) and paginate through it.

### 6e. No tab access gating
- Your spec: Discover tab requires ≥1 uploaded document.
- Code doesn't enforce this, so a brand-new project can hit discover, but the quality will be terrible because the search query is generic.
- Discover uses `project.title` + `project.description` as the query. If those are empty, it returns garbage. Gate the tab until at least one document exists so there's context.

### 6f. Insights / Draft-Analysis cross-population missing
- Your spec: if insights ran first, Discover should be "populated" with insight-derived suggestions; if draft analysis ran first, it pulls the most relevant papers.
- Reality: Discover and Insights are separate pipelines. The auto-called `generate_paper_recommendations` after insights produces paper_recommendations, but that output doesn't feed the Discover tab — the tab just shows "click to discover" empty state.

### 6g. Quota inconsistency with your "5 at a time" flow
If Discover is supposed to return 5 at a time, and Free gets 10/day, that's 2 searches/day. Fine as a limit, but the math should be consistent with the UX.

## Competitive Quotas (Recommendation)
See `10_answered_questions.md` §9.8 for the full benchmarking exercise.
- **Free:** 5/day (current 10/day is overly generous; matches your "5 at a time" UX)
- **Pro:** 50/day (real power users doing 5-10 topical searches/session)
- **Team:** unlimited

## Priority
- **P1:** Create `discovered_papers` staging table; return metadata-only; save-on-click routes through BibTeX resolver.
- **P1:** Dismissal tracking to avoid re-suggestions.
- **P2:** Tab gating (≥1 doc) + meaningful empty state.
- **P2:** Insights and draft analysis pre-populate Discover suggestions.
- **P3:** Pagination over cached candidate set.
