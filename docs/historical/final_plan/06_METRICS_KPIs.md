# Noesis — Metrics & KPIs Dashboard
*Revenue Operations Framework | Weekly Tracking*
*Owner: Both founders | Updated every Friday*

---

## THE ONE METRIC THAT MATTERS

**Activated Users with Day-7 Return**

Definition: User who signed up, analyzed ≥1 draft, AND returned to analyze or view results within 7 days.

This is the only PMF signal that matters at this stage. Everything else is a leading/lagging indicator of this number.

**Current value:** Unknown (not tracked yet)
**Week 4 target:** 10
**Week 8 target:** 50
**Week 12 target:** 150

---

## WEEKLY DASHBOARD TEMPLATE

```
Date: Week ___ (MM/DD/YYYY)
Filled by: Praneel / Ashwin

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACQUISITION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
New signups this week:              ___
Signups MoM growth:                 ___%
Extension installs (Chrome):        ___
Organic signups (SEO/Reddit/word):  ___
Outreach-sourced signups:           ___

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ACTIVATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Users who uploaded ≥1 document:     ___
Users who analyzed ≥1 draft:        ___
Activation rate (analyzed/signups): ___%
Time to first analysis (median):    ___min

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RETENTION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Week -1 cohort] Day-7 return rate: ___%
[Week -4 cohort] Day-30 return rate: ___%
MAU (Monthly Active Users):         ___
DAU (Daily Active Users):           ___
DAU/MAU ratio:                      ___ (target: >0.15)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REVENUE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total paying users:                 ___
  - Pro ($12/mo):                   ___
  - Lab ($49/mo):                   ___
  - Dept ($199/mo):                 ___
New paying users this week:         ___
Churned users this week:            ___
Net new MRR:                        $___
Total MRR:                          $___
MRR MoM growth:                     ___%
ARR:                                $___

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRODUCT HEALTH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Drafts analyzed this week:          ___
Documents uploaded this week:       ___
Paper discovery searches:           ___
Average analysis latency (P50):     ___s
Average analysis latency (P95):     ___s
Error rate (failed analyses):       ___%
Celery task failure rate:           ___%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
GTM ACTIVITY (Praneel)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Outreach emails sent:               ___
Demo calls completed:               ___
Testimonials collected:             ___
Open rate (cold email):             ___%
Response rate (cold email):         ___%
Demo → trial conversion:            ___%
Trial → paid conversion:            ___%
```

---

## KPI DEFINITIONS (Investor-Ready)

### Acquisition Metrics

**Monthly Signups:** Total new accounts created in a calendar month.
- Target Month 1: 50-100
- Target Month 3: 200-400
- Target Month 6: 700+

**Channel Attribution:** Signups tagged by source (organic search, cold outreach, Product Hunt, referral, direct). Use UTM parameters on all links Praneel sends.

**Extension Install Rate:** Chrome Web Store installs per week. This is the most important acquisition metric once the extension is live — it signals workflow-level adoption.

### Activation Metrics

**Activation Rate:** % of signups who analyze ≥1 draft within 14 days of signup.
- Industry benchmark (research tools): 20-30%
- Target: >30%
- If below 15%: activation friction is critical, stop outreach, fix product

**Time to First Analysis:** Median minutes from signup to first completed draft analysis. Should be measurable from backend logs.
- Target: <10 minutes (including document upload)
- Alarm threshold: >20 minutes (too much friction)

**Library Size at Activation:** How many documents a user has in their library when they run their first draft analysis. More documents = better analysis quality = better retention.
- Track this distribution: <3 docs, 3-10 docs, 10+ docs
- Users with 10+ docs in library at first analysis have likely much higher retention

### Retention Metrics

**Day-7 Retention:** % of users who analyzed their first draft who return within 7 days.
- Cold start target: >15%
- PMF signal: >25%
- If below 10%: analysis quality or usefulness is the problem

**Day-30 Retention:** % of Month N users who return in Month N+1.
- Industry average for academic SaaS: 15-25%
- Target: >20%

**DAU/MAU Ratio:** Average daily users / monthly users. Measures habit formation.
- Below 0.05: casual tool, not a habit
- 0.05-0.15: occasional use (acceptable for draft review cycle)
- Above 0.15: habitual use (excellent for academic tool)

**Draft Version Progression:** Users who analyze Draft v1 AND then analyze a Draft v2 (same paper). This is the retention hook — improvement score creates a loop.
- Target: >30% of users who analyze v1 come back for v2

### Revenue Metrics

