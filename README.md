# Noesis

Noesis was a draft-aware research intelligence platform for academics. It analyzed a manuscript against a project-scoped literature library and returned structured reviewer-style feedback: unsupported claims, citation mismatches, coverage gaps, revision signals, and source-grounded critique. It was designed to review and help researchers revise their own work, not to auto-write or rewrite drafts.

## Status

This project has been discontinued. It is published as a technical portfolio piece documenting a full-stack AI agentic system built and tested in a real startup context through Georgia Tech CREATE-X Startup Launch in 2026.

The public deployment was converted to a paused-beta landing page. Backend infrastructure, production billing, and Supabase data were shut down separately.

## Technical Architecture

- **Frontend:** React 19, TypeScript, Vite, Tailwind-based design tokens, and a dark research-workspace UI.
- **Backend:** Python 3.11, FastAPI, Pydantic v2, route-level auth checks, and structured API error handling.
- **Database, auth, and storage:** Supabase PostgreSQL, Supabase Auth, Supabase Storage, JSONB metadata, and Row Level Security migrations.
- **Embeddings and RAG:** OpenAI embeddings, pgvector, retrieval over uploaded literature and draft chunks, embedding cache paths, and project-scoped evidence lookup.
- **PDF processing:** GROBID for structured scientific PDF extraction with PyMuPDF fallback when GROBID failed.
- **AI:** OpenAI GPT models for document analysis, Stage 1 editing, reviewer feedback, synthesis, and structured-output workflows.
- **Background processing:** Celery workers backed by Redis for document analysis, BibTeX resolution, Literature Map generation, draft analysis, and recommendation tasks.
- **Multi-agent review pipeline:** Stage 1 mechanical editing, Reviewer 1 strengths generation, multiple reviewer-style agents, a four-reviewer panel, meta-review, editor-style decision, unsupported claim detection, citation mismatch detection, literature gap detection, external source discovery, draft text span anchoring, and draft revision comparison.

## Features Built

- Project workspaces with literature libraries.
- PDF upload and processing with structured extraction.
- BibTeX/Zotero-style import paths for reference libraries.
- Literature Map generation for themes, gaps, conflicts, and synthesis.
- Discover flow for paper recommendations and save-to-library behavior.
- Draft upload with paper type and citation style metadata.
- Draft analysis with claim extraction, citation checks, coverage gaps, reviewer feedback, and meta-review.
- Stage 1 mechanical editing pass using a separate lightweight model path.
- Reviewer 1 strengths pass and four-reviewer panel UI.
- Progress streaming for long-running draft-analysis workflows.
- Draft revision comparison backend and partial frontend support.
- Export paths for BibTeX and draft-analysis PDFs.
- Quota-management logic for projects, PDFs, BibTeX imports, Discover, Literature Map refreshes, and draft analyses.
- Stripe integration code for subscriptions and webhooks.
- A prototype Chrome/Overleaf extension scaffold.

## Not Completed

- Stripe checkout was not fully productionized. Price IDs, live webhook verification, billing portal behavior, and checkout-to-quota-upgrade testing remained unfinished.
- Collaboration features were not built. Shared projects, invites, lab workspaces, roles, and advisor/student review flows remained product plans.
- Stronger PDF parsing for figures, tables, captions, and page-anchored evidence remained incomplete.
- Overleaf integration was only prototyped. A complete inline editing workflow was not built.
- Claim extraction and evidence-grounding quality still needed another pass before serious production use.
- Legacy Discover routes and some historical docs were not fully cleaned up before discontinuation.

## Lessons Learned

Customer discovery showed that manuscript review pain is real, but willingness to adopt another standalone research workspace was weaker than expected. The strongest interest clustered around advisor/lab workflows and inline tools near existing writing environments, while the standalone app required too much behavior change. The project was shut down because market pull, distribution path, and monetization confidence did not justify continued buildout.

## Local Development

Prerequisites:

- Node.js 22+
- Python 3.11+
- Docker and Docker Compose
- Supabase project with PostgreSQL, Auth, Storage, and pgvector enabled
- OpenAI API key
- Redis and GROBID, either through Docker Compose or separate local services

Clone and configure:

```bash
git clone https://github.com/your-username/noesis.git
cd noesis
cp .env.example .env
cp .env.example services/backend/.env
cp .env.example services/frontend/.env
```

Fill in the placeholders in `.env`, `services/backend/.env`, and `services/frontend/.env`. Never commit real environment files.

Start local infrastructure and backend services:

```bash
cd infra
docker compose up --build
```

Run the frontend in another terminal:

```bash
cd services/frontend
npm install
npm run dev
```

Run backend tests:

```bash
cd services/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest tests/ -v
```

Run frontend checks:

```bash
cd services/frontend
npm run build
npm run test
```

The historical lint configuration is stricter than the current codebase. `npm run lint` may report pre-existing type and hook lint issues that were not resolved before discontinuation.

## Environment Variables

Use `.env.example` as the source of truth for required variable names. Key groups:

- Supabase: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`
- OpenAI: `OPENAI_API_KEY`, optional `OPENAI_ORGANIZATION_ID`
- Redis/GROBID: `REDIS_URL`, `REDIS_HOST`, `REDIS_PORT`, `GROBID_URL`
- Stripe: `STRIPE_PUBLISHABLE_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID_PRO`, `STRIPE_PRICE_ID_TEAM`
- Frontend: `VITE_API_URL`, `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_STRIPE_PUBLISHABLE_KEY`

## Repository Notes

- The production database was Supabase; local PostgreSQL containers are not part of the app data path.
- Application code uses Supabase client operations rather than SQLAlchemy-backed app flows.
- The repo includes historical planning docs to show product and architecture evolution. They are not current operating plans.
- The project is not maintained as a live product.
