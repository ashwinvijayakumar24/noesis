-- Migration: Complete RLS Coverage for Document Analysis Tables
-- Purpose: Add RLS policies to document analysis tables (only tables that exist)
-- Date: 2026-02-14
-- Note: This migration skips dataset tables that don't exist in this database

-- =====================================================
-- DOCUMENT ANALYSIS TABLES (Project-based ownership via JOIN)
-- =====================================================
-- These tables already have RLS ENABLED (globe icons visible in Supabase)
-- We just need to ensure they have the correct POLICIES

-- =====================================================
-- 1. DOCUMENT_CLAIMS TABLE
-- =====================================================

-- Drop existing policies if any (to avoid conflicts)
DROP POLICY IF EXISTS "Users can view claims in own projects" ON document_claims;
DROP POLICY IF EXISTS "Users can insert claims in own projects" ON document_claims;
DROP POLICY IF EXISTS "Users can update claims in own projects" ON document_claims;
DROP POLICY IF EXISTS "Users can delete claims in own projects" ON document_claims;

-- Ensure RLS is enabled (idempotent - won't fail if already enabled)
ALTER TABLE document_claims ENABLE ROW LEVEL SECURITY;

-- Create RLS Policies for document_claims
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

-- =====================================================
-- 2. DOCUMENT_METHODS TABLE
-- =====================================================

-- Drop existing policies if any
DROP POLICY IF EXISTS "Users can view methods in own projects" ON document_methods;
DROP POLICY IF EXISTS "Users can insert methods in own projects" ON document_methods;
DROP POLICY IF EXISTS "Users can update methods in own projects" ON document_methods;
DROP POLICY IF EXISTS "Users can delete methods in own projects" ON document_methods;

-- Ensure RLS is enabled
ALTER TABLE document_methods ENABLE ROW LEVEL SECURITY;

-- Create RLS Policies for document_methods
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

-- =====================================================
-- 3. DOCUMENT_FINDINGS TABLE
-- =====================================================

-- Drop existing policies if any
DROP POLICY IF EXISTS "Users can view findings in own projects" ON document_findings;
DROP POLICY IF EXISTS "Users can insert findings in own projects" ON document_findings;
DROP POLICY IF EXISTS "Users can update findings in own projects" ON document_findings;
DROP POLICY IF EXISTS "Users can delete findings in own projects" ON document_findings;

-- Ensure RLS is enabled
ALTER TABLE document_findings ENABLE ROW LEVEL SECURITY;

-- Create RLS Policies for document_findings
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
-- COMMENTS
-- =====================================================

COMMENT ON POLICY "Users can view claims in own projects" ON document_claims IS 'Project-based ownership via JOIN - users can only see claims from their projects';
COMMENT ON POLICY "Users can view methods in own projects" ON document_methods IS 'Project-based ownership via JOIN - users can only see methods from their projects';
COMMENT ON POLICY "Users can view findings in own projects" ON document_findings IS 'Project-based ownership via JOIN - users can only see findings from their projects';

-- =====================================================
-- VERIFICATION
-- =====================================================

DO $$
DECLARE
    enabled_count INTEGER;
    policy_count INTEGER;
BEGIN
    -- Verify RLS is enabled on all 3 tables
    SELECT COUNT(*) INTO enabled_count
    FROM pg_tables
    WHERE schemaname = 'public'
      AND tablename IN ('document_claims', 'document_methods', 'document_findings')
      AND rowsecurity = true;

    -- Verify policies were created (12 total expected)
    SELECT COUNT(*) INTO policy_count
    FROM pg_policies
    WHERE tablename IN ('document_claims', 'document_methods', 'document_findings');

    -- Assertions
    ASSERT enabled_count = 3,
           'Migration failed: Expected 3 tables with RLS enabled, found ' || enabled_count;

    ASSERT policy_count = 12,
           'Migration failed: Expected 12 RLS policies, found ' || policy_count;

    -- Success message
    RAISE NOTICE '✓ Migration 003_complete_rls_coverage_corrected.sql completed successfully';
    RAISE NOTICE '✓ RLS enabled on 3 tables: document_claims, document_methods, document_findings';
    RAISE NOTICE '✓ Created 12 RLS policies (4 per table: SELECT, INSERT, UPDATE, DELETE)';
    RAISE NOTICE '✓ Security model: Project-based ownership via JOIN with projects table';
    RAISE NOTICE '⚠ NOTE: Skipped dataset tables (datasets, dataset_chat_messages, dataset_threads) - not present in database';
END $$;
