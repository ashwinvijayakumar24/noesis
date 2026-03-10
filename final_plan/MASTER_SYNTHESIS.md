# Noesis — Master Synthesis & Action Plan
*Wave 3 Synthesis | March 2026*
*This document synthesizes all 7 planning documents into a single source of truth.*

---

## THE ONE-PAGE VERDICT

**Noesis is viable. The market is proven. The product works. The founders have built the wrong things in the wrong order.**

Elicit went from $1M to $18-22M ARR in 2 years by staying focused on their specific wedge (literature discovery) and growing distribution channels before over-engineering. Scite reached $3.6M ARR with 21,000 users before being acquired — that's a real business built on a narrow capability (citation sentiment). Noesis has a MORE defensible position (draft-aware critique) with a MORE sophisticated product — but zero revenue and zero validated users.

**The 3 things that must happen this week:**
1. ~~Verify the GPT model ID works in production.~~ ✅ DONE — `gpt-5.2` and `gpt-5.2-chat-latest` both confirmed working (March 10, 2026).
2. Praneel sends 20 cold emails to PIs today. Not next Monday. Today.
3. Remove the university logo/name claims from the live site. Today.

**The 3 things that must happen this month:**
1. Browser extension ships (Overleaf sidebar, analyze button, feedback display)
2. 10 users analyze their first draft and come back within 7 days
3. One PI says "this caught something a real reviewer would have flagged"

**The 3 things that must NOT happen:**
1. Building any new features before the extension is live and 10 users have validated the core experience
2. Outreach to PIs before the live site reflects the sprint changes (deploy first)
3. Raising seed capital before $5K MRR

---

## DOCUMENT INDEX

| Document | Owner | Key Takeaway |
|---|---|---|
| [00_VC_VIABILITY_VERDICT.md](00_VC_VIABILITY_VERDICT.md) | Both | Don't raise now. Fix GPT model. Get quote from PI. 6-month roadmap. |
| [01_PRD_FINAL.md](01_PRD_FINAL.md) | Ashwin | RICE says: browser extension first, WebSocket second, everything else after PMF. |
| [02_SPRINT_ROADMAP.md](02_SPRINT_ROADMAP.md) | Both | Week-by-week tasks for both founders for 12 weeks. Do not skip steps. |
| [03_GTM_MARKETING.md](03_GTM_MARKETING.md) | Praneel | 30-day outreach calendar, cold email templates, Product Hunt plan, Overleaf partnership. |
| [04_TECHNICAL_ROADMAP.md](04_TECHNICAL_ROADMAP.md) | Ashwin | GPT validation, WebSocket, Chrome extension architecture, test coverage strategy. |
| [05_PRICING_REVENUE.md](05_PRICING_REVENUE.md) | Praneel | Revised projections: $1K MRR Month 3, $5K Month 6. $50K/mo target is unrealistic. |
| [06_METRICS_KPIs.md](06_METRICS_KPIs.md) | Both | Weekly dashboard template + investor-ready KPI definitions + go/no-go triggers. |
| [07_COMPETITIVE_LANDSCAPE.md](07_COMPETITIVE_LANDSCAPE.md) | Both | No competitor does draft-aware critique. Elicit $18-22M ARR is the benchmark to aspire to. |

---

## WHAT TO STOP DOING IMMEDIATELY

For **Ashwin:**
- Stop building new backend services
- Stop refining the analytics dashboard
- Stop building referral system edge cases
- Stop anything related to draft comparison version timelines, recurring patterns, etc.
- **Do:** Fix the foundation. Build the extension. Write tests.

For **Praneel:**
- Stop waiting for the product to be "ready" before doing outreach
- Stop writing sprint plans and pivot analyses
- Stop working on non-technical documents
- **Do:** Send emails. Make calls. Collect quotes. Build a list.

---

## MARKET CONTEXT (Updated with Real Competitive Data)

### What Elicit's Success Tells Us

Elicit went from **$1M ARR (2023)** to **$18-22M ARR (2025)** and just raised a **$22M Series A** in February 2025. That's ~18-22x revenue growth in 2 years, from a tool that does literature discovery — a feature that arguably overlaps with Semantic Scholar's free offering.

**Key lessons:**
1. Academic researchers DO pay for AI research tools — the "academics are cheap" objection is wrong
2. A narrow, well-executed product grows faster than a broad platform (Elicit stayed focused on one thing)
3. The market is large enough for multiple players — Noesis doesn't need to beat Elicit; they need to own the adjacent "critique" category

### What Scite's Acquisition Tells Us

Scite was acquired by Research Solutions (a public academic research company) in December 2023 with **$3.6M annualized subscription revenue** and **21,000 active B2C subscribers**.

**Key lessons:**
1. Academic tools with real users get acquired at meaningful multiples — this is a valid exit path
2. $3.6M ARR → acquisition validates that there are institutional buyers for niche academic SaaS
3. 21,000 active users = the kind of number achievable in 2-3 years for a well-executed product

