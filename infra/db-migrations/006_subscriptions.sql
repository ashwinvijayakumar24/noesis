-- ================================
-- Migration 006: Subscription Management
-- Purpose: Track user subscriptions and usage limits
-- ================================

CREATE TABLE IF NOT EXISTS subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    stripe_customer_id TEXT UNIQUE,
    stripe_subscription_id TEXT UNIQUE,
    plan_tier TEXT NOT NULL DEFAULT 'free',  -- 'free', 'pro', 'team'
    status TEXT DEFAULT 'active',  -- 'active', 'canceled', 'past_due', 'trialing'
    current_period_start TIMESTAMP WITH TIME ZONE,
    current_period_end TIMESTAMP WITH TIME ZONE,
    cancel_at_period_end BOOLEAN DEFAULT false,
    trial_end TIMESTAMP WITH TIME ZONE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS usage_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
    plan_tier TEXT NOT NULL DEFAULT 'free',

    -- Usage counters (reset monthly)
    drafts_analyzed_this_month INTEGER DEFAULT 0,
    papers_in_library INTEGER DEFAULT 0,
    chat_messages_this_month INTEGER DEFAULT 0,

    -- Limits per plan
    monthly_draft_limit INTEGER,
    library_size_limit INTEGER,
    monthly_chat_limit INTEGER,

    -- Reset tracking
    reset_date TIMESTAMP WITH TIME ZONE DEFAULT (DATE_TRUNC('month', NOW()) + INTERVAL '1 month'),
    last_reset TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_stripe_customer ON subscriptions(stripe_customer_id);
CREATE INDEX IF NOT EXISTS idx_subscriptions_status ON subscriptions(status);
CREATE INDEX IF NOT EXISTS idx_usage_limits_user ON usage_limits(user_id);

-- RLS policies
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_limits ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own subscription"
ON subscriptions FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "System can manage subscriptions"
ON subscriptions FOR ALL
USING (true);  -- Service role access

CREATE POLICY "Users can view their own usage limits"
ON usage_limits FOR SELECT
USING (auth.uid() = user_id);

CREATE POLICY "System can manage usage limits"
ON usage_limits FOR ALL
USING (true);  -- Service role access

-- Function to set default usage limits based on plan tier
CREATE OR REPLACE FUNCTION set_usage_limits(user_id_param UUID, tier TEXT)
RETURNS void AS $$
DECLARE
    draft_limit INTEGER;
    library_limit INTEGER;
    chat_limit INTEGER;
BEGIN
    -- Set limits based on tier
    CASE tier
        WHEN 'free' THEN
            draft_limit := 1;  -- 1 draft per month
            library_limit := 5;  -- 5 papers max
            chat_limit := 20;  -- 20 chat messages per month
        WHEN 'pro' THEN
            draft_limit := -1;  -- Unlimited (-1 means no limit)
            library_limit := -1;
            chat_limit := -1;
        WHEN 'team' THEN
            draft_limit := -1;
            library_limit := -1;
            chat_limit := -1;
        ELSE
            draft_limit := 1;
            library_limit := 5;
            chat_limit := 20;
    END CASE;

    -- Insert or update usage limits
    INSERT INTO usage_limits (
        user_id,
        plan_tier,
        monthly_draft_limit,
        library_size_limit,
        monthly_chat_limit
    )
    VALUES (
        user_id_param,
        tier,
        draft_limit,
        library_limit,
        chat_limit
    )
    ON CONFLICT (user_id) DO UPDATE SET
        plan_tier = tier,
        monthly_draft_limit = draft_limit,
        library_size_limit = library_limit,
        monthly_chat_limit = chat_limit,
        updated_at = NOW();
END;
$$ LANGUAGE plpgsql;

-- Function to reset monthly usage counters
CREATE OR REPLACE FUNCTION reset_monthly_usage()
RETURNS void AS $$
BEGIN
    UPDATE usage_limits
    SET
        drafts_analyzed_this_month = 0,
        chat_messages_this_month = 0,
        last_reset = NOW(),
        reset_date = DATE_TRUNC('month', NOW()) + INTERVAL '1 month'
    WHERE reset_date <= NOW();
END;
$$ LANGUAGE plpgsql;

-- Trigger to create default subscription and usage limits for new users
CREATE OR REPLACE FUNCTION create_default_subscription()
RETURNS trigger AS $$
BEGIN
    -- Create subscription record
    INSERT INTO subscriptions (user_id, plan_tier, status)
    VALUES (NEW.id, 'free', 'active');

    -- Set usage limits
    PERFORM set_usage_limits(NEW.id, 'free');

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Use a unique trigger name to avoid conflict with existing on_user_created_create_quota
DROP TRIGGER IF EXISTS on_user_created_subscription ON auth.users;
CREATE TRIGGER on_user_created_subscription
AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE FUNCTION create_default_subscription();
