# 06 - Discover Papers

Last updated: May 10, 2026

Original scope: paper discovery, save/dismiss flow, deduplication, pagination, and cross-population from Literature Map/draft analysis.

## Status

Partially implemented through the newer `paper_recommendations` route family.

Completed:

- Generate recommendations: `POST /paper-recommendations/projects/{id}/generate`.
- Search recommendations: `POST /paper-recommendations/projects/{id}/search`.
- Paginated payload: `GET /paper-recommendations/projects/{id}`.
- Save-to-literature endpoint: `POST /paper-recommendations/projects/{id}/save-discovered/{recommendation_id}`.
- Quota status endpoint.
- Free quota is 5 Discover actions/day.
- Pro quota is 50 Discover actions/day.
- Recommendation pool is capped at 30.
- UI presents results 5 at a time.
- Saved recommendations become `documents` records with `source_type='discovered'` and resolution metadata.

## Known Caveat

The older `services/backend/app/api/routes/paper_discovery.py` route still exists. It auto-adds discovered papers and uses older quota semantics. Treat it as legacy cleanup unless intentionally revived.

## Remaining Work

- Delete or formally deprecate the legacy auto-add route.
- Add dismissal/no-repeat tracking so rejected papers do not recur.
- Clarify quota accounting for saved discovered papers.
- Make Discover require useful project context before generation, or improve empty-project query quality.
- Improve cross-population from Literature Map and draft gaps.

## Files

- `services/backend/app/api/routes/paper_recommendations.py`
- `services/backend/app/services/paper_recommendations.py`
- `services/frontend/src/components/DiscoverTab/index.tsx`
- `services/backend/app/api/routes/paper_discovery.py` (legacy)

## Next Actions

1. Decide whether to remove `paper_discovery.py`.
2. Add dismissal/no-repeat persistence.
3. Add tests around save-to-literature accounting and resolution behavior.
