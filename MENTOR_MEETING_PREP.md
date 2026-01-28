# Noesis Mentor Meeting Preparation
## I2P First Meeting - January 2025

---

# 1. MEETING AGENDA (15-30 minutes)

## Suggested Time Structure

| Time | Section | Duration | Notes |
|------|---------|----------|-------|
| 0:00 | Introduction & Context | 2-3 min | Who I am, what I'm building, why |
| 3:00 | Live Demo | 5-7 min | Show core workflow, not every feature |
| 10:00 | Honest Assessment | 3-4 min | What's working, what's uncertain |
| 14:00 | Questions for Mentor | 8-12 min | Prepared questions (most valuable time) |
| 26:00 | Next Steps & Close | 2-3 min | Summarize, confirm follow-up |

**Total: 22-29 minutes**

### Contingency if short on time (15 min version):
- Introduction: 2 min
- Demo: 4 min (show only draft analysis flow)
- Questions: 7-8 min
- Close: 1-2 min

---

# 2. MENTOR BRIEF (1 Page)

## Noesis: Draft-Aware Research Intelligence Platform

### The Problem
PhD students and researchers submit papers that get rejected for **preventable reasons**:
- Claims made without proper citations
- Incomplete literature coverage (missing key papers)
- Poor positioning relative to existing work

Advisors are busy. Peer review feedback comes months later. Researchers need expert-level critique *before* they submit.

### What Noesis Does
Noesis analyzes research drafts alongside a user's literature collection to provide **expert reviewer-style feedback**:

1. **Claim Extraction** - AI identifies every assertion in a draft (empirical, theoretical, methodological)
2. **Citation Mapping** - Maps claims to supporting papers in the user's collection
3. **Gap Detection** - Identifies areas where literature coverage is weak or missing
4. **Reviewer Feedback** - Generates academic critique (without rewriting content)
5. **Export** - BibTeX for LaTeX, PDF reports for advisor review

### What Noesis Does NOT Do
- **No auto-writing or rewriting** - We critique, we don't replace the researcher's voice
- **No hallucinated citations** - All suggestions come from the user's uploaded papers
- **Not a chatbot** - It's structured analysis, not general Q&A

### Current State (January 2025)
| Component | Status |
|-----------|--------|
| Core platform | Live at noesis.is |
| Draft analysis pipeline | Working (LangGraph orchestration) |
| Citation management | Working (BibTeX export, multiple formats) |
| RAG chat | Working (but retrieval quality needs improvement) |
| Background processing | Working (Celery + Redis) |
| Infrastructure | Production ($10/month on AWS + Supabase) |
| Users | 0 (pre-launch, not yet marketed) |

### Known Weaknesses (Honest Assessment)
1. **RAG retrieval quality** - Chunking strategy is too basic for academic papers
2. **Analysis depth** - Long papers get shallow analysis (need tiered depth)
3. **No real-time progress** - Users can't see analysis progress
4. **Untested with real users** - Built to spec, not validated with actual researchers

### Short-Term Goals (Next 2 Weeks)
- [ ] Fix critical RAG quality issues (adaptive chunking, hybrid search)
- [ ] Recruit 5-10 beta testers from GT PhD community
- [ ] Conduct first user interviews to validate core value prop

### Semester Goals
- [ ] 50 active beta users with qualitative feedback
- [ ] Validate willingness to pay (10 paid conversions at $9.99/mo)
- [ ] Achieve 70% week-over-week retention
- [ ] Identify clear product-market fit signal (or pivot direction)

### Key Question for This Semester
**Is "draft-aware research intelligence" a real category that researchers will pay for, or is this a feature of a larger tool?**

---

# 3. DEMO WALKTHROUGH SCRIPT

## What to Show (5-7 minutes)

### Setup Before Meeting
- Have a project pre-loaded with 5-10 papers already analyzed
- Have a sample draft already uploaded and analyzed
- Have the demo in an incognito window (fresh session)
- Test everything works 30 min before meeting

### Demo Flow

#### Part 1: Context (30 seconds)
**Say:** "Let me show you what Noesis does with a real example. I've loaded a project with 8 papers from [topic area] and a draft literature review section."

**Don't say:** Don't explain the architecture or tech stack yet.

#### Part 2: Show the Draft Analysis (2 minutes)
**Navigate to:** Draft analysis view

**Say:** "When a researcher uploads their draft, Noesis extracts every claim they make. Here you can see [X] claims identified, categorized by type - empirical claims, theoretical claims, methodological claims."

**Show:** Click on a specific claim

**Say:** "For each claim, we show whether it has citation support from their literature collection. This claim about [topic] is flagged because their uploaded papers don't support it well."

**Don't say:** Don't explain how the AI works or mention GPT-4o.

#### Part 3: Show Coverage Gaps (1 minute)
**Navigate to:** Coverage gaps section

**Say:** "We also detect coverage gaps - areas where the draft touches on topics but the literature collection is thin. This is the 'you're missing key papers in X area' feedback that reviewers often give."

**Don't say:** Don't promise this catches everything.

#### Part 4: Show Citation Suggestions (1 minute)
**Navigate to:** Citation suggestions

**Say:** "For claims that need support, we suggest relevant papers from their collection with confidence scores. One click adds the citation in the right format."

#### Part 5: Show Export (30 seconds)
**Say:** "Everything exports to BibTeX for LaTeX users, or PDF reports they can share with their advisor."

**Show:** Click export, show the BibTeX file briefly.

#### Part 6: Acknowledge Limitations (30 seconds)
**Say:** "I should be clear - this is an analysis tool, not a writing tool. We don't rewrite their work. We also can't find papers they haven't uploaded - it's not a discovery tool. The value is in making the review process faster and catching issues before submission."

