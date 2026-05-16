# AGENTS.md - Noesis Codebase Guide

Last updated: May 10, 2026

Read `current_state.md` first. It is the live source of truth for what Noesis is, what changed recently, what remains unfinished, and what we are building next.

## What Is Noesis

Noesis is a draft-aware research intelligence platform for academics. It analyzes user manuscripts against their literature collections and behaves like an expert peer reviewer: unsupported claims, coverage gaps, citation mismatches, reviewer-style critique, and revision tracking.

Noesis does not auto-write or rewrite drafts.

Stage: production hardening plus immediate lab outreach.

GTM focus: Georgia Tech labs and researchers first, then broader university expansion.

## Current Product Shape

The live product loop is:

1. Project
2. Literature
3. Literature Map
4. Discover
5. Draft Analysis
6. Revision / comparison

Current workspace: `services/frontend/src/pages/ProjectDetail.tsx`

Primary tabs: `Literature`, `Literature Map`, `Discover`, `Drafts`

Draft analysis page: `services/frontend/src/pages/DraftAnalysis.tsx`

Chat is no longer part of the core product.

## Tech Stack

- Frontend: React 19 + TypeScript + Vite + Tailwind tokens
- Backend: Python 3.11 + FastAPI 0.115 + Pydantic v2
- Database: Supabase PostgreSQL 15 + pgvector
- Auth / Storage: Supabase Auth + Supabase Storage
- AI: GPT-5.2 / `gpt-5.2-chat-latest`; `gpt-5-mini` for Stage 1 editing
- Embeddings: RAG paths currently use `text-embedding-3-large` with 1536-dimensional storage expectations; some comparison paths use `text-embedding-3-small`
- Background tasks: Celery + Redis, concurrency 4
- PDF processing: GROBID 0.7.0 + PyMuPDF fallback
- Payments: Stripe code exists, but production pricing/checkout is not finished
- Deploy: Vercel frontend + AWS backend + Supabase DB

## Critical OpenAI API Rules

GPT-5.2 requires `max_completion_tokens`, not `max_tokens`.

```python
# Correct
client.chat.completions.create(
    model="gpt-5.2",
    max_completion_tokens=2000,
    messages=[...],
)

# Wrong
client.chat.completions.create(
    model="gpt-4o",
    max_tokens=2000,
    messages=[...],
)
```

Never revert to `gpt-4o` or use `max_tokens`.

## Database Rules

- Supabase only for application data access: use `supabase.table()`.
- Do not introduce SQLAlchemy-backed app flows.
- No local DB containers. Supabase is the database.
- JSONB columns are used for structured metadata.
- pgvector-backed retrieval is the embedding substrate.

## Design System

Design tokens source of truth: `services/frontend/tailwind.config.js`.

Key tokens/rules:

- Background: `bg-bg-void` / `bg-bg-surface`
- Accent: `accent-primary (#E5484D)`
- Borders: `rgba(255,255,255,0.08)`
- Max border radius: `rounded-xl`; never `rounded-2xl` or `rounded-3xl`
- Heading weight: `font-semibold`, not `font-bold`
- Transitions: `duration-fast` / 150ms
- Icons: `@heroicons/react/24/outline`

## Key API Routes

```text
POST /documents/upload
POST /projects/{id}/import-bibtex
GET  /projects/{id}/bundle
POST /projects/{id}/insights/analyze
GET  /projects/{id}/insights
POST /paper-recommendations/projects/{id}/generate
POST /paper-recommendations/projects/{id}/search
GET  /paper-recommendations/projects/{id}
GET  /paper-recommendations/projects/{id}/quota-status
POST /paper-recommendations/projects/{id}/save-discovered/{recommendation_id}
POST /drafts/upload
GET  /drafts/{id}/all-feedback
GET  /drafts/{id}/analysis-stream
GET  /projects/{id}/export-bibtex
GET  /drafts/{id}/export-pdf
GET  /auth/quota-summary
GET  /projects/{id}/bib-resolution-status
POST /subscriptions/checkout
POST /webhooks/stripe
GET  /referrals/stats
```

The older `paper_discovery.py` route still exists and auto-adds papers. Treat it as legacy unless the current task explicitly asks for it.

## Pricing And Quotas

Current intended quota model:

- Free: 3 projects, 30 PDFs/month total, 30 BibTeX refs/month total, 2 draft analyses/month, 5 Discover actions/day, 5 Literature Map refreshes/day
- Pro: 10 projects, 100 PDFs/month total, 100 BibTeX refs/month total, 20 draft analyses/month, 50 Discover actions/day, unlimited Literature Map refreshes
- Team/Enterprise/Admin: effectively unlimited usage with hard caps

