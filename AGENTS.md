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