**MRR (Monthly Recurring Revenue):** Sum of all active subscriptions × monthly price.

**Net Revenue Retention (NRR):** (MRR start of month + expansion - contraction - churn) / MRR start of month.
- Below 90%: churning faster than growing
- 90-100%: healthy, neutral
- Above 100%: expansion revenue exceeds churn (best-case academic SaaS)

**Payback Period:** CAC / (MRR per user × gross margin). For outreach-driven acquisition:
- Praneel time cost for 50 emails + 5 calls = ~8 hours
- 8 hours × $50/hr opportunity cost = $400 CAC for 3 conversions = $133/user
- Pro user LTV = $144 (12-month) → payback = 11 months
- Lab user LTV = $882 (18-month) → payback = 2.7 months
- Focus outreach on Lab conversions (PIs, not students)

**Churn Rate:** Paying users who cancel / total paying users at start of period.
- Target: <5% monthly churn
- Academic SaaS risk: semester-cycle churn (January, May, August)
- Counter: annual pricing offers

### Quality Metrics (Internal)

**Analysis Error Rate:** % of draft analysis attempts that fail (Celery task failure, OpenAI error, timeout).
- Alert threshold: >5%
- Track by error type: model errors, timeout errors, parsing errors

**Feedback Helpfulness Rate:** % of reviewer feedback items marked "Helpful" (not disputed).
- Baseline to establish in Month 1
- If below 50%: analysis quality is the retention problem

**Source Grounding Coverage:** % of feedback items that include a source passage from literature.
- Target: 100% (every feedback item is grounded)
- If below 80%: source grounding service has a bug

---

## GO / NO-GO TRIGGERS

These are binary decisions based on metric thresholds:

### Month 1 Check (Week 4)
| Metric | Go | No-Go |
|---|---|---|
| Activated users | ≥10 | <5 |
| Day-7 retention | ≥10% | <5% |
| Testimonials | ≥1 authentic | 0 |
| **No-Go Action** | | Fix activation friction, delay outreach |

### Month 3 Check (Week 12)
| Metric | Go | No-Go |
|---|---|---|
| MRR | ≥$1,000 | <$500 |
| Activated users | ≥80 | <30 |
| Day-7 retention | ≥15% | <10% |
| Browser extension installs | ≥100 | <30 |
| **No-Go Action** | | Pivot to different distribution or narrower ICP |

### Month 6 Check (Fundraising Gate)
| Metric | Raise Seed | Wait |
|---|---|---|
| MRR | ≥$5,000 | <$3,000 |
| MoM growth (3-mo avg) | ≥20% | <10% |
| Day-30 retention | ≥20% | <15% |
| Paying users | ≥50 | <20 |
| Institutional interest | ≥1 pilot | None |
| **If Wait:** | Extend runway 3 months | Reassess at Month 9 |

---

## INVESTOR-READY METRICS SUMMARY (When Ready to Raise)

```
Company: Noesis
Stage: Pre-Seed
Date: [Month 6]

Core Metrics:
  MRR:                    $X,XXX
  MoM Growth:             XX%
  ARR:                    $XX,XXX
  Paying Users:           XX
  Blended ARPU:           $XX/mo

Engagement:
  MAU:                    XXX
  Activation Rate:        XX% (signup → first draft analyzed)
  Day-7 Retention:        XX%
  Day-30 Retention:       XX%

Unit Economics:
  Gross Margin:           ~90%
  CAC (outreach):         $XXX
  LTV (Pro, 12-mo):       $144
  LTV (Lab, 18-mo):       $882
  Payback Period (Pro):   XX months

Product:
  Total Drafts Analyzed:  X,XXX
  Papers in Corpus:       XX,XXX
  Extension Installs:     XXX
  NPS Score:              XX

Pipeline:
  University Pilots:      X active
  Enterprise Conversations: X
```

---

## WHAT NOT TO TRACK (Vanity Metrics)

- **Page views / unique visitors** — misleading without activation data
- **Social media followers** — irrelevant for B2B academic SaaS
- **Total signups** — meaningless without activation; academics sign up for everything
- **Paper discovery searches** — usage metric, not value metric
- **Time on site** — not meaningful for asynchronous analysis tools
- **Press mentions** — nice, not useful

Focus on: Activated users, MRR, Day-7 retention. Everything else is context.

---

*This dashboard should be filled out every Friday and shared between Ashwin and Praneel. It takes 15 minutes to fill. If it's not filled, the data doesn't exist, and you're flying blind.*
