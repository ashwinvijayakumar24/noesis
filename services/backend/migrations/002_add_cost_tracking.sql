-- Migration: Add Cost Tracking and Quota Management
-- Description: Prevent cost explosion with usage quotas and OpenAI cost tracking
-- Date: 2025-12-30
-- Critical: MUST be applied before public beta launch

-- =============================================================================
-- USER QUOTAS TABLE
-- =============================================================================

CREATE TABLE user_quotas (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

  -- Plan tier
  plan_tier TEXT NOT NULL DEFAULT 'free',

  -- Monthly limits per tier
  monthly_document_limit INTEGER NOT NULL DEFAULT 20,
  monthly_draft_limit INTEGER NOT NULL DEFAULT 5,
  monthly_chat_messages_limit INTEGER NOT NULL DEFAULT 100,

  -- Current month usage counters
  current_month_documents INTEGER NOT NULL DEFAULT 0,
  current_month_drafts INTEGER NOT NULL DEFAULT 0,
  current_month_chat_messages INTEGER NOT NULL DEFAULT 0,

  -- Quota reset tracking
  quota_reset_date TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT (NOW() + INTERVAL '1 month'),

  -- Metadata
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

  -- Constraints
  CONSTRAINT valid_plan_tier CHECK (plan_tier IN ('free', 'pro', 'enterprise')),
  CONSTRAINT positive_limits CHECK (
    monthly_document_limit >= 0 AND
    monthly_draft_limit >= 0 AND
    monthly_chat_messages_limit >= 0
  ),
  CONSTRAINT positive_usage CHECK (
    current_month_documents >= 0 AND
    current_month_drafts >= 0 AND
    current_month_chat_messages >= 0
  ),
  CONSTRAINT unique_user_quota UNIQUE (user_id)
);

-- Index for fast user lookups
CREATE INDEX idx_user_quotas_user_id ON user_quotas(user_id);

-- Enable RLS
ALTER TABLE user_quotas ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view own quotas"
  ON user_quotas
  FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own quotas"
  ON user_quotas
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own quotas"
  ON user_quotas
  FOR UPDATE
  USING (auth.uid() = user_id);

-- =============================================================================
-- OPENAI USAGE TRACKING TABLE
-- =============================================================================

CREATE TABLE openai_usage_tracking (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

  -- Operation details
  operation_type TEXT NOT NULL,
  model TEXT NOT NULL,

  -- Token usage
  prompt_tokens INTEGER NOT NULL DEFAULT 0,
  completion_tokens INTEGER NOT NULL DEFAULT 0,
  total_tokens INTEGER NOT NULL DEFAULT 0,

  -- Cost estimation (in USD)
  estimated_cost_usd NUMERIC(10, 6) NOT NULL DEFAULT 0,

  -- Metadata
  project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
  document_id UUID REFERENCES documents(id) ON DELETE SET NULL,
  draft_id UUID REFERENCES drafts(id) ON DELETE SET NULL,

  -- Timestamp
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

  -- Constraints
  CONSTRAINT valid_operation_type CHECK (
    operation_type IN (
      'document_analysis',
      'draft_analysis',
      'chat',
      'embeddings',
      'insights_generation',
      'compass_guidance',
      'citation_suggestions',
      'claim_extraction',
      'coverage_analysis',
      'reviewer_feedback'
    )
  ),
  CONSTRAINT positive_tokens CHECK (
    prompt_tokens >= 0 AND
    completion_tokens >= 0 AND
    total_tokens >= 0
  ),
  CONSTRAINT positive_cost CHECK (estimated_cost_usd >= 0)
);

-- Indexes for analytics and cost monitoring
CREATE INDEX idx_openai_usage_user_id ON openai_usage_tracking(user_id);
CREATE INDEX idx_openai_usage_created_at ON openai_usage_tracking(created_at DESC);
CREATE INDEX idx_openai_usage_operation_type ON openai_usage_tracking(operation_type);
CREATE INDEX idx_openai_usage_user_date ON openai_usage_tracking(user_id, created_at DESC);

