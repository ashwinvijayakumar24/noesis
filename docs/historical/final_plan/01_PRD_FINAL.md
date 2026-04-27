# Noesis — Final Product Requirements Document (v1.0)
*Product Manager Toolkit Framework | March 2026*
*Owner: Ashwin (technical lead) | Reviewed by: Praneel (GTM lead)*

---

## Product Vision

**"Know What Reviewer 2 Will Say Before You Submit."**

Noesis is the pre-submission peer review layer for academic research. It takes a researcher's draft manuscript + their literature collection and produces structured, evidence-grounded critique — the kind a senior colleague or experienced reviewer would give, but available at 2am on a Sunday before a conference deadline.

**What Noesis is NOT:**
- Not a writing assistant (no auto-rewriting)
- Not a literature discovery tool (Elicit owns that)
- Not a grammar checker (Grammarly owns that)
- Not a citation manager (Zotero/Mendeley own that)

**What Noesis IS:**
- The only tool that reads YOUR draft + YOUR library and says "here's what a reviewer will flag"
- Evidence-grounded critique (every feedback item traces to specific literature passages)
- A coverage gap detector (what literature are you missing that reviewers will notice)
- A claim defensibility checker (which of your claims lack citation support)

---

## Jobs to be Done

### Primary Buyer: Principal Investigator (PI)

**JTBD:** "When I have a draft from my lab that needs to go to a top-tier journal, I want to know exactly what reviewers will object to before I submit, so I can protect my publication timeline and my grant deliverables."

**Context:** PIs manage lab output, not just their own papers. They review 2-5 student drafts before submission. Senior PIs have been burned by Reviewer 2 objections that could have been caught. They have grant budgets. They are the buyer.

**Pain intensity:** 9/10. A rejected paper can delay a grant renewal by 6-12 months. One resubmission cycle = 3-6 months lost. Stakes are extremely high.

**Price sensitivity:** Low. $49/month for a lab is noise against a $500K NSF grant budget.

### Secondary User: Postdoc

**JTBD:** "When I'm preparing my first author paper for submission, I want expert feedback on my draft without waiting for my PI's busy schedule, so I can iterate faster and build my publication record."

**Context:** Postdocs are under intense publication pressure. They have limited access to senior feedback. They're often 6-12 months from the job market. They will pay $12/month from their own pocket if the value is clear.

**Pain intensity:** 8/10. Publication speed directly affects career trajectory.

**Price sensitivity:** Medium. $12 is in the range of a personal expense; $49 requires lab budget approval.

### Tertiary User: PhD Student

**JTBD:** "When I'm writing my first journal paper, I want to understand if my arguments are defensible before my advisor sees it, so I can stop being embarrassed in lab meetings."

**Context:** PhD students are the largest volume segment but lowest conversion. They're budget-constrained and often need to use free tier. They are good for activation metrics and referrals but not primary revenue.

**Pain intensity:** 7/10. Anxiety about advisor feedback is real but less acute than grant risk.

**Price sensitivity:** High. Will not pay $12/month reliably. Lab tier (shared by PI) is their path.

---

## RICE Prioritization — All Candidate Features

*Reach: # users impacted per quarter | Impact: 1-10 | Confidence: % | Effort: weeks*

| Feature | Reach | Impact | Confidence | Effort (wks) | RICE Score | Decision |
|---|---|---|---|---|---|---|
| **Browser Extension (Chrome/Overleaf)** | 300 | 10 | 85% | 3 | **850** | ✅ Build Sprint 1 |
| **WebSocket Progress Streaming** | 150 | 7 | 90% | 1.5 | **630** | ✅ Build Sprint 1 |
| **Deploy All Sprint 1-3 Changes** | 500 | 9 | 99% | 0.5 | **8,910** | ✅ Do TODAY |
| **Remove University Fake Claims** | 500 | 9 | 99% | 0.1 | **44,550** | ✅ Do TODAY |
| **Verify GPT Model ID** | 500 | 10 | 99% | 0.1 | **49,500** | ✅ Do TODAY |
| **Overleaf API Integration** | 200 | 9 | 60% | 5 | **216** | ⚠️ Partner Track |
| **RAG Adaptive Chunking** | 100 | 7 | 80% | 2 | **280** | ✅ Build Sprint 2 |
| **Remove User RAG Settings UI** | 200 | 5 | 95% | 0.3 | **3,167** | ✅ Do Sprint 1 |
| **Dispute Suppression Logic** | 80 | 5 | 70% | 1 | **280** | ⚠️ Post-PMF |
| **Human-in-Loop Claim Validation** | 40 | 4 | 50% | 3 | **27** | ❌ Cut for now |
| **Team Real-time Collaboration** | 20 | 6 | 40% | 8 | **6** | ❌ Series A feature |
| **Word/DOCX Export** | 60 | 4 | 70% | 1.5 | **112** | ⚠️ Sprint 3 |
| **Overleaf Direct Export** | 100 | 8 | 50% | 4 | **100** | ⚠️ Partner Track |
| **Grant Proposal Mode** | 40 | 7 | 50% | 4 | **35** | ❌ Post-$10K MRR |
| **Argument Structure Visualization** | 50 | 5 | 60% | 6 | **25** | ❌ Cut |
| **Section-Aware Chunking** | 100 | 7 | 80% | 2 | **280** | ✅ Build Sprint 2 |
| **Test Coverage (44+ services)** | 0 | 8 | 99% | 4 | **0 (risk mitigation)** | ✅ Sprint 2 |
| **Testimonial System** | 200 | 7 | 80% | 1 | **1,120** | ✅ Sprint 1 |

