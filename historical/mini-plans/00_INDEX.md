# Mini-Plans Index

Last updated: May 10, 2026

These mini-plans are historical implementation slices from the architecture audit. They are no longer the primary source of truth. Use `../current_state.md` first, then use the mini-plan files for context on why decisions were made and what remains.

## Existing Files

| File | Area | Current status |
|---|---|---|
| `05_literature_insights.md` | Literature Map | Mostly implemented: rename, quota, staleness, progress, recommendation context. Remaining: quality of synthesis, stronger grounding, raw chunk use. |
| `06_discover_papers.md` | Discover | Partially implemented through `paper_recommendations`: quota, 30-paper pool, pagination, save-to-literature. Remaining: legacy route cleanup, dismissal/no-repeat, clearer accounting. |
| `07_draft_analysis.md` | Draft Analysis | Major progress: upload context, Stage 1, Reviewer 1, external source discovery, privacy copy, progress stream. Remaining: better claims, anchors, revision UX, figure/table handling. |
| `08_quotas_and_plan_tier.md` | Quotas / Stripe | Quota constants and Stripe quota sync exist. Remaining: production Stripe pricing/checkout/webhook verification and billing portal. |
| `09_cross_cutting_trust_ux.md` | Trust / UX / infra | Privacy copy and progress improved. Remaining: structured frontend errors, OpenAI tier/throughput checks, more specific failure states. |

The earlier index referenced files `01` through `04` and `10` through `12`, but those files are not present in the repo. Do not assume they exist.

## Completed Or Mostly Completed

- Literature Map naming in product copy.
- Literature Map daily quota: Free 5/day, paid/admin tiers unlimited.
- Literature Map staleness computed by backend.
- Literature Map progress and error payloads.
- Recommendation groupings in Literature Map payload.
- Free Discover quota lowered to 5/day and Pro to 50/day on current `paper_recommendations` route.
- Discover recommendation pool capped at 30 and paginated.
- Pro project cap changed to 10.
- Plan-aware quota constants for PDFs, BibTeX, drafts, and projects.
- Stripe webhook handlers call quota sync helpers.
- Draft upload context fields: paper type and citation style.
- Stage 1 editing pass.
- Reviewer 1 strengths pass.
- External source discovery in draft workflow.
- Privacy/not-used-for-training copy in major user-facing surfaces.
- Sentry scanner requests rejected as clean 400 responses.

## Current Priority List

### P0 - Before Serious Paid Launch

1. Finish Stripe production connection:
   - live price IDs
   - production webhook endpoint and secret
   - pricing-page checkout path
   - checkout-to-quota-upgrade verification
   - cancellation/downgrade verification
   - billing portal verification
2. Start and continue lab outreach now.
3. Improve PDF parsing and feedback anchors enough for credible demos.
4. Improve claim extraction and support-strength grounding.

### P1 - Product Differentiators

5. Collaboration: shared projects, invites, roles, lab workspace, advisor/student review flow.
6. Inline editing and Overleaf workflow, likely browser extension/sidebar first.
7. Discover cleanup: retire legacy `paper_discovery.py`, add dismissal/no-repeat, clarify save accounting.
8. Draft revision UX: stronger per-item resolved/still-open display.

### P2 - Quality And Cleanup

9. Evaluate PyMuPDF4LLM for better PDF structure and anchors.
10. Figure/table/caption extraction if it becomes demo-critical.
11. Structured frontend errors for uploads, BibTeX, quotas, and analysis failures.
12. Archive or delete stale docs after `current_state.md` is accepted as canonical.

## Historical Source

Original audit: `../here-is-the-comprehensive-curried-hedgehog.md`
