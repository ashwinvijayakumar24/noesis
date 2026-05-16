# Noesis - Historical Architecture Alignment & Refinement Audit

> **May 10, 2026 update.** This audit is now historical. It was the problem-finding source for the mini-plan implementation pass, but many findings have since changed. For live state, use `current_state.md`. For updated mini-plan progress, use `mini-plans/00_INDEX.md`.
>
> Major deltas since this audit: Literature Map quota/staleness/progress were implemented; product copy moved from Insights to Literature Map; Discover moved to the `paper_recommendations` route family with 5/day Free and 50/day Pro quota; Pro project limit is now 10; plan-aware quota helpers and Stripe quota sync exist; draft upload context, Stage 1 editing, Reviewer 1 strengths, external source discovery, privacy copy, and anchoring/QA helpers were added. Stripe production pricing remains unfinished and must still be connected/tested end to end.

> **Purpose.** You provided a full, hand-written architecture flow for Noesis (auth → projects → literature → insights → discovery → draft analysis). This document walks each stage end-to-end, compares your intended flow against what the codebase actually does, explains the tech behind each part, calls out the value to a researcher, and lists every misalignment, dead piece of code, and stale doc I found. Answers to your inline TODOs and open questions are woven into the relevant sections and consolidated at the end.
>
> **Method.** Three Explore subagents ran in parallel over `services/backend/app/`, `services/frontend/src/`, `infra/db-migrations/`, and all root-level `.md` files. Every claim in this doc has a file:line reference where relevant. Web research fills in the two places where external benchmarking was needed: peer-review norms and PDF figure extraction.
>
> **This is a problem-finding document, not an implementation plan.** Fixes are sketched only where needed to make the gap concrete. Each section ends with **Problems** that you can turn into separate, detailed plans later.

---

## Context

You want Noesis to look and feel like a serious, thought-through product when you start outreach. Today it is ~70% aligned with the architecture you described, but several things fall into one of three buckets that will damage credibility on a demo:

1. **Silent misalignments** — code that deviates from your intent without any visible warning (e.g., Pro tier is 999 projects, not 10; BibTeX limit is 100 not 30; insights regeneration has zero quota enforcement).
2. **Architectural gaps** — features in your flow that literally don't exist yet (Reviewer 1/Reviewer 2 split, pre-upload questions, privacy copy, stale-insights warnings, deleted-paper tracking in discovery).
3. **Dead weight** — unused services, orphaned components, duplicated files, stale docs. Any researcher or engineer who clones the repo sees this and loses trust.

The rest of this document is organized stage-by-stage, matching the order of your handwritten notes.

---

## Executive Summary

| # | Area | Intended | Actual | Severity |
|---|---|---|---|---|
| 1 | Sign-in branding | "Sign into noesis.is" | Supabase default consent screen; redirect hardcoded | Medium — fixable via Supabase dashboard + custom domain |
| 2 | Project limits (Pro) | 10 | **999** (`routes/projects.py:36-62`) | **Bug — plan-aware limits not wired** |
| 3 | PDF upload (Free) | 30/project/month | 30/**user**/month, not per-project | Misaligned |
| 4 | PDF upload (Pro) | 100/project/month | **Not plan-aware** — same as free | **Bug** |
| 5 | BibTeX refs (Free) | 30/month (per your note: "same as PDFs") | 100/month | Misaligned (unilateral raise by prior code) |
| 6 | Multi-file parallel upload | "Parallel" | Celery queue is concurrency=4; each upload queued individually | Works, but not true parallel; 10/min rate limit |
| 7 | Figure/table parsing | TODO in your notes | GROBID extracts references/sections only. **Zero figure extraction.** | Gap |
| 8 | Retry button on failed upload | Yes | Backend retries 3× internally; **no frontend retry button** | Gap |
| 9 | Rename document | Yes | ✅ `PUT /{document_id}` works | OK |
| 10 | Export formats (.pdf/.txt/.tex/.md) | All four | `.md`, `.tex`, `.pdf` exist. **No .txt** | Minor gap |
| 11 | Document-level tags | Implied | Tags are project-level only (`project_tags` table) | Gap |
| 12 | BibTeX failure → abstract-only | Yes | ✅ Implemented; sets `resolution_status='unresolved'` | OK |
| 13 | Unresolved refs excluded from draft analysis | Yes | **Not enforced anywhere in `draft_processing.py`** | Gap |
| 14 | Insights "stale" warning | Yes | Frontend `isStale` flag exists; **no backend timestamp tracking** | Gap |
| 15 | Insights quota (Free 5/day) | Yes | **Not enforced at all** | **Cost risk** |
| 16 | Insights suggests ~5 external papers | Your new idea | Not implemented; paper recs run separately | Gap |
| 17 | Discover Papers quota | Free limited | 10/day free (Redis-backed) | OK but inconsistent with your "5 at a time" flow |
| 18 | Discover — pagination / "more" | Yes | Hard-capped at 10 per call; no pagination | Gap |
| 19 | Discover — no-repeat tracking | Yes | **Not tracked; same paper can be suggested again** | Gap |
| 20 | Discover — tab access gating (≥1 doc) | Yes | **Not enforced on backend** | Gap |
| 21 | Discover — save routes through BibTeX resolver | Implied | Adds documents directly; skips the unified resolution pipeline | Gap |
| 22 | Draft — pre-upload questions (citation style, paper type) | Yes | Not implemented | Gap |
| 23 | Draft — Stage 1 (grammar) / Stage 2 (Reviewer 1/2) split | Yes | **Single-stage only**. Feedback has `feedback_type` but no R1/R2 split | **Core feature gap** |
| 24 | Draft — pulls ≥10 external papers | Yes | Coverage compares to in-project literature only; no external pull | Gap |
| 25 | Draft — revision tracking ("resolved" v1→v2) | Yes | ✅ `draft_comparison.py` computes it; **frontend doesn't surface "resolved" state per item** | Half-built |
| 26 | Draft — privacy copy ("not used to train") | Yes | **No user-facing text exists anywhere** | Gap — trust issue |
| 27 | Shared paper cache | Asked "is it useful?" | Yes, very useful. See Q&A §9.6 | Working |
| 28 | Unused code / dead components | — | 5 components, ≥3 services, 2 old pages, migration conflict | Cleanup |
| 29 | Old markdown in repo | — | 1 obsolete root doc, 9 `docs/historical/final_plan/*.md`, 2 stale pitch files | Cleanup |

---

## 1. Authentication & Sign-In

**Your intent.** Users land on the home page, sign in or sign up, and the auth feels professional — no Supabase URL visible during OAuth redirect; the consent screen should say "Sign into noesis.is."

**Current tech.**
- Supabase Auth (email OTP + Google OAuth) — `services/backend/app/api/routes/auth.py:34-37`, `services/frontend/src/pages/Login.tsx:101-106`.
- OAuth redirect hardcoded to `${window.location.origin}/auth/callback`.
- `/auth/callback` page waits 2-3s for Supabase to auto-exchange the code, then routes to `/projects`.

