-- ============================================
-- ADD DOCUMENT ANALYSIS SUPPORT
-- ============================================
-- This migration adds structured analysis capabilities to documents
-- Enables storage of AI-generated paper summaries and insights

-- Add analysis column to store structured paper analysis
ALTER TABLE documents
ADD COLUMN IF NOT EXISTS analysis JSONB DEFAULT NULL;

-- Add index for faster queries on documents with analysis
CREATE INDEX IF NOT EXISTS idx_documents_has_analysis
ON documents((analysis IS NOT NULL));

-- Add index for querying within analysis JSON
CREATE INDEX IF NOT EXISTS idx_documents_analysis
ON documents USING gin (analysis);

-- Add comment for documentation
COMMENT ON COLUMN documents.analysis IS 'Structured AI analysis of the paper including: executive_summary, research_problem, methodology, key_findings, limitations, citations, etc. Generated via GPT-4o';

-- Update existing documents to have NULL analysis (already default, but explicit)
UPDATE documents SET analysis = NULL WHERE analysis IS NULL;

-- Example analysis structure (for documentation):
/*
{
  "executive_summary": "Brief 2-3 sentence overview",
  "research_problem": "What problem does this paper address?",
  "key_questions": ["Question 1", "Question 2"],
  "methodology": {
    "approach": "Description of methods",
    "techniques": ["Technique 1", "Technique 2"],
    "dataset": "Dataset description if applicable"
  },
  "key_findings": [
    "Finding 1",
    "Finding 2"
  ],
  "results": {
    "summary": "Overview of results",
    "metrics": ["Metric 1: value", "Metric 2: value"]
  },
  "limitations": ["Limitation 1", "Limitation 2"],
  "future_work": ["Direction 1", "Direction 2"],
  "key_citations": [
    {
      "authors": "Author et al.",
      "year": "2023",
      "title": "Paper title",
      "relevance": "Why this citation matters"
    }
  ],
  "relevance_score": 8.5,
  "analysis_timestamp": "2024-01-15T10:30:00Z",
  "analysis_model": "gpt-4o",
  "processing_time_seconds": 23.5
}
*/
