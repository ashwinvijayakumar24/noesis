-- ============================================
-- CREATE DRAFT-AWARE RESEARCH INTELLIGENCE TABLES
-- ============================================
-- This migration creates the database schema for the draft analysis system
-- Transforms Noesis from literature review generator to draft-aware research intelligence platform
--
-- Features:
-- - Draft ingestion and version management
-- - Claim identification and categorization
-- - Coverage gap detection
-- - Reviewer-style feedback
-- - Integration with existing RAG system

-- ============================================
-- 1. DRAFTS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS drafts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  version INTEGER DEFAULT 1,
  file_url TEXT NOT NULL,
  file_type TEXT NOT NULL, -- 'pdf', 'docx', 'txt'
  file_size INTEGER,
  status TEXT DEFAULT 'uploaded', -- 'uploaded', 'processing', 'analyzed', 'failed'
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_drafts_user_id ON drafts(user_id);
CREATE INDEX IF NOT EXISTS idx_drafts_project_id ON drafts(project_id);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
CREATE INDEX IF NOT EXISTS idx_drafts_version ON drafts(project_id, version DESC);

COMMENT ON TABLE drafts IS 'User research drafts uploaded for analysis and feedback';
COMMENT ON COLUMN drafts.version IS 'Draft version number, increments with each upload of new version';
COMMENT ON COLUMN drafts.status IS 'Processing status: uploaded -> processing -> analyzed (or failed)';

