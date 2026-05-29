# AGENTS.md - Noesis Public Repository Guide

Noesis is discontinued and published as a technical portfolio repository. Treat the codebase as an archival full-stack AI system, not as an actively maintained production service.

## Product Context

Noesis was a draft-aware research intelligence platform for academics. It analyzed manuscripts against a project-scoped literature library and returned reviewer-style feedback: unsupported claims, citation mismatches, literature gaps, reviewer panel critique, meta-review, editor-style decision, and revision comparison.

Noesis did not auto-write or rewrite drafts.

## Stack

- Frontend: React 19, TypeScript, Vite
- Backend: Python 3.11, FastAPI, Pydantic v2
- Database/auth/storage: Supabase PostgreSQL, Supabase Auth, Supabase Storage
- Retrieval: OpenAI embeddings, pgvector, project-scoped literature chunks
- AI: OpenAI GPT models
- Background work: Celery and Redis
- PDF processing: GROBID with PyMuPDF fallback

## Public-Repo Safety Rules

- Never commit real `.env` files or credentials.
- Use `.env.example` for placeholder environment variable names.
- Do not add uploaded PDFs, manuscripts, exports, logs, database dumps, or user data.
- Do not add local absolute paths.
- Keep Supabase service-role keys backend-only.
- Use `max_completion_tokens` for GPT calls; do not introduce `max_tokens` for GPT-5-family calls.

## Development

See `README.md` for setup instructions. Local development expects Docker Compose for Redis/GROBID/backend services and Vite for the frontend.

## Status

The project is not maintained as a live product. Major unfinished areas include production Stripe checkout, collaboration, stronger figure/table PDF parsing, and full Overleaf/inline editing support.


<claude-mem-context>
# Memory Context

# [noesis] recent context, 2026-05-24 11:33am EDT

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (20,378t read) | 1,086,058t work | 98% savings

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
### May 10, 2026
S19 Noesis improvements.md — Full 3-Pillar RFC Written to Project Root (May 10 at 8:52 PM)
### May 11, 2026
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
### May 20, 2026
230 1:22a 🔵 Noesis — Technical Architecture Summary for Resume Optimization
231 1:24a 🔵 Noesis Current State — Full Product + Stack Snapshot (May 2026)
232 " 🔵 Noesis LangGraph Draft Analysis — Full 14-Node Workflow Architecture
233 " 🔵 Noesis DraftAnalysisState — Complete TypedDict Schema with Annotated Reducer
234 " 🔵 Noesis LLM-as-a-Judge — Citation Judge and Reviewer Judge Nodes
235 " 🔵 Noesis RAG Pipeline — Two-Tier Literature Search + B2 Citation Discovery
236 " 🔵 Noesis External Source Discovery — Draft Analysis Pipeline with Semantic Scholar + OpenAlex
237 " 🔵 Noesis Structured Output Schemas — Pydantic v2 StrictOutputModel with extra=forbid
238 " 🔵 Noesis retry_utils — Shared OpenAI Semaphore + Validation Retry Loop
239 3:31p ✅ Noesis Mentor Outreach — Evan Goldberg Email Draft Initiated
### May 22, 2026
240 7:35p 🟣 Noesis Draft Analysis — In-PDF Search (Ctrl+F) Feature Request
241 7:37p 🟣 Noesis Draft Analysis — In-Paper Word Search Feature Requested
242 " 🟣 Noesis DocumentViewer — In-Paper Word Search (Ctrl+F) Implemented
244 " 🔴 DocumentViewer — TypeScript Build Error Fixed, Search Feature Builds Clean
245 7:39p 🔴 DocumentViewer — TypeScript type error fixed for PDF text content items
246 " 🟣 DocumentViewer — production build succeeds with in-document search feature
247 7:45p 🔵 Noesis DraftAnalysis — Production Stuck Bug + Observability Gap
### May 23, 2026
248 10:59a 🟣 DocumentViewer — In-Document Search Bar (Cmd+F) for Draft Analysis
249 11:04a ⚖️ Noesis Project Killed — Pivot Decision Made
250 " ⚖️ Noesis — Project Killed, Pivot Decision Made
251 11:05a ⚖️ Noesis Project Killed — Pivot Decision Made
252 " 🟣 Noesis Frontend Converted to "Beta Coming Soon" Maintenance Mode
255 11:06a ✅ Login.tsx Fully Replaced — Auth Logic Stripped, Maintenance Shell Added
256 " 🔵 Build Succeeds Clean — 3 Routes, No Dead Imports
257 11:16a ⚖️ Noesis Project Killed — Pivot Decision Made
258 " ✅ Noesis Landing Page — Beta Pause Mode Activated
259 11:17a ✅ Noesis Frontend Deployed to Production via Vercel
261 11:28a 🔵 Noesis Backend Infrastructure — Full Stack Inventory

Access 1086k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>