Quota source: `services/backend/app/services/quota_management.py`

Important: Stripe pricing is not finished. Checkout and webhook code exist, and quota sync helpers exist, but live price IDs, production webhook verification, billing portal behavior, and end-to-end checkout-to-quota-upgrade testing still need to be completed.

## Recent Progress

- Literature Map quota and staleness implemented.
- Discover quota is now 5/day free and 50/day Pro on the `paper-recommendations` surface.
- Plan-aware quota helpers and migration `016_user_quota_plan_alignment.sql` added.
- Draft upload context added: `paper_type`, `citation_style`.
- Stage 1 editing and Reviewer 1 strengths generation added.
- External source discovery added to draft analysis workflow.
- Privacy/not-used-for-training copy added across major user-facing surfaces.
- Sentry path traversal scanner requests now return clean 400 JSON responses instead of unhandled middleware exceptions.

## Open Product Priorities

1. Start lab outreach now.
2. Finish Stripe production pricing/checkout.
3. Build collaboration: shared projects, invites, roles, advisor/student review flow.
4. Build inline editing/Overleaf workflow support.
5. Improve PDF parsing: sections, figures, tables, page anchors, and text spans.
6. Improve claim extraction and support-strength grounding.
7. Clean up legacy Discover route and stale docs.

## Development Commands

```bash
# Start all containers
cd infra && docker-compose up --build

# Rebuild after backend changes
cd infra && docker-compose down && docker-compose up --build

# Backend tests
cd services/backend && python3 -m pytest tests/ -v

# Backend E2E
cd services/backend && python3 -m pytest tests/e2e/ -v --timeout=120 -m "not slow"

# Frontend dev
cd services/frontend && npm run dev

# Frontend checks
cd services/frontend && npm run build && npm run lint && npm run test
```

## Workflow Notes

- This repo is worked on with Claude Code and Cursor Pro in parallel.
- Review `current_state.md` and `mini-plans/00_INDEX.md` at session start.
- Commit before switching tools.
- Claude Code owns backend, multi-file refactors, docs, and E2E testing.
- Cursor owns frontend component polish and quick UI edits.


<claude-mem-context>
# Memory Context

# [noesis] recent context, 2026-05-16 3:42pm EDT

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (22,830t read) | 544,807t work | 96% savings

