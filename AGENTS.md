# AGENTS.md — Noesis Codebase Guide

## What Is Noesis
Draft-aware research intelligence platform for academics. Analyzes user manuscripts against their literature collections. Behaves like an expert peer reviewer — identifies unsupported claims, coverage gaps, citation mismatches. **Does NOT auto-write or rewrite drafts.**

**Stage**: Seed startup, targeting Georgia Tech researchers → university expansion.
**Goal**: 100-500 signups/30 days, $5K MRR Month 3, seed raise Month 6.

---

## Tech Stack
- **Frontend**: React 18 + TypeScript + Vite + TailwindCSS 3
- **Backend**: Python 3.11 + FastAPI 0.115 + Pydantic v2
- **Database**: Supabase PostgreSQL 15 + pgvector (1536-dim embeddings)
- **Auth / Storage**: Supabase Auth + Supabase Storage
- **AI**: OpenAI **GPT-5.2** (`max_completion_tokens`) + text-embedding-3-small
- **Background tasks**: Celery (concurrency=4) + Redis
- **PDF processing**: GROBID 0.7.0 (Docker)
- **Payments**: Stripe (Free / Pro $12/mo / Team $20/user/mo)
- **Deploy**: Vercel (frontend) + AWS (backend) + Supabase (DB)

---

## CRITICAL: OpenAI API Rules
GPT-5.2 requires `max_completion_tokens`, NOT `max_tokens`. Using `max_tokens` causes a 400 error.

```python
# CORRECT
client.chat.completions.create(model="gpt-5.2", max_completion_tokens=2000, ...)

# WRONG — do not use
client.chat.completions.create(model="gpt-4o", max_tokens=2000, ...)
```

Never revert to `gpt-4o` or use `max_tokens`.

---

## Database Rules
- **Supabase only** — use `supabase.table()`, never SQLAlchemy or local PostgreSQL
- Embeddings: 1536 dimensions via text-embedding-3-small
- JSONB columns with GIN indexes for structured metadata
- No local DB containers — Supabase is the only database

---

## Design System (Frontend)
Design tokens source of truth: `services/frontend/tailwind.config.js`. Key tokens:
- Background: `bg-bg-void (#0F0F14)`, `bg-bg-surface (#18181F)`
- Accent: `accent-primary (#E5484D)` (rose-crimson)
- Borders: `rgba(255,255,255,0.08)`
- Max border radius: `rounded-xl` — **never** `rounded-2xl`/`rounded-3xl`
- Font: Inter, `font-semibold` for headings (not `font-bold`)
- Transitions: 150ms (`duration-fast`)
- Icons: `@heroicons/react/24/outline`
- Source of truth: `services/frontend/tailwind.config.js`

---

## File Structure
```
noesis/
├── services/
│   ├── backend/
│   │   ├── app/
│   │   │   ├── api/routes/       # FastAPI endpoints
│   │   │   ├── services/         # Business logic
│   │   │   ├── workflows/        # LangGraph workflows
│   │   │   └── main.py
│   │   └── tests/                # Unit + E2E tests (tests/e2e/)
│   └── frontend/
│       └── src/
│           ├── components/
│           └── pages/
├── infra/
│   ├── docker-compose.yml
│   └── db-migrations/            # SQL migrations (run on Supabase)
└── claude.md                     # Full context (authoritative)
```

---

## Key API Routes
```
POST /documents/upload             # PDF upload + GROBID + analysis
POST /projects/{id}/import-bibtex  # BibTeX import into project literature
GET  /projects/{id}/bundle         # Project workspace bootstrap payload
POST /projects/{id}/insights/analyze  # Start Literature Map generation
GET  /projects/{id}/insights       # Literature Map UI payload
POST /paper-recommendations/projects/{id}/generate  # Discover recommendations
GET  /paper-recommendations/projects/{id}  # Discover pagination payload
POST /paper-recommendations/projects/{id}/save-discovered/{recommendation_id}  # Save to literature
POST /drafts/upload                # Draft upload + auto-analysis
GET  /drafts/{id}/all-feedback     # Unified draft feedback view
GET  /projects/{id}/export-bibtex  # BibTeX .bib export
GET  /drafts/{id}/export-pdf       # Draft analysis PDF report
GET  /auth/quota-summary           # User quota state
GET  /projects/{id}/bib-resolution-status  # BibTeX resolution polling
POST /subscriptions/checkout       # Stripe checkout
GET  /referrals/stats              # Referral dashboard
```

