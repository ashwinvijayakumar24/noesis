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

# [noesis] recent context, 2026-04-30 1:21pm EDT

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (23,142t read) | 888,962t work | 97% savings

### Apr 20, 2026
S4 DraftAnalysisModal — Live Processing Status UI (Apr 20 at 11:41 PM)
S2 Completed DESIGN_SYSTEM.md reference cleanup and planning updates (Apr 20 at 11:41 PM)
### Apr 22, 2026
112 11:36p ✅ Codex Prompt Created for Dead Code Cleanup Task
113 " ✅ Codex Prompt Written for Dead Code Cleanup Mini-Plan
114 11:37p 🔵 Dead Frontend Components Have Zero External Import Sites
115 11:42p 🔵 draft_rag_integration Still Imported at Runtime via Lazy Import in rag_retrieval.py
116 " 🔵 Compass Feature Actively Used Across 7 Frontend Files — Not Dead Code
117 11:43p 🔵 rag_retrieval_enhanced, claim_based_citations, and transparency Actively Imported by 7 Backend Files
118 11:47p 🔵 claim_based_citations Has Single Lazy Import in literature_search.py — rag_retrieval_enhanced and transparency Have Zero
119 11:52p 🔵 Noesis Task 11 — Backend Service Reachability Audit Results
### Apr 27, 2026
120 11:38a 🟣 DraftAnalysisModal — Live Processing Status UI
S9 Claim Analysis Text Positioning Uses Multi-Strategy Fuzzy Matching (Apr 27 at 11:38 AM)
121 11:42a 🔵 Noesis Draft Open Spinner — 15s Delay Investigation
122 11:43a 🔵 DraftAnalysis.tsx — Sequential Bottleneck in Draft Initialization
124 " 🔴 Draft Open Spinner — Removed Sequential Dependency on assignSections
128 12:36p 🔵 Claim Analysis Text Positioning Uses Multi-Strategy Fuzzy Matching
S10 Noesis Team Structure — Solo Technical Founder, No External Contributors (Apr 27 at 12:36 PM)
129 12:55p 🔴 DocumentViewer PDF highlighting made client-side extraction + guaranteed single-span search
130 1:13p 🔵 Noesis CI/CD Pipeline Architecture — GitHub Actions to EC2 + Vercel
131 1:14p 🔵 Noesis Pre-Deploy State — 120 Uncommitted Files, Clean TypeScript
132 1:15p 🟣 Noesis Major Commit — Draft Analysis UX, Client-Side PDF Highlighting, Citation Fixes
133 1:17p 🔵 Noesis Frontend — TypeScript Build Errors Found Post-Commit
### Apr 28, 2026
134 12:14a 🔵 Noesis Team Structure — Solo Technical Founder, No External Contributors
S14 Noesis tagline refinement — multiple rounds of 50-char company description options (Apr 28 at 12:14 AM)
S12 Noesis company description — 50-char tagline brainstorm with recommendation (Apr 28 at 12:17 AM)
135 12:37a 🔵 Ashwin's YC Application Motivation — Background and Path
S15 Ashwin's YC Application Motivation — Background and Path (Apr 28 at 12:37 AM)
136 2:43p ✅ Noesis YC Application — "Progress" Question Drafting Started
137 2:46p 🔵 Noesis Technical Stack — Full Architecture Audit for YC Application
138 4:46p ✅ Noesis YC Application — "Progress" Question Active
### Apr 29, 2026
139 5:54p 🟣 Noesis DraftAnalysis — Comprehensive Overhaul Plan Requested
140 5:55p 🔵 Noesis Draft Analysis — Full Codebase Architecture Mapped
141 " 🟣 Noesis Draft Analysis — Comprehensive Overhaul Plan Requested
142 5:57p ⚖️ Noesis DraftAnalysis — Full Rewrite Plan Initiated for prompt.md
143 5:58p 🟣 Noesis Draft Analysis — Comprehensive Overhaul Plan Requested
144 " 🟣 Noesis Draft Analysis — External Source Discovery Backend Module
145 " 🟣 Noesis — Reviewer Feedback Anchor & QA Backend Helper
147 5:59p 🔵 Noesis Draft Analysis — External Source Discovery Architecture Mapped
146 " 🔵 Noesis Reviewer Feedback & Claim Anchoring — Full Architecture Map
148 6:00p 🔵 Noesis Backend Test Coverage Map — Draft Analysis Reliability
149 " 🟣 Noesis Draft Analysis — Text Anchor Service Implemented
150 " 🟣 Noesis Draft Analysis — Feedback Quality Gate Service Implemented
151 " 🔵 Noesis Draft Analysis — Existing Architecture Mapped
154 6:01p 🟣 Noesis Draft Analysis — External Source Discovery Module
155 " 🟣 Noesis Draft Analysis Graph — External Source Discovery Node Added
156 " 🟣 Noesis Reviewer Feedback Node — External Sources Surfaced in LLM Context
152 " 🟣 Noesis — test_draft_analysis_reliability.py Created (Worker D)
153 " 🔵 claim_analysis.py Calls get_async_openai_client() at Module Import Time
158 6:02p ✅ Noesis Draft Analysis — Gap Detection Populates Gap ID in State
159 " ✅ Noesis Reviewer Feedback — LLM Prompt Now Includes Claim/Gap IDs and QA Integration
157 6:04p 🔵 Noesis draft_anchor_qa.py — Pure-Python Feedback QA and Claim Anchoring Module
160 6:06p 🟣 Noesis — draft_anchor_qa.py: New Bounded Backend Module for Feedback QA and Text Anchoring
161 " 🟣 Noesis test_draft_analysis_reliability.py — All 6 Tests Passing
162 6:07p 🟣 Noesis Draft Analysis — Anchor QA Module (draft_anchor_qa.py) Implemented
163 " 🟣 Noesis Draft Analysis — External Source Discovery Service Implemented
164 " 🔵 Noesis Draft Analysis — LangGraph Workflow Full Node Graph Mapped
165 6:20p ✅ Noesis — Supabase CLI Authenticated via .env Access Token

Access 889k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>
