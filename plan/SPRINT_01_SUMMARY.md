# Noesis Sprint 01 — "Sharpen the Wedge" — Retrospective

## Why This Sprint Existed

Gemini critique surfaced 6 core problems with the original Noesis positioning:
1. Too generic — "research intelligence" doesn't explain the value in one sentence
2. Target user unclear — grad students vs. PIs have different pain/budget profiles
3. No urgency trigger — researchers don't need better literature review, they need to survive submission
4. Workflow silo — lives inside Noesis, not where researchers actually write
5. Draft features buried — the killer differentiator wasn't front and center
6. Monetization too late — free tier too generous, no upgrade pressure at natural walls

**Decision: Option A — Stay the Course + Sharpen the Wedge.** Don't pivot. Sharpen the current product's messaging, distribution leverage, and pricing to match the actual buyer (PI/postdoc with grant budget) instead of rebuilding.

---

## Original Goals vs What Was Built

| Goal | Status | Notes |
|------|--------|-------|
| Rewrite landing page for Reviewer 2 framing | ✅ Done | Hero: "Know What Reviewer 2 Will Say Before You Submit" |
| PI/postdoc-targeted copy | ✅ Done | Landing page, pricing, onboarding copy all updated |
| BibTeX import | ✅ Done | `POST /projects/{project_id}/import-bibtex` + UploadDocumentModal tab |
| Paper Discovery quota (3/day free) | ✅ Done | Redis-backed, degrades gracefully |
| Source grounding on reviewer feedback | ✅ Done | `_get_source_grounding()` enriches every feedback item |
| Free tier tightened (10 drafts, 50 docs) | ✅ Done | quota_management.py + Pricing.tsx updated |
| Helpful/Dispute reactions on feedback | ✅ Done | user_feedback_on_analysis table + ReactionBar.tsx |
| VersionProgressCard surfaced in DraftsPanel | ✅ Done | First thing a returning user sees |
| Lab Invite system | ✅ Done | Code generation, SignUp banner, Projects.tsx join-on-load |
| Lab tier ($49/mo flat, 5 users) | ✅ Done | Stripe checkout + PLAN_CONFIGS + Pricing.tsx card |
| UpgradeModal global store | ✅ Done | Zustand + singleton in App.tsx + errorHandler intercept |
| "Refer a Lab" viral loop | ✅ Done | 3+ institutional referrals → auto-grant Lab tier |
| Browser extension MVP | ❌ Deferred | Week 3 stretch goal — highest priority for Sprint 02 |
| WebSocket progress streaming | ❌ Deferred | Backend groundwork exists, frontend not built |
| Human-in-the-loop claim validation | ❌ Deferred | Backend supports resumable workflows, no UI yet |

---

## Week 1: Messaging + Core Product (Days 1–7)

### Built

**BibTeX Import**
- Endpoint: `POST /projects/{project_id}/import-bibtex`
- File: `services/backend/app/api/routes/documents.py`
- Frontend: new BibTeX tab in `UploadDocumentModal.tsx` alongside PDF upload
- Parses `.bib` files server-side, creates document records, queues analysis

**Paper Discovery Quota**
- 3 searches/day for free users (Redis key: `daily_discovery:{user_id}:{date}`)
- Quota logic in `services/backend/app/api/routes/paper_discovery.py`
- Pro/Lab users get unlimited discovery
- Degrades gracefully: shows upgrade prompt at wall, doesn't hard-error

**Source Grounding on Reviewer Feedback**
- `_get_source_grounding()` in `services/backend/app/services/reviewer_feedback.py`
- Every feedback item now includes which papers from the library support or contradict the feedback
- Makes feedback defensible and connected to the literature collection

**Free Tier Limits Updated**
- 10 drafts/month, 50 documents/month (down from more generous previous limits)
- Updated: `services/backend/app/services/quota_management.py`
- Frontend: `services/frontend/src/pages/Pricing.tsx`

**Landing Page Rewrite**
- Hero: "Know What Reviewer 2 Will Say Before You Submit"
- Subheading targets PI/postdoc audience directly
- File: `services/frontend/src/pages/Landing.tsx`

---

## Week 2: Distribution Leverage + Trust (Days 8–14)

### Built

**Helpful/Dispute Reactions**
- Reaction bar on every reviewer feedback item in `DraftAnalysisModal.tsx`
- `user_feedback_on_analysis` table (migration 010)
- Columns: user_id, draft_id, feedback_id, reaction (helpful/dispute), created_at
- File: `services/backend/app/api/routes/drafts.py` (reaction endpoint)

