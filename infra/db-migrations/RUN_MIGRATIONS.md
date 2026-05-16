# Database Migrations - Run Instructions

Last updated: May 10, 2026

For current product/architecture state, see `../../current_state.md`.

## Overview
These migrations should be run on Supabase. Noesis does not use a local PostgreSQL container for application data.

Current migration set includes:

- draft analysis quality improvements
- full-text search for hybrid RAG
- user feedback
- referrals
- testimonials/platform stats
- subscription management and Stripe event tables
- analytics functions
- shared paper cache
- Literature/Discover/Literature Map schema additions
- user quota plan alignment
- draft comparisons
- reviewer feedback anchor fields

## How to Run on Supabase

### Option 1: Supabase Dashboard (Recommended)
1. Go to https://supabase.com/dashboard
2. Select your project (ufnaadgdrraqnatvgarq)
3. Click "SQL Editor" in the left sidebar
4. Open a new query
5. Copy and paste the contents of each migration file in filename order:
   - 001_improve_draft_analysis_quality.sql
   - 002_fulltext_search.sql
   - 003_user_feedback.sql
   - 004_referrals.sql
   - 005_testimonials.sql
   - 006_subscriptions.sql
   - 007_analytics.sql
   - 008_subscriptions.sql
   - 009_sprint_week1_features.sql
   - 010_week2_features.sql
   - 011_shared_paper_cache.sql
   - 012_literature_tab_redesign.sql
   - 013_discover_tab_redesign.sql
   - 014_document_tags.sql
   - 015_literature_map_recommendation_context.sql
   - 016_user_quota_plan_alignment.sql
   - 017_draft_comparisons.sql
   - 018_add_insights_metadata_to_projects.sql
   - 019_add_recommendation_context_to_paper_recommendations.sql
   - 020_reviewer_feedback_anchor_fields.sql
6. Click "Run" for each migration

### Option 2: Supabase CLI
```bash
# Install Supabase CLI if not installed
npm install -g supabase

# Login
supabase login

# Link to your project
supabase link --project-ref ufnaadgdrraqnatvgarq

# Run migrations
supabase db push --include-all

# Or run individually
psql "$DATABASE_URL" -f infra/db-migrations/002_fulltext_search.sql
psql "$DATABASE_URL" -f infra/db-migrations/003_user_feedback.sql
# ... continue in filename order
```

Note: there are two subscription migrations, `006_subscriptions.sql` and `008_subscriptions.sql`. Do not delete or skip one without checking the target Supabase schema history.

## Verification

After running all migrations, verify with:

```sql
-- Check new tables exist
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN (
    'user_feedback',
    'referrals',
    'testimonials',
    'platform_stats',
    'subscriptions',
    'usage_limits',
    'draft_comparisons',
    'shared_papers'
);

-- Check full-text search columns
SELECT column_name FROM information_schema.columns
WHERE table_name = 'document_chunks'
AND column_name = 'content_tsvector';

-- Test analytics functions if installed
SELECT * FROM get_monthly_active_users(3);
SELECT * FROM analytics_dashboard;
```

## Rollback (if needed)

If you need to rollback:

```sql
-- Drop tables in reverse order
DROP TABLE IF EXISTS draft_comparisons CASCADE;
DROP VIEW IF EXISTS analytics_dashboard CASCADE;
DROP TABLE IF EXISTS usage_limits CASCADE;
DROP TABLE IF EXISTS subscriptions CASCADE;
DROP TABLE IF EXISTS platform_stats CASCADE;
DROP TABLE IF EXISTS testimonials CASCADE;
DROP TABLE IF EXISTS referrals CASCADE;
DROP TABLE IF EXISTS user_feedback CASCADE;

-- Remove full-text search
ALTER TABLE document_chunks DROP COLUMN IF EXISTS content_tsvector;
ALTER TABLE draft_chunks DROP COLUMN IF EXISTS content_tsvector;
```
