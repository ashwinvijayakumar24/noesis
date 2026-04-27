---
name: test-flow
description: Validate the core Noesis backend flow after API or workflow changes. Runs the current E2E suite and checks the upload-to-analysis and draft-analysis paths without relying on removed chat functionality.
version: 1.0.0
user-invocable: true
---

# Test Flow

`AGENTS.md` says chat was removed. Do not validate legacy chat flows. Current focus is document upload, analysis, literature pipeline, and draft analysis.

## Primary command

```bash
cd services/backend && python3 -m pytest tests/e2e/ -v --timeout=120 -m "not slow"
```

## Run when

- Backend routes, services, workflows, Celery tasks, or quota logic changed
- GPT/OpenAI integration changed
- Before deploy when backend behavior may have shifted

## Procedure

1. Run the primary E2E command from `AGENTS.md`.
2. If it fails because dependencies are not running, state the blocker precisely.
3. If failures are targeted, run narrower follow-up tests only after the full suite establishes the breakage.
4. Summarize by user flow:
- document upload / ingestion
- analysis pipeline
- literature tab or BibTeX resolution path if relevant
- draft analysis / export path if relevant

## Guardrails

- Do not talk about RAG chat as a required pass condition unless the repo clearly reintroduced it
- Prefer current `tests/e2e/` over older ad hoc test scripts
- Report exact failing tests and first meaningful traceback, not the entire log dump
