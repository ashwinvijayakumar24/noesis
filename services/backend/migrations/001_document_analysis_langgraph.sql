-- Migration: Document Analysis LangGraph Tables
-- Description: Add structured tables for document analysis results (claims, methods, findings)
-- Author: Claude Code
-- Date: 2026-01-03

-- =====================================================
-- 1. Document Claims Table
-- =====================================================
-- Stores extracted claims from research papers for precise citation matching

CREATE TABLE IF NOT EXISTS document_claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Claim content
    claim_text TEXT NOT NULL,
    claim_type VARCHAR(50) NOT NULL CHECK (claim_type IN ('empirical', 'theoretical', 'methodological', 'comparative', 'causal')),

    -- Context
    section_title VARCHAR(255),
    section_type VARCHAR(50), -- intro, methods, results, discussion, conclusion
    page_number INTEGER,

    -- Metadata
    importance_score DECIMAL(3,2) CHECK (importance_score BETWEEN 0 AND 1), -- 0.0 to 1.0
    confidence_score DECIMAL(3,2) CHECK (confidence_score BETWEEN 0 AND 1), -- AI extraction confidence
    supports_primary_thesis BOOLEAN DEFAULT false,

    -- Vector embedding for similarity search
    embedding vector(1536), -- Same dimension as RAG chunks for consistency

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Indexes
    CONSTRAINT unique_claim_per_document UNIQUE (document_id, claim_text)
);

-- Indexes for document_claims
CREATE INDEX idx_document_claims_document_id ON document_claims(document_id);
CREATE INDEX idx_document_claims_project_id ON document_claims(project_id);
CREATE INDEX idx_document_claims_type ON document_claims(claim_type);
CREATE INDEX idx_document_claims_importance ON document_claims(importance_score DESC);

-- Vector similarity index for claim matching
CREATE INDEX idx_document_claims_embedding ON document_claims
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

COMMENT ON TABLE document_claims IS 'Extracted claims from research papers for citation matching and cross-paper analysis';
COMMENT ON COLUMN document_claims.claim_type IS 'empirical: data-driven finding, theoretical: conceptual contribution, methodological: approach/technique, comparative: comparison with prior work, causal: cause-effect relationship';
COMMENT ON COLUMN document_claims.importance_score IS 'How central this claim is to the paper (0.0 = minor detail, 1.0 = primary contribution)';
COMMENT ON COLUMN document_claims.confidence_score IS 'AI extraction confidence (0.0 = uncertain, 1.0 = very confident)';


-- =====================================================
-- 2. Document Methods Table
-- =====================================================
-- Stores methodology details for research reproducibility and comparison

