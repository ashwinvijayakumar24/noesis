# Startup Metrics Explained

**Purpose:** Foundational understanding of key metrics for first-time founders

---

## Growth Metrics

### MAU (Monthly Active Users)
**Definition:** Number of unique users who log in and use the product at least once per month

**Why it matters:** Primary measure of product adoption and growth velocity

**Noesis targets:**
- Month 1: 100 MAU
- Month 3: 2,000 MAU
- Month 6: 20,000 MAU

---

### DAU (Daily Active Users)
**Definition:** Number of unique users who use the product each day

**Why it matters:** Shows product stickiness (how often users return)

**Noesis target:** DAU/MAU ratio of 15-25% is healthy for research tools
- Users don't analyze drafts daily, so lower DAU/MAU is expected
- Power users may check 2-3x per week during active writing periods

---

### Churn Rate
**Definition:** Percentage of users who stop using the product in a given period

**Why it matters:** High churn = product isn't solving real problem

**Noesis targets:**
- Month 1-2: <30% monthly churn (70%+ retention)
- Month 3+: <20% monthly churn (80%+ retention)

**Academic tools benchmark:** 10-20% monthly churn for sticky products

**How to calculate:**
```
Monthly Churn = (Users lost this month / Users at start of month) × 100%
```

---

### Activation Rate
**Definition:** Percentage of signups who complete "aha moment" action

**Aha moment for Noesis:**
- Upload first paper
- Analyze first draft
- See first claim extracted OR first reviewer feedback

**Why it matters:** Users who don't activate never become engaged

**Noesis target:** 40-60% activation rate
- Industry benchmark: 25-40%
- We should beat this with better onboarding

**How to improve:**
- Reduce time to first value (<5 minutes)
- One-click demo (no signup required)
- Email onboarding sequence
- In-app tooltips and guidance

---

## Revenue Metrics (For Future Monetization)

### MRR (Monthly Recurring Revenue)
**Definition:** Predictable revenue per month from subscriptions

**Why it matters:** Shows business health and growth trajectory

**Noesis targets:**
- Month 1-2: $0 (free tier only)
- Month 3: $3,000-7,500 (launch pricing)
- Month 4: $7,500-15,000
- Month 6: $40,000-60,000

**Components:**
- New MRR: Revenue from new customers
- Expansion MRR: Revenue from upgrades (Free → Pro → Team)
- Churned MRR: Revenue lost from cancellations
- Net New MRR = New + Expansion - Churned

---

### ARR (Annual Recurring Revenue)
**Definition:** MRR × 12 (annualized recurring revenue)

**Why it matters:** VCs use ARR to value SaaS companies

**Noesis targets:**
- Month 3: $36K-90K ARR
- Month 6: $480K-720K ARR
- Year 2: $2.5M-3M ARR

**VC Benchmarks:**
- $1M ARR: Seed stage entry point
- $5M ARR: Series A consideration
- $10M+ ARR: Strong Series A candidate

---

### ARPU (Average Revenue Per User)
**Definition:** Total revenue ÷ number of paying users

**Why it matters:** Shows pricing power and user value

**Noesis target:** $12-18/month
- Competitive with Elicit ($12-25/mo)
- Higher than ChatGPT Plus ($20/mo) but more specialized
- Lower than enterprise tools ($50-200/mo) initially

**How to increase ARPU:**
- Team plans ($20/user/mo, minimum 3 users = $20 ARPU per user)
- Enterprise pricing ($10-20K/year per university)
- Feature upsells (advanced analytics, priority support)

---

### LTV (Lifetime Value)
**Definition:** Average revenue per user over their entire lifetime as a customer

**Formula:**
```
LTV = ARPU × (1 / monthly churn rate)
```

**Example:**
- ARPU: $15/month
- Monthly churn: 20%
- Average lifetime: 1 / 0.20 = 5 months
- LTV: $15 × 5 = $75

**Why it matters:** Must be >3x CAC for sustainable business

**Noesis target:** $150-300 LTV
- Assumes $15 ARPU, 20% monthly churn = 5 months average lifetime
- Or $12 ARPU, 10% monthly churn = 10 months average lifetime = $120 LTV
- Enterprise customers: Much higher LTV ($10K+)

---

### CAC (Customer Acquisition Cost)
**Definition:** Total sales/marketing spend ÷ number of new customers acquired

**Why it matters:** If CAC > LTV, you lose money on each customer

**Noesis target:** <$50 CAC
- Rely on organic, word-of-mouth, university partnerships
- Minimal paid ads in early stages
- Content marketing (free except time)

**How to calculate:**
```
CAC = (Marketing spend + Sales spend) / New customers acquired
```

**Month 1-3 CAC breakdown:**
- $0 paid ads
- $0 sales team (founders do sales)
- $50/month infrastructure → ~$1 CAC if we get 50 signups/month
- Effectively $0-10 CAC in early stages

---

### LTV:CAC Ratio
**Definition:** LTV ÷ CAC

**Why it matters:** Must be >3:1 for healthy SaaS business

**Benchmarks:**
- <1:1 = Losing money on every customer
- 1:1 to 3:1 = Breaking even to marginally profitable
- 3:1 to 5:1 = Healthy SaaS business
- >5:1 = Very efficient (but may be under-investing in growth)

