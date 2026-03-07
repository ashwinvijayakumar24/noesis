-- Migration: Improve Draft Analysis Quality (Week 1 Priority)
-- Date: 2026-02-27
-- Description: Add enhanced claim categorization and reviewer feedback fields

-- ============================================
-- 1. Enhance draft_claims table
-- ============================================

-- Add enhanced claim categorization fields
ALTER TABLE draft_claims
ADD COLUMN IF NOT EXISTS claim_subtype TEXT,
ADD COLUMN IF NOT EXISTS claim_level TEXT,
ADD COLUMN IF NOT EXISTS evidence_type TEXT,
ADD COLUMN IF NOT EXISTS confidence_level TEXT;

-- Drop existing check constraint if it exists
ALTER TABLE draft_claims
DROP CONSTRAINT IF EXISTS draft_claims_citation_strength_check;

-- Add citation strength analysis fields
ALTER TABLE draft_claims
ADD COLUMN IF NOT EXISTS citation_strength TEXT,
ADD COLUMN IF NOT EXISTS max_similarity FLOAT DEFAULT 0.0,
ADD COLUMN IF NOT EXISTS unsupported BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS supporting_literature JSONB DEFAULT '[]'::jsonb;

-- Add updated check constraint with all valid values
ALTER TABLE draft_claims
ADD CONSTRAINT draft_claims_citation_strength_check
CHECK (citation_strength IS NULL OR citation_strength IN ('strong', 'moderate', 'weak', 'missing', 'original_contribution'));

-- Add comments for new fields
COMMENT ON COLUMN draft_claims.claim_subtype IS 'Secondary classification: factual, causal, comparative, normative, descriptive';
COMMENT ON COLUMN draft_claims.claim_level IS 'Hierarchy: thesis, main, supporting, contextual';
COMMENT ON COLUMN draft_claims.evidence_type IS 'experimental, observational, theoretical, computational, qualitative, mixed';
COMMENT ON COLUMN draft_claims.confidence_level IS 'Author certainty: definitive, tentative, exploratory, speculative';
COMMENT ON COLUMN draft_claims.citation_strength IS 'strong, moderate, weak, missing, original_contribution';
COMMENT ON COLUMN draft_claims.max_similarity IS 'Maximum semantic similarity to project literature (0.0-1.0)';
COMMENT ON COLUMN draft_claims.unsupported IS 'Flag for claims lacking adequate citation support';
COMMENT ON COLUMN draft_claims.supporting_literature IS 'Top 5 most similar literature chunks with similarity scores';

-- Create index on unsupported claims for quick filtering
CREATE INDEX IF NOT EXISTS idx_draft_claims_unsupported ON draft_claims(draft_id, unsupported) WHERE unsupported = TRUE;

-- Create index on citation strength for analytics
CREATE INDEX IF NOT EXISTS idx_draft_claims_citation_strength ON draft_claims(draft_id, citation_strength);

-- ============================================
-- 2. Enhance reviewer_feedback table
-- ============================================

-- Add enhanced feedback fields
ALTER TABLE reviewer_feedback
ADD COLUMN IF NOT EXISTS line_reference TEXT,
ADD COLUMN IF NOT EXISTS specific_issue TEXT,
ADD COLUMN IF NOT EXISTS example_fix TEXT,
ADD COLUMN IF NOT EXISTS reasoning TEXT;

-- Add comments for new fields
COMMENT ON COLUMN reviewer_feedback.line_reference IS 'Specific line number or paragraph location (e.g., "Line 45-47", "Paragraph 3")';
COMMENT ON COLUMN reviewer_feedback.specific_issue IS 'The exact problem identified (e.g., "Unsupported claim", "Missing citation")';
COMMENT ON COLUMN reviewer_feedback.example_fix IS 'Brief directional example of how to address this (NOT a rewrite)';
COMMENT ON COLUMN reviewer_feedback.reasoning IS 'Why this matters for peer review acceptance';

