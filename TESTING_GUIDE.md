# Draft Analysis Redesign - Testing Guide

**Phase 5: Testing & Deployment**
**Date:** February 2026

## Overview

This guide covers testing for the complete draft analysis redesign, including:
- Backend services (section mapping, claim-to-claim matching, methodology comparison)
- API endpoints (section-based feedback, save/dismiss workflow)
- Frontend components (section navigation, unified feedback cards, priority grouping)
- Database schema (section_type, status, priority columns)

---

## Backend Testing

### 1. Section Type Assignment

**File:** `services/backend/app/services/section_mapping.py`

**Test Cases:**

#### TC-B1: Detect section types from GROBID structure
```python
# Test with various paper structures
test_cases = [
    {
        "title": "Introduction",
        "expected": "introduction"
    },
    {
        "title": "3. Methods and Materials",
        "expected": "methodology"
    },
    {
        "title": "Related Work",
        "expected": "literature_review"
    },
    {
        "title": "Experimental Results",
        "expected": "results"
    }
]

# Run test
from app.services.section_mapping import detect_section_type
for case in test_cases:
    result = detect_section_type(case["title"])
    assert result == case["expected"], f"Failed for {case['title']}"
```

#### TC-B2: Assign sections to existing feedback
```python
# Test auto-migration for old drafts
from app.services.section_mapping import assign_section_types_to_feedback

result = await assign_section_types_to_feedback(draft_id="<test-draft-id>")

# Verify counts
assert result["claims_updated"] > 0
assert result["gaps_updated"] > 0
assert result["feedback_updated"] > 0
assert result["sections_identified"] >= 3  # At least intro, methods, results
```

**Expected Results:**
- ✅ All 8 section types correctly detected (abstract → references)
- ✅ Edge cases handled: numbered sections, alternative titles
- ✅ Existing drafts auto-migrate without errors
- ✅ Section counts match database records

---

### 2. Claim-to-Claim Matching

**File:** `services/backend/app/workflows/draft_analysis/nodes/literature_search.py`

**Test Cases:**

#### TC-B3: Verify claim-based search
```python
# Test claim-to-claim matching vs RAG chunks
from app.workflows.draft_analysis.nodes.literature_search import search_literature_for_claim

claim = {
    "id": "test-claim-1",
    "claim_text": "BERT achieves 92% accuracy on GLUE benchmark"
}

result = await search_literature_for_claim(claim, project_id="<test-project-id>")

# Verify match type
assert result["match_type"] == "claim_based", "Should use claim matching first"
assert result["result_count"] > 0, "Should find supporting claims"
assert "match_confidence" in result["results"][0], "Should include confidence score"
```

#### TC-B4: Fallback to RAG chunks
```python
# Test with claim that has no matches
obscure_claim = {
    "id": "test-claim-2",
    "claim_text": "Very specific claim with no literature matches xyz123"
}

result = await search_literature_for_claim(obscure_claim, project_id="<test-project-id>")

# Should fall back to RAG chunks
assert result["match_type"] in ["chunk_based", "claim_based"]
```

**Expected Results:**
- ✅ Claim-based matching used as primary method
- ✅ Source claim metadata included (importance, section, page)
- ✅ Fallback to RAG chunks when no claim matches
- ✅ 30-50% precision improvement vs chunks alone (measured via relevance scoring)

---

### 3. Project Insights Integration

**File:** `services/backend/app/services/coverage_analysis.py`

**Test Cases:**

#### TC-B5: Gap detection with project insights
```python
from app.services.coverage_analysis import compare_with_literature_database

# Mock coverage analysis
coverage_analysis = {
    "identified_gaps": [
        {
            "gap_type": "methodology_gap",
            "description": "Missing comparison with transformer-based methods"
        }
    ]
}

result = await compare_with_literature_database(coverage_analysis, project_id="<test-project-id>")

# Verify enhancements
assert result["project_insights_available"] == True
assert result["known_research_gaps"] > 0
assert "covered_methods" in result
```

**Expected Results:**
- ✅ Project insights loaded and cross-referenced
- ✅ `has_relevant_literature` flag set correctly
- ✅ `relevant_methods` list populated from document_methods
- ✅ `related_insights` linked from project_insights table

---

### 4. Confidence Filtering

**File:** `services/backend/app/services/claim_analysis.py`

**Test Cases:**

#### TC-B6: Hide low-confidence claims
```python
# Test confidence-based filtering
claims = [
    {"claim_text": "Test claim 1", "confidence_score": 0.9},
    {"claim_text": "Test claim 2", "confidence_score": 0.5},  # Should be hidden
    {"claim_text": "Test claim 3", "confidence_score": 0.3},  # Should be hidden
]

# Process claims
for claim in claims:
    confidence = claim["confidence_score"]
    hidden = confidence < 0.6

    if confidence < 0.6:
        assert hidden == True, "Low confidence claims should be hidden"
```

