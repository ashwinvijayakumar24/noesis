-- Migration: Enable Row-Level Security (RLS) - FINAL
-- Description: Protect user data by ensuring users can only access their own resources
-- Date: 2025-12-30
-- Critical: MUST be applied before public beta launch
-- Note: Only includes tables that actually exist in the database

-- =============================================================================
-- ENABLE RLS ON TABLES THAT DON'T HAVE IT YET
-- =============================================================================

-- These tables currently have rls_enabled: false
ALTER TABLE project_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE methodology_recommendations ENABLE ROW LEVEL SECURITY;
ALTER TABLE paper_recommendations ENABLE ROW LEVEL SECURITY;

-- =============================================================================
-- DROP EXISTING POLICIES (IF ANY) TO AVOID CONFLICTS
-- =============================================================================

-- Projects
DROP POLICY IF EXISTS "Users can view own projects" ON projects;
DROP POLICY IF EXISTS "Users can insert own projects" ON projects;
DROP POLICY IF EXISTS "Users can update own projects" ON projects;
DROP POLICY IF EXISTS "Users can delete own projects" ON projects;

-- Documents
DROP POLICY IF EXISTS "Users can view own documents" ON documents;
DROP POLICY IF EXISTS "Users can insert own documents" ON documents;
DROP POLICY IF EXISTS "Users can update own documents" ON documents;
DROP POLICY IF EXISTS "Users can delete own documents" ON documents;

-- Document chunks
DROP POLICY IF EXISTS "Users can view own document chunks" ON document_chunks;
DROP POLICY IF EXISTS "Users can insert own document chunks" ON document_chunks;
DROP POLICY IF EXISTS "Users can delete own document chunks" ON document_chunks;

-- Drafts
DROP POLICY IF EXISTS "Users can view own drafts" ON drafts;
DROP POLICY IF EXISTS "Users can insert own drafts" ON drafts;
DROP POLICY IF EXISTS "Users can update own drafts" ON drafts;
DROP POLICY IF EXISTS "Users can delete own drafts" ON drafts;

-- Draft chunks
DROP POLICY IF EXISTS "Users can view own draft chunks" ON draft_chunks;
DROP POLICY IF EXISTS "Users can insert own draft chunks" ON draft_chunks;
DROP POLICY IF EXISTS "Users can delete own draft chunks" ON draft_chunks;

-- Chat messages
DROP POLICY IF EXISTS "Users can view own chat messages" ON chat_messages;
DROP POLICY IF EXISTS "Users can insert own chat messages" ON chat_messages;
DROP POLICY IF EXISTS "Users can delete own chat messages" ON chat_messages;

-- Analytics events
DROP POLICY IF EXISTS "Users can view own analytics events" ON analytics_events;
DROP POLICY IF EXISTS "Users can insert own analytics events" ON analytics_events;

-- =============================================================================
-- CREATE POLICIES FOR ALL TABLES
-- =============================================================================

-- PROJECTS
CREATE POLICY "Users can view own projects"
  ON projects FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own projects"
  ON projects FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own projects"
  ON projects FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own projects"
  ON projects FOR DELETE
  USING (auth.uid() = user_id);

-- DOCUMENTS
CREATE POLICY "Users can view own documents"
  ON documents FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own documents"
  ON documents FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own documents"
  ON documents FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own documents"
  ON documents FOR DELETE
  USING (auth.uid() = user_id);

-- DOCUMENT_CHUNKS (via project ownership)
CREATE POLICY "Users can view own document chunks"
  ON document_chunks FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_chunks.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own document chunks"
  ON document_chunks FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_chunks.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own document chunks"
  ON document_chunks FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_chunks.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- DRAFTS
CREATE POLICY "Users can view own drafts"
  ON drafts FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own drafts"
  ON drafts FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own drafts"
  ON drafts FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own drafts"
  ON drafts FOR DELETE
  USING (auth.uid() = user_id);

-- DRAFT_CHUNKS (via project ownership)
CREATE POLICY "Users can view own draft chunks"
  ON draft_chunks FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = draft_chunks.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own draft chunks"
  ON draft_chunks FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = draft_chunks.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own draft chunks"
  ON draft_chunks FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = draft_chunks.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- DRAFT_ANALYSIS (via draft ownership)
