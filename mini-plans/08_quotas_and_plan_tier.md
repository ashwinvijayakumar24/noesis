# 08 - Quotas And Plan-Tier Awareness

Last updated: May 10, 2026

Original scope: cross-cutting quota bugs, Stripe webhook flow, and per-project vs. per-user scoping.

## Status

Quota code has been substantially updated. Stripe production setup remains unfinished.

Completed:

- Plan constants live in `services/backend/app/services/quota_management.py`.
- Free: 3 projects, 30 PDFs/month, 30 BibTeX refs/month, 2 drafts/month.
- Pro: 10 projects, 100 PDFs/month, 100 BibTeX refs/month, 20 drafts/month.
- Team/Enterprise/Admin: effectively unlimited with hard caps.
- Literature Map daily quota exists outside monthly quota counters.
- Discover daily quota exists on `paper_recommendations`.
- `sync_user_quota_plan()` updates quota limits without resetting usage.
- Stripe webhook handlers call quota sync.
- Migration `016_user_quota_plan_alignment.sql` aligns existing quota rows.

## Current Pricing Caveat

Stripe pricing is not finished. Checkout and webhook code exist, but production billing cannot be treated as complete until:

- live Stripe price IDs are configured and verified
- webhook endpoint and signature secret are verified
- pricing page checkout succeeds in production
- checkout upgrades `user_quotas` in production
- cancellation/downgrade resets quotas correctly
- billing portal behavior is verified
- Team copy is aligned with actual collaboration functionality

## Decisions

- Quotas are per user, not per project.
- Pricing copy should say monthly totals, not per-project totals.

## Files

- `services/backend/app/services/quota_management.py`
- `services/backend/app/services/stripe_service.py`
- `services/backend/app/api/routes/subscriptions.py`
- `services/frontend/src/pages/Pricing.tsx`
- `infra/db-migrations/016_user_quota_plan_alignment.sql`

## Next Actions

1. Finish production Stripe connection.
2. Test checkout-to-quota-upgrade end to end.
3. Add cancellation/downgrade tests.
4. Reconcile Team pricing copy with collaboration roadmap.