---

## User Journey Map — Current State vs. Target State

### Current State (Broken)

```
[Researcher in Overleaf at 11pm]
        ↓ (leaves writing environment)
[Opens noesis.is in new tab]
        ↓ (creates account)
[Creates project] — 60% drop-off here (why do I need a "project"?)
        ↓
[Uploads PDF of draft] — 45% drop-off here (have to convert from .docx first)
        ↓ (waits 2-5 minutes, no progress indicator)
[Black box processing screen] — 30% abandon during wait
        ↓
[Views analysis results] — 20% of original visitors reach this
        ↓ (has to manually cross-reference with draft in other tab)
[Reads feedback, doesn't know what to do next] — <5% return for v2
```

**Estimated funnel:**
- Visit → Signup: 5-8%
- Signup → First Analysis: 15-25%
- First Analysis → Return: 5-10%
- Return → Paid: 2-5%
- **End-to-end paid conversion: <0.1%**

### Target State (After Browser Extension)

```
[Researcher in Overleaf writing their draft]
        ↓ (clicks Noesis sidebar icon, already installed)
[Noesis sidebar opens in Overleaf] — no tab switching
        ↓ (one click: "Analyze against my library")
[Real-time streaming progress: "Extracting claims... Finding coverage gaps..."]
        ↓ (2-3 minutes, visible progress)
[Feedback appears in sidebar, inline with draft sections]
        ↓ (click on feedback → jump to relevant draft section)
[Researcher edits draft with Noesis sidebar open] — habit forming
        ↓ (re-analyze v2 → sees improvement score)
[Sees "Draft Score improved from 74 → 89"] — retention hook
```

**Target funnel:**
- Extension install → First Analysis: 60-70%
- First Analysis → Return within 7 days: 30-40%
- Return → Paid Conversion: 8-12%
- **End-to-end paid conversion: 2-4%** (20-40x improvement)

---

## Activation Friction Analysis

### Friction Point 1: "Why do I need a project?" (CRITICAL)
**Problem:** The first thing a new user must do is create a "Project" — an abstraction that doesn't map to how researchers think. Researchers think: "I'm working on my CRISPR paper."
**Fix:** Rename to "Paper" or "Manuscript." Auto-create one on signup with a guided first action.

### Friction Point 2: "I have to upload a PDF but my draft is in Overleaf" (CRITICAL)
**Problem:** Researchers write in Overleaf/Google Docs. Getting a PDF requires manual export.
**Fix:** Browser extension provides direct integration. For web app: accept URL (arXiv preprint link) + Google Docs URL as alternative to PDF upload.

### Friction Point 3: "I have to rebuild my entire library" (HIGH)
**Problem:** Uploading 50 papers one-by-one is hours of work.
**Fix:** BibTeX import (DONE ✅). Also: arXiv URL import (paste URL, auto-fetch metadata + PDF).

### Friction Point 4: "It's been 3 minutes and nothing happened" (HIGH)
**Problem:** Analysis takes 2-5 minutes. No progress indicator. Users think it's broken.
**Fix:** WebSocket streaming with step-by-step progress updates. CRITICAL for conversion.

### Friction Point 5: "The feedback is generic, not specific to my paper" (MEDIUM)
**Problem:** If analysis quality is low, feedback reads as generic AI criticism.
**Fix:** Source grounding (DONE ✅). Ensure every feedback item quotes exact literature passage.

### Friction Point 6: "I can see the feedback but I don't know how to fix my draft" (MEDIUM)
**Problem:** Feedback says "Claim X lacks support" but researcher doesn't know which passage to cite.
**Fix:** One-click "Find Supporting Citations" on every feedback item → surfaces top 3 matching papers from their library with relevant excerpts.

---

## Feature Flag Strategy