---

## Current State (April 2026)
- **Chat removed** — `routes/chat.py`, `schemas/chat.py`, `ChatBox.tsx`, all chat components deleted
- **ProjectDetail is the live workspace** — `Literature`, `Discover`, `Drafts`, and `Literature Map`
- **Literature system unified** — PDFs, BibTeX/Zotero imports, and saved recommendations all land in the same document library
- **Literature Map is the live synthesis surface** — freshness, quota, coverage snapshot, grounded insights, and inline recommendations
- **Draft analysis is two-stage in product shape** — upload context, editing review, reviewer-style critique, and revision tracking
- **E2E test suite** at `services/backend/tests/e2e/` — 38 tests, run with:
  ```bash
  cd services/backend && python3 -m pytest tests/e2e/ -v --timeout=120 -m "not slow"
  ```
- **Current architecture doc**: `docs/current-architecture.md`
- **Pricing**: Free / Pro $12/mo / Team $20/user/mo (min 2, max 3 seats) / Enterprise

---

## Pricing & Quotas
- Free tier: 30 PDFs/mo total, 30 BibTeX refs/mo total, 2 draft analyses/mo, 5 Discover actions/day, 5 Literature Map refreshes/day
- Pro tier: 100 PDFs/mo total, 100 BibTeX refs/mo total, 20 draft analyses/mo, 50 Discover actions/day, unlimited Literature Map refreshes
- Team tier: effectively unlimited usage, billed at $20/user/mo (2-3 seats)
- Quota managed in `services/backend/app/services/quota_management.py`
- Discover quota: Redis key `daily_discovery:{user_id}:{date}`
- Literature Map refresh quota: Redis key `daily_insights:{user_id}:{date}`

---

## Development Commands
```bash
# Start all containers
cd infra && docker-compose up --build

# Rebuild after backend changes
cd infra && docker-compose down && docker-compose up --build

# Watch Celery tasks
docker logs -f noesis-celery-worker

# Backend API docs
open http://localhost:8000/docs

# Frontend
open http://localhost:5173

# TypeScript check
cd services/frontend && npx tsc --noEmit

# Run tests
cd services/backend && python3 -m pytest tests/ -v
```

---

## Workflow Notes
- This repo is worked on with **Claude Code** and **Cursor Pro** in parallel
- Review `mini-plans/00_INDEX.md` and the active mini-plan at session start
- Commit before switching tools
- Claude Code owns: backend, multi-file refactors, E2E testing
- Cursor owns: frontend component polish, quick UI edits

For full context see `claude.md` and `docs/current-architecture.md`. For design tokens see `services/frontend/tailwind.config.js`.


<claude-mem-context>
# Memory Context

# [noesis] recent context, 2026-04-23 12:53am EDT

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (28,644t read) | 654,860t work | 96% savings

