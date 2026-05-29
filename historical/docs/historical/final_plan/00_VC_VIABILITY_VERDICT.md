# Noesis — VC Viability Verdict
*Full C-Level Board Evaluation | March 2026*
*Prepared as if: VC partner who has read every document and visited the live product*

---

## BOARD VERDICT: CONDITIONAL CONTINUE

**The thesis is right. The sequencing is catastrophically wrong. You have 60 days to fix it.**

The core hypothesis — that academic researchers need pre-submission peer review and will pay for it — is validated by the market (Elicit raised $18M, Scite was acquired, academic SaaS has proven WTP). The specific wedge — draft-aware critique grounded in the researcher's own literature — is genuinely differentiated. No competitor does this.

The problem: after 3 sprint cycles of significant engineering, you cannot produce a single authentic testimonial from a PI who says "this caught something real." That bar — the lowest possible PMF signal — has not been cleared.

---

## CRITICAL RISKS (Ranked by Severity)

### ✅ RESOLVED: GPT-5.2 Model Validity (March 10, 2026)

**Verified — both model IDs are valid and working.**

Tested live from the `noesis-backend` container:
- `gpt-5.2` ✅ confirmed working
- `gpt-5.2-chat-latest` ✅ confirmed working
- `max_completion_tokens` ✅ accepted correctly by both

All 15 migrated files are using the correct API contract. This risk is cleared.

### 🔴 CRITICAL: 0 Paying Customers After Months of Engineering

**The facts:**
- 3 sprint cycles of engineering completed
- 88 React components, 44+ backend services
- Stripe integration live (but CTAs may be disabled/broken on live site)
- 0 paying users
- 0 confirmed testimonials from real researchers
- Success metric from sprint plan ("any PI says this caught something") not achieved

**The implication:** This is not a product problem — it is a distribution and validation problem. No amount of additional engineering will fix this.

### 🟡 HIGH: Live Site vs. Codebase Discrepancy

The landing page in code says "Know What Reviewer 2 Will Say Before You Submit" but the live site may show different copy (pre-sprint messaging). All Sprint 01-03 changes need to be deployed before any outreach happens. **Do not outreach to PIs against a landing page that doesn't reflect the product value proposition.**

### 🟡 HIGH: University Logo Claim Risk

"Used by researchers at Georgia Tech, Rice University, UT Austin, Texas A&M, UNC, University of Houston" is displayed as social proof. If there are no verified users from these institutions, this is:
1. **Legally risky**: potentially false advertising
2. **Trust-destroying**: if a PI from Georgia Tech visits and investigates, one bad tweet ends the launch
3. **Ethics violation**: startups have been torpedoed for unverified social proof claims

**Action: Remove all institution name/logo claims immediately unless you can name the actual researcher who uses it.** Replace with "Researchers from major R1 universities" until verified.

### 🟡 HIGH: Browser Extension Deferred Twice

The browser extension was identified as the #1 UX friction item (workflow silo problem) 6+ weeks ago. It was deferred in Sprint 01 and Sprint 02. The product currently requires researchers to:
1. Leave their writing environment (Google Docs / Overleaf / Word)
2. Log into a separate web app
3. Upload their draft manually
4. Wait for processing
5. Read feedback in a separate tab
6. Return to their writing environment and manually implement changes

This is not a workflow improvement — it's a workflow tax. Researchers who don't have extreme motivation will not adopt it. **The browser extension IS the product.** Everything else is infrastructure.

### 🟠 MEDIUM: 3 Tests for 44+ Services

There is no automated way to detect quality regression. When prompt changes or model changes happen, analysis quality silently degrades. Users experience worse results and churn without filing a support ticket. At this stage of zero retention data, silent quality degradation could be the reason no one returns.

### 🟠 MEDIUM: Beta/Paid Messaging Conflict

Footer says "Beta Period: All features are free" while the pricing page shows $12/$49/$20 tiers. This confuses users:
- Is this free or paid?
- If I sign up during beta, do I get locked in at free?
- Why is there a pricing page if it's free?

