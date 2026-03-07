-- ================================
-- Migration 004: Referral System
-- Purpose: Track user referrals for viral growth
-- ================================

CREATE TABLE IF NOT EXISTS referrals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    referrer_user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    referee_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    referral_code TEXT UNIQUE NOT NULL,
    referee_email TEXT,
    status TEXT DEFAULT 'pending',  -- 'pending', 'completed', 'expired'
    reward_granted BOOLEAN DEFAULT false,
    reward_type TEXT,  -- 'free_month', 'credits', etc.
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_user_id);
CREATE INDEX IF NOT EXISTS idx_referrals_code ON referrals(referral_code);
CREATE INDEX IF NOT EXISTS idx_referrals_referee ON referrals(referee_user_id);
CREATE INDEX IF NOT EXISTS idx_referrals_status ON referrals(status);

-- RLS policies
ALTER TABLE referrals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own referrals"
ON referrals FOR SELECT
USING (auth.uid() = referrer_user_id OR auth.uid() = referee_user_id);

CREATE POLICY "Users can insert their own referrals"
ON referrals FOR INSERT
WITH CHECK (auth.uid() = referrer_user_id);

CREATE POLICY "System can update referrals"
ON referrals FOR UPDATE
USING (true);  -- Allow updates from service role

-- Function to generate unique referral code
CREATE OR REPLACE FUNCTION generate_referral_code(user_id_param UUID)
RETURNS TEXT AS $$
DECLARE
    code TEXT;
BEGIN
    -- Generate code like: NOESIS-ABC123
    code := 'NOESIS-' || UPPER(SUBSTRING(MD5(user_id_param::TEXT || NOW()::TEXT) FROM 1 FOR 6));
    RETURN code;
END;
$$ LANGUAGE plpgsql;
