# Noesis — 12-Week Sprint Roadmap
*Weeks 1-12 | Starting March 2026*
*Ashwin: Engineering | Praneel: GTM*

---

## NORTH STAR METRIC

**Activated users who analyzed ≥1 draft AND returned within 7 days.**

This single metric determines whether Noesis has product-market fit. Everything in this roadmap serves this number.

**Target progression:**
- Week 4: 10 activated users
- Week 8: 50 activated users
- Week 12: 150 activated users, 15+ paying

---

## HARD RULES FOR THIS ROADMAP

1. **Ashwin does NOT build new features until browser extension is complete (Week 4).** No exceptions.
2. **Praneel sends outreach every single day.** Not "when the product is ready." Starting Monday.
3. **Weekly sync every Friday:** Review metrics, adjust next week's priorities. 30 minutes only.
4. **Feature requests from users > feature requests from founders.** If a user asks for something twice, it goes on the roadmap. If founders think of it, it waits.
5. **Ship ≥ one deployable improvement per week.** No dark sprints.

---

## SPRINT 1: "FIX THE FOUNDATION" (Weeks 1-3)

**Sprint Goal:** Verify the product works, deploy everything, and launch the browser extension.

### Week 1: Emergency Fixes + Deployment

#### Ashwin (Engineering)

| Task | Priority | Effort | Done When |
|---|---|---|---|
| Verify GPT-5.2 model ID works in production | 🔴 Blocker | 30 min | API call succeeds |
| Deploy all Sprint 01-03 frontend changes to Vercel | 🔴 Blocker | 2 hrs | noesis.is shows new hero |
| Run DB migrations 009 + 010 on production Supabase | 🔴 Blocker | 1 hr | Tables exist in DB |
| Add Stripe Lab price ID to production .env | 🔴 Blocker | 1 hr | Lab checkout works |
| Remove RAGSettingsModal.tsx from frontend | 🟡 High | 2 hrs | Settings icon gone |
| Remove university logo/name claims from landing page | 🔴 Blocker | 30 min | Legal/trust risk resolved |
| Remove beta/paid messaging conflict | 🟡 High | 30 min | Consistent messaging |
| WebSocket backend endpoint for analysis progress | 🟡 High | 1 day | ws:// endpoint available |

#### Praneel (GTM)

| Task | Priority | Effort | Done When |
|---|---|---|---|
| Build target PI list: 100 names from GT/Rice/UT Austin faculty directories | 🔴 Blocker | 3 hrs | Spreadsheet with names, emails, recent papers |
| Send 20 cold emails (PI template from GTM playbook) | 🔴 Blocker | 2 hrs | 20 emails sent, tracked |
| Twitter/X setup: monitor "reviewer 2", "paper rejected" daily | 🟡 High | 1 hr | Saved searches set up |
| LinkedIn: send 10 postdoc outreach messages | 🟡 High | 1 hr | 10 messages sent |
| Record 2-minute Loom demo video | 🟡 High | 2 hrs | Link ready to share |

**Week 1 Success Criteria:**
- [ ] noesis.is live with new hero copy
- [ ] GPT model verified (or fixed)
- [ ] University claims removed
- [ ] 30+ outreach messages sent

---

### Week 2: WebSocket + Extension Foundation

#### Ashwin

| Task | Priority | Effort | Done When |
|---|---|---|---|
| WebSocket frontend hook (useAnalysisStream.ts) | 🔴 Blocker | 1 day | Progress bar shows during analysis |
| WebSocket integration in DraftAnalysisModal | 🔴 Blocker | 4 hrs | Users see step-by-step progress |
| Chrome extension: manifest.json + service worker + auth | 🟡 High | 1.5 days | Extension loads in Chrome |
| CORS config: add chrome-extension:// origins | 🟡 High | 1 hr | Extension can call backend |
| New API endpoint: POST /drafts/analyze-from-extension | 🟡 High | 4 hrs | Accepts raw text from extension |

#### Praneel

| Task | Priority | Effort | Done When |
|---|---|---|---|
| Follow up on Week 1 emails (check open rates) | 🔴 Daily | 30 min/day | Responses tracked |
| Schedule 3+ demo calls from responses | 🔴 Blocker | Ongoing | Cal invites sent |
| Send 20 more cold emails | 🟡 High | 2 hrs | 50 total sent |
| r/GradSchool post: "We're building X — want early access?" | 🟡 High | 1 hr | Post live, monitoring |
| Create simple landing page tracking: which channel → signup | 🟡 High | 1 hr | UTM links set up |

**Week 2 Success Criteria:**
- [ ] WebSocket progress streaming live in production
- [ ] Chrome extension loads in developer mode
- [ ] 3 demo calls scheduled
- [ ] 50+ total outreach messages sent

---

### Week 3: Browser Extension MVP Live

#### Ashwin

