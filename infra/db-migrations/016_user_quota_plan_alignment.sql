-- ============================================================
-- Migration 016: Align user_quotas with billing-backed plan limits
--
-- Purpose:
--   1. Ensure user_quotas contains BibTeX quota columns.
--   2. Backfill missing quota rows for all users.
--   3. Align enforced quota limits to the current billing plan without
--      resetting any existing monthly usage counters.
-- ============================================================

ALTER TABLE user_quotas
  ADD COLUMN IF NOT EXISTS current_month_bib_refs INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS monthly_bib_refs_limit INTEGER DEFAULT 30;

ALTER TABLE user_quotas
  DROP CONSTRAINT IF EXISTS valid_plan_tier;

ALTER TABLE user_quotas
  ADD CONSTRAINT valid_plan_tier
  CHECK (plan_tier IN ('free', 'pro', 'team', 'enterprise', 'admin', 'lab'));

WITH effective_plans AS (
  SELECT
    u.id AS user_id,
    CASE
      WHEN LOWER(COALESCE(uq.plan_tier, '')) = 'admin' THEN 'admin'
      WHEN LOWER(COALESCE(uq.plan_tier, '')) = 'lab' THEN 'lab'
      WHEN LOWER(COALESCE(s.status, '')) IN ('active', 'trialing', 'past_due') THEN LOWER(COALESCE(s.plan_tier, 'free'))
      WHEN LOWER(COALESCE(uq.plan_tier, '')) IN ('pro', 'team', 'enterprise') THEN LOWER(uq.plan_tier)
      ELSE 'free'
    END AS effective_plan_tier
  FROM auth.users u
  LEFT JOIN subscriptions s
    ON s.user_id = u.id
  LEFT JOIN user_quotas uq
    ON uq.user_id = u.id
),
quota_targets AS (
  SELECT
    user_id,
    effective_plan_tier,
    CASE
      WHEN effective_plan_tier = 'pro' THEN 100
      WHEN effective_plan_tier IN ('team', 'enterprise', 'admin', 'lab') THEN 9999
      ELSE 30
    END AS monthly_document_limit,
    CASE
      WHEN effective_plan_tier = 'pro' THEN 20
      WHEN effective_plan_tier IN ('team', 'enterprise', 'admin', 'lab') THEN 9999
      ELSE 2
    END AS monthly_draft_limit,
    CASE
      WHEN effective_plan_tier = 'pro' THEN 100
      WHEN effective_plan_tier IN ('team', 'enterprise', 'admin', 'lab') THEN 9999
      ELSE 30
    END AS monthly_bib_refs_limit
  FROM effective_plans
)
INSERT INTO user_quotas (
  user_id,
  plan_tier,
  monthly_document_limit,
  monthly_draft_limit,
  monthly_chat_messages_limit,
  monthly_bib_refs_limit,
  current_month_bib_refs
)
SELECT
  user_id,
  effective_plan_tier,
  monthly_document_limit,
  monthly_draft_limit,
  500,
  monthly_bib_refs_limit,
  0
FROM quota_targets
ON CONFLICT (user_id) DO UPDATE
SET
  plan_tier = EXCLUDED.plan_tier,
  monthly_document_limit = EXCLUDED.monthly_document_limit,
  monthly_draft_limit = EXCLUDED.monthly_draft_limit,
  monthly_bib_refs_limit = EXCLUDED.monthly_bib_refs_limit,
  updated_at = NOW();