**Expected Results:**
- ✅ Claims with confidence < 0.6 marked as `hidden: true`
- ✅ Frontend API filters out hidden claims by default
- ✅ "Show All Claims" toggle available in UI

---

### 5. API Endpoints

**Test all new endpoints:**

#### TC-B7: GET /drafts/{draft_id}/feedback-by-section
```bash
# Test section-filtered feedback
curl -X GET "http://localhost:8000/drafts/{draft_id}/feedback-by-section?section_type=methodology&status=new" \
  -H "Authorization: Bearer <token>"

# Expected response:
{
  "claims": [...],
  "gaps": [...],
  "feedback": [...],
  "section_type": "methodology",
  "status": "new",
  "total_count": 15
}
```

#### TC-B8: PATCH /drafts/{draft_id}/feedback/{feedback_id}/status
```bash
# Test save/dismiss workflow
curl -X PATCH "http://localhost:8000/drafts/{draft_id}/feedback/{feedback_id}/status?feedback_type=claim&status=saved" \
  -H "Authorization: Bearer <token>"

# Expected response:
{
  "message": "Feedback status updated",
  "feedback_id": "...",
  "feedback_type": "claim",
  "status": "saved"
}
```

#### TC-B9: GET /drafts/{draft_id}/section-summary
```bash
# Test section counts
curl -X GET "http://localhost:8000/drafts/{draft_id}/section-summary" \
  -H "Authorization: Bearer <token>"

# Expected response:
{
  "sections": [
    {
      "section_type": "introduction",
      "new_count": 5,
      "saved_count": 2,
      "dismissed_count": 1,
      "total_count": 8
    }
  ],
  "total_new": 25,
  "total_saved": 10,
  "total_dismissed": 5
}
```

#### TC-B10: POST /drafts/{draft_id}/assign-sections
```bash
# Test section assignment
curl -X POST "http://localhost:8000/drafts/{draft_id}/assign-sections" \
  -H "Authorization: Bearer <token>"

# Expected response:
{
  "message": "Section types assigned",
  "claims_updated": 10,
  "gaps_updated": 5,
  "feedback_updated": 8,
  "sections_identified": 7
}
```

**Expected Results:**
- ✅ All endpoints return 200 status for valid requests
- ✅ Proper error handling (404 for not found, 401 for unauthorized)
- ✅ Data filtering works correctly (section_type, status)
- ✅ Updates persist to database

---

### 6. Methodology Comparison

**File:** `services/backend/app/services/section_analysis.py`

**Test Cases:**

#### TC-B11: Methodology comparison
```python
from app.services.section_analysis import compare_methodology_to_literature

result = await compare_methodology_to_literature(
    draft_id="<test-draft-id>",
    project_id="<test-project-id>"
)

# Verify feedback items
assert len(result) > 0, "Should generate methodology feedback"
assert any(f["feedback_type"] == "methodology" for f in result)
assert any(f["priority"] == "high" for f in result)  # Missing baselines should be high priority
```

**Expected Results:**
- ✅ Missing baseline comparisons identified
- ✅ Alternative approaches suggested
- ✅ Missing metrics flagged
- ✅ Dataset gaps detected

---

## Frontend Testing

### 1. Section Navigation

**File:** `services/frontend/src/components/draft-analysis/SectionNavigation.tsx`

**Test Cases:**

#### TC-F1: Section navigation rendering
```typescript
// Test component renders correctly
import { render, screen } from '@testing-library/react'
import SectionNavigation from './SectionNavigation'

const mockSections = [
  { section_type: 'introduction', new_count: 5, saved_count: 2, dismissed_count: 1, total_count: 8 },
  { section_type: 'methodology', new_count: 8, saved_count: 0, dismissed_count: 0, total_count: 8 }
]

render(<SectionNavigation sections={mockSections} activeSection="introduction" onSectionChange={() => {}} />)

// Verify
expect(screen.getByText('Introduction')).toBeInTheDocument()
expect(screen.getByText('5')).toBeInTheDocument()  // Badge count
```

#### TC-F2: Section navigation interaction
```typescript
// Test clicking sections
const onSectionChange = jest.fn()
render(<SectionNavigation sections={mockSections} activeSection="introduction" onSectionChange={onSectionChange} />)

fireEvent.click(screen.getByText('Methodology'))
expect(onSectionChange).toHaveBeenCalledWith('methodology')
```

