-- Migration: Enable Row-Level Security (RLS) - CORRECTED
-- Description: Protect user data by ensuring users can only access their own resources
-- Date: 2025-12-30
-- Critical: MUST be applied before public beta launch

-- =============================================================================
-- ENABLE RLS ON ALL USER TABLES (VERIFIED TO EXIST)
-- =============================================================================

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE draft_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE draft_analysis ENABLE ROW LEVEL SECURITY;
ALTER TABLE draft_claims ENABLE ROW LEVEL SECURITY;
ALTER TABLE coverage_gaps ENABLE ROW LEVEL SECURITY;
ALTER TABLE reviewer_feedback ENABLE ROW LEVEL SECURITY;
ALTER TABLE citations ENABLE ROW LEVEL SECURITY;
ALTER TABLE citation_suggestions ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE methodology_recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE project_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;
ALTER TABLE analytics_events ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- PROJECTS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own projects"
  ON projects
  FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own projects"
  ON projects
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own projects"
  ON projects
  FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own projects"
  ON projects
  FOR DELETE
  USING (auth.uid() = user_id);

-- =============================================================================
-- DOCUMENTS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own documents"
  ON documents
  FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own documents"
  ON documents
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own documents"
  ON documents
  FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own documents"
  ON documents
  FOR DELETE
  USING (auth.uid() = user_id);

-- =============================================================================
-- DOCUMENT_CHUNKS TABLE POLICIES
-- =============================================================================

-- document_chunks uses project_id for isolation
CREATE POLICY "Users can view own document chunks"
  ON document_chunks
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_chunks.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own document chunks"
  ON document_chunks
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_chunks.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own document chunks"
  ON document_chunks
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_chunks.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- =============================================================================
-- DRAFTS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own drafts"
  ON drafts
  FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own drafts"
  ON drafts
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own drafts"
  ON drafts
  FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own drafts"
  ON drafts
  FOR DELETE
  USING (auth.uid() = user_id);

-- =============================================================================
-- DRAFT_CHUNKS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own draft chunks"
  ON draft_chunks
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = draft_chunks.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own draft chunks"
  ON draft_chunks
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = draft_chunks.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own draft chunks"
  ON draft_chunks
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = draft_chunks.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- =============================================================================
-- DRAFT_ANALYSIS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own draft analysis"
  ON draft_analysis
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_analysis.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own draft analysis"
  ON draft_analysis
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_analysis.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can update own draft analysis"
  ON draft_analysis
  FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_analysis.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own draft analysis"
  ON draft_analysis
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_analysis.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

-- =============================================================================
-- DRAFT_CLAIMS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own draft claims"
  ON draft_claims
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_claims.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own draft claims"
  ON draft_claims
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_claims.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own draft claims"
  ON draft_claims
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_claims.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

-- =============================================================================
-- COVERAGE_GAPS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own coverage gaps"
  ON coverage_gaps
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = coverage_gaps.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own coverage gaps"
  ON coverage_gaps
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = coverage_gaps.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own coverage gaps"
  ON coverage_gaps
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = coverage_gaps.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

-- =============================================================================
-- REVIEWER_FEEDBACK TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own reviewer feedback"
  ON reviewer_feedback
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = reviewer_feedback.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own reviewer feedback"
  ON reviewer_feedback
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = reviewer_feedback.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own reviewer feedback"
  ON reviewer_feedback
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = reviewer_feedback.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

-- =============================================================================
-- CITATIONS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own citations"
  ON citations
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = citations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own citations"
  ON citations
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = citations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own citations"
  ON citations
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = citations.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- =============================================================================
-- CITATION_SUGGESTIONS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own citation suggestions"
  ON citation_suggestions
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = citation_suggestions.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own citation suggestions"
  ON citation_suggestions
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = citation_suggestions.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own citation suggestions"
  ON citation_suggestions
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = citation_suggestions.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

-- =============================================================================
-- CHAT_MESSAGES TABLE POLICIES
-- =============================================================================

-- chat_messages has both user_id and project_id
CREATE POLICY "Users can view own chat messages"
  ON chat_messages
  FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own chat messages"
  ON chat_messages
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own chat messages"
  ON chat_messages
  FOR DELETE
  USING (auth.uid() = user_id);

-- =============================================================================
-- RESEARCH_QUESTIONS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own research questions"
  ON research_questions
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = research_questions.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own research questions"
  ON research_questions
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = research_questions.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own research questions"
  ON research_questions
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = research_questions.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- =============================================================================
-- METHODOLOGY_RECOMMENDATIONS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own methodology recommendations"
  ON methodology_recommendations
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = methodology_recommendations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own methodology recommendations"
  ON methodology_recommendations
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = methodology_recommendations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own methodology recommendations"
  ON methodology_recommendations
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = methodology_recommendations.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- =============================================================================
-- PAPER_RECOMMENDATIONS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own paper recommendations"
  ON paper_recommendations
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = paper_recommendations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own paper recommendations"
  ON paper_recommendations
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = paper_recommendations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own paper recommendations"
  ON paper_recommendations
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = paper_recommendations.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- =============================================================================
-- PROJECT_TAGS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own project tags"
  ON project_tags
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = project_tags.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own project tags"
  ON project_tags
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = project_tags.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own project tags"
  ON project_tags
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = project_tags.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- =============================================================================
-- DATASETS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own datasets"
  ON datasets
  FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = datasets.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own datasets"
  ON datasets
  FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = datasets.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own datasets"
  ON datasets
  FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = datasets.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- =============================================================================
-- ANALYTICS_EVENTS TABLE POLICIES
-- =============================================================================

CREATE POLICY "Users can view own analytics events"
  ON analytics_events
  FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own analytics events"
  ON analytics_events
  FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- =============================================================================
-- VERIFICATION QUERY
-- =============================================================================

-- Run this query after applying migration to verify RLS is enabled:
-- SELECT tablename, rowsecurity
-- FROM pg_tables
-- WHERE schemaname = 'public'
-- AND tablename IN ('projects', 'documents', 'drafts', 'chat_messages');
-- Expected: rowsecurity = true for all tables

-- =============================================================================
-- TESTING CHECKLIST
-- =============================================================================

-- 1. Create two test accounts (Account A and Account B)
-- 2. Have Account A create a project
-- 3. Try to access Account A's project from Account B - should fail
-- 4. Verify direct database queries respect RLS:
--    SELECT * FROM projects; -- Should only return current user's projects
-- 5. Test all CRUD operations (SELECT, INSERT, UPDATE, DELETE) for each table
-- 6. Verify no cross-user data leakage in joins
