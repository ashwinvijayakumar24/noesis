# Noesis

Draft-aware research intelligence for academics.

Noesis helps researchers review their own manuscripts against their project literature before submission. It surfaces unsupported claims, coverage gaps, citation mismatches, and reviewer-style critique. It does not write or rewrite the draft.

Live product: `https://noesis.is`

## Current State

Read [current_state.md](current_state.md) first. It is the live source of truth for product shape, pricing status, recent progress, and next priorities.

Current loop:

1. Create a project.
2. Add literature with PDFs, BibTeX/Zotero imports, and saved recommendations.
3. Generate a Literature Map.
4. Discover missing papers.
5. Upload a draft with paper type and citation style.
6. Run Stage 1 editing checks plus reviewer-style analysis.
7. Revise, upload a new version, and compare progress.

Primary surfaces:

- `services/frontend/src/pages/ProjectDetail.tsx` - project workspace
- `services/frontend/src/pages/DraftAnalysis.tsx` - draft analysis view
- `services/frontend/src/components/InsightsTab/` - Literature Map
- `services/frontend/src/components/DiscoverTab/` - Discover

## Stack

- Frontend: React 19, TypeScript, Vite, Tailwind tokens in `services/frontend/tailwind.config.js`
- Backend: Python 3.11, FastAPI, Pydantic v2
- Database/Auth/Storage: Supabase PostgreSQL, Supabase Auth, Supabase Storage
- Jobs: Celery plus Redis
- PDF processing: GROBID plus PyMuPDF fallback
- AI: GPT-5.2 / `gpt-5.2-chat-latest`, `gpt-5-mini` for Stage 1 editing
- Payments: Stripe code exists, but production pricing/checkout is not finished

## Critical Rules

Use GPT-5.2 with `max_completion_tokens`. Do not use `max_tokens` and do not revert to `gpt-4o`.

Use Supabase client operations for application data access. Do not introduce SQLAlchemy-backed app flows or a local database.

Design tokens come from `services/frontend/tailwind.config.js`; keep the dark charcoal/rose-crimson system and do not exceed `rounded-xl`.

## Development

Start local services:

```bash
cd infra
docker-compose up --build
```

Frontend:

```bash
cd services/frontend
npm run dev
```

Backend tests:

```bash
cd services/backend
python3 -m pytest tests/ -v
```

E2E tests:

```bash
cd services/backend
python3 -m pytest tests/e2e/ -v --timeout=120 -m "not slow"
```

Frontend checks:

```bash
cd services/frontend
npm run build
npm run lint
npm run test
```

## Documentation

- [current_state.md](current_state.md) - live status and priorities
- [AGENTS.md](AGENTS.md) - coding agent guide
- [claude.md](claude.md) - project context for Claude/Cursor work
- [docs/current-architecture.md](docs/current-architecture.md) - architecture snapshot
- [mini-plans/00_INDEX.md](mini-plans/00_INDEX.md) - mini-plan progress and remaining work
- [here-is-the-comprehensive-curried-hedgehog.md](here-is-the-comprehensive-curried-hedgehog.md) - historical architecture audit
- [docs/historical/](docs/historical/) - historical planning and fundraising docs only

## Immediate Priorities

1. Start lab outreach now while continuing product hardening.
2. Finish Stripe production pricing/checkout and verify quota upgrades end to end.
3. Build collaboration around shared lab projects and advisor/student review flows.
4. Add inline editing/Overleaf workflow support.
5. Improve PDF parsing, text anchors, and claim/evidence grounding.

