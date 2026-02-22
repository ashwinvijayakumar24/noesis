# Draft Analysis Redesign - Deployment Guide

**Phase 5: Testing & Deployment**
**Date:** February 2026

## Overview

This guide covers the deployment of the draft analysis redesign to production, including:
- Database migration execution
- Backend service deployment
- Frontend deployment to Vercel
- Post-deployment verification
- Rollback procedures

---

## Pre-Deployment Checklist

### 1. Testing Complete
- [ ] All backend tests passed (see TESTING_GUIDE.md)
- [ ] All frontend tests passed
- [ ] Manual testing checklist 100% complete
- [ ] Performance targets met
- [ ] No critical bugs identified

### 2. Code Review
- [ ] Backend code reviewed
- [ ] Frontend code reviewed
- [ ] Database migration reviewed
- [ ] API endpoints tested

### 3. Backups
- [ ] Database backup created (Supabase dashboard)
- [ ] Current production code tagged in git
- [ ] Environment variables documented

### 4. Communication
- [ ] Users notified of upcoming deployment (if applicable)
- [ ] Deployment window scheduled
- [ ] Rollback plan prepared

---

## Deployment Steps

### Step 1: Database Migration

**Execute migration on Supabase:**

#### 1.1 Connect to Supabase
```bash
# Option A: Via Supabase Dashboard
# 1. Go to https://app.supabase.com
# 2. Select your project
# 3. Navigate to SQL Editor

# Option B: Via psql (local)
psql "postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-PROJECT-REF].supabase.co:5432/postgres"
```

#### 1.2 Run Migration
```sql
-- Copy contents of services/backend/migrations/016_draft_analysis_redesign.sql
-- Paste into SQL Editor
-- Click "Run"

-- Verify migration success
SELECT COUNT(*) FROM draft_claims WHERE section_type IS NOT NULL;
-- Should return 0 initially (sections not assigned yet)

SELECT COUNT(*) FROM draft_claims WHERE status = 'new';
-- Should return count of all existing claims (defaulted to 'new')

-- Test unified view
SELECT * FROM draft_feedback_unified LIMIT 5;
-- Should return combined claims, gaps, feedback

-- Test count function
SELECT * FROM get_feedback_counts_by_section('<test-draft-id>');
-- Should return counts grouped by section
```

#### 1.3 Verify Indexes
```sql
-- Verify indexes created
SELECT indexname, tablename
FROM pg_indexes
WHERE tablename IN ('draft_claims', 'coverage_gaps', 'reviewer_feedback')
  AND indexname LIKE '%section%';

-- Expected indexes:
-- idx_draft_claims_section_type
-- idx_draft_claims_status
-- idx_coverage_gaps_section_type
-- idx_coverage_gaps_status
-- idx_reviewer_feedback_section_type
-- idx_reviewer_feedback_status
-- idx_reviewer_feedback_priority
```

#### 1.4 Rollback Plan (If Needed)
```sql
-- ONLY RUN IF MIGRATION FAILS

-- Drop added columns
ALTER TABLE draft_claims DROP COLUMN IF EXISTS section_type CASCADE;
ALTER TABLE draft_claims DROP COLUMN IF EXISTS status CASCADE;
ALTER TABLE draft_claims DROP COLUMN IF EXISTS confidence_score CASCADE;
ALTER TABLE draft_claims DROP COLUMN IF EXISTS hidden CASCADE;

ALTER TABLE coverage_gaps DROP COLUMN IF EXISTS section_type CASCADE;
ALTER TABLE coverage_gaps DROP COLUMN IF EXISTS status CASCADE;

ALTER TABLE reviewer_feedback DROP COLUMN IF EXISTS section_type CASCADE;
ALTER TABLE reviewer_feedback DROP COLUMN IF EXISTS status CASCADE;
ALTER TABLE reviewer_feedback DROP COLUMN IF EXISTS priority CASCADE;

-- Drop view and function
DROP VIEW IF EXISTS draft_feedback_unified CASCADE;
DROP FUNCTION IF EXISTS get_feedback_counts_by_section(UUID);

-- Drop enums
DROP TYPE IF EXISTS section_type_enum CASCADE;
DROP TYPE IF EXISTS feedback_status_enum CASCADE;
DROP TYPE IF EXISTS priority_enum CASCADE;
```

**Migration Status:** ✅ Complete / ❌ Failed / ⏭️ Rolled Back

---

### Step 2: Backend Deployment

**Deploy to AWS EC2 / production server:**

#### 2.1 Build Backend
```bash
cd services/backend

# Pull latest code
git pull origin master

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Verify all new services exist
ls app/services/section_mapping.py
ls app/services/section_analysis.py
```

#### 2.2 Update Environment Variables
```bash
# Verify .env has all required variables
cat .env | grep -E "(SUPABASE_URL|SUPABASE_SERVICE_ROLE_KEY|OPENAI_API_KEY)"

# No changes needed (using existing variables)
```

