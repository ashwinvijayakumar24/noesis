# 05 - Literature Map

Last updated: May 10, 2026

Original scope: the old "Insights" feature, quota enforcement, staleness, synthesis quality, and external paper suggestions.

Current name: Literature Map.

## Status

Mostly implemented.

Completed:

- Product copy moved from "Insights" toward "Literature Map".
- `POST /projects/{id}/insights/analyze` starts generation.
- `GET /projects/{id}/insights` returns UI state.
- Free refresh quota is 5/day via Redis key `daily_insights:{user_id}:{date}`.
- Pro/Team/Enterprise/Admin tiers have unlimited refreshes.
- Backend returns quota state.
- Backend staleness detection compares current analyzed document count and latest document update time against `insights_updated_at`.
- Progress snapshots are stored and returned while analysis is running.
- Literature Map payload includes top-level and grouped recommendation context.

## Remaining Work

- Make synthesis less generic by feeding more raw chunk evidence, not only pre-summarized analyses.
- Require stronger citation anchors for every key insight.
- Improve inline recommendation quality inside gaps/conflicts.
- Make frontend failure states more specific and recovery-oriented.
- Confirm Literature Map generation cost under realistic project sizes.

## Files

- `services/backend/app/api/routes/projects.py`
- `services/backend/app/services/project_insights.py`
- `services/backend/app/tasks/insights_analysis.py`
- `services/frontend/src/components/InsightsTab/`
- `infra/db-migrations/018_add_insights_metadata_to_projects.sql`
- `infra/db-migrations/019_add_recommendation_context_to_paper_recommendations.sql`

## Next Actions

1. Add source-paper anchors to each major insight.
2. Evaluate raw chunk retrieval for synthesis context.
3. Improve Literature Map error copy and retry behavior.