-- Create index on severity for prioritization
CREATE INDEX IF NOT EXISTS idx_reviewer_feedback_severity ON reviewer_feedback(draft_id, severity);

-- ============================================
-- 3. Create view for unsupported claims analytics
-- ============================================

CREATE OR REPLACE VIEW v_unsupported_claims_summary AS
SELECT
    d.id AS draft_id,
    d.title AS draft_title,
    d.project_id,
    COUNT(*) FILTER (WHERE dc.unsupported = TRUE) AS unsupported_claims_count,
    COUNT(*) AS total_claims_count,
    ROUND(
        (COUNT(*) FILTER (WHERE dc.unsupported = TRUE)::NUMERIC / NULLIF(COUNT(*), 0) * 100)::NUMERIC,
        2
    ) AS unsupported_percentage,
    COUNT(*) FILTER (WHERE dc.citation_strength = 'missing') AS missing_citations,
    COUNT(*) FILTER (WHERE dc.citation_strength = 'weak') AS weak_citations,
    COUNT(*) FILTER (WHERE dc.citation_strength = 'moderate') AS moderate_citations,
    COUNT(*) FILTER (WHERE dc.citation_strength = 'strong') AS strong_citations
FROM drafts d
LEFT JOIN draft_claims dc ON d.id = dc.draft_id
GROUP BY d.id, d.title, d.project_id;

COMMENT ON VIEW v_unsupported_claims_summary IS 'Summary of unsupported claims by draft for analytics dashboard';

-- ============================================
-- 4. Create view for critical feedback summary
-- ============================================

CREATE OR REPLACE VIEW v_critical_feedback_summary AS
SELECT
    d.id AS draft_id,
    d.title AS draft_title,
    d.project_id,
    COUNT(*) FILTER (WHERE rf.severity = 'critical') AS critical_count,
    COUNT(*) FILTER (WHERE rf.severity = 'major') AS major_count,
    COUNT(*) FILTER (WHERE rf.severity = 'minor') AS minor_count,
    COUNT(*) FILTER (WHERE rf.severity = 'suggestion') AS suggestion_count,
    COUNT(*) AS total_feedback_count,
    json_agg(
        json_build_object(
            'type', rf.feedback_type,
            'severity', rf.severity,
            'specific_issue', rf.specific_issue,
            'section', rf.section_reference
        ) ORDER BY
            CASE rf.severity
                WHEN 'critical' THEN 1
                WHEN 'major' THEN 2
                WHEN 'minor' THEN 3
                WHEN 'suggestion' THEN 4
            END
    ) FILTER (WHERE rf.severity IN ('critical', 'major')) AS priority_issues
FROM drafts d
LEFT JOIN reviewer_feedback rf ON d.id = rf.draft_id
GROUP BY d.id, d.title, d.project_id;

COMMENT ON VIEW v_critical_feedback_summary IS 'Summary of critical and major feedback by draft';

-- ============================================
-- 5. Update existing data (set defaults for new fields)
-- ============================================

-- Set default values for existing claims
UPDATE draft_claims
SET
    citation_strength = CASE
        WHEN requires_citation = FALSE THEN 'original_contribution'
        WHEN existing_citations IS NULL OR array_length(existing_citations, 1) IS NULL OR array_length(existing_citations, 1) = 0 THEN 'missing'
        WHEN array_length(existing_citations, 1) = 1 THEN 'weak'
        WHEN array_length(existing_citations, 1) >= 2 THEN 'moderate'
        ELSE 'missing'
    END,
    unsupported = CASE
        WHEN requires_citation = TRUE AND (existing_citations IS NULL OR array_length(existing_citations, 1) IS NULL OR array_length(existing_citations, 1) = 0) AND importance_score > 0.5 THEN TRUE
        ELSE FALSE
    END
WHERE citation_strength IS NULL;

-- ============================================
-- End of Migration
-- ============================================