Remove the beta messaging entirely, or make it explicit: "Beta ends [date] — sign up now, your first month is free."

---

## MARKET SIZING (TAM/SAM/SOM)

### Total Addressable Market
- Global academic researchers: ~8M active publishing researchers
- US R1 university researchers (primary target): ~400K
- Annual publications in STEM: ~3M papers/year

### Serviceable Addressable Market
- Researchers publishing 1+ papers/year who need pre-submission review: ~1.5M globally
- US focus (Year 1): ~300K researchers
- Subset who use AI tools: ~20% = 60K researchers

### Serviceable Obtainable Market (3-year horizon)
- With sustained distribution: 1-3% of SAM = 600-1,800 paying researchers
- At $12 Pro / $49 Lab average blended ARPU ~$20/month
- SOM revenue: $144K - $432K ARR in Year 3

**This is a real business. It is NOT a $1B business on this trajectory.** The path to venture-scale is: (1) prove the individual researcher market, (2) move up to institutional licensing (university libraries pay $10K-50K/year for faculty tools), (3) expand internationally. That's a 5-7 year journey, not 18 months.

---

## FUNDRAISING READINESS ASSESSMENT

| Metric | Current | Seed Target | Series A Target |
|---|---|---|---|
| ARR | $0 | $60K ($5K MRR) | $1.2M ($100K MRR) |
| Active users | Unknown | 500+ MAU | 5,000+ MAU |
| Activation rate | Unknown | >30% | >40% |
| Day-30 retention | Unknown | >20% | >35% |
| Paying users | 0 | 50+ | 500+ |
| Organic growth | None | 10%+ MoM | 20%+ MoM |
| Team size | 2 (founders only) | 2-3 | 8-12 |

**Fundraising recommendation: Do NOT raise seed capital now.**

Raising at $0 ARR with 2 technical founders and no traction means:
- Pre-money valuation: $500K - $2M (idea-stage)
- Giving up 15-25% for $200-500K
- That capital buys 12 months of runway but doesn't fix the distribution problem
- You'll be raising Series A in 12 months with the same problem but more dilution

**Wait until:** $5K MRR for 2 consecutive months + Day-7 retention > 20% + 3+ institutional users.

At that point, pre-money valuation jumps to $3-8M, you raise on better terms, and the data tells the story.

---

## COMPETITIVE POSITIONING (HONEST)

| Competitor | What They Do | ARR/Status | Noesis Advantage | Noesis Risk |
|---|---|---|---|---|
| Elicit | Literature discovery, paper Q&A | ~$18M ARR | Draft-aware critique vs. just discovery | Elicit is far ahead on distribution |
| Scite | Citation sentiment tracking | Acquired (~$20-30M) | Full reviewer feedback vs. just sentiment | Scite has institutional contracts |
| SciSpace | Paper summarization + chat | ~$5-10M ARR est. | Draft-specific analysis vs. general papers | SciSpace has 10M+ users |
| Research Rabbit | Citation network mapping | Free, VC-backed | Actionable critique vs. just visualization | Research Rabbit owns discovery |
| Semantic Scholar | Paper search/discovery | Free, Allen AI | Reviewer simulation vs. search | Semantic Scholar has 200M+ papers |
| Grammarly for Science | Writing assistance | Not yet real | Different category — critique vs. grammar | Could be built by Grammarly |

**Defensible position:** None of these do draft-aware pre-submission review. The positioning "Know What Reviewer 2 Will Say Before You Submit" is genuinely differentiated. The risk is that Elicit or SciSpace ships this feature in 6 months once Noesis proves the market.

**The moat is time, not technology.** Get to institutional contracts before competitors notice.

---

## 6-MONTH EXECUTIVE ROADMAP

