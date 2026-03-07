# Working State — Noesis

> Update this file when switching between Claude Code and Cursor. Commit before switching tools.

---

## Last Updated
**Date:** March 2026
**Last tool used:** Claude Code

---

## Current Priority
**End-to-end testing** — validate full document upload → RAG ingestion → GPT-5.2 analysis pipeline after recent fixes.

---

## In Progress

- [ ] E2E test: single document upload → processing → analyzing → analyzed
- [ ] E2E test: multi-file upload (3-5 files, verify parallel processing)
- [ ] E2E test: draft upload + analysis
- [ ] OpenAI Tier 1 upgrade needed for parallel batch uploads (currently 3 req/min)

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
