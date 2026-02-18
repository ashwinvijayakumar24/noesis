-- Verification Script: Check RLS Status
-- Run this in Supabase SQL Editor to see which tables need RLS policies

-- 1. Check which tables have RLS enabled
SELECT
    tablename,
    rowsecurity as rls_enabled,
    CASE
        WHEN rowsecurity THEN '✅ RLS Enabled'
        ELSE '❌ RLS Disabled'
    END as status
FROM pg_tables
WHERE schemaname = 'public'
    AND tablename IN (
        'document_claims',
        'document_methods',
        'document_findings',
        'draft_analysis_checkpoints'
    )
ORDER BY tablename;

-- 2. Check which RLS policies exist for these tables
SELECT
    tablename,
    policyname,
    cmd as operation,
    qual as using_expression
FROM pg_policies
WHERE tablename IN (
    'document_claims',
    'document_methods',
    'document_findings',
    'draft_analysis_checkpoints'
)
ORDER BY tablename, cmd;

-- 3. Count total policies per table
SELECT
    tablename,
    COUNT(*) as policy_count,
    CASE
        WHEN COUNT(*) = 4 THEN '✅ Complete (4 policies)'
        WHEN COUNT(*) > 0 THEN '⚠️ Partial (' || COUNT(*) || ' policies)'
        ELSE '❌ No policies'
    END as status
FROM pg_policies
WHERE tablename IN (
    'document_claims',
    'document_methods',
    'document_findings',
    'draft_analysis_checkpoints'
)
GROUP BY tablename
ORDER BY tablename;
