# Noesis — Pricing Strategy & Revenue Model
*Business Growth Skills Framework: Revenue Operations + Customer Success*
*Owner: Praneel (pricing decisions) + Ashwin (technical implementation)*
*March 2026*

---

## REVENUE MODEL CRITIQUE

### Current Pricing Structure

| Tier | Price | Users | Monthly Limit |
|---|---|---|---|
| Free | $0 | 1 | 1 draft/mo, 5 docs |
| Pro | $12/mo | 1 | 10 drafts/mo, unlimited docs |
| Lab | $49/mo | Up to 5 | Unlimited |
| Team | $20/user/mo | Min 3 = $60 | Unlimited |

### What's Wrong With This Structure

**Problem 1: Lab vs. Team Pricing Conflict**
- Lab: $49/mo for 5 users = $9.80/user
- Team: $20/user for 3+ users minimum = $60/mo for 3 users
- A PI with 3 people pays $60 on Team but only $49 on Lab — they'd obviously choose Lab
- A PI with 6 people pays $49 on Lab (but can't add more) or $120 on Team
- The pricing break point is unclear and confusing

**Problem 2: Free Tier is Too Generous for Conversion**
- 1 draft/month is plenty for a graduate student who submits twice per year
- The quota wall might never be hit by the primary users
- This means the upgrade pressure is low

**Problem 3: $12 Pro May Be Too Cheap for PIs, Too Expensive for Students**
- PIs think in terms of lab budgets — $12 is noise but $12 *per person* isn't an obvious value frame
- PhD students have their own money but $12/month adds up (=$144/year)
- The sweet spot might be $15-20 for Pro and position it as "per paper analyzed"

**Problem 4: No Annual Pricing**
- Annual pricing typically improves cash flow (collect 12 months upfront) and retention (committed)
- A researcher who pays $100/year ($8.33/month) is harder to churn than one paying $12/month

### Revised Pricing Recommendation

| Tier | Price | Users | Limits | Positioning |
|---|---|---|---|---|
| Free | $0 | 1 | 2 drafts/mo, 10 docs | "Try it once, seriously" |
| Pro | $15/mo ($12/mo annual) | 1 | Unlimited | "Individual researcher" |
| Lab | $59/mo ($49/mo annual) | Up to 5 | Unlimited + shared library | "PI + lab" |
| Department | $199/mo | Up to 20 | All Lab features + SSO | "Research group" |
| University | Custom | Unlimited | Enterprise + LMS integration | "$2K-5K/mo" |

**Why these changes:**
- Free tier: 2 drafts instead of 1 (enough to experience value, still limited)
- Pro: $15/mo is $180/year — slightly higher but clearly "individual tool" not "team tool"
- Annual discount (20%): improves cash flow, 2x retention vs. monthly
- Drop the confusing Team tier, add Department at a higher price point
- University tier for institutional sales (Month 4+)

---

## PIPELINE: 0 → 100 PAYING USERS

### Stage 1: 0 → 10 paying (Month 1-2)
**Strategy:** Hand-to-hand combat. Personal demos. High touch.

These will be people Praneel personally demos the product to, then follows up with until they convert. Each person will require:
- 1 demo call (15 min)
- 1-2 follow-up emails
- Often: answering specific questions about data privacy, model quality

**Target:** 3 Pro ($12) + 1 Lab ($49) = $85 MRR

**What to do:**
1. Do 50 PI outreach conversations (Week 1-2)
2. Demo to 10 interested people (Week 2-3)
3. Ask 5 of those for a credit card (Week 3-4)
4. Convert 3-4 (Month 1 close)

**Conversion enablers:**
- Offer "first month free, cancel anytime" to reduce friction
- Have Stripe live and tested before first demo
- Create a 2-minute Loom demo video as follow-up

### Stage 2: 10 → 30 paying (Month 2-3)
**Strategy:** Add organic channels + referral activation.

At 10 paying users, you have social proof. Now:
- Ask each paying user for 1 referral (Lab tier gets natural viral spread within labs)
- Post on r/academia and r/PhD (with real testimonials)
- Launch Product Hunt (Week 6-7)

**Target:** 20 Pro ($12) + 5 Lab ($49) + 2 referral-converted users = ~$540 MRR

### Stage 3: 30 → 100 paying (Month 3-5)
**Strategy:** Sustainable acquisition channels.

- SEO content starts ranking (3-month lag from publishing)
- Product Hunt post-launch referral traffic
- Academic conference outreach (find conferences in your target fields, DM presenters)
- University library pilot conversations begin

**Target by Month 5:** 60 Pro ($15) + 20 Lab ($59) + 1 Dept pilot ($199) = $2,279 MRR

---

## REVENUE PROJECTIONS

### Pessimistic Scenario (Things Go Slower Than Expected)

*Assumes: slow activation, high churn, late extension launch*

| Month | Signups (mo) | Active Users | Pro | Lab | Dept | MRR |
|---|---|---|---|---|---|---|
| 1 | 30 | 8 | 2 | 0 | 0 | $30 |
| 2 | 50 | 20 | 5 | 0 | 0 | $75 |
| 3 | 80 | 40 | 10 | 1 | 0 | $199 |
| 4 | 100 | 70 | 20 | 2 | 0 | $398 |
| 5 | 150 | 120 | 35 | 4 | 0 | $761 |
| 6 | 200 | 180 | 50 | 6 | 0 | $1,104 |

**Pessimistic MRR at Month 6:** $1,104

### Realistic Scenario (Consistent Execution)

*Assumes: extension launches Week 3, 20% activation rate, 10% paid conversion, 5% monthly churn*

| Month | Signups (mo) | Active Users | Pro | Lab | Dept | MRR |
|---|---|---|---|---|---|---|
| 1 | 50 | 15 | 3 | 1 | 0 | $94 |
| 2 | 100 | 40 | 10 | 2 | 0 | $248 |
| 3 | 200 | 90 | 25 | 5 | 0 | $670 |
| 4 | 350 | 180 | 50 | 10 | 1 | $1,540 |
| 5 | 500 | 300 | 80 | 18 | 2 | $2,662 |
| 6 | 700 | 450 | 120 | 28 | 3 | $4,052 |

**Realistic MRR at Month 6:** $4,052

### Optimistic Scenario (Viral + Partnership Acceleration)

*Assumes: Overleaf partnership, Product Hunt Top 5, institutional pilot signed*

| Month | Signups (mo) | Active Users | Pro | Lab | Dept | MRR |
|---|---|---|---|---|---|---|
| 1 | 100 | 30 | 8 | 2 | 0 | $218 |
| 2 | 300 | 100 | 30 | 8 | 0 | $842 |
| 3 | 800 | 300 | 90 | 25 | 1 | $2,924 |
| 4 | 1,500 | 700 | 200 | 60 | 3 | $6,540 |
| 5 | 2,500 | 1,200 | 350 | 100 | 5 | $11,240 |
| 6 | 4,000 | 2,000 | 550 | 150 | 8 | $17,342 |

**Optimistic MRR at Month 6:** $17,342

### Reality Check: The $50K MRR by Month 6 Target

The original plan targets $50K MRR at Month 6. The **optimistic** scenario reaches $17K. $50K MRR in 6 months from zero requires:
- ~2,500 paying users
- Or ~400 Lab/Department tier users
- Or 1-2 large institutional contracts ($20-30K/month each)

**Verdict:** The $50K target was aspirational, not operational. Reset to $5K MRR by Month 6 as the seed fundraising trigger. $5K MRR is achievable in the realistic scenario by Month 5-6.

---

## CUSTOMER SUCCESS PLAYBOOK

### Academic SaaS Churn Risk Factors

**Semester-cycle churn:**
- Researchers submit papers at conference deadlines (NeurIPS, ICML, ICLR, Nature, Science submission windows)
- Usage spikes before submission → drops after → churns when "don't need it right now"
- **Counter:** Build habit around the inter-submission period ("use between submissions to build your next draft")

**Grant-cycle churn:**
- NSF/NIH grant submissions happen on fixed cycles (once or twice per year)
- PIs may use Noesis heavily during grant season then cancel
- **Counter:** Lab tier should include grant proposal support (Phase 2 feature)

**Student graduation churn:**
- PhD students who use Noesis graduate and leave their institution
- **Counter:** Personal email signup (not institutional), portable library

**Free tier limbo:**
- Users who never hit the free tier limit and never have a reason to upgrade
- **Counter:** Show "you have X free analyses remaining" prominently. Reduce free tier to 1/month.

### Customer Health Scoring

```python
# Healthy user signals (score 0-100):
def calculate_health_score(user_id: str) -> int:
    score = 0

    # Recency: last login within 14 days (+30)
    if last_login_days <= 14: score += 30

    # Product usage: analyzed draft in last 30 days (+25)
    if recent_analysis_count > 0: score += 25

    # Depth: has 5+ documents in library (+20)
    if document_count >= 5: score += 20

    # Engagement: clicked through on feedback items (+15)
    if feedback_interaction_rate > 0.3: score += 15

    # Social: invited a lab member (+10)
    if lab_invite_sent: score += 10

    return score

# Score interpretation:
# 70-100: Healthy — expansion candidate
# 40-69: Neutral — engagement campaign
# 0-39:  At-risk — rescue campaign
```

### Customer Success by Segment

**Pro Users (Low-touch, self-serve):**
- Onboarding: 3-email sequence (Day 1, Day 4, Day 10)
- Health check: weekly automated score
- Intervention: email when score drops below 40 for 14 days
- Expansion: upgrade prompt when approaching draft limit

**Lab Users (Medium-touch):**
- Onboarding: 30-min onboarding call with Praneel (offer this, don't force it)
- Monthly check-in email: "How's the draft pipeline? Any feedback?"
- Quarterly: "Would a department-wide trial make sense for your group?"

**Department/University (High-touch):**
- Dedicated point of contact (Praneel in Month 1-6)
- Monthly success meeting
- Quarterly business review
- This segment requires at least 2-3 months to close initially

---

## UNIT ECONOMICS

### Cost Per Acquisition (CAC) Targets

| Channel | Target CAC | LTV Needed | LTV at $12/mo, 12-mo retention |
|---|---|---|---|
| Cold outreach | $0 (time cost only) | Any positive | $144 |
| Product Hunt | $5-15 (marketing time) | $30+ | $144 |
| Content/SEO | $10-30 (content time) | $50+ | $144 |
| Paid ads | $50-100 | $150+ | Borderline |
| Conference sponsorship | $500-2,000 | $2,000+ | Lab/Dept tier only |

**LTV Assumptions:**
- Pro user: 12-month average retention (academics submit 2-3 papers/year, renew twice) = $144 LTV
- Lab user: 18-month average retention (PI has ongoing research) = $882 LTV
- Dept user: 24-month average (institutional inertia) = $4,776 LTV

**Gross Margin:**
- Infrastructure cost per active user: ~$0.50-2/month (Supabase, Vercel, OpenAI per-call)
- At $12 Pro: ~85-95% gross margin (SaaS-standard)
- At $49 Lab: ~90-95% gross margin (OpenAI costs spread across 5 users)
- **OpenAI is the main variable cost.** Monitor it weekly. Set a $100/month alert.

---

## WHEN TO TURN ON STRIPE

**Turn on Stripe ONLY after:**
- [ ] 20+ activated users (not just signups — people who have analyzed at least 1 draft)
- [ ] 3+ authentic testimonials collected
- [ ] Browser extension live (the product is complete)
- [ ] All sprint changes deployed to production

**Why wait:** Sending people to a Stripe checkout for a product they haven't validated creates refunds, chargebacks, and damaged trust. Get users activated first, then ask for money.

**First payment ask strategy:** "You've used X draft analyses this month. You're approaching your free limit. Would you like to upgrade to Pro to keep going?" — this is the natural moment. The UpgradeModal already handles this.

---

*Revised targets: $1K MRR by Month 3, $5K MRR by Month 6. These are achievable with consistent outreach execution. The $50K MRR by Month 6 target in the original plan is not realistic from zero and should be removed from founder narrative.*