-- ============================================
-- 2. DRAFT_ANALYSIS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS draft_analysis (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  draft_id UUID REFERENCES drafts(id) ON DELETE CASCADE,
  structure JSONB NOT NULL, -- Document structure: sections, paragraphs, metadata
  word_count INTEGER,
  analysis_metadata JSONB, -- Processing info, timestamps, model used
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_draft_analysis_draft_id ON draft_analysis(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_analysis_structure ON draft_analysis USING gin (structure);

COMMENT ON TABLE draft_analysis IS 'Structural analysis of research drafts including sections, word count, and metadata';
COMMENT ON COLUMN draft_analysis.structure IS 'Document structure: sections, headings, paragraphs extracted from draft';
COMMENT ON COLUMN draft_analysis.analysis_metadata IS 'Processing metadata including timestamps, model version, processing time';

-- ============================================
-- 3. DRAFT_CLAIMS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS draft_claims (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  draft_id UUID REFERENCES drafts(id) ON DELETE CASCADE,
  claim_text TEXT NOT NULL,
  claim_type TEXT NOT NULL, -- 'empirical', 'theoretical', 'methodological'
  section_location TEXT, -- Which section the claim appears in
  importance_score FLOAT, -- 0.0 to 1.0
  requires_citation BOOLEAN DEFAULT true,
  existing_citations TEXT[], -- Array of citation strings found in draft
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_draft_claims_draft_id ON draft_claims(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_claims_type ON draft_claims(claim_type);
CREATE INDEX IF NOT EXISTS idx_draft_claims_importance ON draft_claims(importance_score DESC);
CREATE INDEX IF NOT EXISTS idx_draft_claims_requires_citation ON draft_claims(requires_citation) WHERE requires_citation = true;

COMMENT ON TABLE draft_claims IS 'Claims, hypotheses, and assertions extracted from research drafts';
COMMENT ON COLUMN draft_claims.claim_type IS 'Type of claim: empirical (data-based), theoretical (conceptual), methodological (approach-based)';
COMMENT ON COLUMN draft_claims.importance_score IS 'AI-assessed importance score from 0.0 (low) to 1.0 (high)';
COMMENT ON COLUMN draft_claims.requires_citation IS 'Whether this claim needs literature support (false for original contributions)';
COMMENT ON COLUMN draft_claims.existing_citations IS 'Array of citation strings found supporting this claim in the draft';

-- ============================================
-- 4. COVERAGE_GAPS TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS coverage_gaps (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  draft_id UUID REFERENCES drafts(id) ON DELETE CASCADE,
  gap_type TEXT NOT NULL, -- 'missing_seminal', 'methodology_gap', 'theoretical_gap'
  description TEXT NOT NULL,
  priority TEXT NOT NULL, -- 'high', 'medium', 'low'
  suggested_papers JSONB, -- Array of paper recommendations with metadata
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_coverage_gaps_draft_id ON coverage_gaps(draft_id);
CREATE INDEX IF NOT EXISTS idx_coverage_gaps_priority ON coverage_gaps(priority);
CREATE INDEX IF NOT EXISTS idx_coverage_gaps_type ON coverage_gaps(gap_type);

COMMENT ON TABLE coverage_gaps IS 'Identified gaps in literature coverage for research drafts';
COMMENT ON COLUMN coverage_gaps.gap_type IS 'Type of gap: missing_seminal (key papers), methodology_gap (approach), theoretical_gap (framework)';
COMMENT ON COLUMN coverage_gaps.priority IS 'Priority level: high (critical), medium (important), low (optional)';
COMMENT ON COLUMN coverage_gaps.suggested_papers IS 'Recommended papers to address this gap with relevance scores and reasoning';

-- ============================================
-- 5. REVIEWER_FEEDBACK TABLE
-- ============================================
CREATE TABLE IF NOT EXISTS reviewer_feedback (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  draft_id UUID REFERENCES drafts(id) ON DELETE CASCADE,
  feedback_type TEXT NOT NULL, -- 'positioning', 'argumentation', 'coverage', 'methodology'
  feedback_text TEXT NOT NULL,
  severity TEXT NOT NULL, -- 'critical', 'major', 'minor', 'suggestion'
  section_reference TEXT, -- Which part of draft this applies to
  suggested_improvements TEXT[],
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_draft_id ON reviewer_feedback(draft_id);
CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_type ON reviewer_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_severity ON reviewer_feedback(severity);

COMMENT ON TABLE reviewer_feedback IS 'Expert academic reviewer-style feedback for research drafts';
COMMENT ON COLUMN reviewer_feedback.feedback_type IS 'Category: positioning (field placement), argumentation (logic), coverage (literature), methodology (approach)';
COMMENT ON COLUMN reviewer_feedback.severity IS 'Severity: critical (must fix), major (should fix), minor (nice to fix), suggestion (consider)';
COMMENT ON COLUMN reviewer_feedback.section_reference IS 'Specific section or paragraph this feedback applies to';
COMMENT ON COLUMN reviewer_feedback.suggested_improvements IS 'Array of concrete suggestions (without rewriting content)';

-- ============================================
-- 6. DRAFT_CHUNKS TABLE (RAG Integration)
-- ============================================
CREATE TABLE IF NOT EXISTS draft_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  draft_id UUID REFERENCES drafts(id) ON DELETE CASCADE,
  project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL,
  content TEXT NOT NULL,
  embedding VECTOR(1536), -- OpenAI embedding vector (same dimension as document_chunks)
  section_type TEXT, -- 'abstract', 'introduction', 'methods', 'results', 'discussion', 'conclusion'
  metadata JSONB,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for faster queries
CREATE INDEX IF NOT EXISTS idx_draft_chunks_draft_id ON draft_chunks(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_chunks_project_id ON draft_chunks(project_id);
CREATE INDEX IF NOT EXISTS idx_draft_chunks_section_type ON draft_chunks(section_type);

-- Create vector similarity search index using HNSW (same as document_chunks)
CREATE INDEX IF NOT EXISTS idx_draft_chunks_embedding
ON draft_chunks
USING hnsw (embedding vector_cosine_ops);

COMMENT ON TABLE draft_chunks IS 'Text chunks from research drafts with embeddings for integrated RAG search';
COMMENT ON COLUMN draft_chunks.embedding IS 'OpenAI embedding vector (1536 dimensions, compatible with document_chunks)';
COMMENT ON COLUMN draft_chunks.section_type IS 'Academic section type for contextual retrieval';
COMMENT ON COLUMN draft_chunks.metadata IS 'Additional chunk metadata: position, keywords, etc.';

-- ============================================
-- 7. CREATE VECTOR SEARCH FUNCTION FOR DRAFTS
-- ============================================
-- Function to search draft chunks by semantic similarity (mirrors match_document_chunks)
CREATE OR REPLACE FUNCTION match_draft_chunks(
  query_embedding VECTOR(1536),
  p_draft_id UUID,
  match_count INT DEFAULT 5
)
RETURNS TABLE (
  id UUID,
  draft_id UUID,
  content TEXT,
  section_type TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  SELECT
    dc.id,
    dc.draft_id,
    dc.content,
    dc.section_type,
    1 - (dc.embedding <=> query_embedding) AS similarity
  FROM draft_chunks dc
  WHERE dc.draft_id = p_draft_id
  ORDER BY dc.embedding <=> query_embedding
  LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION match_draft_chunks IS 'Search draft chunks by semantic similarity using cosine distance';

-- ============================================
-- 8. CREATE INTEGRATED SEARCH FUNCTION
-- ============================================
-- Function to search both draft and literature chunks for integrated RAG
CREATE OR REPLACE FUNCTION match_project_content(
  query_embedding VECTOR(1536),
  p_project_id UUID,
  match_count INT DEFAULT 10,
  include_drafts BOOLEAN DEFAULT true,
  include_documents BOOLEAN DEFAULT true
)
RETURNS TABLE (
  id UUID,
  content TEXT,
  source_type TEXT, -- 'draft' or 'document'
  source_id UUID,
  section_type TEXT,
  similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
  RETURN QUERY
  WITH draft_results AS (
    SELECT
      dc.id,
      dc.content,
      'draft'::TEXT AS source_type,
      dc.draft_id AS source_id,
      dc.section_type,
      1 - (dc.embedding <=> query_embedding) AS similarity
    FROM draft_chunks dc
    WHERE dc.project_id = p_project_id
      AND include_drafts = true
  ),
  document_results AS (
    SELECT
      dchunk.id,
      dchunk.content,
      'document'::TEXT AS source_type,
      dchunk.document_id AS source_id,
      NULL::TEXT AS section_type,
      1 - (dchunk.embedding <=> query_embedding) AS similarity
    FROM document_chunks dchunk
    WHERE dchunk.project_id = p_project_id
      AND include_documents = true
  ),
  combined_results AS (
    SELECT * FROM draft_results
    UNION ALL
    SELECT * FROM document_results
  )
  SELECT cr.*
  FROM combined_results cr
  ORDER BY cr.similarity DESC
  LIMIT match_count;
END;
$$;

COMMENT ON FUNCTION match_project_content IS 'Search both draft and document chunks for integrated RAG (literature + user draft content)';