### Noesis's Target State in 18 Months (Revised)

| Metric | Target |
|---|---|
| ARR | $500K-1M (not $50K/month by Month 6) |
| Active users | 5,000-10,000 |
| Paying users | 500-1,000 |
| Institutional clients | 3-5 university library pilots |
| Raise target | $1-2M seed at $6-10M pre-money |

---

## CRITICAL PATH — DEPENDENCY MAP

```
Today
│
├─► [Ashwin] Verify GPT model ID → If broken: fix immediately
│
├─► [Ashwin] Deploy all sprint changes → Without this, outreach is harmful
│
└─► [Praneel] Remove university claims + Send 20 cold emails

         │
         ▼ (Week 2)

[Ashwin] WebSocket streaming → Users see progress, don't abandon
[Praneel] Follow up on emails → Schedule 5 demo calls

         │
         ▼ (Week 3)

[Ashwin] Browser extension (Overleaf MVP) → First workflow-native users
[Praneel] Demo calls → Collect testimonials

         │
         ▼ (Week 4) ← FIRST MILESTONE: 10 activated users

         │
         ├─► If ≥10 activated: Continue plan
         └─► If <5 activated: STOP. Investigate activation failure before more outreach.

         │
         ▼ (Week 8) ← SECOND MILESTONE: 50 activated, first MRR

         │
         ├─► If MRR ≥ $300: Continue and accelerate
         └─► If MRR = $0: Pricing or value proposition broken. Get on 10 calls to understand why.

         │
         ▼ (Week 12) ← THIRD MILESTONE: $3K MRR, fundraising readiness check

         │
         ├─► If MRR ≥ $3K: Begin investor conversations
         └─► If MRR < $1K: Serious pivot conversation. Not failure — diagnosis.
```

---

## THE "NORTH STAR" QUESTION

Every decision Ashwin and Praneel make for the next 90 days should be filtered through this question:

**"Does this move us closer to 10 users who have analyzed a draft and returned within 7 days?"**

- Building a new feature? → Only if existing users asked for it. Otherwise, no.
- Writing another planning document? → Only if it contains tasks being executed this week. Otherwise, no.
- Doing 5 more cold emails? → Always yes.
- Fixing a bug real users hit? → Always yes.
- Polishing the landing page without user data? → No.
- Adding another analytics feature to the dashboard? → No.
- Doing another Gemini critique session? → No. Execute the plan you have.

---

## WHAT A SUCCESSFUL MONTH 6 LOOKS LIKE

Ashwin and Praneel sit down with an investor who asks: "Tell me about Noesis."

**The answer they should be able to give:**

*"We built the only tool that analyzes a researcher's draft against their own literature and tells them what Reviewer 2 will flag before they submit. We have 150 active users — researchers at 12 universities — and $5K monthly recurring revenue growing 20% month-over-month. Our browser extension is installed in Overleaf by 200+ researchers who use it as part of their submission workflow. We have one university library pilot running at Georgia Tech with 10 PI accounts. A postdoc at Rice told us: 'Noesis caught exactly the methodological gap Reviewer 2 mentioned in their rejection — if I'd used it before submitting, I would have saved 4 months.' We're raising $800K to accelerate distribution and close our first 3 institutional contracts."*

That's the story. Every task in every document in this final_plan/ folder is in service of being able to tell that story.

---

## ACKNOWLEDGMENT OF WHAT COULD KILL THIS

**1. ~~GPT-5.2 is not a valid model.~~** ✅ RESOLVED — Both `gpt-5.2` and `gpt-5.2-chat-latest` verified working on March 10, 2026. `max_completion_tokens` accepted correctly.

**2. Praneel doesn't do the outreach.** The GTM function has been deferred for 3 sprint cycles. If it's deferred again, the company stalls regardless of product quality.

**3. The browser extension stays deferred.** It has been the correct priority for 6+ weeks. If Sprint 02 ends without the extension live, the workflow silo problem remains unsolved and retention will be structurally capped.

**4. A well-funded competitor ships draft analysis.** SciSpace or Elicit could announce this tomorrow. The response: accelerate institutional sales. Make depth of integration (Overleaf extension, BibTeX, structured feedback) the differentiator a big company can't match overnight.

**5. The founders lose confidence before the market validates.** Academic SaaS has a long feedback loop — researchers submit papers twice a year. Month 2 may feel like nothing is working. The data will be thin. This is normal. Trust the metrics framework, not the feelings.

---

*Final_plan generated: March 2026. All 8 documents complete. Source: c-level-skills board meeting, product-skills RICE framework, marketing-skills CRO + GTM + SEO framework, business-growth-skills revenue operations, engineering-skills architecture assessment, competitive intelligence via web search (Elicit $18-22M ARR, Scite $3.6M ARR at acquisition by Research Solutions December 2023).*