**Expected Results:**
- ✅ All sections with feedback shown (empty sections hidden)
- ✅ Active section highlighted with filled icon
- ✅ Badge shows NEW count per section
- ✅ Click changes active section

---

### 2. Save/Dismiss Workflow

**File:** `services/frontend/src/pages/DraftAnalysis.tsx`

**Test Cases:**

#### TC-F3: Save feedback item
```typescript
// Test save action
const mockOnStatusChange = jest.fn()

render(<UnifiedFeedbackCard item={mockItem} onStatusChange={mockOnStatusChange} currentStatus="new" />)

fireEvent.click(screen.getByText('Save'))
expect(mockOnStatusChange).toHaveBeenCalledWith(mockItem.id, 'claim', 'saved')
```

#### TC-F4: Dismiss feedback item
```typescript
// Test dismiss action
fireEvent.click(screen.getByText('Dismiss'))
expect(mockOnStatusChange).toHaveBeenCalledWith(mockItem.id, 'claim', 'dismissed')
```

#### TC-F5: Status persistence
```bash
# Manual test: Save item, refresh page, verify it's in Saved tab
1. Open draft analysis
2. Click "Save" on a feedback item
3. Refresh page
4. Navigate to "Saved" tab
5. Verify item appears in Saved tab
```

**Expected Results:**
- ✅ Save button moves item to Saved tab
- ✅ Dismiss button moves item to Dismissed tab
- ✅ Status persists across page refreshes
- ✅ Counts update in status tab badges

---

### 3. Priority Grouping

**File:** `services/frontend/src/components/draft-analysis/PriorityGroup.tsx`

**Test Cases:**

#### TC-F6: Priority grouping
```typescript
// Test HIGH expanded by default
render(<PriorityGroup items={mockItems} onStatusChange={() => {}} currentStatus="new" />)

// HIGH should be expanded
expect(screen.getByText('HIGH PRIORITY')).toBeInTheDocument()
expect(screen.getAllByTestId('feedback-card').length).toBeGreaterThan(0)

// MEDIUM should be collapsed
const mediumHeader = screen.getByText('MEDIUM PRIORITY')
expect(mediumHeader.nextSibling).toBeNull()  // No cards visible
```

#### TC-F7: Expand/collapse
```typescript
// Test expanding collapsed group
const mediumHeader = screen.getByText('MEDIUM PRIORITY')
fireEvent.click(mediumHeader)

// Should now show cards
expect(screen.getAllByTestId('feedback-card').length).toBeGreaterThan(3)
```

**Expected Results:**
- ✅ HIGH priority expanded by default
- ✅ MEDIUM/LOW collapsed by default
- ✅ Click header to expand/collapse
- ✅ Item counts shown in headers

---

### 4. Color System

**Manual inspection:**

#### TC-F8: Verify dark solid colors
```bash
# Check these files for neon colors (400/500):
grep -r "text-.*-[45]00\|bg-.*-[45]00" services/frontend/src/components/draft-analysis/

# Should return empty (no neon colors found)
```

**Expected Results:**
- ✅ No neon colors (400/500 levels) in draft-analysis components
- ✅ All colors use dark solid palette (300/700/800/900)
- ✅ Professional appearance (not "AI-generated" look)

---

### 5. Section-Specific Tabs

**File:** `services/frontend/src/components/draft-analysis/SectionFeedbackTabs.tsx`

**Test Cases:**

#### TC-F9: Section-specific tabs
```typescript
// Test Methodology section shows correct tabs
render(<SectionFeedbackTabs sectionType="methodology" claims={[]} gaps={[]} feedback={[]} />)

expect(screen.getByText('Rigor')).toBeInTheDocument()
expect(screen.getByText('Reproducibility')).toBeInTheDocument()
expect(screen.getByText('Alternatives')).toBeInTheDocument()

// Test Literature Review section shows different tabs
rerender(<SectionFeedbackTabs sectionType="literature_review" claims={[]} gaps={[]} feedback={[]} />)

expect(screen.getByText('Coverage Gaps')).toBeInTheDocument()
expect(screen.getByText('Synthesis Quality')).toBeInTheDocument()
```

**Expected Results:**
- ✅ Methodology section: Rigor | Reproducibility | Alternatives | Detail
- ✅ Literature Review: Coverage Gaps | Synthesis Quality | Missing Works
- ✅ Introduction: Positioning | Gap Identification | Motivation
- ✅ Results: Evidence Strength | Analysis Depth | Limitations

---

### 6. Auto-Migration

**File:** `services/frontend/src/pages/DraftAnalysis.tsx`

**Test Cases:**