-- Enable RLS
ALTER TABLE openai_usage_tracking ENABLE ROW LEVEL SECURITY;

-- RLS Policies
CREATE POLICY "Users can view own usage"
  ON openai_usage_tracking
  FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own usage"
  ON openai_usage_tracking
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Function to auto-create quota record for new users
CREATE OR REPLACE FUNCTION create_default_quota_for_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO user_quotas (user_id, plan_tier)
  VALUES (NEW.id, 'free')
  ON CONFLICT (user_id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to create quota when user signs up
CREATE TRIGGER on_user_created_create_quota
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION create_default_quota_for_user();

-- Function to increment quota usage atomically
CREATE OR REPLACE FUNCTION increment_quota_field(
  user_id_param UUID,
  field_name TEXT
)
RETURNS VOID AS $$
BEGIN
  IF field_name = 'current_month_documents' THEN
    UPDATE user_quotas
    SET current_month_documents = current_month_documents + 1,
        updated_at = NOW()
    WHERE user_id = user_id_param;
  ELSIF field_name = 'current_month_drafts' THEN
    UPDATE user_quotas
    SET current_month_drafts = current_month_drafts + 1,
        updated_at = NOW()
    WHERE user_id = user_id_param;
  ELSIF field_name = 'current_month_chat_messages' THEN
    UPDATE user_quotas
    SET current_month_chat_messages = current_month_chat_messages + 1,
        updated_at = NOW()
    WHERE user_id = user_id_param;
  END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to reset quota counters (call monthly via cron or scheduler)
CREATE OR REPLACE FUNCTION reset_quota_if_needed(user_id_param UUID)
RETURNS VOID AS $$
BEGIN
  UPDATE user_quotas
  SET
    current_month_documents = 0,
    current_month_drafts = 0,
    current_month_chat_messages = 0,
    quota_reset_date = NOW() + INTERVAL '1 month',
    updated_at = NOW()
  WHERE user_id = user_id_param
  AND quota_reset_date < NOW();
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get total cost for user in date range
CREATE OR REPLACE FUNCTION get_user_total_cost(
  user_id_param UUID,
  start_date TIMESTAMP WITH TIME ZONE,
  end_date TIMESTAMP WITH TIME ZONE
)
RETURNS NUMERIC AS $$
DECLARE
  total_cost NUMERIC;
BEGIN
  SELECT COALESCE(SUM(estimated_cost_usd), 0)
  INTO total_cost
  FROM openai_usage_tracking
  WHERE user_id = user_id_param
  AND created_at >= start_date
  AND created_at <= end_date;

  RETURN total_cost;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Function to get aggregate usage stats (for admin dashboard)
CREATE OR REPLACE FUNCTION get_aggregate_usage_stats(
  start_date TIMESTAMP WITH TIME ZONE,
  end_date TIMESTAMP WITH TIME ZONE
)
RETURNS TABLE (
  operation_type TEXT,
  total_calls BIGINT,
  total_tokens BIGINT,
  total_cost_usd NUMERIC,
  avg_tokens_per_call NUMERIC
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    t.operation_type,
    COUNT(*) as total_calls,
    SUM(t.total_tokens) as total_tokens,
    SUM(t.estimated_cost_usd) as total_cost_usd,
    AVG(t.total_tokens) as avg_tokens_per_call
  FROM openai_usage_tracking t
  WHERE t.created_at >= start_date
  AND t.created_at <= end_date
  GROUP BY t.operation_type
  ORDER BY total_cost_usd DESC;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- =============================================================================
-- PLAN TIER CONFIGURATIONS
-- =============================================================================

-- Helper view for plan tier details
CREATE OR REPLACE VIEW plan_tier_configs AS
SELECT
  'free' AS tier,
  20 AS monthly_documents,
  5 AS monthly_drafts,
  100 AS monthly_chat_messages,
  0.00 AS monthly_price_usd
UNION ALL
SELECT
  'pro' AS tier,
  100 AS monthly_documents,
  25 AS monthly_drafts,
  500 AS monthly_chat_messages,
  10.00 AS monthly_price_usd
UNION ALL
SELECT
  'enterprise' AS tier,
  -1 AS monthly_documents,  -- -1 = unlimited
  -1 AS monthly_drafts,
  -1 AS monthly_chat_messages,
  0.00 AS monthly_price_usd;  -- Custom pricing

-- =============================================================================
-- SEED DATA - Create quotas for existing users
-- =============================================================================

-- Insert default quotas for all existing users who don't have one
INSERT INTO user_quotas (user_id, plan_tier)
SELECT id, 'free'
FROM auth.users
WHERE id NOT IN (SELECT user_id FROM user_quotas)
ON CONFLICT (user_id) DO NOTHING;

-- =============================================================================
-- COST ESTIMATION REFERENCE (as of January 2025)
-- =============================================================================

-- GPT-4o:
--   Input: $0.0025 per 1K tokens
--   Output: $0.01 per 1K tokens

-- text-embedding-3-small:
--   $0.00002 per 1K tokens

-- Example calculations in application code:
-- cost = (prompt_tokens / 1000) * 0.0025 + (completion_tokens / 1000) * 0.01

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================

-- Check quotas were created for all users:
-- SELECT COUNT(*) FROM user_quotas;
-- SELECT COUNT(*) FROM auth.users;
-- (Should match)

-- View current usage for a user:
-- SELECT * FROM user_quotas WHERE user_id = 'YOUR_USER_ID';

-- View total OpenAI costs:
-- SELECT SUM(estimated_cost_usd) as total_cost FROM openai_usage_tracking;

-- Get usage by operation type:
-- SELECT operation_type, COUNT(*), SUM(estimated_cost_usd)
-- FROM openai_usage_tracking
-- GROUP BY operation_type
-- ORDER BY SUM(estimated_cost_usd) DESC;

-- =============================================================================
-- MONITORING QUERIES (Run periodically)
-- =============================================================================

-- Top 10 users by cost this month:
-- SELECT
--   u.user_id,
--   u.email,
--   SUM(o.estimated_cost_usd) as monthly_cost,
--   COUNT(*) as operations_count
-- FROM openai_usage_tracking o
-- JOIN auth.users u ON u.id = o.user_id
-- WHERE o.created_at >= DATE_TRUNC('month', NOW())
-- GROUP BY u.user_id, u.email
-- ORDER BY monthly_cost DESC
-- LIMIT 10;

-- Users approaching quota limits:
-- SELECT
--   u.email,
--   q.current_month_documents,
--   q.monthly_document_limit,
--   q.current_month_drafts,
--   q.monthly_draft_limit,
--   q.quota_reset_date
-- FROM user_quotas q
-- JOIN auth.users u ON u.id = q.user_id
-- WHERE q.current_month_documents >= q.monthly_document_limit * 0.8
--    OR q.current_month_drafts >= q.monthly_draft_limit * 0.8;

-- =============================================================================
-- ROLLBACK INSTRUCTIONS
-- =============================================================================

-- DROP TRIGGER IF EXISTS on_user_created_create_quota ON auth.users;
-- DROP FUNCTION IF EXISTS create_default_quota_for_user();
-- DROP FUNCTION IF EXISTS increment_quota_field(UUID, TEXT);
-- DROP FUNCTION IF EXISTS reset_quota_if_needed(UUID);
-- DROP FUNCTION IF EXISTS get_user_total_cost(UUID, TIMESTAMP WITH TIME ZONE, TIMESTAMP WITH TIME ZONE);
-- DROP FUNCTION IF EXISTS get_aggregate_usage_stats(TIMESTAMP WITH TIME ZONE, TIMESTAMP WITH TIME ZONE);
-- DROP VIEW IF EXISTS plan_tier_configs;
-- DROP TABLE IF EXISTS openai_usage_tracking;
-- DROP TABLE IF EXISTS user_quotas;
