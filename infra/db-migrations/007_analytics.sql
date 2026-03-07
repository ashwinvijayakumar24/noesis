-- ================================
-- Migration 007: Analytics Functions
-- Purpose: Calculate key metrics (MAU, DAU, retention, etc.)
-- ================================

-- Function to calculate Monthly Active Users
CREATE OR REPLACE FUNCTION get_monthly_active_users(months_back INTEGER DEFAULT 0)
RETURNS TABLE(month_date DATE, mau_count BIGINT) AS $$
BEGIN
    RETURN QUERY
    SELECT
        DATE_TRUNC('month', created_at)::DATE as month_date,
        COUNT(DISTINCT user_id) as mau_count
    FROM analytics_events
    WHERE created_at >= (NOW() - (months_back || ' months')::INTERVAL)
    GROUP BY DATE_TRUNC('month', created_at)
    ORDER BY month_date DESC;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate Daily Active Users
CREATE OR REPLACE FUNCTION get_daily_active_users(days_back INTEGER DEFAULT 30)
RETURNS TABLE(day_date DATE, dau_count BIGINT) AS $$
BEGIN
    RETURN QUERY
    SELECT
        DATE_TRUNC('day', created_at)::DATE as day_date,
        COUNT(DISTINCT user_id) as dau_count
    FROM analytics_events
    WHERE created_at >= (NOW() - (days_back || ' days')::INTERVAL)
    GROUP BY DATE_TRUNC('day', created_at)
    ORDER BY day_date DESC;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate activation rate
CREATE OR REPLACE FUNCTION get_activation_rate()
RETURNS TABLE(
    total_signups BIGINT,
    activated_users BIGINT,
    activation_rate NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(DISTINCT u.id)::BIGINT as total_signups,
        COUNT(DISTINCT CASE
            WHEN EXISTS (
                SELECT 1 FROM documents d WHERE d.user_id = u.id
            ) AND EXISTS (
                SELECT 1 FROM drafts dr WHERE dr.user_id = u.id
            ) THEN u.id
        END)::BIGINT as activated_users,
        ROUND(
            CAST(COUNT(DISTINCT CASE
                WHEN EXISTS (
                    SELECT 1 FROM documents d WHERE d.user_id = u.id
                ) AND EXISTS (
                    SELECT 1 FROM drafts dr WHERE dr.user_id = u.id
                ) THEN u.id
            END) AS NUMERIC) /
            NULLIF(COUNT(DISTINCT u.id), 0) * 100,
            2
        ) as activation_rate
    FROM auth.users u
    WHERE u.created_at >= NOW() - INTERVAL '30 days';
END;
$$ LANGUAGE plpgsql;

-- Function to get power users (3+ drafts analyzed)
CREATE OR REPLACE FUNCTION get_power_users(min_drafts INTEGER DEFAULT 3)
RETURNS TABLE(
    user_id UUID,
    user_email TEXT,
    drafts_analyzed BIGINT,
    papers_uploaded BIGINT,
    last_active TIMESTAMP WITH TIME ZONE
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        u.id as user_id,
        u.email as user_email,
        COUNT(DISTINCT d.id)::BIGINT as drafts_analyzed,
        COUNT(DISTINCT doc.id)::BIGINT as papers_uploaded,
        MAX(ae.created_at) as last_active
    FROM auth.users u
    LEFT JOIN drafts d ON d.user_id = u.id
    LEFT JOIN documents doc ON doc.user_id = u.id
    LEFT JOIN analytics_events ae ON ae.user_id = u.id
    GROUP BY u.id, u.email
    HAVING COUNT(DISTINCT d.id) >= min_drafts
    ORDER BY drafts_analyzed DESC;
END;
$$ LANGUAGE plpgsql;

-- Function to calculate 7-day retention
CREATE OR REPLACE FUNCTION get_retention_rate(days INTEGER DEFAULT 7)
RETURNS TABLE(
    cohort_date DATE,
    cohort_size BIGINT,
    retained_users BIGINT,
    retention_rate NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    WITH cohorts AS (
        SELECT
            DATE_TRUNC('day', created_at)::DATE as signup_date,
            id as user_id
        FROM auth.users
        WHERE created_at >= NOW() - INTERVAL '30 days'
    ),
    retained AS (
        SELECT
            c.signup_date,
            c.user_id,
            EXISTS(
                SELECT 1 FROM analytics_events ae
                WHERE ae.user_id = c.user_id
                AND ae.created_at BETWEEN c.signup_date + (days || ' days')::INTERVAL
                                      AND c.signup_date + ((days + 1) || ' days')::INTERVAL
            ) as is_retained
        FROM cohorts c
    )
    SELECT
        signup_date as cohort_date,
        COUNT(*)::BIGINT as cohort_size,
        COUNT(*) FILTER (WHERE is_retained)::BIGINT as retained_users,
        ROUND(
            CAST(COUNT(*) FILTER (WHERE is_retained) AS NUMERIC) /
            NULLIF(COUNT(*), 0) * 100,
            2
        ) as retention_rate
    FROM retained
    WHERE signup_date <= NOW() - (days || ' days')::INTERVAL
    GROUP BY signup_date
    ORDER BY signup_date DESC;
END;
$$ LANGUAGE plpgsql;

-- Function to get feature usage stats
CREATE OR REPLACE FUNCTION get_feature_usage_stats()
RETURNS TABLE(
    feature_name TEXT,
    usage_count BIGINT,
    unique_users BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        event_type as feature_name,
        COUNT(*)::BIGINT as usage_count,
        COUNT(DISTINCT user_id)::BIGINT as unique_users
    FROM analytics_events
    WHERE created_at >= NOW() - INTERVAL '30 days'
    GROUP BY event_type
    ORDER BY usage_count DESC;
END;
$$ LANGUAGE plpgsql;

-- View for quick analytics dashboard
CREATE OR REPLACE VIEW analytics_dashboard AS
SELECT
    (SELECT COUNT(DISTINCT user_id) FROM analytics_events WHERE created_at >= NOW() - INTERVAL '30 days') as mau,
    (SELECT COUNT(DISTINCT user_id) FROM analytics_events WHERE created_at >= NOW() - INTERVAL '1 day') as dau,
    (SELECT COUNT(*) FROM auth.users WHERE created_at >= NOW() - INTERVAL '30 days') as new_signups_30d,
    (SELECT COUNT(*) FROM drafts WHERE status = 'completed' AND created_at >= NOW() - INTERVAL '30 days') as drafts_analyzed_30d,
    (SELECT COUNT(*) FROM documents WHERE status = 'completed' AND created_at >= NOW() - INTERVAL '30 days') as papers_uploaded_30d,
    (SELECT COUNT(*) FROM subscriptions WHERE plan_tier != 'free') as paying_users,
    NOW() as last_updated;