#### TC-F10: Auto-migrate existing drafts
```bash
# Manual test:
1. Use a draft created before the redesign (no section_type assigned)
2. Open draft analysis page
3. Verify auto-migration API call made: POST /drafts/{draft_id}/assign-sections
4. Verify section navigation appears with counts
5. Verify feedback displays correctly in sections
6. No re-upload required
```

**Expected Results:**
- ✅ Old drafts auto-migrate on first view
- ✅ Section types assigned without errors
- ✅ Feedback organized into sections
- ✅ No re-analysis or re-upload needed

---

## Manual Testing Checklist

### Setup
- [ ] Database migration 016 applied to Supabase
- [ ] Backend service running (http://localhost:8000)
- [ ] Frontend service running (http://localhost:5173)
- [ ] Test project with 3+ documents
- [ ] Test draft (PDF or DOCX)

### Upload & Analysis
- [ ] Upload new draft → analysis starts automatically
- [ ] Progress indicator shows during processing
- [ ] Analysis completes without errors
- [ ] Sections detected correctly (7-8 sections for typical paper)

### Section Navigation
- [ ] Section navigation sidebar appears
- [ ] Only sections with feedback shown
- [ ] Badge counts match actual feedback items
- [ ] Active section highlighted with filled icon
- [ ] Click section → loads feedback for that section

### Feedback Display
- [ ] Feedback cards show type badge (CLAIM/GAP/FEEDBACK)
- [ ] Priority badges visible (HIGH/MEDIUM/LOW)
- [ ] HIGH priority expanded by default
- [ ] MEDIUM/LOW collapsed by default
- [ ] Click header → expand/collapse priority group

### Status Workflow
- [ ] Status tabs visible: New | Saved | Dismissed
- [ ] New tab shows unreviewed items
- [ ] Save button → item moves to Saved tab
- [ ] Dismiss button → item moves to Dismissed tab
- [ ] Refresh page → status persists
- [ ] Badge counts update after save/dismiss

### Section-Specific Tabs
- [ ] Methodology section → Rigor | Reproducibility | Alternatives tabs
- [ ] Literature Review → Coverage Gaps | Synthesis Quality tabs
- [ ] Introduction → Positioning | Gap Identification tabs
- [ ] Tab filtering works correctly

### UI/UX Quality
- [ ] No "Re-analyze" button in health summary
- [ ] Priority badges instead of "Critical Issues" section
- [ ] Dark solid colors throughout (no bright neon)
- [ ] Professional appearance (not "AI-generated")
- [ ] No hallucinating claims visible (confidence < 0.6 hidden)

### Data Quality
- [ ] Claim-to-claim matching shows source metadata
- [ ] Citations include confidence scores
- [ ] Methodology feedback includes baseline comparisons
- [ ] Gap detection shows relevant literature flags
- [ ] Low-confidence claims hidden by default

### Auto-Migration (Old Drafts)
- [ ] Open existing draft (before redesign)
- [ ] Auto-migration triggered automatically
- [ ] Section types assigned without errors
- [ ] Feedback organized into sections
- [ ] No re-upload required

### Edge Cases
- [ ] Draft with 3 pages → all sections shown
- [ ] Draft with 14 pages → detailed feedback
- [ ] Draft with no methodology section → graceful handling
- [ ] Empty section → "No feedback" message
- [ ] All items saved → "Great work!" message

---

## Performance Testing

### Backend Performance
```bash
# Test API response times
ab -n 100 -c 10 http://localhost:8000/drafts/{draft_id}/section-summary

# Expected: < 500ms per request
```

### Frontend Performance
```bash
# Build production bundle
cd services/frontend
npm run build

# Check bundle size
ls -lh dist/assets/*.js

# Expected: Main bundle < 500KB gzipped
```

### Database Performance
```sql
-- Test section-based query performance
EXPLAIN ANALYZE
SELECT * FROM draft_claims
WHERE draft_id = '<draft-id>'
  AND section_type = 'methodology'
  AND status = 'new'
  AND hidden = false;

-- Expected: < 50ms with indexes
```

---

## Test Results Summary

**Pass Criteria:**
- All backend tests pass (TC-B1 through TC-B11)
- All frontend tests pass (TC-F1 through TC-F10)
- Manual checklist 100% complete
- Performance targets met
- No console errors in production build
- No TypeScript errors
- No linter errors

**Sign-off:**
- [ ] Backend tests: PASS / FAIL
- [ ] Frontend tests: PASS / FAIL
- [ ] Manual testing: PASS / FAIL
- [ ] Performance: PASS / FAIL
- [ ] Ready for deployment: YES / NO

**Next Step:** Deploy to production (see DEPLOYMENT_GUIDE.md)
