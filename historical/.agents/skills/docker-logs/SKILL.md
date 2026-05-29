---
name: docker-logs
description: Summarize recent Noesis container errors from backend and Celery workers. Use while debugging uploads, analysis jobs, or local infra issues.
version: 1.0.0
user-invocable: true
---

# Docker Logs

Use this for fast diagnosis when Noesis background processing or API behavior looks broken.

## Default targets

- `noesis-backend`
- `noesis-celery-worker`

## Procedure

1. Pull recent logs:

```bash
docker logs --tail 200 noesis-backend
docker logs --tail 200 noesis-celery-worker
```

2. If the user wants live logs, tail them explicitly instead:

```bash
docker logs -f noesis-backend
docker logs -f noesis-celery-worker
```

3. Extract:
- repeated exceptions
- OpenAI or rate-limit failures
- Supabase auth/storage failures
- Celery retries or worker crashes
- GROBID and file-processing errors

4. Summarize the likely root cause, affected subsystem, and immediate next debugging step.

## Guardrails

- Do not paste long raw logs unless the user asks
- Call out if a container is missing or stopped instead of pretending analysis succeeded
