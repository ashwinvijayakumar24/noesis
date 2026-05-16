# Claude.md - Noesis Context

Last updated: May 10, 2026

Read `current_state.md` first. It is the live status file for Noesis.

## Quick Context

Noesis is a project-centered, draft-aware research intelligence workspace for academics. Users bring manuscripts and literature collections; Noesis reviews, critiques, maps claims to evidence, finds coverage gaps, and helps researchers prepare for peer review.

Noesis must not write or rewrite the user's manuscript.

Current priority: start lab outreach now while finishing production hardening, Stripe pricing, collaboration, Overleaf/inline workflow, PDF parsing, and claim quality.

## Current Product Loop

1. Create a project.
2. Add literature via PDFs, BibTeX/Zotero imports, or saved recommendations.
3. Generate a Literature Map.
4. Use Discover to find missing papers.
5. Upload a draft with paper type and citation style.
6. Run Stage 1 editing plus reviewer-style analysis.
7. Revise and compare versions.

Main workspace: `services/frontend/src/pages/ProjectDetail.tsx`

Draft analysis page: `services/frontend/src/pages/DraftAnalysis.tsx`

Chat has been removed from the core product.

## Critical GPT-5.2 Rule

All GPT-5.2 calls must use `max_completion_tokens`, not `max_tokens`.

```python
response = client.chat.completions.create(
    model="gpt-5.2",
    max_completion_tokens=2000,
    messages=[...],
)
```

Do not use `gpt-4o`. Do not use `max_tokens`.

`gpt-5-mini` is allowed for bounded mechanical Stage 1 editing checks.

## Stack

- Frontend: React 19, TypeScript, Vite, Tailwind token config
- Backend: Python 3.11, FastAPI 0.115, Pydantic v2
- DB/Auth/Storage: Supabase
- Jobs: Celery plus Redis
- PDF: GROBID plus PyMuPDF fallback
- AI: GPT-5.2 / `gpt-5.2-chat-latest`; `gpt-5-mini` for Stage 1
- Embeddings: RAG paths currently use `text-embedding-3-large`; keep 1536-dimensional storage compatibility in mind
- Payments: Stripe code exists but production pricing is not finished

## Recent Implementation Progress

### Literature Map

- Renamed from "Insights" in product copy.
- Daily refresh quota implemented: Free 5/day, paid/admin tiers unlimited.
- Backend staleness detection implemented.
- Progress snapshots and retry/error states implemented.
- Recommendation groupings are included in the Literature Map payload.

### Discover

- Current Discover surface is `paper_recommendations`.
- Free Discover quota is 5/day; Pro is 50/day.
- Rolling pool is capped at 30 recommendations.
- UI paginates 5 at a time.
- Save-to-literature creates a discovered document and starts resolution.
- Legacy `paper_discovery.py` still exists and should be treated as cleanup/deprecation work.

### Draft Analysis

- Upload context: `paper_type`, `citation_style`.
- Stage 1 editing: `services/backend/app/services/stage1_editing.py`.
- Reviewer 1 strengths: `services/backend/app/services/reviewer1_feedback.py`.
- Reviewer 2/deep critique: reviewer feedback workflow.
- External source discovery node added.
- Progress stream emits named steps.
- Privacy copy added in major user-facing surfaces.

### Quotas

- Plan constants live in `services/backend/app/services/quota_management.py`.
- Pro project limit is 10.
- Free draft quota is 2/month; Pro is 20/month.
- `sync_user_quota_plan()` updates quota rows without resetting counters.
- Stripe webhooks call quota sync, but production Stripe is not fully finished.

### Security

- Path traversal scanner requests are rejected with clean 400 JSON responses from middleware.
- Regression test: `services/backend/tests/test_ci_api_contracts.py`.

## Known Unfinished Work

### Payment

Stripe is not finished. Do not tell users payments are fully live until all of this is verified:

- live price IDs
- production webhook endpoint and signature secret
- checkout from pricing page
- successful upgrade reflected in `user_quotas`
- cancellation/downgrade behavior
- billing portal flow
- Team copy aligned with actual collaboration functionality

### Product

- Collaboration: shared projects, invites, roles, lab workspace model.
- Inline editing / Overleaf: likely browser extension/sidebar first; deeper Overleaf integration later if demand is proven.
- PDF parsing: stronger section structure, figures/tables/captions, page anchors, exact text spans.
- Claims: better granularity, evidence support strength, fewer vague findings, better anchors.
- Discover cleanup: retire or replace legacy auto-add route, add dismissal/no-repeat behavior, clarify save accounting.
- Revision UX: backend comparison exists; per-item resolved/still-open display needs to be stronger.

## Documentation Map

- `current_state.md`: live source of truth
- `README.md`: repo overview and commands
- `AGENTS.md`: agent operating guide
- `docs/current-architecture.md`: architecture snapshot
- `mini-plans/00_INDEX.md`: progress against mini-plans
- `here-is-the-comprehensive-curried-hedgehog.md`: historical audit
- `docs/historical/`: old planning/fundraising docs only

## Development Commands

```bash
# Start local services
cd infra && docker-compose up --build

# Backend tests
cd services/backend && python3 -m pytest tests/ -v

# E2E tests
cd services/backend && python3 -m pytest tests/e2e/ -v --timeout=120 -m "not slow"

# Frontend
cd services/frontend && npm run dev

# Frontend verification
cd services/frontend && npm run build && npm run lint && npm run test
```

## Design System

Source of truth: `services/frontend/tailwind.config.js`

- Dark charcoal backgrounds.
- Rose-crimson primary accent `#E5484D`.
- White-alpha borders.
- Max radius `rounded-xl`.
- `font-semibold` for headings.
- 150ms transitions.
- `@heroicons/react/24/outline`.

## Operating Notes

- Use Supabase client operations, not SQLAlchemy app flows.
- Preserve the critique-not-writing product boundary.
- Prefer existing services, routes, and local patterns.
- Before changing pricing, quotas, or product claims, update `current_state.md`.
