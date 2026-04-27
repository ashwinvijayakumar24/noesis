# Backend Context

## Stack
Python 3.11, FastAPI 0.115, Pydantic v2, Supabase Python Client, Celery + Redis, OpenAI GPT-5.2

## Critical Rules
- **GPT-5.2 only**: `model="gpt-5.2"` and `max_completion_tokens=N` (NOT `max_tokens`)
- **Supabase only**: use `supabase.table()` — no SQLAlchemy, no raw psycopg2
- **No auto-writing**: never rewrite user drafts; critique/review behavior only
- Embeddings: always 1536 dimensions (`text-embedding-3-small`)
- Background tasks: Celery with `task.delay()` — never `asyncio.create_task()` for heavy work

## Patterns
```python
# OpenAI call
response = client.chat.completions.create(
    model="gpt-5.2",
    max_completion_tokens=2000,
    messages=[...]
)

# Supabase query
result = supabase.table("documents").select("*").eq("project_id", pid).execute()

# Celery task
from app.core.celery_app import celery_app
@celery_app.task
def my_task(doc_id: str): ...
my_task.delay(doc_id)
```

## Key Services
- `services/document_analysis.py` — paper analysis pattern to follow
- `services/rag_ingest.py` — chunking + embedding pattern
- `services/retry_utils.py` — use for all external API calls
- `services/embedding_cache.py` — always check before generating embeddings

## Auth
All routes require `current_user = Depends(get_current_user)` except:
- `/health`, `/platform/stats`, `/subscriptions/webhook`
