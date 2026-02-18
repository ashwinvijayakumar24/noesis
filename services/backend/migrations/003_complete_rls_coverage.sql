-- Migration: Complete RLS Coverage for All User Data Tables
-- Purpose: Enable Row-Level Security on remaining tables to ensure complete user data isolation
-- Critical Security: Closes data leakage vulnerabilities in dataset and document analysis tables
-- Date: 2026-02-14

-- =====================================================
-- DATASET TABLES (Direct user_id ownership)
-- =====================================================

-- 1. DATASETS TABLE
-- Already has user_id column, just needs RLS enabled
ALTER TABLE datasets ENABLE ROW LEVEL SECURITY;

-- RLS Policies for datasets
CREATE POLICY "Users can view own datasets"
  ON datasets FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own datasets"
  ON datasets FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own datasets"
  ON datasets FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own datasets"
  ON datasets FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);

-- 2. DATASET_CHAT_MESSAGES TABLE
ALTER TABLE dataset_chat_messages ENABLE ROW LEVEL SECURITY;

-- RLS Policies for dataset_chat_messages
CREATE POLICY "Users can view own dataset chat messages"
  ON dataset_chat_messages FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own dataset chat messages"
  ON dataset_chat_messages FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own dataset chat messages"
  ON dataset_chat_messages FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own dataset chat messages"
  ON dataset_chat_messages FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);

-- 3. DATASET_THREADS TABLE
ALTER TABLE dataset_threads ENABLE ROW LEVEL SECURITY;

-- RLS Policies for dataset_threads
CREATE POLICY "Users can view own dataset threads"
  ON dataset_threads FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own dataset threads"
  ON dataset_threads FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own dataset threads"
  ON dataset_threads FOR UPDATE
  TO authenticated
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own dataset threads"
  ON dataset_threads FOR DELETE
  TO authenticated
  USING (auth.uid() = user_id);

-- =====================================================
-- DOCUMENT ANALYSIS TABLES (Project-based ownership via JOIN)
-- =====================================================

-- 4. DOCUMENT_CLAIMS TABLE
-- Ownership determined via project_id -> projects.user_id
ALTER TABLE document_claims ENABLE ROW LEVEL SECURITY;

-- RLS Policies for document_claims
CREATE POLICY "Users can view claims in own projects"
  ON document_claims FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_claims.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert claims in own projects"
  ON document_claims FOR INSERT
  TO authenticated
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_claims.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can update claims in own projects"
  ON document_claims FOR UPDATE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_claims.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete claims in own projects"
  ON document_claims FOR DELETE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_claims.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- 5. DOCUMENT_METHODS TABLE
ALTER TABLE document_methods ENABLE ROW LEVEL SECURITY;

-- RLS Policies for document_methods
CREATE POLICY "Users can view methods in own projects"
  ON document_methods FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_methods.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert methods in own projects"
  ON document_methods FOR INSERT
  TO authenticated
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_methods.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can update methods in own projects"
  ON document_methods FOR UPDATE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_methods.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete methods in own projects"
  ON document_methods FOR DELETE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_methods.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- 6. DOCUMENT_FINDINGS TABLE
ALTER TABLE document_findings ENABLE ROW LEVEL SECURITY;

-- RLS Policies for document_findings
CREATE POLICY "Users can view findings in own projects"
  ON document_findings FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_findings.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can insert findings in own projects"
  ON document_findings FOR INSERT
  TO authenticated
  WITH CHECK (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_findings.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can update findings in own projects"
  ON document_findings FOR UPDATE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_findings.project_id
      AND projects.user_id = auth.uid()
    )
  );

CREATE POLICY "Users can delete findings in own projects"
  ON document_findings FOR DELETE
  TO authenticated
  USING (
    EXISTS (
      SELECT 1 FROM projects
      WHERE projects.id = document_findings.project_id
      AND projects.user_id = auth.uid()
    )
  );

-- =====================================================
-- VERIFICATION & COMMENTS
-- =====================================================

