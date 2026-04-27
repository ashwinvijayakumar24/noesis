# 08 — Quotas & Plan-Tier Awareness

**Scope:** Cross-cutting quota bugs, Stripe webhook flow, per-project vs per-user scoping.
**Source:** `arch_plan.md` §8, §10.1, §9.8.

---

## Current State

| Quota Type | Free (stated) | Free (actual) | Pro (stated) | Pro (actual) | Enforced? |
|---|---|---|---|---|---|
| Projects | 3 | 3 ✅ | 10 | 999 ❌ | Yes |
| PDF uploads | 30/project/mo | 30/user/mo | 100/project/mo | 30/user/mo ❌ | Yes |
| BibTeX refs | 30/mo (per notes) | 100/mo | same as PDFs | 100/mo | Yes |
| Drafts | 5/mo | 5/mo ✅ | TBD | 5/mo ❌ | Yes |
| Paper discovery | "Free limited" | 10/day | higher | 999/day ✅ | Yes (Redis) |
| **Insights regen** | **5/day** | **unlimited** ❌ | unlimited | unlimited | **No** |

## Three Distinct Problems

### 8a. Tier-awareness is broken
- `create_default_quota()` hardcodes free values (30 PDFs, 5 drafts, 100 BibTeX refs, 500 chat).
- There's **no "upgrade-time" hook** that flips them to pro values when Stripe webhooks mark a user `plan_tier='pro'`.
- **Effectively: paying users get free-tier limits unless you manually update their rows.**
- **Fix locations:**
  - `services/backend/app/services/stripe_service.py` — webhook handler should update quota fields on `customer.subscription.created/updated`.
  - `services/backend/app/services/quota_management.py` — add `upgrade_quota_to_tier(user_id, tier)` helper.
  - Data repair: one-off script to backfill current Pro users who are stuck with free-tier caps.

### 8b. Insights has zero enforcement
- Single biggest cost leak.
- Detailed in `05_literature_insights.md` §5a.
- Fix is ~15 lines (mirror `daily_discovery` Redis pattern).

### 8c. Per-project vs. per-user scoping mismatch
- Stated "per project" (e.g., "30 PDFs per project per month") but coded "per user" (`monthly_document_limit` on `user_quotas`).
- **Decision matrix:**
  - **Per user (current):** simpler accounting; one counter per user; matches how OpenAI costs are tracked.
  - **Per project (stated):** more generous on marketing; users with 3 projects get 3× the uploads; harder to model cost.
- **Recommendation:** stick with per-user but **update your pricing page and architecture notes to match** (say "30 PDFs/month total" not "per project"). Or if you want to keep the per-project story, schema change: add `monthly_document_limit` column to `projects` table, track usage in `project_quotas`.

## Recommended Quota Values (after competitive benchmarking)

### Free Tier
- Projects: 3
- PDF uploads: 30/month (scope: user-wide)
- BibTeX refs: 30/month (align with PDFs, not 100)
- Drafts: **2/month** (down from 5 — wedge into paid)
- Discovery: **5/day** (down from 10)
- Insights regen: 5/day

### Pro Tier ($12/mo)
- Projects: 10 (match stated limit)
- PDF uploads: 100/month
- BibTeX refs: 100/month
- Drafts: 20/month
- Discovery: 50/day
- Insights regen: unlimited

### Team Tier ($20/user/mo)
- Everything unlimited except hard caps (Discovery 999/day already in place).

## Implementation Ordering

1. **Fix Pro project limit** (3-line change in `routes/projects.py:36-62`).
2. **Add insights quota** (~15 lines; mirrors `daily_discovery`).
3. **Wire Stripe webhook to quota upgrade** (audit `stripe_service.py` + add `upgrade_quota_to_tier()`).
4. **Backfill paying users** who are currently stuck with free limits.
5. **Per-project vs per-user decision** (likely just update copy).

## Priority
- **P0:** Fix Pro project limit (999 → 10).
- **P0:** Insights quota enforcement.
- **P0:** Stripe webhook → quota upgrade flow.
- **P1:** Backfill script for existing paying users.
- **P2:** Pricing-page copy alignment (per-project vs per-user).
