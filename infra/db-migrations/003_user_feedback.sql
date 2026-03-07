-- ================================
-- Migration 003: User Feedback System
-- Purpose: Track user feedback for product improvements
-- ================================

CREATE TABLE IF NOT EXISTS user_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    feature_type TEXT NOT NULL,  -- 'draft_analysis', 'chat', 'paper_discovery', etc.
    context_id UUID,  -- ID of the draft, chat session, etc.
    rating INTEGER CHECK (rating BETWEEN 1 AND 5),
    feedback_text TEXT,
    feedback_category TEXT,  -- 'bug', 'feature_request', 'positive', 'negative', 'suggestion'
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_feedback_user ON user_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_feature ON user_feedback(feature_type);
CREATE INDEX IF NOT EXISTS idx_feedback_created ON user_feedback(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_feedback_rating ON user_feedback(rating);

-- RLS policies
ALTER TABLE user_feedback ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can insert their own feedback"
ON user_feedback FOR INSERT
WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can view their own feedback"
ON user_feedback FOR SELECT
USING (auth.uid() = user_id);

-- Admin access (optional - create admin role if needed)
-- CREATE POLICY "Admins can view all feedback"
-- ON user_feedback FOR SELECT
-- USING (auth.jwt()->>'role' = 'admin');
