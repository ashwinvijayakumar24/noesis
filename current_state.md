# Noesis Current State

Last updated: May 23, 2026

Noesis has been discontinued. The repository is being prepared for public release as a technical portfolio piece, not as an active product roadmap.

## What Noesis Was

Noesis was a draft-aware research intelligence platform for academics. Researchers created projects, added literature, generated a Literature Map, discovered missing papers, uploaded manuscripts, and received source-grounded reviewer-style feedback before submission.

The system critiqued drafts and surfaced evidence gaps. It did not write or rewrite manuscripts.

## Built Product Loop

1. Project workspace
2. Literature library from PDFs, BibTeX/Zotero imports, and saved recommendations
3. Literature Map generation
4. Discover recommendations
5. Draft upload with paper type and citation style
6. Stage 1 editing checks plus reviewer-style draft analysis
7. Revision comparison support

Primary frontend surfaces:

- `services/frontend/src/pages/ProjectDetail.tsx`
- `services/frontend/src/pages/DraftAnalysis.tsx`
- `services/frontend/src/components/InsightsTab/`
- `services/frontend/src/components/DiscoverTab/`

## Technical Stack

- Frontend: React 19, TypeScript, Vite, Tailwind tokens
- Backend: Python 3.11, FastAPI, Pydantic v2
- Database/auth/storage: Supabase PostgreSQL, Supabase Auth, Supabase Storage
- Retrieval: OpenAI embeddings, pgvector, project-scoped literature chunks
- AI: OpenAI GPT models
- Background work: Celery and Redis
- PDF processing: GROBID with PyMuPDF fallback
- Payments: Stripe code exists, but production checkout was not finished

## Not Completed

- Stripe production checkout, billing portal, and webhook verification
- Collaboration and shared lab workspaces
- Full Overleaf/inline editing workflow
- Stronger PDF parsing for figures, tables, captions, and exact page anchors
- Final claim extraction and evidence-grounding quality pass
- Full cleanup of legacy Discover routes and historical planning docs

## Public Release Notes

- Real environment files must remain untracked.
- `.env.example` contains placeholders only.
- Historical uploaded-file paths were removed from git history before public release.
- The project should be treated as archival code.
