-- Create analytics_events table for tracking user actions
CREATE TABLE IF NOT EXISTS public.analytics_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    event_name VARCHAR(255) NOT NULL,
    event_properties JSONB,
    user_agent TEXT,
    ip_address INET,
    session_id VARCHAR(255),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Add indexes for common queries
CREATE INDEX IF NOT EXISTS idx_analytics_events_user_id ON public.analytics_events(user_id);
CREATE INDEX IF NOT EXISTS idx_analytics_events_event_name ON public.analytics_events(event_name);
CREATE INDEX IF NOT EXISTS idx_analytics_events_created_at ON public.analytics_events(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analytics_events_session_id ON public.analytics_events(session_id);

-- Add GIN index for querying event properties
CREATE INDEX IF NOT EXISTS idx_analytics_events_properties ON public.analytics_events USING GIN(event_properties);

-- Enable Row Level Security
ALTER TABLE public.analytics_events ENABLE ROW LEVEL SECURITY;

-- Policy: Users can only insert their own analytics events
CREATE POLICY "Users can insert their own analytics events"
    ON public.analytics_events
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Policy: Users can view their own analytics events
CREATE POLICY "Users can view their own analytics events"
    ON public.analytics_events
    FOR SELECT
    USING (auth.uid() = user_id);

-- Policy: Service role can view all analytics (for admin dashboards)
CREATE POLICY "Service role can view all analytics"
    ON public.analytics_events
    FOR SELECT
    USING (auth.jwt() ->> 'role' = 'service_role');

-- Add comment for documentation
COMMENT ON TABLE public.analytics_events IS 'Stores user analytics events for tracking feature usage, engagement, and product metrics';
COMMENT ON COLUMN public.analytics_events.event_name IS 'Name of the event (e.g., sign_up, project_created, document_uploaded)';
COMMENT ON COLUMN public.analytics_events.event_properties IS 'Additional event data stored as JSON (e.g., project_id, document_id, etc.)';
COMMENT ON COLUMN public.analytics_events.user_agent IS 'Browser user agent string for device/browser tracking';
COMMENT ON COLUMN public.analytics_events.ip_address IS 'IP address for geographic analytics (optional, privacy-sensitive)';
COMMENT ON COLUMN public.analytics_events.session_id IS 'Session identifier for tracking user sessions';