### Apr 20, 2026
S2 Completed DESIGN_SYSTEM.md reference cleanup and planning updates (Apr 20 at 11:41 PM)
### Apr 21, 2026
65 8:11p 🔵 Insights Backend: Schema, Triggers, Staleness, Quota, and Rec-Embedding Options
66 " 🔵 Frontend Component Map: Live vs Legacy Insights and Recommendations Surfaces
67 8:16p ⚖️ Literature Map Overhaul — Architecture & Scope Decisions
68 " ⚖️ Literature Map Overhaul Architecture Plan for 05_literature_insights
69 8:17p 🔵 RAG ingest pipeline stores GROBID structured data in document metadata
70 8:18p ⚖️ Literature Map Overhaul Plan Finalized for Noesis InsightsTab
71 8:19p ⚖️ Literature Map Overhaul Architecture Plan for 05_literature_insights
72 " ⚖️ Literature Map Overhaul Plan for 05_literature_insights
73 8:21p ⚖️ Literature Map Overhaul Plan — `05_literature_insights` Implementation Handoff
74 " ⚖️ Literature Map Overhaul — Architecture & Scope Decisions
75 " 🟣 Literature Map — Four-Block UI Restructure Planned
76 " 🟣 Insights Synthesis Context Priority Upgraded
77 8:22p ⚖️ Literature Map Overhaul Architecture Plan for 05_literature_insights
78 8:24p 🟣 Backend test suite created for Literature Map feature
79 " 🔵 WeasyPrint import blocks any test that imports `app.api.routes.projects`
80 " 🟣 Frontend Literature Map helper tests created and passing
81 " ⚖️ Literature Map Overhaul Plan for 05_literature_insights
82 " 🟣 Literature Map Overhaul Plan Submitted for Implementation
83 10:26p 🟣 Discover Papers feature overhaul planned: quota unification, pagination, tab gating, insights cross-population
85 10:27p ⚖️ Literature Map Overhaul Plan for `05_literature_insights`
84 " ⚖️ Literature Map Overhaul Plan for `05_literature_insights`
87 10:29p 🟣 DiscoverTab Frontend Refactor: Unified Quota, Pagination, Tab Gating
86 " 🟣 Insights background task now conditionally auto-seeds Discover tab via Celery instead of always regenerating
88 10:30p 🔵 paper_recommendations.py route already partially implements Task 06 requirements before work begins
89 " 🔄 paper_recommendations.py quota constants updated and shared generation helper extracted
90 10:31p 🔄 paper_recommendations route endpoints wired to shared helper; bib_save Redis quota removed; GET default limit set to 5
91 10:32p 🔵 DiscoverTab frontend already fully implements Tasks 3–5 from codex_prompt.md before backend work
92 10:33p 🟣 New test file test_discover_papers.py added covering unified quota, pagination, save flow, and insights auto-seed
93 10:34p 🟣 New Celery task paper_recommendation_tasks.py created for background Discover tab seeding
94 " 🔵 api.ts discover client hardcodes limit=5 and tasks/__init__.py exports new Celery task
95 10:50p 🔵 Noesis Draft Analysis v2 — Schema Gap Confirmed, Implementation Plan Loaded
96 10:51p 🔵 Noesis Draft Analysis Full Architecture Mapped — Implementation Touchpoints for Task 07
97 10:56p ⚖️ Literature Map Overhaul Plan for Noesis (`05_literature_insights`)
98 " 🔵 Task 07 Draft Analysis — Pre-Implementation State Audit
### Apr 22, 2026
104 10:27p 🔵 Noesis Quota Limits, feedback_type Enum, and Unresolved Ref Filtering — Code Audit
105 10:29p 🔵 Noesis Insights Tab Architecture — Current Implementation Structure
106 10:31p ⚖️ Noesis 10_answered_questions.md Audit — Already Done, Deferred, and Remaining Tasks
107 11:00p ⚖️ Noesis 10_answered_questions.md Audit — Already-Fixed Items Confirmed, 3 Actionable Tasks Identified
108 11:06p 🔵 Noesis Task 10 Frontend Copy Audit — Stale "Insights Tab" Strings Found
109 11:09p 🔵 Noesis project_insights.py — Full Implementation Review (Task 10)
110 " 🔵 Noesis paper_recommendations.py — Full Route Implementation Review (Task 10)
111 " 🔵 Noesis shared_paper_cache.py — Global Cross-User Paper Store Implementation Review
112 11:36p ✅ Codex Prompt Created for Dead Code Cleanup Task
113 " ✅ Codex Prompt Written for Dead Code Cleanup Mini-Plan
114 11:37p 🔵 Dead Frontend Components Have Zero External Import Sites
115 11:42p 🔵 draft_rag_integration Still Imported at Runtime via Lazy Import in rag_retrieval.py
116 " 🔵 Compass Feature Actively Used Across 7 Frontend Files — Not Dead Code
117 11:43p 🔵 rag_retrieval_enhanced, claim_based_citations, and transparency Actively Imported by 7 Backend Files
118 11:47p 🔵 claim_based_citations Has Single Lazy Import in literature_search.py — rag_retrieval_enhanced and transparency Have Zero
119 11:52p 🔵 Noesis Task 11 — Backend Service Reachability Audit Results

Access 655k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