### What NOT to Demo
- Don't show the chat feature (it's not the core differentiator)
- Don't show the citation network (cool but secondary)
- Don't show settings or configuration
- Don't show the code or architecture diagrams
- Don't demo a fresh upload (too slow, might fail)

### If Something Breaks
**Say:** "Looks like [X] isn't loading right now - that's one of the things I'm fixing this week. Let me show you [Y] instead."

**Don't:** Apologize excessively or try to debug live.

---

# 4. QUESTIONS TO ASK YOUR MENTOR

## Macro Product Feedback (Pick 2-3)

1. **"Does the 'draft-aware' framing resonate? Or does this feel like a feature rather than a product?"**
   - Why ask: Need to validate if this is a standalone category or just a bolt-on

2. **"If you were a PhD student, at what point in your workflow would you reach for this tool?"**
   - Why ask: Understand the actual trigger moment

3. **"What would make you skeptical of using this for your own research?"**
   - Why ask: Surface trust/adoption barriers

4. **"Is 'no auto-writing' a strength or does it feel like a missing feature?"**
   - Why ask: Validate the core principle vs. market expectation

## Research Workflow Validation (Pick 2-3)

5. **"In your experience, how much time do PhD students actually spend on literature review vs. other tasks?"**
   - Why ask: Validate the time-savings value proposition

6. **"What percentage of paper rejections in your field are due to literature review issues vs. other factors?"**
   - Why ask: Validate the problem severity

7. **"How do researchers in your field typically get pre-submission feedback today?"**
   - Why ask: Understand the competitive alternative (might be "nothing" or "advisor")

8. **"Are there specific disciplines where this would be more or less valuable?"**
   - Why ask: Identify beachhead market

## Startup Direction (Pick 2-3)

9. **"Should I focus on user acquisition now, or continue improving the product before marketing?"**
   - Why ask: Prioritization guidance

10. **"What would you want to see before believing this has product-market fit?"**
    - Why ask: Define success criteria

11. **"Who should I be talking to this semester beyond users? Other founders? Investors? Academics?"**
    - Why ask: Network building

12. **"What's the biggest mistake you see student founders make at this stage?"**
    - Why ask: Pattern matching from experience

## Risk & Ethics (Pick 1-2)

13. **"What ethical concerns would you raise about AI in academic research workflows?"**
    - Why ask: Anticipate objections, show you've thought about this

14. **"How do universities typically view AI tools - and what would help vs. hurt adoption?"**
    - Why ask: Understand institutional dynamics

15. **"Is there a risk this becomes a 'crutch' that makes researchers worse at literature review?"**
    - Why ask: Long-term impact consideration

## Questions to Avoid Asking
- Don't ask: "What features should I build?" (too broad, not their job)
- Don't ask: "Will this succeed?" (unanswerable, puts them on the spot)
- Don't ask: "Can you introduce me to X?" (too early, earn it first)

---

# 5. POST-MEETING FOLLOW-UP EMAIL

**Send within 24 hours. Keep it short.**

---

**Subject:** Thank you - Noesis I2P Meeting Follow-up

Hi [Mentor Name],

Thank you for taking the time to meet with me today about Noesis. I really appreciated your candid feedback, especially [specific insight they shared].

**Key takeaways I'm acting on:**
1. [First concrete action based on their feedback]
2. [Second concrete action]
3. [Third concrete action, if applicable]

**My next steps for the next 2 weeks:**
- [Specific thing you'll do]
- [Specific thing you'll do]
- [Specific thing you'll do]

**One follow-up question** (if you have time to respond):
[Single, specific question that came up or you forgot to ask]

I'll send a brief update before our next meeting on [date if scheduled]. Please don't hesitate to reach out if you think of anything else.

Best,
[Your name]
[Your email]
[noesis.is]

---

# 6. ADDITIONAL PREP NOTES

## If They Ask About Competition
**Say:** "The closest tools are Elicit and Scholarcy, but they focus on paper summarization - they don't analyze the user's own draft. Zotero and Mendeley are reference managers, not analysis tools. The real 'competitor' is the advisor or doing it manually."

## If They Ask About Business Model
**Say:** "Freemium SaaS. Free tier at 10 papers/month, paid tier at $9.99/month for students. Unit economics work at about 69% gross margin. But I'm not focused on revenue yet - first priority is validating that researchers will actually use this consistently."

## If They Ask About Tech
**Say:** "React frontend, Python/FastAPI backend, LangGraph for workflow orchestration, GPT-4o for analysis, Supabase for database and auth. Running on AWS at about $10/month. I can go deeper if helpful, but the tech isn't the risk - user adoption is."

## If They Ask Why You're Building This
**Be honest and personal.** Connect it to your own experience if relevant. Don't give a rehearsed "startup pitch" answer.

## Red Flags to Watch For
- If they seem skeptical of the "no auto-writing" principle, probe deeper
- If they think this should be a feature of an existing tool, that's important signal
- If they question whether this solves a real problem, listen carefully

## What Success Looks Like for This Meeting
- You understand whether your framing resonates with someone who knows research
- You have 2-3 concrete action items
- You've built a relationship, not just given a pitch
- They're willing to meet again or connect you to beta testers

---

# QUICK REFERENCE CARD

**One-liner:** "Noesis catches what reviewers will catch - before you submit."

**What it does:** Analyzes research drafts against your literature to find unsupported claims and coverage gaps.

**What it doesn't do:** Write or rewrite anything.

**Current status:** Live, working, zero users (pre-launch).

**Biggest uncertainty:** Will researchers actually change their workflow to use this?

**This semester:** 50 beta users, validate PMF, find out if this is a product or a feature.
