# 09 - Cross-Cutting Trust, UX, And Infrastructure

Last updated: May 10, 2026

Original scope: privacy copy, error messages, progress visibility, and OpenAI rate limits.

## Status

Partially implemented.

Completed:

- Privacy/no-training copy appears in signup, privacy policy, document analysis, draft analysis, and Literature Map contexts.
- Draft analysis has stepwise progress streaming.
- Literature Map has progress snapshots.
- Sentry path traversal scanner requests now return clean 400 JSON from security middleware instead of unhandled 500s.

## Remaining Work

- Structured frontend errors are inconsistent.
- Upload/BibTeX/quota errors need specific user-facing next actions.
- OpenAI throughput/rate-limit readiness needs validation before heavier demos.
- More workflows should expose precise progress states and retry affordances.
- Failed document retry UX still needs strengthening if not already covered by current frontend changes.

## Files

- `services/backend/app/core/api_errors.py`
- `services/backend/app/core/security_middleware.py`
- `services/backend/app/services/progress_tracking.py`
- `services/backend/app/services/progress_publisher.py`
- `services/frontend/src/components/ui/InlineAlert.tsx`
- `services/frontend/src/components/ui/Toast.tsx`

## Next Actions

1. Standardize backend error payloads.
2. Standardize frontend toast/inline error rendering.
3. Validate OpenAI tier and throughput before lab demos with batch uploads.