#### 2.3 Restart Backend Service
```bash
# Option A: Docker Compose
docker-compose down
docker-compose up -d backend celery-worker

# Option B: Systemd
sudo systemctl restart noesis-backend
sudo systemctl restart noesis-celery

# Verify services running
docker ps | grep backend
# OR
sudo systemctl status noesis-backend
```

#### 2.4 Verify Backend Deployment
```bash
# Health check
curl http://localhost:8000/health

# Test new endpoints
curl -X GET "http://localhost:8000/drafts/{draft_id}/section-summary" \
  -H "Authorization: Bearer <token>"

# Check logs
docker logs noesis-backend --tail 100
# OR
sudo journalctl -u noesis-backend -n 100
```

**Backend Status:** ✅ Deployed / ❌ Failed

---

### Step 3: Frontend Deployment

**Deploy to Vercel:**

#### 3.1 Build Frontend Locally (Test)
```bash
cd services/frontend

# Install dependencies
npm install

# Build production bundle
npm run build

# Verify build success
ls -lh dist/assets/

# Test build locally
npm run preview
# Open http://localhost:4173
```

#### 3.2 Deploy to Vercel
```bash
# Option A: Vercel CLI
vercel --prod

# Option B: Git Push (if Vercel auto-deploy enabled)
git add .
git commit -m "Deploy: Draft analysis redesign (Phases 1-4)"
git push origin master

# Vercel auto-deploy triggers
```

#### 3.3 Verify Frontend Deployment
```bash
# Visit production URL
open https://noesis.vercel.app

# Check browser console for errors
# Open DevTools → Console
# Should see no errors

# Verify build info
curl https://noesis.vercel.app/assets/*.js | grep "version"
```

#### 3.4 Environment Variables (Vercel Dashboard)
```bash
# Verify environment variables set in Vercel dashboard:
# VITE_SUPABASE_URL=https://your-project.supabase.co
# VITE_SUPABASE_ANON_KEY=your_anon_key
# VITE_API_URL=https://your-backend-url.com

# No changes needed (using existing variables)
```

**Frontend Status:** ✅ Deployed / ❌ Failed

---

### Step 4: Post-Deployment Verification

#### 4.1 Smoke Tests (Production)

**Test 1: Upload New Draft**
```bash
1. Go to https://noesis.vercel.app/projects/<project-id>
2. Upload a new draft (PDF or DOCX)
3. Verify analysis starts
4. Wait for completion
5. Open draft analysis page
6. ✅ Verify sections appear in navigation
7. ✅ Verify feedback displayed in sections
```

**Test 2: Existing Draft Auto-Migration**
```bash
1. Open an existing draft (created before deployment)
2. Navigate to draft analysis page
3. ✅ Verify auto-migration triggered (check network tab for /assign-sections call)
4. ✅ Verify sections appear
5. ✅ Verify feedback organized correctly
```

**Test 3: Save/Dismiss Workflow**
```bash
1. Open draft analysis
2. Navigate to a section with feedback
3. Click "Save" on a feedback item
4. ✅ Verify item moves to "Saved" tab
5. Refresh page
6. ✅ Verify item still in "Saved" tab
7. Click "Dismiss" on another item
8. ✅ Verify item moves to "Dismissed" tab
```

**Test 4: Section Navigation**
```bash
1. Open draft analysis with multiple sections
2. Click different sections in navigation
3. ✅ Verify feedback loads for each section
4. ✅ Verify active section highlighted
5. ✅ Verify badge counts accurate
```

**Test 5: API Endpoints**
```bash
# Test section summary
curl -X GET "https://your-backend-url.com/drafts/{draft_id}/section-summary" \
  -H "Authorization: Bearer <token>"

# Expected: 200 status, sections array

# Test feedback by section
curl -X GET "https://your-backend-url.com/drafts/{draft_id}/feedback-by-section?section_type=methodology&status=new" \
  -H "Authorization: Bearer <token>"

# Expected: 200 status, claims/gaps/feedback arrays
```

#### 4.2 Monitor Logs (First 24 Hours)

**Backend Logs:**
```bash
# Watch backend logs
docker logs -f noesis-backend
# OR
sudo journalctl -u noesis-backend -f

# Look for:
# ✅ No errors on /assign-sections endpoint
# ✅ No errors on section-based queries
# ✅ Successful section type assignments
```

**Frontend Logs (Vercel Dashboard):**
```bash
1. Go to Vercel dashboard
2. Select project
3. Navigate to "Logs"
4. Filter by "Errors"

# Look for:
# ✅ No 404 errors on new components
# ✅ No TypeScript errors
# ✅ No API call failures
```

**Database Logs (Supabase Dashboard):**
```bash
1. Go to Supabase dashboard
2. Navigate to "Database" → "Logs"

# Look for:
# ✅ No failed queries
# ✅ Section-based queries performing well (< 100ms)
# ✅ No deadlocks or constraint violations
```

#### 4.3 Performance Monitoring

**Response Times:**
```bash
# Test API response times
time curl -X GET "https://your-backend-url.com/drafts/{draft_id}/section-summary" \
  -H "Authorization: Bearer <token>"

# Target: < 500ms

# Test page load time
# Chrome DevTools → Network → Reload
# Target: < 3s total load time
```

