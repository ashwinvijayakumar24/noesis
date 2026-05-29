# 07 - Draft Analysis

Last updated: May 10, 2026

Original scope: two-stage review, Reviewer 1 / Reviewer 2 personas, pre-upload questions, external paper pull, revision tracking, and privacy copy.

## Status

Major progress made.

Completed:

- Draft upload captures `paper_type` and `citation_style`.
- Stage 1 mechanical editing exists in `stage1_editing.py` and uses `gpt-5-mini`.
- Reviewer 1 strengths generation exists in `reviewer1_feedback.py`.
- Reviewer 2/deep critique remains the main reviewer feedback path.
- External source discovery was added to the LangGraph workflow.
- Feedback anchor QA helpers were added.
- Draft progress stream emits named workflow steps.
- Privacy/no-training copy appears in major user-facing draft surfaces.
- Reliability tests cover key anchoring and external-source behavior.

## Remaining Work

- Improve claim extraction quality and granularity.
- Improve exact text anchors and page/position matching.
- Strengthen support/contradiction scoring for claims.
- Add better per-item resolved/still-open revision UX.
- Improve figure/table/caption understanding in drafts.
- Build inline editing / Overleaf workflow support.
- Make Reviewer 1 / Reviewer 2 separation clearer in the UI.

## Files

- `services/backend/app/api/routes/drafts.py`
- `services/backend/app/services/draft_processing.py`
- `services/backend/app/services/stage1_editing.py`
- `services/backend/app/services/reviewer1_feedback.py`
- `services/backend/app/services/reviewer_feedback.py`
- `services/backend/app/services/draft_external_source_discovery.py`
- `services/backend/app/services/draft_anchor_qa.py`
- `services/backend/app/workflows/draft_analysis/`
- `services/frontend/src/pages/DraftAnalysis.tsx`
- `services/frontend/src/components/draft-analysis/`

## Next Actions

1. Improve claim/evidence grounding and anchors.
2. Strengthen revision comparison UI.
3. Start Overleaf/sidebar workflow design.