| Task | Priority | Effort | Done When |
|---|---|---|---|
| Overleaf content script: sidebar injection | 🔴 Blocker | 1.5 days | Sidebar visible in Overleaf |
| Extension sidebar UI: React component bundled | 🔴 Blocker | 1 day | Analyze button works |
| Extension: display top 3 action items in sidebar | 🟡 High | 4 hrs | Feedback shows in Overleaf |
| Extension: "View Full Analysis" link to noesis.is | 🟡 High | 1 hr | Click opens dashboard |
| Submit to Chrome Web Store | 🟡 High | 2 hrs | Extension published |
| Test full flow: Overleaf → extension → analysis → sidebar results | 🔴 QA | 3 hrs | E2E verified |

#### Praneel

| Task | Priority | Effort | Done When |
|---|---|---|---|
| Run 5 demo calls | 🔴 Blocker | 5 hrs | Completed, notes written |
| After each demo: collect quote or testimonial | 🔴 Blocker | Per call | At least 2 quotes collected |
| Send Overleaf extension link to all demo attendees | 🟡 High | 30 min | Follow-up emails sent |
| Post on Twitter: "We shipped a Chrome extension for Overleaf" | 🟡 High | 30 min | Tweet published |
| DM 20 researchers on arXiv (who posted preprints in last 30 days) | 🟡 High | 2 hrs | 20 DMs sent |

**Sprint 1 Success Criteria:**
- [ ] Browser extension live in Chrome Web Store
- [ ] 10 users who have analyzed a draft (any channel)
- [ ] 3+ authentic testimonials collected
- [ ] Day-7 retention tracked for first cohort (even if just 5 users)
- [ ] $0 MRR → first paying user (optional stretch)

---

## SPRINT 2: "QUALITY + DISTRIBUTION" (Weeks 4-6)

**Sprint Goal:** Fix quality issues surfaced by real users. Add distribution channels.

### Week 4: Listen and Fix

**Rule:** This entire week, Ashwin only fixes bugs and quality issues reported by real users. No new features.

#### Ashwin

| Task | Trigger |
|---|---|
| Fix any extension bugs from Week 3 real users | Extension bug reports |
| Improve feedback specificity if users say "too generic" | User feedback |
| Fix any document upload issues surfaced in demos | Demo observations |
| Add arXiv URL direct import | 3+ users ask for it |
| Core service tests: draft workflow + RAG + quota | Proactive quality |

#### Praneel

| Task | Priority | Done When |
|---|---|---|
| 5 more demo calls | Daily | Calls completed |
| 3 testimonials published on landing page | High | Website updated |
| r/academia value post: "7 things Reviewer 2 always checks" | High | Post published |
| Overleaf community forum engagement | Medium | 3+ helpful replies |
| First Product Hunt prep: screenshots, tagline, description | High | Draft complete |

### Week 5: RAG Quality Improvements

#### Ashwin

| Task | Priority | Effort |
|---|---|---|
| Adaptive chunk sizing (10/30/30+ page tiers) | High | 2 days |
| Section-aware chunking with GROBID | High | 2 days |
| Remove user-adjustable RAG settings API endpoint (deprecate) | Medium | 2 hrs |
| Test coverage: rag_ingest.py + rag_retrieval.py | High | 1 day |

#### Praneel

| Task | Priority | Done When |
|---|---|---|
| University library outreach: 5 research librarians | High | 5 emails sent |
| Conference identification: find 3 upcoming STEM conferences | Medium | List created |
| Overleaf partnership email (use template from GTM playbook) | High | Email sent |
| Social proof: testimonials added to landing page | Blocker | Live on site |

### Week 6: Product Hunt Preparation

#### Ashwin

| Task | Priority | Effort |
|---|---|---|
| Google Docs extension: foundation (different DOM than Overleaf) | High | 2 days |
| API integration tests: drafts, documents, subscriptions | High | 2 days |
| Performance check: analysis latency P95 | Medium | 4 hrs |

#### Praneel

| Task | Priority | Done When |
|---|---|---|
| Product Hunt launch: Day + time selected | Blocker | Tuesday or Wednesday, 12:01 AM PT |
| Product Hunt: find hunter with 1,000+ followers | High | Hunter confirmed |
| Build email list of 100+ people who will upvote | Blocker | 100 names collected |
| Product Hunt maker comment drafted | High | Draft complete |

**Sprint 2 Success Criteria:**
- [ ] 30+ activated users (analyzed ≥1 draft, returned within 7 days)
- [ ] RAG quality improved (anecdotal: users say feedback is more specific)
- [ ] 3+ testimonials live on landing page
- [ ] 3+ paying users ($37+ MRR)
- [ ] Product Hunt launch ready

---

## SPRINT 3: "MONETIZATION + GROWTH" (Weeks 7-9)

**Sprint Goal:** Product Hunt launch, first real MRR, institutional traction begins.

### Week 7: Product Hunt Launch

**Launch day is a full-day event for both Ashwin and Praneel.**

#### Praneel (Launch day — all day)
- Monitor Product Hunt page — respond to every comment within 15 minutes
- Post to every community: r/GradSchool, r/PhD, r/academia, Twitter, LinkedIn
- DM everyone on the 100-person upvote list
- Monitor Twitter for anyone mentioning Noesis
- Respond to every new signup within 1 hour