**Database Performance:**
```sql
-- Check query performance
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
WHERE query LIKE '%section_type%'
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Target: < 100ms mean execution time
```

---

### Step 5: User Communication

#### 5.1 Announce Deployment
```markdown
# Email/Slack Template

Subject: New Feature: Section-Based Draft Analysis

Hi team,

We've deployed a major upgrade to the draft analysis feature:

**What's New:**
✅ Section-based navigation (Abstract → Conclusion)
✅ Save/Dismiss workflow for feedback
✅ Priority-first grouping (HIGH/MEDIUM/LOW)
✅ Enhanced citation quality (claim-to-claim matching)
✅ Methodology comparison against your literature

**What Changed:**
- New UI layout (section navigation sidebar)
- Dark solid color scheme (professional appearance)
- Removed "Re-analyze" button (no longer needed)

**Action Required:**
None! Your existing drafts will auto-migrate when you open them.

**Feedback:**
Report any issues at: https://github.com/anthropics/claude-code/issues

Thanks!
```

#### 5.2 Update Documentation
```bash
# Update README.md
# Update user guide
# Update screenshot (if applicable)
```

---

## Rollback Procedures

### If Deployment Fails:

#### Option 1: Quick Rollback (Frontend Only)
```bash
# Revert Vercel deployment
vercel rollback

# Verify previous version live
curl https://noesis.vercel.app | grep "version"
```

#### Option 2: Full Rollback (Backend + Frontend)
```bash
# 1. Rollback database migration
# Execute rollback SQL from Step 1.4

# 2. Rollback backend code
cd services/backend
git checkout <previous-commit-hash>
docker-compose down
docker-compose up -d backend celery-worker

# 3. Rollback frontend
cd services/frontend
git checkout <previous-commit-hash>
vercel --prod

# 4. Verify rollback
curl https://your-backend-url.com/health
curl https://noesis.vercel.app
```

#### Option 3: Hotfix (Patch Critical Bugs)
```bash
# Create hotfix branch
git checkout -b hotfix/draft-analysis-fix

# Make fixes
# Test locally

# Deploy hotfix
git commit -m "Hotfix: <description>"
git push origin hotfix/draft-analysis-fix

# Deploy to production
vercel --prod
docker-compose up -d backend celery-worker
```

---

## Post-Deployment Monitoring Schedule

**First 1 Hour:**
- [ ] Monitor logs every 15 minutes
- [ ] Test all smoke tests
- [ ] Check for errors in Sentry/error tracking

**First 24 Hours:**
- [ ] Monitor logs every 4 hours
- [ ] Check user feedback
- [ ] Monitor performance metrics

**First Week:**
- [ ] Daily log check
- [ ] Performance review
- [ ] User satisfaction survey

**Metrics to Track:**
- API response times
- Error rates
- User adoption (% using new features)
- Feedback quality (user ratings)

---

## Deployment Checklist

### Pre-Deployment
- [ ] All tests passed
- [ ] Code reviewed
- [ ] Database backup created
- [ ] Rollback plan prepared

### Deployment
- [ ] Database migration executed
- [ ] Backend deployed and verified
- [ ] Frontend deployed and verified
- [ ] Smoke tests passed

### Post-Deployment
- [ ] Logs monitored (first hour)
- [ ] Performance verified
- [ ] Users notified
- [ ] Documentation updated

### Sign-Off
- [ ] Backend: ✅ Deployed Successfully
- [ ] Frontend: ✅ Deployed Successfully
- [ ] Database: ✅ Migration Successful
- [ ] Verification: ✅ All Tests Pass
- [ ] Status: **PRODUCTION READY** 🚀

---

## Support & Troubleshooting

### Common Issues

**Issue 1: Section types not assigned**
```bash
# Manually trigger assignment
curl -X POST "https://your-backend-url.com/drafts/{draft_id}/assign-sections" \
  -H "Authorization: Bearer <token>"
```

**Issue 2: Feedback not loading**
```bash
# Check database
SELECT COUNT(*) FROM draft_claims WHERE draft_id = '<draft-id>' AND section_type IS NOT NULL;

# If 0, run assignment endpoint above
```

**Issue 3: Frontend errors**
```bash
# Check browser console
# Look for API call failures
# Verify environment variables

# Check Vercel logs
vercel logs --follow
```

**Issue 4: Performance degradation**
```sql
-- Check index usage
EXPLAIN ANALYZE
SELECT * FROM draft_claims
WHERE draft_id = '<draft-id>' AND section_type = 'methodology' AND status = 'new';

-- Should use indexes (idx_draft_claims_section_status)
```

### Contact
- **Backend Issues:** Check backend logs, database logs
- **Frontend Issues:** Check Vercel logs, browser console
- **Database Issues:** Check Supabase dashboard
- **Emergency:** Rollback using procedures above

---

**Deployment Date:** _________________
**Deployed By:** _________________
**Verified By:** _________________
**Status:** ✅ SUCCESS / ❌ FAILED / ⏭️ ROLLED BACK