-- Add comments explaining security model
COMMENT ON POLICY "Users can view own datasets" ON datasets IS 'Direct user_id ownership - users can only access their own datasets';
COMMENT ON POLICY "Users can view own dataset chat messages" ON dataset_chat_messages IS 'Direct user_id ownership - chat messages isolated per user';
COMMENT ON POLICY "Users can view own dataset threads" ON dataset_threads IS 'Direct user_id ownership - OpenAI threads isolated per user';
COMMENT ON POLICY "Users can view claims in own projects" ON document_claims IS 'Project-based ownership via JOIN - users can only see claims from their projects';
COMMENT ON POLICY "Users can view methods in own projects" ON document_methods IS 'Project-based ownership via JOIN - users can only see methods from their projects';
COMMENT ON POLICY "Users can view findings in own projects" ON document_findings IS 'Project-based ownership via JOIN - users can only see findings from their projects';

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================
-- Run these queries AFTER migration to verify RLS is enabled

-- Check that RLS is enabled on all tables
-- Expected: All 6 tables should show rowsecurity = true
/*
SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
    'datasets',
    'dataset_chat_messages',
    'dataset_threads',
    'document_claims',
    'document_methods',
    'document_findings'
  )
ORDER BY tablename;
*/

-- Count RLS policies created
-- Expected: 24 policies total (4 per table × 6 tables)
/*
SELECT schemaname, tablename, policyname
FROM pg_policies
WHERE tablename IN (
    'datasets',
    'dataset_chat_messages',
    'dataset_threads',
    'document_claims',
    'document_methods',
    'document_findings'
  )
ORDER BY tablename, policyname;
*/

-- =====================================================
-- SECURITY TEST QUERIES
-- =====================================================
-- Test cross-user access (should return 0 rows when executed as User A)

-- Test 1: Attempt to view User B's datasets as User A
-- SET request.jwt.claim.sub = 'user-a-uuid';
-- SELECT * FROM datasets WHERE user_id = 'user-b-uuid';
-- Expected: 0 rows (blocked by RLS)

-- Test 2: Attempt to view User B's document claims via project_id
-- SELECT * FROM document_claims WHERE project_id IN (
--   SELECT id FROM projects WHERE user_id = 'user-b-uuid'
-- );
-- Expected: 0 rows (blocked by RLS)

-- =====================================================
-- MIGRATION COMPLETE
-- =====================================================

DO $$
DECLARE
    enabled_count INTEGER;
    policy_count INTEGER;
BEGIN
    -- Verify RLS is enabled on all 6 tables
    SELECT COUNT(*) INTO enabled_count
    FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename IN (
        'datasets',
        'dataset_chat_messages',
        'dataset_threads',
        'document_claims',
        'document_methods',
        'document_findings'
      )
      AND rowsecurity = true;

    -- Verify policies were created (24 total expected)
    SELECT COUNT(*) INTO policy_count
    FROM pg_policies
    WHERE tablename IN (
        'datasets',
        'dataset_chat_messages',
        'dataset_threads',
        'document_claims',
        'document_methods',
        'document_findings'
      );

    -- Assertions
    ASSERT enabled_count = 6,
           'Migration failed: Expected 6 tables with RLS enabled, found ' || enabled_count;

    ASSERT policy_count = 24,
           'Migration failed: Expected 24 RLS policies, found ' || policy_count;

    -- Success message
    RAISE NOTICE '✓ Migration 003_complete_rls_coverage.sql completed successfully';
    RAISE NOTICE '✓ RLS enabled on 6 tables: datasets, dataset_chat_messages, dataset_threads, document_claims, document_methods, document_findings';
    RAISE NOTICE '✓ Created 24 RLS policies (4 per table: SELECT, INSERT, UPDATE, DELETE)';
    RAISE NOTICE '✓ Security model: Direct user_id for datasets, project-based JOIN for document analysis tables';
    RAISE NOTICE '⚠ IMPORTANT: Run verification queries to test cross-user access blocking';
END $$;
