-- Migration 006: Draft-Aware Research Intelligence Schema
-- Creates tables for draft analysis features
-- Date: 2025-01-25

-- Enable pgvector extension if not already enabled
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================
-- Core Drafts Table
-- ============================================
CREATE TABLE IF NOT EXISTS public.drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    version INTEGER DEFAULT 1,
    file_url TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('pdf', 'docx', 'txt')),
    status TEXT DEFAULT 'uploaded' CHECK (status IN ('uploaded', 'processing', 'analyzed', 'failed')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    analyzed_at TIMESTAMPTZ
);

-- Indexes for drafts table
CREATE INDEX IF NOT EXISTS idx_drafts_project_id ON public.drafts(project_id);
CREATE INDEX IF NOT EXISTS idx_drafts_user_id ON public.drafts(user_id);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON public.drafts(status);

-- ============================================
-- Draft Claims Table
-- ============================================
CREATE TABLE IF NOT EXISTS public.draft_claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    claim_text TEXT NOT NULL,
    claim_type TEXT NOT NULL CHECK (claim_type IN ('empirical', 'theoretical', 'methodological')),
    section_location TEXT,
    importance_score REAL CHECK (importance_score >= 0 AND importance_score <= 1),
    requires_citation BOOLEAN DEFAULT TRUE,
    existing_citations TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for draft_claims table
CREATE INDEX IF NOT EXISTS idx_draft_claims_draft_id ON public.draft_claims(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_claims_importance ON public.draft_claims(importance_score DESC);

-- ============================================
-- Draft Coverage Gaps Table
-- ============================================
CREATE TABLE IF NOT EXISTS public.draft_coverage_gaps (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    gap_type TEXT NOT NULL,
    description TEXT NOT NULL,
    priority TEXT NOT NULL CHECK (priority IN ('high', 'medium', 'low')),
    suggested_papers JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for draft_coverage_gaps table
CREATE INDEX IF NOT EXISTS idx_draft_gaps_draft_id ON public.draft_coverage_gaps(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_gaps_priority ON public.draft_coverage_gaps(priority);

-- ============================================
-- Draft Feedback Table
-- ============================================
CREATE TABLE IF NOT EXISTS public.draft_feedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    feedback_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('critical', 'major', 'minor', 'suggestion')),
    feedback_text TEXT NOT NULL,
    suggested_improvements TEXT[],
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for draft_feedback table
CREATE INDEX IF NOT EXISTS idx_draft_feedback_draft_id ON public.draft_feedback(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_feedback_severity ON public.draft_feedback(severity);

-- ============================================
-- Draft Chunks Table (for RAG)
-- ============================================
CREATE TABLE IF NOT EXISTS public.draft_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES public.projects(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    section_name TEXT,
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for draft_chunks table
CREATE INDEX IF NOT EXISTS idx_draft_chunks_draft_id ON public.draft_chunks(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_chunks_project_id ON public.draft_chunks(project_id);
CREATE INDEX IF NOT EXISTS idx_draft_chunks_embedding ON public.draft_chunks USING hnsw (embedding vector_cosine_ops);

-- ============================================
-- Draft Structure Table
-- ============================================
CREATE TABLE IF NOT EXISTS public.draft_structure (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL REFERENCES public.drafts(id) ON DELETE CASCADE,
    section_title TEXT NOT NULL,
    section_type TEXT,
    section_order INTEGER NOT NULL,
    start_position INTEGER,
    end_position INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for draft_structure table
CREATE INDEX IF NOT EXISTS idx_draft_structure_draft_id ON public.draft_structure(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_structure_order ON public.draft_structure(section_order);

-- ============================================
-- Row Level Security (RLS) Policies
-- ============================================

-- Enable RLS on all draft tables
ALTER TABLE public.drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.draft_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.draft_coverage_gaps ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.draft_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.draft_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.draft_structure ENABLE ROW LEVEL SECURITY;

-- Drafts table policies
CREATE POLICY "Users can view their own drafts"
    ON public.drafts FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own drafts"
    ON public.drafts FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own drafts"
    ON public.drafts FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own drafts"
    ON public.drafts FOR DELETE
    USING (auth.uid() = user_id);

-- Draft claims policies (inherit from drafts)
CREATE POLICY "Users can view claims for their drafts"
    ON public.draft_claims FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.drafts
            WHERE drafts.id = draft_claims.draft_id
            AND drafts.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert claims for their drafts"
    ON public.draft_claims FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.drafts
            WHERE drafts.id = draft_claims.draft_id
            AND drafts.user_id = auth.uid()
        )
    );

-- Draft coverage gaps policies
CREATE POLICY "Users can view gaps for their drafts"
    ON public.draft_coverage_gaps FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.drafts
            WHERE drafts.id = draft_coverage_gaps.draft_id
            AND drafts.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert gaps for their drafts"
    ON public.draft_coverage_gaps FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.drafts
            WHERE drafts.id = draft_coverage_gaps.draft_id
            AND drafts.user_id = auth.uid()
        )
    );

-- Draft feedback policies
CREATE POLICY "Users can view feedback for their drafts"
    ON public.draft_feedback FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.drafts
            WHERE drafts.id = draft_feedback.draft_id
            AND drafts.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert feedback for their drafts"
    ON public.draft_feedback FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.drafts
            WHERE drafts.id = draft_feedback.draft_id
            AND drafts.user_id = auth.uid()
        )
    );

-- Draft chunks policies
CREATE POLICY "Users can view chunks for their drafts"
    ON public.draft_chunks FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.drafts
            WHERE drafts.id = draft_chunks.draft_id
            AND drafts.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert chunks for their drafts"
    ON public.draft_chunks FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.drafts
            WHERE drafts.id = draft_chunks.draft_id
            AND drafts.user_id = auth.uid()
        )
    );