### Month 1: Stop Building, Start Validating
- **Ashwin:** Verify GPT model ID. Fix it if broken. Browser extension only.
- **Praneel:** 50 PI conversations. Find the quote. Fix university claims.
- **Milestone:** "This caught a real reviewer comment" from 3+ PIs.
- **Go/No-Go:** If no authentic quote after 50 conversations → product is not ready. Rebuild from user feedback.

### Month 2: Fix the Workflow, Not the Dashboard
- **Ashwin:** Browser extension MVP (Chrome, Overleaf sidebar). Deploy all sprint changes.
- **Praneel:** 20 demos with the browser extension. Enable Stripe.
- **Milestone:** 5 paying users ($60-250 MRR). Extension installs > 50.
- **Go/No-Go:** If < 5 paying after demos with working extension → pricing or value proposition problem.

### Month 3: First Revenue
- **Ashwin:** Fix quality issues surfaced from Month 2 users. WebSocket streaming.
- **Praneel:** Outreach to Overleaf community, academic Twitter, r/PhD.
- **Milestone:** $1,000+ MRR (80 Pro or 20 Lab users). Day-7 retention > 20%.
- **Go/No-Go:** $1K MRR = continue. <$500 MRR = serious pivot conversation.

### Month 4: Distribution Channels
- **Ashwin:** RAG quality improvements. Adaptive chunking.
- **Praneel:** Product Hunt launch. University library outreach (3+ conversations).
- **Milestone:** $3,000+ MRR. 1 university pilot conversation active.
- **Go/No-Go:** If Product Hunt launches with <100 upvotes and no organic signups → distribution playbook needs rebuilding.

### Month 5: Institutional Signal
- **Both:** University library pilot (1 institution, 10 researchers, free for 60 days).
- **Milestone:** $5,000 MRR. Pilot institution feedback documented.
- **Fundraising:** Begin investor conversations with data in hand.

### Month 6: Seed Round or Reset
- **Target:** $5K-10K MRR (revised from $50K — see CFO analysis).
- **Raise:** $500K-1.5M seed at $4-8M pre-money if metrics are at target.
- **Alternatively:** If $2K MRR and institutional pilot active → bridge on SAFE, extend runway, continue.
- **Hard stop:** If < $2K MRR and no institutional interest → product-market fit is not proven. Pivot to a single-feature product or shut down.

---

## HONEST FOUNDER FEEDBACK

**For Ashwin:** You are an excellent engineer who has built a technically impressive system. The instinct to build is correct — but the sequencing is wrong. Stop adding features. The product is good enough to validate. Build the browser extension (2-3 weeks), then talk to 50 users. That conversation is the hardest thing you'll do and the most valuable.

**For Praneel:** "10 PI outreach calls" has appeared in the sprint plan for 3 consecutive sprints. If these haven't happened yet, the GTM function is not operational. Non-technical founders live and die by conversations. 50 conversations in 30 days — with recording, notes, and explicit asks — is the job right now. Nothing else.

**For both:** The $50K MRR by Month 6 target is not realistic from zero. Reset expectations to $10K MRR by Month 9. A $10K MRR academic SaaS with institutional traction is fundable at a fair valuation. A $50K MRR miss demoralizes the team and sets a false failure narrative.

---

## DECISION LOG

| Decision | Recommendation | Rationale |
|---|---|---|
| Raise seed capital now | ❌ Do NOT raise | No traction, would raise at bad terms |
| Continue building features | ❌ Stop | Browser extension only for next 8 weeks |
| Keep existing pricing | ✅ Keep | $12/$49 is reasonable; test conversion first |
| Remove university logo claims | ✅ Remove immediately | Legal and trust risk |
| Verify GPT-5.2 model | ✅ Do today | Product may be broken in production |
| Run browser extension sprint | ✅ Build now | Highest-leverage item, deferred twice already |
| 30-day outreach sprint (Praneel) | ✅ 50 PI conversations | Must happen before any growth push |

---

*This verdict is intentionally harsh. A VC would not be this honest — they'd pass quietly. The founders deserve the truth.*