**VersionProgressCard in DraftsPanel**
- Returning users immediately see improvement score delta between draft versions
- Surfaced above the draft list — first thing you see after login
- File: `services/frontend/src/components/DraftsPanel.tsx`

**Lab Invite System**
- PI generates invite code → shares with lab members
- `lab_invites` table (migration 010): code, created_by, lab_name, used_count, max_uses
- `SignUp.tsx`: reads invite code from URL param, shows welcome banner ("Joining [Lab Name]")
- `Projects.tsx`: on load, if invite code in sessionStorage, auto-applies lab membership
- Code auto-cleared from sessionStorage after first use

---

## Week 3: Monetization + Pricing Fix (Days 15–21)

### Built

**Lab Tier ($49/mo, 5 users flat)**
- Added to `PLAN_CONFIGS` in `services/backend/app/services/quota_management.py`
- Stripe checkout: `services/backend/app/services/stripe_service.py`
- Graceful fallback: if `STRIPE_PRICE_ID_LAB` not set, creates dynamic price via API
- Pricing page: `services/frontend/src/pages/Pricing.tsx` — Lab card above Enterprise

**UpgradeModal Global Store**
- `services/frontend/src/stores/upgradeModalStore.ts` — Zustand store
- `services/frontend/src/components/UpgradeModal.tsx` — singleton rendered in App.tsx
- `errorHandler` in API calls intercepts 402/429 quota errors → triggers modal automatically
- No prop drilling — any component can call `useUpgradeModal().open(reason)` to show modal

**"Refer a Lab" Viral Loop**
- Extended referral system: tracks `referral_type` (individual vs. institutional)
- After 3+ institutional referrals from one user → auto-grant Lab tier
- Logic in `services/backend/app/api/routes/referrals.py`

---

## DB Migrations Required on Production

Both must be run on the Supabase dashboard SQL editor before sprint features are live:

```
infra/db-migrations/009_sprint_week1_features.sql
  → bibtex_import_count, paper_discovery_quota columns on users/projects
  → paper_discovery_sessions table

infra/db-migrations/010_week2_features.sql
  → user_feedback_on_analysis table (Helpful/Dispute reactions)
  → lab_invites table (Lab Invite system)
```

---

## Technical Decisions Made This Sprint

**GPT-5.2 parameter naming**: `max_completion_tokens` everywhere, never `max_tokens`. Breaking change from GPT-4o. Fixed in 15 files (see `GPT52_API_FIX.md`). Do not revert.

**Quota state split**: Redis for rate-limit tracking (TTL-based, resets daily/monthly), Supabase for persistent counts (total lifetime usage, billing period usage). Never use Supabase for high-frequency per-request quota checks.

**sessionStorage for lab invite code**: Single-use only, auto-cleared after Projects.tsx processes it. Chosen over URL params (can be bookmarked and reused) and cookies (over-engineered for this use case).

**UpgradeModal architecture**: Module-level Zustand store called from the shared `errorHandler` utility. Keeps quota wall UX consistent everywhere without requiring components to know about billing. Any future quota check just throws the right error code.

**Stripe Lab tier pricing**: Graceful fallback to `stripe.prices.create()` if env var not set. Allows local dev and staging to work without a real Stripe price configured.

---

## Success Metrics Status (as of sprint end)

Fill in with actual data from Supabase analytics + Stripe after deploying:

- [ ] Landing page conversion rate (visitor → signup): target >5%
- [ ] Activation rate (signup → 1 draft analyzed): target >30%
- [ ] Day-7 retention (returned after first analysis): target >20%
- [ ] Lab invites sent: target >10 in first week after launch
- [ ] Upgrade modal impressions vs. conversions: target >3% conversion
- [ ] Paper Discovery searches/day: tracking starts after deploy

---

## What Wasn't Built (Deferred to Sprint 02)

**Browser Extension MVP** — Week 3 stretch goal. Highest-ROI deferred item. Eliminates the workflow silo critique by bringing Noesis into Google Docs and Overleaf. ~10-12 hours of work. First priority for Sprint 02.

**WebSocket Progress Streaming** — Backend workflows already emit step events (LangGraph). Missing the WebSocket endpoint and frontend progress UI. Analysis still feels like a black box to users.

**Human-in-the-Loop Claim Validation** — Backend supports resumable LangGraph workflows (checkpoint system implemented). No UI to pause, review, and resume claim extraction. Low priority until core retention is proven.

**Dispute Suppression Logic** — `user_feedback_on_analysis` table exists but reactions don't yet affect future analyses. After N disputes of the same feedback type, those patterns should be suppressed in reviewer_feedback.py prompt construction.