#### Ashwin (Launch day — standby)
- Be available for emergency bug fixes
- Monitor error logs every 30 minutes
- Have rollback plan ready if extension breaks under load

**Post-launch (Week 7, days 2-5):**
- Analyze Product Hunt traffic: how many signups? Conversion rate?
- Follow up with everyone who commented or upvoted
- Write post-launch email to all signups from PH: "Thanks for checking out Noesis"

### Week 8: Capitalize on Launch Traffic

#### Ashwin

| Task | Priority | Effort |
|---|---|---|
| Fix bugs from Product Hunt traffic surge | Blocker | As needed |
| Dispute suppression logic (if 5+ users have disputed same feedback type) | Medium | 1 day |
| E2E critical path test | High | 1 day |
| Google Docs extension: sidebar working | High | 2 days |

#### Praneel

| Task | Priority | Done When |
|---|---|---|
| Follow up with all Product Hunt signups | Blocker | 100% followed up |
| Offer 5 PH users a 15-min "how'd you find it?" call | High | 5 calls scheduled |
| arXiv preprint submission: "Pre-submission review methodology" | Medium | Submitted |
| University library follow-ups on Week 5 emails | High | Response or no-response documented |

### Week 9: Institutional Traction

#### Praneel

| Task | Priority | Done When |
|---|---|---|
| 3 university library conversations | High | Calls completed |
| Present free pilot offer: "10 researchers, 60 days, free" | High | At least 1 "yes" to pilot |
| Academic conference outreach: 3 upcoming conferences | Medium | Emails sent to organizers |

**Sprint 3 Success Criteria:**
- [ ] Product Hunt top 10 in category (target: top 5)
- [ ] 100+ new signups from Product Hunt
- [ ] 15+ paying users ($180-400+ MRR)
- [ ] 1 university library pilot conversation active
- [ ] Day-30 retention tracked for Week 1 cohort

---

## SPRINT 4: "STABILITY + SCALE" (Weeks 10-12)

**Sprint Goal:** Solidify retention, build institutional pipeline, prepare fundraising narrative.

### Week 10-11: Quality Loop + Churn Prevention

#### Ashwin

| Task | Priority | Effort |
|---|---|---|
| Customer health score implementation | High | 1 day |
| Automated re-engagement email when health score drops | High | 1 day |
| gpt-4o-mini for cheap task optimization (cost reduction) | Medium | 2 days |
| Celery task failure user notifications | Medium | 4 hrs |
| Observability: basic Prometheus metrics on key endpoints | Low | 1 day |

#### Praneel

| Task | Priority | Done When |
|---|---|---|
| Monthly check-in with all paying Lab users | Blocker | 100% contacted |
| Collect NPS scores from 20+ users | High | Survey sent + 10 responses |
| Refine investor pitch with real metrics | High | Deck updated |
| Begin investor outreach if MRR > $3K | Medium | 5 warm intros requested |

### Week 12: Fundraising Readiness

#### Both

| Task | Done When |
|---|---|
| Compile metrics: MAU, activation rate, Day-7/30 retention, MRR, paying users | Dashboard complete |
| 3-minute founder story video | Recorded |
| Investor deck (10 slides) | Complete |
| Data room: financial model, KPIs, team bios | Complete |
| **Go/No-Go decision:** Is MRR ≥ $3K? Are there 50+ activated users? Is Day-7 retention ≥ 15%? | Decision made |

**Sprint 4 / Quarter 1 Success Criteria:**
- [ ] 150+ activated users
- [ ] 30+ paying users
- [ ] $3K+ MRR
- [ ] Day-7 retention ≥ 15%
- [ ] 1 institutional pilot (free) running
- [ ] Investor conversations started (if metrics support)

---

## WEEKLY SYNC TEMPLATE (Every Friday, 30 minutes)

```
1. Metrics review (10 min):
   - New signups this week: ___
   - Activated users (analyzed 1+ draft): ___
   - Day-7 retention of last week's cohort: ___
   - Paying users total: ___
   - MRR: $___
   - Browser extension installs: ___

2. What worked this week: (5 min)

3. What didn't work: (5 min)

4. Next week priorities (Ashwin / Praneel): (10 min)
   - 3 things each, MAX
```

---

## GO / NO-GO DECISION FRAMEWORK

| Week | Check | Go Criteria | No-Go Action |
|---|---|---|---|
| 4 | First activated users | ≥5 users analyzed ≥1 draft | Fix activation friction before more outreach |
| 8 | Retention check | Day-7 retention ≥ 10% | Pause growth, fix product quality |
| 8 | First revenue | ≥1 paying user | Extend timeline, not strategy |
| 12 | PMF check | MRR ≥ $3K, Day-7 retention ≥ 15% | Serious conversation about pivot or shut down |
| 12 | Fundraising readiness | $5K MRR, 50+ activated users | Wait 2 more months before investor outreach |

---

*This is an execution document, not an aspiration document. If tasks are not completed on schedule, the sprint retrospective must explain why — not rationalize it. The product will not survive another sprint of deferred browser extension.*
