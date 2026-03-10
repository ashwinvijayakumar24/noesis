# Noesis Strategic Analysis & 3-Week Sprint Plan
*Generated: March 2026*

---

## Viability Verdict

**Decision: Continue — Option A (Stay the Course + Sharpen Wedge)**

After full analysis of the codebase, competitive landscape (Elicit $18M ARR, Scite acquired, q.e.d on bioRxiv, SciSpace), and the live product, Noesis is viable and worth continuing. The core product is technically differentiated and the market has proven willingness-to-pay. The problems are distribution and activation friction, not product-market fit.

---

## Gemini Critique: 6 Core Issues & Responses

### Issue 1: Thin Wrapper / No Moat
**Critique:** "This is just GPT-4 calling Supabase." No defensible technical moat.

**Response:** The moat is workflow, not model. Elicit raised $18M building a wrapper too — what matters is workflow fit and switching cost. The draft analysis pipeline (claim extraction → coverage gap detection → citation mapping → reviewer feedback, all grounded in user's own library) is non-trivial to replicate quickly. The real moat is data network effects: as more drafts are analyzed, we'll learn what feedback patterns actually correlate with reviewer acceptance vs. rejection. That's a training signal no one else has.

**Action:** Focus on retention and iteration cycles per user (draft v1 → feedback → revision → draft v2 → better score). Each iteration builds switching cost.

### Issue 2: Broke Academic Market
**Critique:** Academics don't pay for tools, grants don't cover this, researchers are cheap.

**Response:** Partially true, but incomplete. The correct target is PIs (Principal Investigators) with active NSF/NIH grants who have lab budgets. A $49/month "Lab" tier (PI + 4 grad students) is $588/year — trivially small vs. a $500K NSF grant. The framing is wrong: this isn't a "software subscription," it's "pre-submission review insurance." One rejected paper resubmission costs 3-6 months and risks the entire grant deliverable. $49/month is noise.

**Action:** Shift buyer persona from grad students (no budget) to PIs (budget authority). Lead outreach with "protect your publication timeline."

### Issue 3: Crowded Space
**Critique:** Elicit, Scite, Semantic Scholar, SciSpace, Research Rabbit all exist.

**Response:** None of these do draft-aware pre-submission review. Elicit is a literature discovery tool. Scite tracks citation sentiment (who cites a paper skeptically vs. supportively). SciSpace summarizes papers. Research Rabbit maps citation networks. None of them take your draft + your library and say "Reviewer 2 is going to flag claim 3 because it lacks support from the literature you've collected." That's Noesis's specific wedge.

**Action:** Own the "pre-submission review" positioning explicitly. Kill "Research Intelligence Platform" — it sounds like Elicit.

### Issue 4: Workflow Silo
**Critique:** Researchers won't rebuild their library in a new app. Too much friction.

**Response:** This is the #1 activation blocker and it's real. The fix is BibTeX import. Every researcher using Zotero, Mendeley, or Endnote can export their entire library as a .bib file in 30 seconds. Noesis can import that .bib file, create document records with metadata (title, authors, year, abstract, DOI), and researchers can optionally attach PDFs later. This drops the "rebuild your library" friction from hours to seconds.

**Action:** BibTeX import is Priority #1 this sprint.

### Issue 5: Limited Corpus
**Critique:** Users can only analyze papers they've uploaded. Compared to Semantic Scholar's 200M+ papers, this is nothing.

**Response:** The Paper Discovery Agent already exists in the codebase (services/paper_discovery_agent.py) but has been left disabled. It searches PubMed, arXiv, and Semantic Scholar, finds free PDFs, and auto-adds them to projects. Re-enabling this directly addresses the corpus limitation — Noesis can scan 200M+ papers and surface the ones relevant to a user's research gaps.

**Action:** Re-enable Paper Discovery Agent with quotas (3 searches/day free, unlimited Pro).

### Issue 6: Trust Deficit
**Critique:** "How do I know the AI isn't hallucinating these 'gaps' and 'claims'?"

**Response:** Every feedback item needs to show the exact passage from the literature that informed it. "Based on: Zhang et al. (2023) — 'Our model achieved 97.2% accuracy on benchmark X, compared to the 91.4% reported by Liu et al. (2021).'" When researchers can see the grounding passage, they can evaluate whether the AI's critique is valid. Without this, it's a black box and trust never develops.

**Action:** Source citations on every feedback item is Priority #3 this sprint.

---

## 4 Pivot Options Evaluated

### Option A: Stay the Course + Sharpen Wedge ✅ SELECTED
**Verdict: Do this.**
- Keep current positioning but sharpen to "Pre-Submission Peer Review"
- Fix activation blockers (BibTeX import, Paper Discovery)
- Add trust layer (source citations on feedback)
- Shift buyer to PIs with grant budgets

### Option B: Pivot to Lab Workflow Tool
**Verdict: Too early.**
- Requires team features, real-time collaboration, role management
- Months of engineering before first revenue
- Distraction from proving core value

### Option C: Pivot to Conference/Journal Submission Service
**Verdict: Interesting, but kills SaaS model.**
- High-touch, one-time transactions
- Hard to automate, not scalable
- Could be an enterprise pricing tier later, not the core business

### Option D: Pivot to Grant Proposal Review
**Verdict: Adjacent opportunity, not now.**
- Grant proposals and papers share 80% of the same analysis
- Could be a separate feature toggle for "Grant Mode" after core is proven
- Requires different evaluation rubrics and NIH/NSF-specific logic

---

## 3-Week Sprint Plan

### Week 1: Messaging + Core Product Fixes (Days 1–7)

**Technical:**
1. BibTeX Import (Priority #1 — ~8 hours) ← Kills "workflow silo" objection
2. Re-enable Paper Discovery Agent (Priority #2 — ~4 hours) ← Kills "limited corpus" objection
3. Source citations on every feedback item (Priority #3 — ~6 hours) ← Kills "trust deficit" objection
4. Fix free tier limit discrepancy (~1 hour) ← Remove activation friction

**Messaging:**
5. Rewrite landing page hero ← Own "Pre-Submission Peer Review"
6. Outreach pivot to PIs/postdocs ← Target buyers with budget authority

### Week 2: Distribution Leverage + Trust (Days 8–14)

**Technical:**
7. Confidence + dispute system (~4 hours) ← Continuous trust building
8. Draft comparison visibility improvement (~4 hours) ← Core retention mechanic
9. Lab Welcome onboarding flow (~6 hours) ← Viral loop within research groups

**Non-Technical:**
10. arXiv/bioRxiv partnership outreach ← Long-term distribution
11. Academic Twitter content strategy ← Organic growth
12. Overleaf community + partnership ← Distribution at near-zero cost

### Week 3: Monetization + Pricing Fix (Days 15–21)

**Technical:**
13. Lab tier pricing ($49/mo flat for 5 users) + Research Group tier ($149/mo, 15 users)
14. Enable Stripe payments after 25 activated users
15. "Refer a Lab" feature (3+ referrals from same institution → free Lab tier)
16. Browser extension MVP (stretch goal)

**Non-Technical:**
17. Product Hunt launch (Tuesday/Wednesday)
18. 10 PI outreach calls (validate, collect testimonials)
19. First paid users target: 3 paying ($12 Pro or $49 Lab = $36+ MRR)

---

## Success Metrics (Day 21)

- [ ] 25+ activated non-friend users (uploaded ≥1 paper + analyzed ≥1 draft)
- [ ] 3+ paying users ($12 Pro or $49 Lab)
- [ ] BibTeX import working end-to-end
- [ ] Paper Discovery Agent live and used by ≥10 users
- [ ] Source citations visible on all reviewer feedback items
- [ ] arXiv/bioRxiv partnership email sent + acknowledged
- [ ] Product Hunt launched (Top 10 minimum)
- [ ] At least 1 PI: "this would have caught a reviewer comment I actually got"
- [ ] Lab tier pricing live on Stripe

---

## Early Warning Signals

**Stop if:** After this sprint, <5 activated users despite outreach → workflow friction is fundamental. Build browser extension / Overleaf plugin BEFORE growth push. Pause outreach, build the extension, relaunch.

**Pivot UX if:** Activated users don't return after first analysis → analysis quality or UX is failing. Focus 100% on source citation visibility and dispute system before any growth work.

**Keep going if:** Any PI says "this would have caught a comment I actually got" → product-market fit signal. Double down on outreach to that PI's institution immediately.