CREATE TABLE IF NOT EXISTS document_methods (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Method identification
    method_name VARCHAR(255) NOT NULL, -- e.g., "BERT fine-tuning", "Random Forest", "Survey methodology"
    method_type VARCHAR(50), -- algorithm, experimental_design, data_collection, statistical_analysis

    -- Details
    description TEXT,
    parameters JSONB, -- e.g., {"learning_rate": 0.001, "batch_size": 32, "epochs": 10}

    -- Context
    section_title VARCHAR(255),
    page_number INTEGER,

    -- Associated data
    datasets_used TEXT[], -- Array of dataset names
    evaluation_metrics TEXT[], -- Array of metrics (e.g., ["accuracy", "F1-score", "BLEU"])

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for document_methods
CREATE INDEX idx_document_methods_document_id ON document_methods(document_id);
CREATE INDEX idx_document_methods_project_id ON document_methods(project_id);
CREATE INDEX idx_document_methods_name ON document_methods(method_name);
CREATE INDEX idx_document_methods_type ON document_methods(method_type);
CREATE INDEX idx_document_methods_datasets ON document_methods USING GIN(datasets_used);

COMMENT ON TABLE document_methods IS 'Methodology extraction for reproducibility and cross-paper comparison';
COMMENT ON COLUMN document_methods.parameters IS 'Hyperparameters, settings, or configuration details in JSON format';


-- =====================================================
-- 3. Document Findings Table
-- =====================================================
-- Stores quantitative results and key findings with metrics

CREATE TABLE IF NOT EXISTS document_findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

    -- Finding content
    finding_text TEXT NOT NULL,
    finding_type VARCHAR(50), -- performance_metric, statistical_result, qualitative_insight, limitation

    -- Quantitative data
    metrics JSONB, -- e.g., {"accuracy": 0.92, "F1": 0.89, "p_value": 0.001}
    comparison_baseline VARCHAR(255), -- What this result is compared against
    improvement_over_baseline VARCHAR(100), -- e.g., "+5% accuracy", "2x faster"

    -- Context
    section_title VARCHAR(255),
    page_number INTEGER,
    table_or_figure_reference VARCHAR(100), -- e.g., "Table 3", "Figure 5"

    -- Metadata
    statistical_significance BOOLEAN,
    confidence_score DECIMAL(3,2) CHECK (confidence_score BETWEEN 0 AND 1),

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for document_findings
CREATE INDEX idx_document_findings_document_id ON document_findings(document_id);
CREATE INDEX idx_document_findings_project_id ON document_findings(project_id);
CREATE INDEX idx_document_findings_type ON document_findings(finding_type);
CREATE INDEX idx_document_findings_metrics ON document_findings USING GIN(metrics);

COMMENT ON TABLE document_findings IS 'Extracted quantitative results and key findings with metrics for comparison';
COMMENT ON COLUMN document_findings.metrics IS 'Performance numbers, statistics, or measurements in JSON format';
COMMENT ON COLUMN document_findings.statistical_significance IS 'Whether the result is statistically significant (if applicable)';


-- =====================================================
-- 4. Update existing documents table
-- =====================================================
-- Add analysis_version to track LangGraph vs legacy analysis

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS analysis_version VARCHAR(20) DEFAULT 'v1_legacy';

COMMENT ON COLUMN documents.analysis_version IS 'Version of analysis: v1_legacy (simple GPT-4o), v2_langgraph (structured workflow)';


-- =====================================================
-- 5. Create views for common queries
-- =====================================================

-- View: Document Analysis Summary
CREATE OR REPLACE VIEW document_analysis_summary AS
SELECT
    d.id as document_id,
    d.title,
    d.status,
    d.analysis_version,
    COUNT(DISTINCT dc.id) as claim_count,
    COUNT(DISTINCT dm.id) as method_count,
    COUNT(DISTINCT df.id) as finding_count,
    MAX(dc.updated_at) as last_analysis_update
FROM documents d
LEFT JOIN document_claims dc ON d.id = dc.document_id
LEFT JOIN document_methods dm ON d.id = dm.document_id
LEFT JOIN document_findings df ON d.id = df.document_id
GROUP BY d.id, d.title, d.status, d.analysis_version;

COMMENT ON VIEW document_analysis_summary IS 'Quick overview of document analysis completeness';


-- =====================================================
-- 6. Helper Functions
-- =====================================================

-- Function: Find similar claims across documents
CREATE OR REPLACE FUNCTION find_similar_claims(
    query_embedding vector(1536),
    similarity_threshold DECIMAL DEFAULT 0.7,
    max_results INTEGER DEFAULT 10,
    exclude_document_id UUID DEFAULT NULL
)
RETURNS TABLE (
    claim_id UUID,
    document_id UUID,
    claim_text TEXT,
    similarity_score DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        dc.id,
        dc.document_id,
        dc.claim_text,
        ROUND((1 - (dc.embedding <=> query_embedding))::NUMERIC, 3) as similarity
    FROM document_claims dc
    WHERE (exclude_document_id IS NULL OR dc.document_id != exclude_document_id)
        AND (1 - (dc.embedding <=> query_embedding)) >= similarity_threshold
    ORDER BY dc.embedding <=> query_embedding ASC
    LIMIT max_results;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION find_similar_claims IS 'Find claims similar to a query embedding using cosine similarity';


-- =====================================================
-- 7. Triggers
-- =====================================================

-- Auto-update timestamps
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_document_claims_updated_at
    BEFORE UPDATE ON document_claims
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_document_methods_updated_at
    BEFORE UPDATE ON document_methods
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_document_findings_updated_at
    BEFORE UPDATE ON document_findings
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- =====================================================
-- Migration Complete
-- =====================================================

-- Verify tables exist
DO $$
BEGIN
    ASSERT (SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name IN ('document_claims', 'document_methods', 'document_findings')) = 3,
           'Migration failed: Not all tables created';

    RAISE NOTICE 'Migration 001_document_analysis_langgraph.sql completed successfully';
    RAISE NOTICE 'Created tables: document_claims, document_methods, document_findings';
    RAISE NOTICE 'Created view: document_analysis_summary';
    RAISE NOTICE 'Created function: find_similar_claims()';
END $$;