### Free Tier — Enough to Validate the Core Value
- 1 draft analysis per month (not per document — per analysis run)
- 5 documents in library
- 3 paper discovery searches per day
- Standard reviewer feedback (no granular claim-level detail)
- **No:** Source grounding on feedback, draft comparison, export

### Pro Tier ($12/month) — Full Individual Researcher Workflow
- 10 draft analyses per month
- Unlimited documents
- Unlimited paper discovery
- Full source grounding on all feedback
- Draft version comparison (improvement score)
- BibTeX export + PDF report export
- Priority processing queue

### Lab Tier ($49/month, up to 5 users) — PI + Lab Workflow
- Everything in Pro, for 5 users
- Lab project sharing (PI sees all students' drafts)
- Lab-wide citation library (shared documents)
- Lab analytics (which students are using it, activation tracking)
- PI dashboard showing team's draft health scores
- Priority support

### Enterprise (Custom) — University Library / Department
- Unlimited users
- SSO/SAML integration
- Custom data retention policies
- Quarterly review with success team
- Starting at $2,000/month

---

## Competitive Positioning Matrix

| Capability | Noesis | Elicit | Scite | SciSpace | Research Rabbit |
|---|---|---|---|---|---|
| Draft upload + analysis | ✅ Core | ❌ | ❌ | ❌ | ❌ |
| Claim extraction | ✅ | ❌ | ❌ | ❌ | ❌ |
| Coverage gap detection | ✅ | ⚠️ basic | ❌ | ❌ | ❌ |
| Reviewer simulation | ✅ | ❌ | ❌ | ❌ | ❌ |
| Literature discovery | ⚠️ via agent | ✅ Core | ❌ | ✅ | ✅ Core |
| Citation sentiment | ❌ | ❌ | ✅ Core | ❌ | ❌ |
| Paper summarization | ⚠️ via RAG | ✅ | ❌ | ✅ Core | ❌ |
| BibTeX import/export | ✅ | ❌ | ⚠️ | ❌ | ❌ |
| Overleaf integration | 🔴 Planned | ❌ | ❌ | ❌ | ❌ |
| Browser extension | 🔴 Planned | ❌ | ❌ | ❌ | ❌ |
| Free tier | ✅ | ✅ | ✅ | ✅ | ✅ |
| Institutional pricing | ✅ | ✅ | ✅ | ✅ | ❌ |

**Positioning Statement (internal):** Noesis is the only tool that analyzes YOUR draft against YOUR literature and tells you what reviewers will object to — before you submit.

**Elevator Pitch (Praneel's line):** "You know how you submit a paper and Reviewer 2 says your methodology section ignores three important papers from 2023? Noesis tells you that before you submit, so you can address it."

---

## PRD Scope: What's In v1.0

### IN (Required for v1.0)
- [x] Draft upload (PDF, DOCX, TXT)
- [x] Document library with BibTeX import
- [x] AI claim extraction and categorization
- [x] Coverage gap detection
- [x] Reviewer feedback with source grounding
- [x] Draft version comparison (improvement score)
- [x] Paper discovery (PubMed/arXiv/Semantic Scholar)
- [x] Stripe checkout (Pro + Lab tiers)
- [x] Export: BibTeX, PDF report, JSON
- [ ] Browser extension (Chrome + Overleaf) — **BUILD NEXT**
- [ ] WebSocket progress streaming — **BUILD NEXT**
- [ ] Deploy all sprint changes — **DO TODAY**

### OUT (Explicitly Deferred — NOT in v1.0)
- ❌ Real-time collaboration (multi-user editing)
- ❌ Word/LaTeX editor integration (beyond extension)
- ❌ Grant proposal mode (adjacent use case)
- ❌ Argument structure visualization
- ❌ Human-in-loop claim validation UI
- ❌ Video tutorial / interactive onboarding (use text for now)
- ❌ Mobile app
- ❌ Slack/email notification integrations

### MAYBE (Include if done in <1 week total effort)
- ⚠️ arXiv URL direct import (paste link → auto-fetch paper)
- ⚠️ Google Scholar integration (read-only)
- ⚠️ Rename "Project" → "Manuscript" in all UI

---

## Success Metrics for v1.0

| Metric | Target | Measurement |
|---|---|---|
| Activation rate | >30% (signup → first draft analyzed) | Supabase analytics |
| Day-7 retention | >20% (return after first analysis) | Supabase analytics |
| Time to first analysis | <5 min from signup | Backend logs |
| NPS score | >40 | In-app survey (n=50+) |
| Paid conversion | >5% of activated users | Stripe |
| Browser extension installs | >100 in first month | Chrome Web Store |
| "Caught something real" quotes | ≥3 authentic testimonials | User interviews |

---

*PRD Version 1.0 | Approved for implementation. Browser extension and WebSocket are the only blocking items before growth push.*