### Apr 20, 2026
S4 DraftAnalysisModal — Live Processing Status UI (Apr 20 at 11:41 PM)
### Apr 27, 2026
S9 Claim Analysis Text Positioning Uses Multi-Strategy Fuzzy Matching (Apr 27 at 11:38 AM)
S10 Noesis Team Structure — Solo Technical Founder, No External Contributors (Apr 27 at 12:36 PM)
### Apr 28, 2026
S14 Noesis tagline refinement — multiple rounds of 50-char company description options (Apr 28 at 12:14 AM)
S15 Ashwin's YC Application Motivation — Background and Path (Apr 28 at 12:17 AM)
S12 Noesis company description — 50-char tagline brainstorm with recommendation (Apr 28 at 12:17 AM)
S16 Noesis — Push dev changes to production via CI/CD and verify pipeline success (Apr 28 at 12:37 AM)
### Apr 30, 2026
S18 Noesis Beta Outreach Plan — 5-Day Sprint Document Created (Apr 30 at 1:40 PM)
177 1:44p 🔵 Noesis Frontend — onViewInDocument Type Mismatch Across Draft Analysis Components
178 " 🔴 Noesis Frontend — Fixed onViewInDocument TypeScript Type Mismatch in PriorityGroup
179 1:47p 🔴 Noesis Frontend — Fixed onViewInDocument TypeScript Type Mismatch in ReviewerFeedbackTab
### May 10, 2026
183 1:54p 🔵 Noesis Backend Security Middleware Architecture
184 " 🔴 InputValidationMiddleware — HTTPException replaced with JSONResponse
185 3:02p ✅ Noesis Documentation Overhaul — current_state.md Created
186 3:03p 🔵 Noesis Project State Audit — May 2026 Doc Inventory
187 3:04p 🔵 Noesis Confirmed Tech Stack Versions — May 2026
188 3:05p ✅ current_state.md Created as Noesis Living Source of Truth
189 3:06p ✅ AGENTS.md Fully Rewritten for May 2026 State
190 " ✅ claude.md and docs/current-architecture.md Fully Rewritten for May 2026
191 3:07p ✅ mini-plans/00_INDEX.md Rewritten with Current Implementation Status
192 " ✅ All Five Mini-Plan Files Updated with May 2026 Implementation Status Headers
193 3:08p ✅ Mini-Plans 05-09 Fully Rewritten with Detailed File Maps and Next Actions
194 " ✅ Hedgehog Doc, Historical README, and Migration Runbook Updated
195 8:52p 🟣 Noesis Beta Outreach Plan — 5-Day Sprint Document Created
S19 Noesis improvements.md — Full 3-Pillar RFC Written to Project Root (May 10 at 8:52 PM)
### May 11, 2026
196 12:20a ⚖️ Noesis — S-Tier AI Infrastructure RFC Initiated
197 " 🔵 Noesis pgvector Index Audit — Mixed HNSW and IVFFlat Usage
198 12:21a 🔵 Noesis LangGraph Workflow — State Management and Robustness Audit
199 " 🔵 Noesis CI Pipeline — No Nightly Eval or LLM-Judge Tests Exist
200 " 🔵 Noesis Existing Test Suite — Unit Tests Cover Grounding, Anchoring, QA; Not Output Quality
201 12:22a 🔵 Noesis LangGraph Nodes — No Structured Output Enforcement; Prompt-Only JSON Schema
202 " 🔵 Noesis RAG Ingest Pipeline — GROBID Primary, PyMuPDF Fallback, 500-Token Chunks
203 " 🔵 Noesis Full 3-Pillar Architecture Audit — Complete Diagnostic Report
204 12:23a 🔵 Noesis — No response_format Usage Anywhere; Custom JSON Extraction Helpers in Two More Services
205 12:25a ✅ Noesis improvements.md — Full 3-Pillar RFC Written to Project Root
206 12:39a 🔵 Noesis Embedding Model Usage — OpenAI text-embedding-3-large Throughout RAG Pipeline
207 " ⚖️ Noesis improvements.md — Founder Decisions Section Added (D1–D5)
208 12:40a ✅ Noesis improvements.md Phase 3 Step 7 — Golden Set Expansion Clarified
209 " ✅ Noesis improvements.md — Open Questions Replaced with Resolved + New Follow-Ups
S20 Noesis improvements.md — Open Questions Replaced with Resolved + New Follow-Ups (May 11 at 12:40 AM)
### May 14, 2026
210 7:18p ⚖️ Noesis UI Redesign — Two-Pass Editing with Multi-Reviewer Architecture
211 7:19p 🔵 Noesis Draft Analysis — Two-Pass Review Pipeline Architecture
212 " 🔵 Noesis Draft Analysis — Frontend Component Inventory Pre-Redesign
213 7:20p 🔵 Noesis Draft Analysis — Existing Frontend Component Inventory
214 7:21p 🔵 Noesis Frontend Draft Analysis UI — Complete Architecture Map
215 " 🔵 Noesis Backend LangGraph Workflow — 14-Node Two-Pass Architecture Fully Mapped
216 7:23p 🔵 DraftAnalysis.tsx Progress Steps Hardcoded to 2-Reviewer Model — Mismatch with 4-Reviewer Backend
217 " 🔵 Async/Await Mismatch in Draft Analysis Nodes — client.beta.chat.completions.parse() Calls
218 7:25p ⚖️ Noesis Draft Analysis — Two-Pass UI Redesign + Backend Async Bug Fix Plan
219 7:27p ⚖️ Noesis — Full UI Redesign Initiated for Two-Pass Editing with Multi-Reviewer Architecture
220 " 🔴 Draft Analysis Workflow Nodes Switched to Async OpenAI Client
221 7:28p 🔵 Multi-Reviewer Component Architecture Already in Place
222 7:29p 🔄 ReviewerPanelTabs — Replaced tab UI with accordion expand/collapse
223 7:30p 🟣 Noesis — EditingPassTab component created for Stage 1 editing review
224 " 🔄 ReviewerFeedbackList — EditorDecision and EditingReview button removed
225 7:31p ✅ DraftAnalysis — Progress steps updated to reflect two-pass pipeline with meta review
226 " 🔄 DraftAnalysis — Two-Pass Tab Navigation Redesign
227 7:32p 🔄 Noesis DraftAnalysis — EditingReviewTab extracted to EditingPassTab component
228 8:53p 🔵 Noesis Two-Pass Editing UI Redesign — Backend Test Regression Discovered
229 " 🟣 Noesis Two-Pass Editing Architecture — 4 Reviewers + Meta Reviewer LangGraph Nodes Added

Access 545k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>