**Noesis target:** 6:1 ratio
- LTV: $300
- CAC: $50
- Ratio: 6:1 (very healthy)

**Why we can achieve this:**
- Low CAC (organic growth, word-of-mouth)
- High retention (solving real pain point)
- Sticky product (researchers use for multiple papers)

---

## Market Size Metrics

### TAM (Total Addressable Market)
**Definition:** Total revenue opportunity if you captured 100% of market

**Why it matters:** VCs want to see $1B+ TAM for venture scale

**Noesis TAM:** $5-10B
- Global academic research tools market
- Includes literature review, writing assistance, citation management
- Growing at 19.8% CAGR

**Components:**
- Academic researchers worldwide: ~10M
- Industry R&D researchers: ~5M
- Government/NGO researchers: ~2M
- Total potential users: ~17M
- At $15/mo average: $3B ARR
- At $30/mo blended (includes enterprise): $6B ARR

---

### SAM (Serviceable Addressable Market)
**Definition:** Portion of TAM you can realistically reach with your product

**Why it matters:** More realistic estimate of growth potential

**Noesis SAM:** $500M-1B
- English-speaking researchers who write papers
- Primarily: US, UK, EU, Australia, Canada, India
- Excludes: Non-English markets (for now)
- Excludes: Researchers who don't write papers (pure teaching faculty)

**Estimate:**
- English-speaking researchers: ~5M
- Active paper writers: ~3M (60%)
- Willing to pay for tools: ~1M (33%)
- At $20/mo blended ARPU: $240M ARR
- With enterprise (universities): $500M-1B

---

### SOM (Serviceable Obtainable Market)
**Definition:** Portion of SAM you can capture in near-term (3-5 years)

**Why it matters:** Your realistic revenue target

**Noesis SOM:** $50-100M
- Capturing 5-10% of SAM at scale
- Requires strong differentiation and execution

**5-Year Path:**
- Year 1: $1M ARR (1,000 paying users)
- Year 2: $5M ARR (5,000 paying users + 50 enterprise)
- Year 3: $15M ARR (15,000 paying users + 200 enterprise)
- Year 4: $35M ARR (30,000 paying users + 500 enterprise)
- Year 5: $60M ARR (50,000 paying users + 1,000 enterprise)

---

## Operational Metrics

### Burn Rate
**Definition:** How much cash you're spending per month

**Why it matters:** Determines how long you can survive

**Noesis current burn:** ~$50-200/month
- Infrastructure only (Supabase, OpenAI, hosting)
- No salaries (founders not paid)
- No marketing spend (organic only)

**Post-fundraising burn (after seed):**
- ~$150K-200K/month with team of 5-10
- Mostly salaries + infrastructure + marketing

---

### Runway
**Definition:** Months of cash remaining (cash in bank ÷ burn rate)

**Why it matters:** Shows how long before you need revenue or funding

**Noesis current runway:** Effectively infinite
- Bootstrapped with minimal burn
- Can sustain indefinitely on side-project basis
- Need revenue or funding when scaling team

**Post-fundraising runway:**
- Raise $2-5M seed
- Burn $150-200K/month
- Runway: 24-30 months
- Target: Reach Series A metrics before running out

---

### Activation Time
**Definition:** Time from signup to "aha moment" (first value delivered)

**Why it matters:** Faster activation = better retention

**Current:** Unknown (need to measure)

**Noesis target:** <5 minutes
- Signup: 30 seconds
- Upload paper: 1 minute
- Upload draft: 1 minute
- See first analysis: 2-3 minutes
- Total: 4-5 minutes

**Best-in-class:** <2 minutes
- We may need demo mode to achieve this

---

## How to Track These Metrics

### Analytics Tools
1. **Supabase Analytics** (built-in)
   - User signups
   - Active users
   - Database queries

2. **Custom Dashboard** (to build)
   - Activation rate
   - Retention cohorts
   - Feature usage
   - Draft analysis metrics

3. **PostHog or Mixpanel** (optional)
   - Event tracking
   - Funnel analysis
   - Cohort retention

### Weekly Metrics Review (Every Monday)
Track in shared spreadsheet:
- Total signups (cumulative + weekly growth)
- MAU
- Activation rate (% who analyzed ≥1 draft)
- Retention (% who return week 2, week 4)
- Power users (analyzed ≥3 drafts)
- Draft analyses completed
- Average claims per draft
- Feedback quality (user ratings)

---

## Key Metric Targets Summary

| Metric | Month 1 | Month 3 | Month 6 |
|--------|---------|---------|---------|
| **MAU** | 100 | 2,000 | 20,000 |
| **Activation Rate** | 40% | 50% | 60% |
| **Retention** | 70% | 80% | 85% |
| **MRR** | $0 | $5K | $50K |
| **Paying Users** | 0 | 250-500 | 2,000-3,000 |
| **Conversion** | N/A | 5-10% | 10-15% |
| **LTV:CAC** | N/A | 6:1 | 6:1 |

---

**Next:** [Product-Market Fit Analysis](02_PRODUCT_MARKET_FIT.md)
