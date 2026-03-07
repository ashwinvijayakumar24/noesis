-- ================================
-- Migration 005: Testimonials and Social Proof
-- Purpose: Store user testimonials for marketing
-- ================================

CREATE TABLE IF NOT EXISTS testimonials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    testimonial_text TEXT NOT NULL,
    user_name TEXT NOT NULL,
    user_title TEXT,  -- "PhD Student at MIT", "Postdoc at Stanford"
    user_photo_url TEXT,
    user_university TEXT,
    featured BOOLEAN DEFAULT false,
    approved BOOLEAN DEFAULT false,
    display_order INTEGER DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_testimonials_featured ON testimonials(featured, approved);
CREATE INDEX IF NOT EXISTS idx_testimonials_display ON testimonials(display_order);

-- RLS policies
ALTER TABLE testimonials ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Anyone can view approved testimonials"
ON testimonials FOR SELECT
USING (approved = true);

CREATE POLICY "Users can insert their own testimonials"
ON testimonials FOR INSERT
WITH CHECK (auth.uid() = user_id);

-- Table for platform statistics (for landing page)
CREATE TABLE IF NOT EXISTS platform_stats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    stat_name TEXT UNIQUE NOT NULL,
    stat_value INTEGER NOT NULL,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Insert initial stats
INSERT INTO platform_stats (stat_name, stat_value) VALUES
('total_researchers', 0),
('drafts_analyzed', 0),
('universities_count', 0),
('papers_processed', 0)
ON CONFLICT (stat_name) DO NOTHING;

-- Function to update platform stats
CREATE OR REPLACE FUNCTION update_platform_stats()
RETURNS void AS $$
BEGIN
    -- Update total researchers
    UPDATE platform_stats
    SET stat_value = (SELECT COUNT(*) FROM auth.users),
        last_updated = NOW()
    WHERE stat_name = 'total_researchers';

    -- Update drafts analyzed
    UPDATE platform_stats
    SET stat_value = (SELECT COUNT(*) FROM drafts WHERE status = 'completed'),
        last_updated = NOW()
    WHERE stat_name = 'drafts_analyzed';

    -- Update papers processed
    UPDATE platform_stats
    SET stat_value = (SELECT COUNT(*) FROM documents WHERE status = 'completed'),
        last_updated = NOW()
    WHERE stat_name = 'papers_processed';

    -- Update universities count (estimate from email domains)
    UPDATE platform_stats
    SET stat_value = (
        SELECT COUNT(DISTINCT SUBSTRING(email FROM '@(.*)$'))
        FROM auth.users
        WHERE email LIKE '%@%.edu' OR email LIKE '%@%.ac.%'
    ),
    last_updated = NOW()
    WHERE stat_name = 'universities_count';
END;
$$ LANGUAGE plpgsql;
