# Working State — Noesis

> Update this file when switching between Claude Code and Cursor. Commit before switching tools.

---

## Last Updated
**Date:** March 2026
**Last tool used:** Claude Code

---

## Current Priority
**Sprint Week 3 — "Monetization + Pricing Fix"**: All 3 technical tasks complete. Ready to deploy.

---

## In Progress

- [ ] Deploy frontend + backend to Vercel/AWS (includes all Week 1–3 changes)
- [ ] Run DB migrations 009 + 010 on production Supabase (if not already done)
- [ ] Add `STRIPE_PRICE_ID_LAB` to production `.env` (create Lab tier product in Stripe dashboard)
- [ ] Test BibTeX import end-to-end with a real Zotero export
- [ ] Test paper discovery quota (3/day free tier)
- [ ] Verify `source_grounding` stored correctly in reviewer_feedback table
- [ ] Product Hunt launch prep (Week 3 non-technical)
- [ ] 10 PI outreach calls (Week 3 non-technical)
- [ ] First 3 paying users target ($12 Pro or $49 Lab)

---

## Recently Completed (do not re-do these)

- [x] GPT-5.2 migration — all 15 files use `max_completion_tokens` not `max_tokens` (see `GPT52_API_FIX.md`)
- [x] Document upload race condition fixed — backend auto-triggers analysis after RAG
- [x] Multi-select upload (up to 10 files, parallel)
- [x] Success modal simplified (no technical jargon)
- [x] All Week 2-4 backend features: paper discovery, hybrid search, referrals, Stripe, analytics, draft comparison, embedding cache, retry logic
- [x] Frontend components added: PaperDiscoveryModal, FeedbackButton, ReferralWidget, Pricing, AnalyticsDashboard, DraftComparison, EmailCaptureModal
- [x] Design system documented in `DESIGN_SYSTEM.md`
- [x] CLAUDE.md and .cursorrules updated to reflect March 2026 state
- [x] **Sprint Week 1 implemented** (see `plan/noesis_pivot_plan.md`):
  - [x] BibTeX import: `POST /projects/{project_id}/import-bibtex` + BibTeX tab in UploadDocumentModal
  - [x] Paper Discovery quota: 3 searches/day free, unlimited Pro (Redis-backed)
  - [x] Source citations on feedback: `_get_source_grounding()` enriches every feedback item with literature passage
  - [x] Free tier limits updated: 50 documents/month, 10 drafts/month (was 5/1)
  - [x] Landing page hero: "Know What Reviewer 2 Will Say Before You Submit"
  - [x] Landing page features + use cases rewritten for PI/postdoc buyer persona
  - [x] Pricing.tsx updated to reflect new free tier limits and BibTeX import
- [x] **Sprint Week 2 implemented** (see `plan/noesis_pivot_plan.md`):
  - [x] Dispute/Helpful reactions: `POST /drafts/{id}/feedback/{id}/react` + thumbs up / flag buttons on every feedback item in DraftAnalysisModal
  - [x] Draft Comparison Visibility: VersionProgressCard wired into DraftsPanel (shows most recent comparison above draft list)
  - [x] Invite Lab Members: button in DraftsPanel generates lab invite URL; `lab_invites` table tracks codes per project; SignUp.tsx shows welcome banner; Projects.tsx calls join on first load
- [x] **Sprint Week 3 implemented** (see `plan/noesis_pivot_plan.md`):
  - [x] Lab tier pricing ($49/mo flat, up to 5 users): added to `stripe_service.py` PLAN_CONFIGS, `subscriptions.py` validation updated, `Pricing.tsx` card updated
  - [x] UpgradeModal: global `upgradeModalStore.ts` (Zustand) + `UpgradeModal.tsx` rendered in `App.tsx`; `handleQuotaError()` in `errorHandler.ts` intercepts 429 quota_exceeded errors; `UploadDocumentModal` + `UploadDraftModal` both use it
  - [x] "Refer a Lab" viral loop: `_maybe_grant_lab_reward()` in `referrals.py` — when 3+ completed referrals share same institution email domain, grants referrer free Lab tier (9999 limits) via `user_quotas` update

---

## Do Not Touch (currently in progress or recently stabilized)

- `services/backend/app/services/rag_ingest.py` — recently fixed, don't change auto-trigger logic
- `services/backend/app/api/routes/documents.py` — recently fixed re-raise exception bug
- All workflow node files — GPT-5.2 migration just completed, verify before changing

---

## Key Decisions Made (don't undo these)

- **GPT-5.2** is the model — use `max_completion_tokens` everywhere
- **Celery concurrency=4** — configured in `infra/docker-compose.yml`
- **Auto-trigger analysis** from `rag_ingest.py` after RAG completes (backend-controlled sequencing)
- **Design**: dark charcoal theme, rose-crimson accent, max `rounded-xl`, 150ms transitions
- **No auto-writing user drafts** — platform critiques, never rewrites

---

## Next Up (after E2E testing passes)

1. Deploy updated frontend to Vercel
2. Begin Georgia Tech user outreach
3. Phase 1 RAG improvements: adaptive chunking, remove user-adjustable RAG settings
4. Real-time progress streaming for draft analysis (WebSocket)

---

## Tool Division

| Task | Use |
|------|-----|
| Backend logic, multi-file refactors, workflow debugging | Claude Code |
| Frontend component polish, UI iteration, quick edits | Cursor |
| E2E testing, docker logs, API testing | Claude Code |
| New React components, design iteration | Cursor |

---

## Quick Commands

```bash
# Rebuild and start all containers
cd infra && docker-compose down && docker-compose up --build

# Watch celery worker logs
docker logs -f noesis-celery-worker

# Test backend health
curl http://localhost:8000/health

# Check new API docs
open http://localhost:8000/docs

# Frontend dev server
cd services/frontend && npm run dev
```

---

## File Locations (frequently referenced)

```
DESIGN_SYSTEM.md                              ← Design tokens + component patterns
services/frontend/tailwind.config.js          ← Source of truth for all design tokens
services/backend/app/core/config.py           ← Environment config + model settings
services/backend/app/services/rag_ingest.py   ← RAG + auto-trigger logic
services/backend/app/api/routes/documents.py  ← Document upload endpoints
services/backend/app/tasks/document_analysis.py ← Celery task for analysis
infra/docker-compose.yml                      ← Container config (concurrency=4)
plan/00_OVERVIEW.md                           ← 30-day growth plan overview
plan/03_ONE_MONTH_ROADMAP.md                  ← Week-by-week tactics
plan/04_SIX_MONTH_ROADMAP.md                  ← Long-term roadmap
```
