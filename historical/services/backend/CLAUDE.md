# Backend Context

Last updated: May 10, 2026

Read `../../current_state.md` before making broad backend changes.

## Stack

- Python 3.11 in production
- FastAPI 0.115
- Pydantic v2
- Supabase Python client
- Celery + Redis
- GROBID + PyMuPDF fallback
- OpenAI GPT-5.2 / `gpt-5.2-chat-latest`
- `gpt-5-mini` for bounded Stage 1 editing

## Critical Rules

- GPT-5.2 only for substantive analysis.
- Use `max_completion_tokens`, never `max_tokens`.
- Do not revert to `gpt-4o`.
- Use Supabase client operations; do not introduce SQLAlchemy app flows.
- No local database.
- No auto-writing or rewriting of user drafts.
- Heavy work belongs in Celery tasks or existing workflow infrastructure.

## Current Backend Domains

- `api/routes/projects.py`: projects, BibTeX import/export, Literature Map, Literature Map quota/staleness
- `api/routes/documents.py`: PDF upload, document analysis, metadata, export
- `api/routes/paper_recommendations.py`: current Discover surface
- `api/routes/paper_discovery.py`: legacy auto-add discovery route; cleanup candidate
- `api/routes/drafts.py`: draft upload, analysis, stream, all-feedback, export
- `api/routes/subscriptions.py`: Stripe checkout/webhooks

## Key Services

- `quota_management.py`: plan limits and quota rows
- `stripe_service.py`: Stripe session/webhook handling and quota sync
- `project_insights.py`: Literature Map synthesis
- `paper_recommendations.py`: Discover generation/search
- `draft_processing.py`: draft orchestration
- `stage1_editing.py`: mechanical editing pass
- `reviewer1_feedback.py`: strengths pass
- `reviewer_feedback.py`: deep critique
- `draft_external_source_discovery.py`: external sources for draft gaps/claims
- `draft_anchor_qa.py`: feedback QA and anchoring
- `rag_ingest.py` / `rag_retrieval.py`: chunking, embeddings, retrieval
- `progress_tracking.py`: polling progress snapshots

## Quotas

Canonical limits live in `quota_management.py`.

- Free: 3 projects, 30 PDFs/month, 30 BibTeX refs/month, 2 drafts/month, 5 Discover/day, 5 Literature Map/day
- Pro: 10 projects, 100 PDFs/month, 100 BibTeX refs/month, 20 drafts/month, 50 Discover/day, unlimited Literature Map
- Team/Enterprise/Admin: effectively unlimited with hard caps

Stripe caveat: checkout/webhook code exists, but production price IDs, webhook verification, billing portal, and checkout-to-quota-upgrade testing are not complete.

## Patterns

```python
response = client.chat.completions.create(
    model="gpt-5.2",
    max_completion_tokens=2000,
    messages=[...],
)

result = supabase.table("documents").select("*").eq("project_id", project_id).execute()

from app.core.celery_app import celery_app

@celery_app.task
def my_task(document_id: str):
    ...
```

## Auth

Routes should depend on the current user, except explicitly public endpoints like health/platform/public subscription metadata/webhooks.

## Testing

```bash
cd services/backend
python3 -m pytest tests/ -v
python3 -m pytest tests/e2e/ -v --timeout=120 -m "not slow"
```
