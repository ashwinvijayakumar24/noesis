# Database Migrations - Run Instructions

## Overview
These migrations add features for Week 2-4 of the growth plan:
- Full-text search for hybrid RAG
- User feedback system
- Referral tracking
- Testimonials and social proof
- Subscription management
- Analytics functions
- Draft comparison

## How to Run on Supabase

### Option 1: Supabase Dashboard (Recommended)
1. Go to https://supabase.com/dashboard
2. Select your project (ufnaadgdrraqnatvgarq)
3. Click "SQL Editor" in the left sidebar
4. Open a new query
5. Copy and paste the contents of each migration file in order:
   - 002_fulltext_search.sql
   - 003_user_feedback.sql
   - 004_referrals.sql
   - 005_testimonials.sql
   - 006_subscriptions.sql
   - 007_analytics.sql
   - 008_draft_comparisons.sql
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
# ... etc
```

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
    'draft_comparisons'
);

-- Check full-text search columns
SELECT column_name FROM information_schema.columns
WHERE table_name = 'document_chunks'
AND column_name = 'content_tsvector';

-- Test analytics functions
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