CREATE POLICY "Users can view own draft analysis"
  ON draft_analysis FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_analysis.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own draft analysis"
  ON draft_analysis FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_analysis.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can update own draft analysis"
  ON draft_analysis FOR UPDATE
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_analysis.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own draft analysis"
  ON draft_analysis FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_analysis.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

-- DRAFT_CLAIMS (via draft ownership)
CREATE POLICY "Users can view own draft claims"
  ON draft_claims FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_claims.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own draft claims"
  ON draft_claims FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_claims.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own draft claims"
  ON draft_claims FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = draft_claims.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

-- COVERAGE_GAPS (via draft ownership)
CREATE POLICY "Users can view own coverage gaps"
  ON coverage_gaps FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = coverage_gaps.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own coverage gaps"
  ON coverage_gaps FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = coverage_gaps.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own coverage gaps"
  ON coverage_gaps FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = coverage_gaps.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

-- REVIEWER_FEEDBACK (via draft ownership)
CREATE POLICY "Users can view own reviewer feedback"
  ON reviewer_feedback FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = reviewer_feedback.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own reviewer feedback"
  ON reviewer_feedback FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = reviewer_feedback.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own reviewer feedback"
  ON reviewer_feedback FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = reviewer_feedback.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

-- CITATIONS (via project ownership)
CREATE POLICY "Users can view own citations"
  ON citations FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = citations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own citations"
  ON citations FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = citations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own citations"
  ON citations FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = citations.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- CITATION_SUGGESTIONS (via draft ownership)
CREATE POLICY "Users can view own citation suggestions"
  ON citation_suggestions FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = citation_suggestions.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own citation suggestions"
  ON citation_suggestions FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = citation_suggestions.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own citation suggestions"
  ON citation_suggestions FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM drafts
      WHERE drafts.id = citation_suggestions.draft_id
      AND drafts.user_id = auth.uid()
    )
  );

-- CHAT_MESSAGES (direct user_id)
CREATE POLICY "Users can view own chat messages"
  ON chat_messages FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own chat messages"
  ON chat_messages FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own chat messages"
  ON chat_messages FOR DELETE
  USING (auth.uid() = user_id);

-- RESEARCH_QUESTIONS (via project ownership)
CREATE POLICY "Users can view own research questions"
  ON research_questions FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = research_questions.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own research questions"
  ON research_questions FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = research_questions.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own research questions"
  ON research_questions FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = research_questions.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- METHODOLOGY_RECOMMENDATIONS (via project ownership)
CREATE POLICY "Users can view own methodology recommendations"
  ON methodology_recommendations FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = methodology_recommendations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own methodology recommendations"
  ON methodology_recommendations FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = methodology_recommendations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own methodology recommendations"
  ON methodology_recommendations FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = methodology_recommendations.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- PAPER_RECOMMENDATIONS (via project ownership)
CREATE POLICY "Users can view own paper recommendations"
  ON paper_recommendations FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = paper_recommendations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own paper recommendations"
  ON paper_recommendations FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = paper_recommendations.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own paper recommendations"
  ON paper_recommendations FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = paper_recommendations.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- PROJECT_TAGS (via project ownership)
CREATE POLICY "Users can view own project tags"
  ON project_tags FOR SELECT
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = project_tags.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert own project tags"
  ON project_tags FOR INSERT
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = project_tags.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete own project tags"
  ON project_tags FOR DELETE
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = project_tags.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- ANALYTICS_EVENTS (direct user_id)
CREATE POLICY "Users can view own analytics events"
  ON analytics_events FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own analytics events"
  ON analytics_events FOR INSERT
  WITH CHECK (auth.uid() = user_id);

-- =============================================================================
-- VERIFICATION QUERY
-- =============================================================================

-- Run this after migration to verify all tables have RLS enabled:
-- SELECT tablename, rowsecurity
-- FROM pg_tables
-- WHERE schemaname = 'public'
-- AND tablename IN ('projects', 'documents', 'drafts', 'project_tags', 'research_questions');
-- Expected: rowsecurity = true for ALL tables