-- Draft structure policies
CREATE POLICY "Users can view structure for their drafts"
    ON public.draft_structure FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM public.drafts
            WHERE drafts.id = draft_structure.draft_id
            AND drafts.user_id = auth.uid()
        )
    );

CREATE POLICY "Users can insert structure for their drafts"
    ON public.draft_structure FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM public.drafts
            WHERE drafts.id = draft_structure.draft_id
            AND drafts.user_id = auth.uid()
        )
    );

-- ============================================
-- Helper Functions
-- ============================================

-- Function to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger to auto-update updated_at on drafts
DROP TRIGGER IF EXISTS update_drafts_updated_at ON public.drafts;
CREATE TRIGGER update_drafts_updated_at
    BEFORE UPDATE ON public.drafts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Function to search project content (drafts + literature)
CREATE OR REPLACE FUNCTION match_project_content(
    query_embedding vector(1536),
    filter_project_id uuid,
    match_threshold float DEFAULT 0.7,
    match_count int DEFAULT 5,
    include_drafts boolean DEFAULT true,
    filter_draft_id uuid DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    content text,
    similarity float,
    source_type text,
    source_id uuid,
    source_title text,
    metadata jsonb
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT * FROM (
        -- Search literature chunks
        SELECT
            c.id,
            c.chunk_text as content,
            1 - (c.embedding <=> query_embedding) as similarity,
            'literature'::text as source_type,
            d.id as source_id,
            d.title as source_title,
            jsonb_build_object(
                'chunk_index', c.chunk_index,
                'document_id', d.id
            ) as metadata
        FROM chunks c
        JOIN documents d ON c.document_id = d.id
        WHERE d.project_id = filter_project_id
            AND 1 - (c.embedding <=> query_embedding) > match_threshold

        UNION ALL

        -- Search draft chunks (if enabled)
        SELECT
            dc.id,
            dc.chunk_text as content,
            1 - (dc.embedding <=> query_embedding) as similarity,
            'draft'::text as source_type,
            dr.id as source_id,
            dr.title as source_title,
            jsonb_build_object(
                'chunk_index', dc.chunk_index,
                'draft_id', dr.id,
                'section_name', dc.section_name
            ) as metadata
        FROM draft_chunks dc
        JOIN drafts dr ON dc.draft_id = dr.id
        WHERE include_drafts = true
            AND dr.project_id = filter_project_id
            AND (filter_draft_id IS NULL OR dr.id = filter_draft_id)
            AND 1 - (dc.embedding <=> query_embedding) > match_threshold
    ) combined_results
    ORDER BY similarity DESC
    LIMIT match_count;
END;
$$;

-- ============================================
-- Migration Complete
-- ============================================
-- All draft-related tables, indexes, RLS policies, and functions created