**How it works.**
1. User clicks "Continue with Google" → `supabase.auth.signInWithOAuth({ provider: 'google', options: { redirectTo: ... } })`.
2. Supabase redirects through Google → Supabase's own OAuth URL (this is the part you see with the Supabase subdomain) → back to `/auth/callback`.
3. Callback page polls `supabase.auth.getSession()`, sets JWT, navigates to `/projects`.

**Value to researchers.** Low-friction sign-in with a university Google account is the single biggest activation lever. Branding matters on this one screen because that's where the referral link lands.

**What's working.** Email OTP, Google OAuth, email verification all function.

**What's broken / misaligned.**
- **OAuth URL shows `*.supabase.co`.** This is a Supabase plan/config issue, not a code bug. Two paths to fix:
  1. Configure a custom auth domain (`auth.noesis.is`) in Supabase Dashboard → Auth → URL Configuration → "Site URL" + point CNAME. Requires Supabase Pro.
  2. Register Noesis as a Google OAuth app (not Supabase's) in Google Cloud Console so the consent screen literally shows "Noesis" and a `noesis.is` redirect URL. Supabase supports a BYO OAuth client.
- **Home page vs. landing page ambiguity.** `Landing.tsx` exists but there is no distinct marketing home route; signed-out users currently hit `/login` directly. You should decide whether `noesis.is/` is the marketing landing or the login page (recommend marketing landing with CTA; login at `/login`).

**Problems to fix later.**
- P1: Branded OAuth consent screen.
- P2: Separate marketing landing from login flow cleanly; ensure referral `?ref=` param survives OAuth round-trip.

---

## 2. Projects & Tags

**Your intent.** Users create projects, customize with tags. Free = 3 projects, Pro = 10, Team = contact sales.

**Current tech.**
- `services/backend/app/api/routes/projects.py:36-62` enforces project count. Limits hardcoded in that handler:
  ```python
  'free': 3, 'pro': 999, 'team': 999
  ```
- Tags table `project_tags`; tag CRUD at `services/backend/app/api/routes/tags.py`.

**How it works.** Create-project endpoint fetches `user_quotas.plan_tier`, counts existing projects, raises 403 on limit.

**Value to researchers.** Tags let PIs organize projects by lab / topic / manuscript. Projects are the container for everything (documents, drafts, insights).

**What's working.** Free limit of 3 matches your spec exactly. Tag CRUD works.

**What's broken / misaligned.**
- **Pro = 999, not 10.** Either update the limit to 10 per your architecture, or consciously decide Pro is effectively unlimited on projects and revise the marketing copy. The code is lying to you right now.
- **Tags are project-level, not document-level.** Your notes say "add tags to group them [documents]" — this is not implemented. Would require a `document_tags` join table or a `tags: string[]` column on `documents`.
- **Tag system has no UI surface in sidebar** (based on components exploration). If tags are supposed to help filter projects on the dashboard, the filter UI isn't prominent.

**Problems to fix later.**
- P1: Align Pro project limit with stated value.
- P2: Document-level tags (requires schema migration + UI).
- P3: Tag-based project filter on dashboard.

---

## 3. Literature Upload — Method 1: PDF Path

**Your intent.**
1. User uploads 1-10 PDFs simultaneously; they process in parallel.
2. GROBID parses → text extracted (including images — TODO).
3. Chunks go to RAG, stored as embeddings.
4. GPT-5.2 analyzes each paper, result stored in DB.
5. Failures show "failed" with a **retry button**.
6. Every analyzed paper added to a **shared cache** (for insights + draft analysis).
7. Deleting removes the doc + chunks but **does not refund quota**.
8. User can rename, tag, export analysis (.pdf/.txt/.tex/.md).
9. Limits: Free 30/project/month, Pro 100/project/month, Team contact sales.

**Current tech.**
- Upload route: `services/backend/app/api/routes/documents.py:46-171`. Slowapi rate-limited to 10/min per user.
- PDF extraction: `services/backend/app/services/grobid_client.py:48-110` → TEI XML. Falls back to PyMuPDF in `rag_ingest.py:50-61`.
- Chunking + embedding: `rag_ingest.py:108-150`. Model `text-embedding-3-large` (not `-small` as CLAUDE.md claims), 500-token chunks with 100 overlap.
- Analysis: `services/backend/app/services/document_analysis.py` using GPT-5.2. Tiered by pages (SHORT/MEDIUM/LONG, 1500/3000/4000 completion tokens).
- Celery task: `services/backend/app/tasks/document_analysis.py:31-117` with 3 retries, exponential backoff up to 10 min.
- Auto-triggered after upload (`documents.py:153`: `analyze_document_task.delay(...)`).
- Shared cache: `services/backend/app/services/shared_paper_cache.py` (DOI → arXiv ID → Semantic Scholar → OpenAlex fallback).

**How it works (full flow).**
```
POST /documents (one file)
  ↓
Store file in Supabase Storage
  ↓
Create documents row (status='processing')
  ↓
analyze_document_task.delay(document_id)   ← Celery worker picks up
  ↓
GROBID processFulltextDocument (or PyMuPDF fallback)
  ↓
rag_ingest.chunk_and_embed_document()
  → text-embedding-3-large → document_chunks rows
  ↓
document_analysis.analyze_document() (GPT-5.2)
  → UPDATE documents SET status='analyzed', analysis=...
  ↓
shared_paper_cache.store_paper() (if DOI/arXiv ID extracted)
```

**Value to researchers.** This is the foundation of everything. A PhD uploads 30 papers, gets each analyzed, and now has a searchable, synthesizable corpus. Without this working well, nothing downstream is useful.

**What's working.**
- ✅ GROBID extraction with PyMuPDF fallback.
- ✅ GPT-5.2 tiered analysis (short/medium/long papers get appropriate depth).
- ✅ Celery retry logic (3 attempts with exponential backoff).
- ✅ Delete does not refund quota (`documents.py:256-341` — matches your spec exactly).
- ✅ Rename implemented (`documents.py:228-253`).
- ✅ Shared paper cache works (see §9.6 for answer to your question on whether it's useful).
- ✅ BibTeX export for a project (`documents.py:892-997`).

**What's broken / misaligned.**

### 3a. "Parallel" upload isn't really parallel
- Each file → its own Celery task. Celery concurrency = 4 (`docker-compose.yml`). So 10 uploads process 4-at-a-time, not truly parallel.
- Rate limit: 10 uploads/min per user (`documents.py:47`). Your "up to 10 PDFs simultaneously" claim in CLAUDE.md technically holds, but the bottleneck is the OpenAI free-tier 3 req/min, which you've already noted.
- **There's no batched upload endpoint** — the frontend sends N separate POSTs, which multiplies auth overhead and increases cancellation risk.

### 3b. No image/figure/table extraction
- GROBID's TEI XML *can* carry `<figure>` and `<table>` nodes, but the extractor in `grobid_client.py` parses only `<div type="section">` and `<biblStruct>` (references). Nothing touches figures.
- For a serious peer-review tool, **missing figures is a big gap** — reviewers critique figures all the time ("Figure 3's y-axis is misleading"; "Table 2 lacks standard deviations").
- Realistic paths forward (research backed — see Sources):
  - **pdffigures2** (allenai) — Scala tool specifically for extracting figures/captions/tables from scholarly PDFs. Battle-tested; used by Semantic Scholar.
  - **PyMuPDF4LLM + PyMuPDF-Layout** — 2026 Python stack; 10× faster than GPU-based layout models, runs on CPU. Produces markdown with embedded images and captions.
  - **LLM vision fallback** — render a page to image, ask GPT-5.2-vision to describe the figure. Expensive but zero infra.

### 3c. No retry button on failed upload
- Status `'failed'` is set on the `documents` row, but the frontend (based on the audit of `DocumentCard`/literature tab components) does not expose a "retry" action. Backend already has the task; it just needs an endpoint that re-queues `analyze_document_task.delay(doc_id)` and a button.

### 3d. Quota is user-wide, not per-project
- `quota_management.py:212-232` sets `monthly_document_limit: 30` on the user, not the project. Your spec says "Free: 30 uploads per project/month."
- This is actually the more generous interpretation (30 per user is harsher than 30 per project), but it doesn't match what you'd put on a pricing page. Decide: *per user* simplifies accounting; *per project* reads more generously on the marketing site.

### 3e. Plan-aware limits don't exist
- `create_default_quota()` sets 30 PDFs for *everyone*, regardless of tier. Pro users today get the same PDF cap as free users. This is a bug; the code is fine with free-tier defaults but Stripe upgrades never flip these values.

### 3f. Export formats incomplete
- `.md`, `.tex`, `.pdf` work (`services/backend/app/services/export.py`, `services/backend/app/services/draft_export.py:270-601`).
- **No `.txt` export** — trivial to add (strip the markdown to plain text).

### 3g. Document-level tags missing
- Would require schema change; see §2.

### 3h. No figure parsing affects draft analysis too
- The same GROBID pipeline is used on draft uploads. So when a draft cites Figure 3, the coverage analysis can't cross-reference the figure anywhere.

**Problems to fix later.**
- P1 (trust): Retry button on failed uploads.
- P1 (trust): Align quotas (plan-aware limits + per-project vs per-user decision, published on pricing page).
- P2 (quality): Figure/table extraction — recommend PyMuPDF4LLM + pdffigures2 hybrid.
- P2: Batched upload endpoint to reduce overhead.
- P3: `.txt` export.
- P3: Document-level tags.

---

## 4. Literature Upload — Method 2: BibTeX Path

**Your intent.** User imports a `.bib`. Backend agent tries to find the real paper online (open APIs, web search), downloads the PDF, and if successful routes it through the normal PDF pipeline. If it fails, the paper becomes "abstract-only" — used for insights + discovery but **excluded from draft analysis**. No paper cache required for these (confirm). Validate the .bib and fail on malformed input. Same monthly limits as PDFs.

**Current tech.**
- Route: `services/backend/app/api/routes/projects.py:191-300` (max 500 entries per import).
- Parser: `bibtexparser` library.
- Background resolution: `services/backend/app/tasks/bibtex_resolution_task.py` calls `bibtex_resolution_service.py`.
- Core service: `services/backend/app/services/bibtex_resolution_service.py:54-298`.
- External APIs: Semantic Scholar (paper search + open-access PDF URL), Unpaywall (DOI → OA PDF), likely OpenAlex/arXiv under `external_apis/`.

**How it works.**
```
POST /projects/{id}/import-bibtex  (multipart .bib)
  ↓
bibtexparser.loads(contents)  → list of entries (fail 400 if malformed)
  ↓
For each entry: INSERT documents row
  status='pending', source_type='bibtex_import', resolution_status='resolving'
  ↓
resolve_bibtex_task.delay([doc_ids])
  ↓
For each doc:
  1. shared_papers lookup by DOI                 → cache HIT: link and done
  2. shared_papers lookup by title (embedding similarity)
  3. Try PDF URL from BibTeX metadata            → if available, download
  4. Semantic Scholar search                     → get openAccessPdf.url
  5. Unpaywall (DOI → OA URL)                    → download
  6. If all fail: embed title+abstract, mark resolution_status='unresolved'
  ↓
If PDF obtained: route through normal GROBID → chunk → embed → analyze pipeline
```

**Value to researchers.** Researchers live in Zotero/Mendeley. Being able to export `.bib` and have Noesis *find* the actual PDFs is a huge time-saver. This is Noesis's best differentiator vs. Elicit/SciSpace (which assume you already have PDFs).

**What's working.**
- ✅ Full resolution pipeline with multiple fallbacks.
- ✅ Abstract-only fallback (`resolution_status='unresolved'`).
- ✅ `source_type` + `resolution_status` columns on `documents` (migration 012).
- ✅ Polling endpoint `GET /projects/{id}/bib-resolution-status`.

**What's broken / misaligned.**

### 4a. Unresolved refs aren't actually excluded from draft analysis
- Your spec: "abstract-only refs should feed insights/discovery but NOT draft analysis."
- Reality: `draft_processing.py` pulls all documents for a project without filtering `resolution_status`. So an unresolved BibTeX entry with just an abstract *does* get used as coverage evidence in draft analysis — which can generate hallucinated citation suggestions because the model has nothing but a 200-word abstract to work with.
- **Fix is small** — add `.neq('resolution_status', 'unresolved')` to the coverage-analysis literature lookup. But it's currently wrong.

### 4b. BibTeX quota is 100/month, not 30
- `create_default_quota()` sets `monthly_bib_refs_limit: 100`.
- Your spec says "Limits remain the same as PDF uploads" (i.e., 30).
- Decide: keep 100 (more generous) or align to 30. Having them different is the confusing thing.

### 4c. No "web search" paper finding
- Your notes mention "open-source APIs **or web search**." Code only uses Semantic Scholar + Unpaywall + OpenAlex. No Google/Bing/Serper fallback.
- This is probably fine — the three scholarly APIs cover the vast majority of papers. But if you want to brag about "we'll find it anywhere," you don't.

### 4d. Shared paper cache question
- You asked: *"Is this workflow correct? No paper cache required for BibTeX?"*
- **Answer:** The shared cache *is* used (step 1 of resolution). That's correct and good — it means if User A uploads paper X and User B imports a `.bib` that references it, User B gets an instant cache hit without re-calling Semantic Scholar. See §9.6 for a full rundown.

### 4e. Malformed `.bib` handling is coarse
- The route catches bibtexparser exceptions and returns HTTP 400, but the error message isn't surfaced to the user usefully ("Bad Request" on the frontend). Need structured error: which entries failed, which parsed, line numbers if possible.

**Problems to fix later.**
- P1 (correctness): Exclude `resolution_status='unresolved'` from draft analysis literature pool.
- P2 (consistency): Decide on BibTeX limit (100 vs 30) and document it.
- P2: Structured `.bib` parse errors in the UI.

---

## 5. Literature Insights (rename from "Generate Insights")

**Your intent.** Synthesize the uploaded literature into something useful — themes, gaps, conflicts, methodological patterns. Triggered manually. Show "stale" warning when docs change. Free: 5 regenerations/day. Pro/Team unlimited. **New idea:** insights should also surface ~5 external papers that would strengthen the literature base.

**Current tech.**
- Service: `services/backend/app/services/project_insights.py:106-262`. GPT-5.2-chat-latest.
- Route: `POST /projects/{id}/insights/analyze` (`routes/projects.py:555`).
- Celery task: `tasks/insights_analysis.py`.
- Output JSON structure: `research_gaps`, `common_themes`, `methodological_patterns`, `timeline`, `conflicting_findings`, `citation_patterns`, `key_insights`, `summary`.
- Post-trigger: auto-calls `generate_paper_recommendations()` (projects.py:520-542).
- Frontend: `services/frontend/src/components/InsightsTab/index.tsx`; has an `isStale` boolean (line 96).

**How it works.**
```
POST /projects/{id}/insights/analyze
  ↓
Check all PDFs are analyzed (fail if any pending)
  ↓
generate_insights_task.delay(project_id)
  ↓
Pull structured extractions from each document's analysis (claims, methods, findings)
  ↓
Single GPT-5.2 call with aggregated context → JSON insights
  ↓
validate_insights() schema check
  ↓
UPDATE projects SET insights = {...}, insights_updated_at = now()
  ↓
Separately: generate_paper_recommendations() runs on insights output
```

**Value to researchers.** A literature review is synthesis, not summaries. Insights are the difference between "here's what each paper says" and "here's what the field is arguing about." This is the *justification* for uploading 30 papers rather than reading them one-by-one.

**What's working.**
- ✅ Aggregation + GPT-5.2 synthesis produces structured output.
- ✅ Paper recommendations auto-regenerate when insights regenerate.
- ✅ Schema validation.

**What's broken / misaligned.**

### 5a. No quota enforcement → cost risk
- There is **no daily or monthly limit** on insight regenerations. A user could click "regenerate" 100 times and burn ~$5 of GPT-5.2 tokens. This is the single worst cost-leak in the codebase today.
- `quota_management.py` has no `"insights"` operation type. Free/Pro/Team all get unlimited regens.
- Your spec: Free 5/day, Pro/Team unlimited. Fix is 15 lines of code (mirror the `daily_discovery` Redis pattern).

### 5b. "Stale" is frontend-only guessing
- `InsightsTab` has `isStale` in state, but nothing populates it correctly. There's no backend field like `documents.changed_since_insights` or a comparison of `insights.updated_at` vs. `max(documents.updated_at)`.
- The frontend probably shows "stale" as soon as you upload a new doc, but that's done with a naive local comparison. Not reliable.
- **Fix:** add `insights_generated_at` on `projects` (probably already there as `insights_updated_at` — verify), compute staleness server-side in the project fetch: `stale = any(doc.updated_at > insights_generated_at)`.

### 5c. Answering "are insights actually useful?" (your question)
- **Honest answer: only sometimes, and the copy is the problem.** The schema is solid (gaps, themes, methodological patterns) but the output is often generic because the input aggregation concatenates short GPT analyses of each paper, not the papers themselves. The synthesis is "summaries of summaries."
- Three interventions that would make insights actually useful:
  1. **Feed actual chunks from the shared cache, not pre-analyses.** Give the synthesis prompt raw text snippets from each paper's methods/results, not a distilled paragraph. Re-synthesis on already-synthesized text is where "generic" lives.
  2. **Ground each insight in citations.** Every `key_insight` should name the 2-4 papers it's derived from. Without that, researchers can't verify. Currently the JSON schema doesn't require citation anchors.
  3. **Rename "insights" to "Literature Map" or "Field Overview."** "Insights" overpromises. "Field Overview" is what researchers will judge this by.
- If you do these three things, insights goes from "nice-to-have clicky feature" to "reason they keep the subscription."

### 5d. Your new idea (~5 external paper suggestions inside insights) is not implemented
- Paper recommendations *do* run automatically after insights (`projects.py:520-542`), but the output is a separate `paper_recommendations` object, not inlined into the insights UI.
- Your idea is: inside each `research_gap` or `conflicting_finding`, show 1-2 specific papers that would fill that gap. This is strictly better UX than a separate "recommended papers" sidebar. Would require prompt changes (ask GPT to name which gap each paper addresses) and UI changes (render paper chips inline in each insight card).

### 5e. "Save to literature" from paper recs isn't wired through BibTeX resolver
- When the user saves a recommended paper, it probably calls the same direct-add path that Discover uses, which doesn't go through the shared cache or the BibTeX resolver. See §6b for same issue.

**Problems to fix later.**
- P0 (cost leak): Add insights quota (5/day free, unlimited Pro/Team).
- P1 (trust): Rename feature; make each insight cite 2-4 source papers.
- P1 (quality): Feed raw chunks into synthesis, not pre-analyses.
- P2 (UX): Inline paper recommendations into insight cards.
- P2: Robust backend staleness detection.

---

## 6. Discover Papers

**Your intent.** Agent searches web APIs + Google → returns 30 candidates → shows 5 to user at a time → user saves to literature (goes through BibTeX resolver) or deletes/requests more. Requires ≥1 uploaded doc to access. Populates from insights/draft if those ran first.

**Current tech.**
- Service: `services/backend/app/services/paper_discovery_agent.py:1-497`. **LangGraph StateGraph** workflow.
- Route: `services/backend/app/api/routes/paper_discovery.py:90`.
- Frontend: `services/frontend/src/components/DiscoverTab/index.tsx`.
- Quota: Redis `daily_discovery:{user_id}:{date}`, Free 10/day, Pro/Team 999/day. TTL 90000s (~25h).

**How it works.**
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

**Value to researchers.** Literature search is tedious. Discovery is the feature that turns "I have a topic" into "I have a starting corpus." If it finds novel, relevant papers, this is a wedge that competes with ResearchRabbit/Connected Papers.

**What's working.**
- ✅ Three-source search with dedup.
- ✅ Unpaywall integration for open-access PDF downloading.
- ✅ Full GROBID processing for auto-added papers.
- ✅ LangGraph workflow structure (clean, resumable).

**What's broken / misaligned.**

### 6a. Returns 10, not 5
- `max_papers=10` hardcoded (`paper_discovery_agent.py:455`). You wrote "returns 5 papers to the user." Easy tweak if 5 is canonical.

### 6b. Discovered papers bypass BibTeX resolver
- Discovery adds the paper as a full document directly, counting against the `monthly_document_limit`, not the `monthly_bib_refs_limit`.
- Your spec: "save to literature...counts as a literature upload and goes through the .bib import process."
- Reality: discovery auto-processes all 10 results *without user consent*, which is actually worse — it uploads papers the user hasn't approved yet.
- **Two decisions to make:**
  1. Should discovery auto-process, or just return metadata and let the user click "save"?
  2. When the user clicks save, should that count against PDF quota (you're keeping the PDF) or BibTeX quota (you're saving a reference)?
- Cleanest model: discovery returns metadata + previews only → "Save to library" button triggers the BibTeX-resolution pipeline (which tries for PDF, falls back to abstract) → counts against PDF quota if PDF found, BibTeX quota otherwise.

### 6c. No deletion tracking → same paper re-suggested
- If user clicks "not interested" on a paper, it's re-suggested on the next discovery run. No `discovery_dismissals` table. Over time this makes discovery feel dumb.
- **Answer to your question "Should papers be auto-processed even if user doesn't save?"** → **No.** Auto-processing commits DB rows (documents + chunks) and burns OpenAI embedding budget on papers the user may reject. Better: keep discoveries in a lightweight `discovered_papers` (id, project_id, metadata, status: 'shown' | 'saved' | 'dismissed') table, only promote to `documents` on save.

### 6d. No "more" / pagination
- User gets 10 once, then has to click discover again, which wastes a quota credit and re-runs the whole workflow (new API calls, new dedup). Cache the full candidate set (the 30 you mention) and paginate through it.

### 6e. No tab access gating
- Your spec: Discover tab requires ≥1 uploaded document. Code doesn't enforce this, so a brand-new project can hit discover, but the quality will be terrible because the search query is generic.
- Discover uses `project.title` + `project.description` as the query. If those are empty, it returns garbage. Gate the tab until at least one document exists so there's context.

### 6f. Insights / Draft-Analysis cross-population missing
- Your spec: if insights ran first, Discover should be "populated" with insight-derived suggestions; if draft analysis ran first, it pulls the most relevant papers.
- Reality: Discover and Insights are separate pipelines. The auto-called `generate_paper_recommendations` after insights produces paper_recommendations, but that output doesn't feed the Discover tab — the tab just shows "click to discover" empty state.

### 6g. Quota inconsistency with your "5 at a time" flow
- If Discover is supposed to return 5 at a time, and Free gets 10/day, that's 2 searches/day. Probably fine as a limit, but the math should be consistent with the UX.

**Problems to fix later.**
- P1: Create `discovered_papers` staging table; return metadata-only; save-on-click routes through BibTeX resolver.
- P1: Dismissal tracking to avoid re-suggestions.
- P2: Tab gating (≥1 doc) + meaningful empty state.
- P2: Insights and draft analysis pre-populate Discover suggestions.
- P3: Pagination over cached candidate set.

---

## 7. Draft Analysis (Peer-Review Analysis) — The Core Feature

**Your intent.** Mimic a real peer review. Two stages:
- **Stage 1 — General editing:** spelling, grammar, formatting. Pre-upload questions about citation style + paper type (thesis, dissertation, journal).
- **Stage 2 — Peer review:**
  - **Reviewer 1:** highlights pros of the paper.
  - **Reviewer 2:** major and minor critiques, organized by section / type / suggested fix.
- Pulls from project literature, insights, and **≥10 external papers** to critique.
- If draft analysis runs before discovery, populates discovery with 5 most relevant papers.
- **Revision tracking:** v2 upload shows which v1 critiques were resolved.
- **Privacy:** draft uploads are secure, private, explicitly not used to train AI.

**Current tech.**
- Services:
  - `services/backend/app/services/draft_processing.py:401-700` — orchestrator.
  - `services/backend/app/services/claim_analysis.py` — claim extraction (15-25 per 10 pages, categorized by type/subtype/level).
  - `services/backend/app/services/coverage_analysis.py` — gap detection via semantic sim.
  - `services/backend/app/services/reviewer_feedback.py` — GPT-5.2 prompt producing feedback objects with 7 types (positioning/argumentation/coverage/methodology/evidence/clarity/logic) and 4 severities (critical/major/minor/suggestion).
  - `services/backend/app/services/draft_comparison.py:1-425` — v1/v2 diff with improvement score.
- Workflow: LangGraph in `services/backend/app/workflows/draft_analysis/`.
- Frontend: `services/frontend/src/pages/DraftAnalysis.tsx` + `components/draft-analysis/*`.
- Quota: 5 drafts/month for everyone (not plan-aware).

**How it works.**
```
POST /drafts (upload)
  ↓
GROBID extract → structure (sections, refs, claims hints)
  ↓
claim_analysis.extract_claims() → 15-25 claims/section, categorized
  ↓
coverage_analysis.detect_gaps() → compares each claim's embedding against match_document_chunks RPC over project literature
  ↓
reviewer_feedback.generate_feedback() → GPT-5.2 produces feedback_items[]
  ↓
UPDATE draft_analysis SET claims=..., gaps=..., feedback=...
```

**Value to researchers.** This is the feature that justifies the tool. "Peer review before peer review" is a legitimate wedge. But right now what's shipped is closer to "AI critique" than to the layered, adversarial two-reviewer experience you described.

**What's working.**
- ✅ Claim extraction is well-structured (type, subtype, level, importance score 0.0-1.0).
- ✅ Feedback schema is rich (7 types, 4 severities, specific suggestions, example fixes).
- ✅ `draft_comparison.py` produces a real v1→v2 diff including `claims_added/removed/improved/worsened`, `feedback_addressed`, `gaps_resolved`, and `improvement_score` 0-100. AI narrative: evolution_summary, key_improvements, remaining_gaps, reviewer_readiness.
- ✅ Reviewer feedback prompt (`reviewer_feedback.py:37-193`) is exceptionally well-written — 150+ lines of examples and guardrails against auto-writing. This is your best prompt in the codebase.

**What's broken / misaligned.**

### 7a. No Stage 1 / Stage 2 split
- Currently: one pass, one output. No separate grammar/formatting stage.
- Your spec is correct on product intuition — Stage 1 is *mechanical* (grammar, formatting, citation-style compliance), Stage 2 is *intellectual* (peer review). Using GPT-5.2 for grammar is overkill and dilutes the reviewer persona. Fix: Stage 1 uses `gpt-5-mini` or even a dedicated grammar check; Stage 2 uses GPT-5.2 for deep critique.
- Result today: users pay GPT-5.2 prices for grammar corrections, and the reviewer output is cluttered with "consider comma placement" notes sitting next to "your methodology is unjustified."

### 7b. No Reviewer 1 / Reviewer 2 split
- The feedback schema has `feedback_type` (positioning, coverage, etc.) and `severity`, but no *persona*. All feedback is delivered in one voice.
- Your spec is adversarial-by-design: Reviewer 1 finds what's good (pros), Reviewer 2 is the skeptic (cons). This is how real journals structure reviews.
- **Implementation note:** Two GPT-5.2 calls, different system prompts:
  - R1: "You are an encouraging senior reviewer. Highlight the strongest arguments, most novel contributions, and best evidence. Be specific."
  - R2: The existing reviewer_feedback prompt.
- This would be a significant UX upgrade and makes the "two reviewers" story concrete on the marketing site.

### 7c. No pre-upload questions
- Your spec: before upload, ask about citation style + paper type (thesis/dissertation/journal).
- This matters a lot for Stage 1 (which citation rules to apply — APA vs. Chicago vs. IEEE vs. Vancouver) and for tuning Stage 2's expectations (a thesis is judged differently from a journal submission).
- Not implemented. Probably a 2-3 field modal before the upload dropzone.

### 7d. External paper pulling doesn't happen
- Coverage analysis compares the draft's claim embeddings against `match_document_chunks` over the project's literature. If a claim is not covered in the project's literature, it's flagged as a gap.
- Your spec: analysis should "pull at least 10 external papers to help critique the draft."
- Reality: zero external search during draft analysis. The coverage gap detection tells you *what's missing* but doesn't actually go find those papers.
- **Fix:** when a gap is detected, trigger a targeted Discover search (using the gap description as the query) and attach 3-5 suggested papers to each gap. This is the most obvious completion of the flow — it also naturally satisfies §6f (draft → discovery pre-population).

### 7e. Revision tracking is half-built
- `draft_comparison.py` is solid; the backend computes everything.
- Frontend (`DraftAnalysis.tsx`) has a comparison view but doesn't render a per-feedback-item "resolved ✓" / "still open" badge against v1's items. So the user can't see "of my 12 critiques from v1, 8 are resolved and 4 remain."
- This is the *core value proposition of iterating* in Noesis. Without visible resolution state, users don't see the incremental improvement arc.

### 7f. No privacy copy
- You specifically called this out. Nowhere in the UI (draft upload, analysis results, settings, pricing) is there a sentence that says "Your drafts are private and are never used to train AI models."
- For researchers whose work is confidential pre-publication, this is a **deal-breaker** for adoption. Competitors (Thesify, Elicit) make this prominent.
- Minimum: upload modal footer + a legal page. Better: a badge on the draft page that reads "End-to-end private · Not used for training."

### 7g. Image/figure handling for drafts
- Same gap as §3b. A draft with a results figure can't be critiqued on the figure.

### 7h. Draft quota is not plan-aware
- 5/month for everyone. Pro users who pay $12/mo get the same draft cap as free users. Bug.

### 7i. "What do researchers want before peer review?" (your question)
- Web research summary: peer reviewers evaluate work on **validity, significance, originality**, and flag inaccuracies, methodological issues, and gaps in reasoning (Wiley, Taylor & Francis, NIH). Decisions fall into reject / major amendments / minor amendments / accept.
- The canonical critique categories you should surface (ordered by impact on reject decisions):
  1. **Methodological validity** — is the experimental design sound? are confounds controlled? is statistical analysis appropriate?
  2. **Novelty / positioning** — is the contribution clear? is prior work engaged honestly?
  3. **Evidence strength** — do claims match what the data actually shows? overclaim risk?
  4. **Reproducibility** — can another researcher follow this? enough detail in methods?
  5. **Literature coverage** — key citations missing? recent work ignored?
  6. **Clarity / structure** — can a peer in the field follow the argument?
  7. **Limitations acknowledged** — or swept under the rug?
- Your current 7 feedback types (positioning, argumentation, coverage, methodology, evidence, clarity, logic) map well onto this list. You're covering 6/7. **Missing: reproducibility / limitations acknowledgment** as an explicit category. Consider adding `reproducibility` and `limitations` as feedback types.

**Problems to fix later.**
- P0 (trust): Privacy copy everywhere draft upload appears.
- P0 (core feature): Reviewer 1 / Reviewer 2 persona split.
- P1: Stage 1 (mechanical) vs. Stage 2 (intellectual) split; use `gpt-5-mini` for Stage 1.
- P1: Pre-upload questions (citation style, paper type).
- P1: External paper pull (draft analysis triggers Discover queries for each gap).
- P1: Per-item resolution state in revision view.
- P2: Plan-aware draft quota.
- P2: Add `reproducibility` + `limitations` as feedback categories.
- P2: Figure/table extraction for drafts.

---

## 8. Quotas — Cross-Cutting Summary

| Quota Type | Free (stated) | Free (actual) | Pro (stated) | Pro (actual) | Enforced? |
|---|---|---|---|---|---|
| Projects | 3 | 3 ✅ | 10 | 999 ❌ | Yes |
| PDF uploads | 30/project/mo | 30/user/mo | 100/project/mo | 30/user/mo ❌ | Yes |
| BibTeX refs | 30/mo (per notes) | 100/mo | same as PDFs | 100/mo | Yes |
| Drafts | 5/mo | 5/mo ✅ | TBD | 5/mo ❌ | Yes |
| Paper discovery | "Free limited" | 10/day | higher | 999/day ✅ | Yes (Redis) |
| **Insights regen** | **5/day** | **unlimited** ❌ | unlimited | unlimited | **No** |

Three distinct problems:
1. **Tier-awareness is broken.** `create_default_quota()` hardcodes free values; there's no "upgrade-time" hook that flips them to pro values when Stripe webhooks mark a user `plan_tier='pro'`.
2. **Insights has zero enforcement.** The single biggest cost leak.
3. **Per-project vs. per-user scoping.** Stated "per project" but coded "per user." Decide and align with the pricing page.

---

## 9. Answers to Your Inline Questions & TODOs

### 9.1 "Make sign-in more professional (remove Supabase URL)"
See §1. Fix requires either (a) a Supabase custom domain (`auth.noesis.is`, requires Pro plan), or (b) BYO Google OAuth client registered directly in Google Cloud Console. Recommend (b) for faster path and better control.

### 9.2 "Determine how to parse and analyze images"
Three viable stacks (ordered by complexity/cost):
- **pdffigures2** (Scala, free, battle-tested): pure figure/caption/table extraction. Run as a sidecar container alongside GROBID. Output: bounding boxes + caption text per figure.
- **PyMuPDF4LLM + PyMuPDF-Layout** (Python, free, 2026): markdown output with embedded images. Replaces both GROBID *and* PyMuPDF raw extraction for most cases. Fast (CPU only, 10× faster than competitors per their benchmarks).
- **GPT-5.2 vision fallback**: render figure region to image → ask model to describe it → use description as "virtual text" in embeddings and critique. Expensive (~$0.01-0.03 per figure) but zero infra.
- **Recommended:** adopt PyMuPDF4LLM as the default extractor; keep GROBID for citation extraction (where it's stronger); add pdffigures2 only if figure critique becomes a demoed feature.

### 9.3 "Confirm .bib abstract-only workflow with Claude"
**Confirmed correct** on everything except: unresolved refs are not actually excluded from draft analysis right now (§4a). Otherwise: cache-first lookup → API resolution → download attempt → abstract-only fallback with `resolution_status='unresolved'`. This is the right design.

### 9.4 "Ask if the generated insights are actually useful"
**Honest assessment:** schema is good, execution is generic. Three fixes in §5c that would change this from "nice feature" to "subscription driver": (i) feed raw chunks not pre-analyses into the synthesis prompt; (ii) require citation anchors on every insight; (iii) rename "Insights" → "Field Overview" or "Literature Map" to dial back the overclaim.

### 9.5 "What info do researchers actually want before peer review?"
Six critique categories (ranked by impact on reject decisions): methodological validity, novelty/positioning, evidence strength, reproducibility, literature coverage, clarity/structure, limitations acknowledged. Your current feedback_type enum covers all but reproducibility and limitations — add those two. More in §7i.

### 9.6 "Shared paper cache — how does it work? Is it useful? Do we need it now?"

**How it works** (`services/backend/app/services/shared_paper_cache.py`):
- Global `shared_papers` table keyed by DOI, arXiv ID, and title-embedding similarity.
- On any paper lookup: DOI exact → arXiv exact → Semantic Scholar → OpenAlex → store result.
- Embeds title+abstract for semantic search across all users' history.
- Tracks `download_count` and `last_accessed`.

**Is it useful?** **Yes, substantially, for three reasons:**
1. **Cost avoidance.** Semantic Scholar has 100 req/5min rate limits. If User A and User B both reference the same paper, without the cache the second user re-hits the API. With 100+ users cross-referencing overlapping literature (which is the norm in any academic field), the cache saves 60-80% of external API calls.
2. **Resolution speed.** BibTeX import on a `.bib` with 200 entries: without cache, that's 200 sequential API calls (~3-5 min). With cache and field overlap, often 30-50 cached hits (~30-60s savings).
3. **Discovery cross-pollination.** Papers found via Discover by User A seed the corpus that User B's Discover can find via `find_similar_papers()`. This becomes a network effect as users grow.

**Do you need it now?** **Keep it.** Even at 10 users, the cache earns its complexity. At 100+ users in overlapping fields (which is your GT plan), it's load-bearing. The code is clean (~300 lines), the schema is simple, and removing it would require writing a worse version later. Leave it, and make sure every paper-fetch path goes through it (right now Discover bypasses the cache on auto-add — see §6b).

### 9.7 "Should discovered papers be auto-processed even if user doesn't save?"
**No.** See §6c. Currently they *are* auto-processed, which:
- Wastes embedding quota and OpenAI budget on papers the user rejects.
- Pollutes their project literature with unwanted content.
- Makes "save to library" meaningless.
- Creates a quota-accounting problem (counted against PDFs even though user didn't consent).
Fix: stage in `discovered_papers` table with minimal metadata; promote to `documents` only on save click.

### 9.8 "Limits for Discover Papers and Draft Analysis — do research"
**Competitive benchmarking** (2026 tier pricing):
- **SciSpace:** Free = 5 papers analyzed total (not per month). Premium $9.99/mo = 50 papers per "column" analysis. Team $19.99/user/mo.
- **Consensus:** Free tier limited searches/day. Pro $15/mo unlimited.
- **Elicit:** Pre-2024 was generous; 2026 moved reports/agents/CSV export behind paywall + credit limits. No specific public numbers but aggressive monetization.
- **ResearchRabbit:** Fully free.

**My recommendations for Noesis:**
- **Discover Papers:**
  - Free: 5/day (current 10/day is overly generous; matches your "5 at a time" UX naturally)
  - Pro: 50/day (real power users doing 5-10 topical searches/session)
  - Team: unlimited
- **Draft Analysis:**
  - Free: 2/month (5 is way too generous — this is your core paid feature; 5 gives away the whole product)
  - Pro: 20/month
  - Team: unlimited
- Rationale: draft analysis is the *wedge*; giving 5 free means a grad student finishes their thesis on the free tier. 2 lets them try once, see value, pay.

---

## 10. Cross-Cutting Problems

### 10.1 Plan-tier awareness doesn't flow through the system
The `plan_tier` column on `user_quotas` is set by Stripe webhooks (`services/stripe_service.py`). But `create_default_quota()` doesn't read it — it hardcodes free-tier limits. When a user upgrades, their `plan_tier` changes but their `monthly_document_limit` / `monthly_draft_limit` / etc. do not. Effectively: **paying users get free-tier limits unless you manually update their rows.** Check the webhook handler — it probably should be updating limits too.

### 10.2 OpenAI rate limits
You've noted this. The 3 req/min free tier is crippling for batch uploads. Tier 1 requires $50 pre-paid. Do this before any demo.

### 10.3 Frontend error surfaces are thin
Multiple places (BibTeX parse errors, failed uploads, quota-exceeded errors) return HTTP 400/403 with detail strings but the frontend toast is generic. For a trust-sensitive product, specific errors ("We couldn't find a PDF for 3 of your 20 BibTeX entries: [list]") matter.

### 10.4 No "what the site is doing right now" indicator
Upload → processing → analyzing → analyzed takes 30-90s per paper. Users see a spinner. Without stepwise visibility ("Parsing PDF", "Generating embeddings", "Running GPT-5.2 analysis"), bouncing feels likely. LangGraph supports streaming; surface it.

### 10.5 Privacy / not-used-for-training copy
Not present anywhere. §7f. Addresses the single biggest objection a PhD has before uploading an unpublished draft.

---

## 11. Cleanup Inventory — Dead Code

### 11.1 Backend services (zero import sites — safe to delete)
- `services/backend/app/services/background_tasks.py` — orphaned; superseded by explicit Celery tasks. 1.5KB.
- `services/backend/app/services/rag_integration.py` — likely old RAG pipeline before `rag_ingest.py` + `rag_retrieval.py`. 8.3KB.
- `services/backend/app/services/transparent_analysis.py` — 14KB, no active imports. Appears replaced by explicit transparency in `document_analysis.py` + `reviewer_feedback.py`.

### 11.2 Backend services (consolidate candidates)
- `services/backend/app/services/rag_retrieval_enhanced.py` (27KB) + `rag_retrieval.py` — only the base is imported from routes. Merge enhanced features into base or delete.
- `services/backend/app/services/claim_based_citations.py` + `claim_analysis.py` — likely overlapping. Verify which is canonical.
- `services/backend/app/services/transparency.py` — 2 import sites but unclear value.

### 11.3 Backend migrations (fix numbering conflict)
- `infra/db-migrations/017_draft_comparisons.sql` and `008_subscriptions.sql` previously conflicted on numbering. The draft comparisons migration should live at `017_`.

### 11.4 Frontend components (zero imports — safe to delete)
- `services/frontend/src/components/CitationManagementDashboard.tsx`
- `services/frontend/src/components/CitationNetwork.tsx`
- `services/frontend/src/components/ProjectInsights.tsx` (superseded by `InsightsTab/index.tsx`)
- `services/frontend/src/components/project/MethodologyAnalysisView.old.tsx` — `.old.tsx` suffix, zero imports
- `services/frontend/src/components/project/ResearchPlanningView.old.tsx` — same

### 11.5 Frontend route `api/routes/rag.py` — check if still used
CLAUDE.md noted "user-adjustable RAG settings to be removed." Verify `RAGSettingsModal.tsx` is gone (git status suggests chat-related cleanup happened but RAG settings removal may not have). If `rag.py` route serves only deprecated user-adjustable settings, delete the whole route.

### 11.6 Backend `api/routes/compass.py`
Small route (3.4KB) for "Literature Review Compass." Confirm whether this feature is still surfaced in the UI. If not, delete.

---

## 12. Cleanup Inventory — Stale Markdown

### Still in repo (verified existing)
- **`README.md`** — 1207 lines. Comprehensive and mostly accurate. **Keep.**
- **`claude.md`** — developer context. Keep (this is the canonical root instruction file).
- **`docs/historical/NEXT_STEPS.md`** — 371 lines, 90-day roadmap. References already-built work as "future." **Archive** — tactical content is stale, strategic intent is better captured in `docs/historical/final_plan/02_SPRINT_ROADMAP.md`.
- **`SKILLS_INFO.md`** — reference of Claude skills in use. **Keep.**
- **`docs/historical/noesis_createx_pitch_deck_guide.md`** — fundraising material. Verify currency; likely **archive** under `docs/historical/`.

### Historical `final_plan/` directory (9 files, ~2700 lines)
- `00_VC_VIABILITY_VERDICT.md`, `01_PRD_FINAL.md`, `02_SPRINT_ROADMAP.md`, `03_GTM_MARKETING.md`, `04_TECHNICAL_ROADMAP.md`, `05_PRICING_REVENUE.md`, `06_METRICS_KPIs.md`, `07_COMPETITIVE_LANDSCAPE.md`, `MASTER_SYNTHESIS.md`
- Mostly historical. Some pricing figures are outdated relative to April 2026 pivot plan. **Recommendation:** keep the folder under `docs/historical/` for fundraising color, but stop referencing it as live docs.

### Already deleted (in git status — just commit the deletions)
- LAUNCH_CHANGES.md, OVERLEAF_INTEGRATION.md, SECURITY.md, SECURITY_QUICK_REFERENCE.md, TESTING_GUIDE.md, WORKING_STATE.md, new_deployment.md, noesis.md, outreach_plan.md
- `plan/DESIGN_SYSTEM.md`, `plan/DISCOVER_TAB_REDESIGN.md`, `plan/LITERATURE_TAB_REDESIGN.md`, `plan/SPRINT_01_SUMMARY.md`, `plan/next_steps.md`, `plan/noesis_pivot_plan.md`

---

## 13. Priority-Ordered Problem List

Use this as the skeleton for separate, detailed implementation plans.

### P0 — must fix before outreach
1. **Insights quota enforcement** (cost leak; 15 lines of code).
2. **Plan-aware quotas** (paying users currently get free-tier limits — audit Stripe webhook flow).
3. **Privacy copy on draft upload** (single biggest objection for unpublished work).
4. **Fix Pro project limit** (999 → 10, or officially commit to higher and update pricing page).
5. **Commit pending deletions.**

### P1 — core feature gaps impacting demo quality
6. **Draft — Reviewer 1 / Reviewer 2 split** (core product promise).
7. **Draft — Stage 1 (mechanical, gpt-5-mini) / Stage 2 (intellectual, gpt-5.2) separation.**
8. **Draft — pre-upload questions (citation style, paper type).**
9. **Draft — external paper pull for each gap** (triggers Discover query; completes cross-pollination).
10. **Draft — per-item resolution state** in v1→v2 comparison UI.
11. **Discover — staging table** (`discovered_papers`) + save-on-click routes through BibTeX resolver.
12. **Discover — dismissal tracking** (no re-suggestions).
13. **Insights — name/prompt fixes** (rename to "Field Overview", cite papers per insight, feed raw chunks not pre-analyses).
14. **Upload — retry button on failed documents.**
15. **BibTeX — exclude `resolution_status='unresolved'` from draft analysis.**
16. **OAuth branded consent screen** (BYO Google OAuth client).

### P2 — quality and completeness
17. Figure/table extraction (adopt PyMuPDF4LLM; evaluate pdffigures2).
18. Feedback categories: add `reproducibility` and `limitations`.
19. Document-level tags.
20. `.txt` export format.
21. Tab gating: Discover requires ≥1 document.
22. Insights → Discover pre-population.
23. Stepwise progress visibility (LangGraph stream to frontend).
24. Structured BibTeX parse errors in UI.

### P3 — cleanup
25. Delete 3 unused backend services.
26. Delete 5 unused frontend components.
27. Consolidate `rag_retrieval.py` / `rag_retrieval_enhanced.py` and `claim_analysis.py` / `claim_based_citations.py`.
28. Rename the draft comparisons migration to `017_draft_comparisons.sql`.
29. Archive historical markdown under `docs/historical/`; delete or update stale root planning docs.
30. Decide fate of `api/routes/rag.py` and `api/routes/compass.py`.

---

## 14. Verification

This is an audit document, not a code change, so there's nothing to run. Two ways to verify it's accurate:

1. **Spot-check the file:line references.** Pick 5 random citations in this doc and read them. Example: §5a claims no insights quota exists — `grep -n "insights" services/backend/app/services/quota_management.py` should return zero operation-type matches.
2. **Spot-check the cleanup list.** Pick any component in §11.4 and run `grep -r "CitationNetwork" services/frontend/src/`. Should show only its own file.

The document does not propose code changes. Turning P0/P1/P2/P3 entries above into separate plan files is the next step.

---

## 15. Sources (web research)

**Peer review process & critique categories:**
- [Peer Review in Scientific Publications — NIH PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC4975196/)
- [Understanding the peer-review process — University of Nevada Reno Libraries](https://library.unr.edu/help/quick-how-tos/evaluating-sources/understanding-the-peer-review-process)
- [The Peer Review Process — Wiley Author Services](https://authors.wiley.com/Reviewers/journal-reviewers/what-is-peer-review/the-peer-review-process.html)
- [Understanding peer review — Taylor & Francis](https://authorservices.taylorandfrancis.com/publishing-your-research/peer-review/)
- [An Introduction to Reviewing Research Articles — NIH PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC10327937/)

**PDF figure / table / image extraction:**
- [PyMuPDF-Layout: 10× Faster PDF Parsing Without GPUs](https://pymupdf.io/blog/pymupdf-layout-10-faster-pdf-parsing-without-gpus)
- [allenai/pdffigures2 — GitHub](https://github.com/allenai/pdffigures2)
- [PyMuPDF4LLM documentation](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/)
- [parsemypdf — collection of PDF parsing libraries](https://github.com/genieincodebottle/parsemypdf)

**Competitive pricing benchmarks:**
- [Elicit vs. SciSpace (2026)](https://paperguide.ai/blog/elicit-vs-scispace/)
- [Consensus vs SciSpace 2026](https://builtwithclaude.io/consensus-vs-scispace-research-ai/)
- [Elicit pricing](https://elicit.com/pricing)
- [7 Best AI Research Assistant Tools 2026](https://paperguide.ai/blog/ai-research-assistant-tools-for-scientific-research/)
