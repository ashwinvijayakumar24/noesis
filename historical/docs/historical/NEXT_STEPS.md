# Noesis Next Steps - Historical Strategic Plan

> May 10, 2026 note: This document is historical. It includes old roadmap, pricing, and Stripe assumptions that are no longer authoritative. Use `../../current_state.md` for the live state. Current caveat: Stripe production pricing/checkout is not finished, and lab outreach should start now while product hardening continues.

## Context

Historical premise at the time this was written: the product was treated as technically complete and the biggest gap was market contact. Current correction: Stripe production pricing/checkout is not finished, collaboration is not built, and PDF/claim quality still needs hardening. Outreach should still start now.

The founder has correctly identified outreach as the #1 priority. This plan addresses the full stack of next steps across 6 areas, sequenced by dependency and impact, with explicit go/kill conditions at each stage.

---

## Phase 1: Deploy & Unblock (Days 1-3, ~4 hours)

**Do this before any outreach. Sending users to a broken product is harmful.**

### Actions
1. Deploy all Sprint 01-03 changes to Vercel + AWS
2. Run DB migrations on Supabase:
   - `infra/db-migrations/009_sprint_week1_features.sql`
   - `infra/db-migrations/010_week2_features.sql`
   - `infra/db-migrations/012_literature_tab_redesign.sql`
3. Verify GPT-5.2 model ID in production container (`docker exec noesis-backend python -c "import openai; ..."`)
4. Add Stripe Lab price ID to production `.env`
5. Remove ALL "Used by researchers at [Georgia Tech/Rice/UT Austin]" claims from `Landing.tsx` (legal liability — university names were never verified)
6. Verify pricing page matches actual Stripe product IDs

**Files:**
- `services/frontend/src/pages/Landing.tsx` — remove unverified university claims
- `infra/docker-compose.prod.yml` — verify environment vars
- `infra/db-migrations/` — run 009, 010, 012

---

## Phase 2: Outreach (Days 1-90, ongoing)

**This is the only thing that matters for the next 30 days. Do not build anything new.**

### Target Audience
- Primary: Principal Investigators (PIs) with active NSF/NIH grants at R1 universities
- Tier 1 targets: Georgia Tech, Rice, UT Austin (founder network + proximity)
- Tier 2: arXiv authors in CS/ML/Biology who published in the last 6 months
- Secondary: Postdocs submitting to high-impact journals (Nature, Science, NeurIPS, ICML)

### Outreach Playbook

**Email template (cold PI outreach):**
```
Subject: Tool that shows what Reviewer 2 will flag before you submit

Hi [Name],

I saw your recent paper on [topic] — specifically the [specific claim/method].
I built Noesis, a tool that reads your draft and literature, then tells you
exactly what a hostile reviewer would flag: unsupported claims, citation gaps,
methodology blind spots.

It's free to try. Would you be willing to run one of your drafts through it
and tell me if the feedback is worth anything? Takes 5 minutes.

[link]

— Ashwin
```

**Volume targets:**
- Week 1-2: 20 emails/week to GT/Rice/UT Austin faculty directories
- Week 3-4: 20 emails/week to arXiv authors (CS/ML, Biology, Medicine)
- Week 5+: Expand to r/GradSchool, academic Twitter/X, LinkedIn researcher communities

**Demo call script:**
1. "Show me a draft you're worried about" (use their real work, not demo data)
2. Upload it live in the call
3. Show reviewer feedback + citation gaps
4. Ask: "Did this catch something you were actually worried about?"
5. If yes: "Would you pay $12/mo for this for yourself? $49/mo for your lab?"

### Viral Channels (post-activation)
- arXiv author DMs (direct link to paper in message)
- Reddit: r/GradSchool, r/PhD, r/MachineLearning, r/academia
- Academic Twitter: share "Noesis caught this real reviewer comment on my draft" posts
- Lab invite loop: activated PIs → invite PhD students via `POST /referrals/lab-invite`

### Go/Kill Conditions
- **Kill (Week 4):** <5 email responses from 80+ sent → messaging is broken, rewrite copy
- **Kill (Week 8):** 0 activated users after 20+ demo calls → do in-person demos at Georgia Tech, something is wrong with the core loop
- **Go (any point):** 3 PIs say "this caught something I missed" → collect testimonials, double outreach
- **Go (Week 6):** 1 PI pays → don't change anything, just send more emails

---

## Phase 3: Collaborative Features (Days 31-60)

**Trigger: 5+ solo activated users exist. Do not build before this.**

### Why Collaboration Is the Primary Market
Research labs are the buyer. PIs have budgets ($500K NSF grants; $49/mo is noise). PhD students don't. But a PI will only invite their lab to a tool they've personally found valuable. The viral loop is: PI uses alone → gets "this caught something" moment → invites lab.

### What to Build (Minimum Viable Collaboration)

**Backend (2-3 days):**
The `team_members` table already exists (`infra/db-migrations/008_subscriptions.sql`). Zero API routes exist. Need:

```python
# New routes in: services/backend/app/api/routes/projects.py or new routes/teams.py

POST   /projects/{project_id}/members           # Invite member by email
GET    /projects/{project_id}/members           # List members + roles
DELETE /projects/{project_id}/members/{user_id} # Remove member
GET    /projects/shared                          # List projects shared with me
PUT    /projects/{project_id}/members/{user_id} # Update role (owner/member)
```

**Data model (already in DB):**
```sql
team_members: team_owner_id, member_user_id, role (owner/admin/member), status (pending/active/removed)
```

**Frontend (1 day):**
- Add "Invite" button in `ProjectDetail.tsx` header
- New `InviteMemberModal.tsx`: email input + role selector + copy invite link
- Members list in project settings (owner-only view)
- Indicator in `Projects.tsx` for shared projects (e.g., avatar stack)

**Files to modify:**
- `services/backend/app/api/routes/projects.py` — add 5 team routes
- `services/backend/app/main.py` — register router if separate file
- `services/frontend/src/pages/ProjectDetail.tsx` — add Invite button
- New: `services/frontend/src/components/InviteMemberModal.tsx`
- New: `services/frontend/src/components/ProjectMembersList.tsx`

**Role permissions:**
- Owner: full access, can invite/remove, can delete project
- Member: view all content, upload documents, upload drafts, run analyses
- Members cannot: delete project, remove other members, change billing

### Go/Kill Conditions
- **Go:** 5+ solo activated users, at least 1 PI explicitly asks about lab sharing
- **Kill:** After building, no PI invites a single person → collaboration is not the unlock, individual features are

---

## Phase 4: Stripe/Pricing Finalization (Days 15-30)

**Historical state from this plan:** Stripe was assumed mostly implemented for single users. Current correction: production price IDs, webhook verification, pricing-page checkout, billing portal, and checkout-to-quota-upgrade testing remain unfinished.

### What's Needed

1. **Lock canonical pricing** (one source of truth before outreach):
   - Free: $0, 30 PDFs/mo, 5 draft analyses/mo, 10 discovery searches/day
   - Pro: $12/mo, unlimited
   - Lab: $49/mo, 5 seats flat
   - Team: $20/user/mo, min 2 seats
   - Enterprise: Custom

2. **Complete Lab tier member provisioning:**
   ```python
   # services/backend/app/services/stripe_service.py
   # After checkout.session.completed webhook fires for Lab plan:
   # → Create team_members record for owner
   # → Set max_seats = 5 on subscription record
   # → Provision quota for all seats
   ```

3. **Pricing page audit:**
   - `services/frontend/src/pages/Pricing.tsx` — verify all prices match Stripe product IDs in `.env`
   - Add "Most Popular" badge to Pro tier (conversion optimization)
   - Add "For PIs and Labs" label to Lab tier

4. **Upgrade path from Pro → Lab:**
   - When Pro user tries to invite a member → trigger UpgradeModal showing Lab tier benefits
   - `services/frontend/src/components/UpgradeModal.tsx` — add "invite_member" trigger

**Files:**
- `services/backend/app/services/stripe_service.py` — Lab member provisioning on webhook
- `services/backend/app/api/routes/subscriptions.py` — team seat management
- `services/frontend/src/pages/Pricing.tsx` — pricing audit + conversion copy

---

## Phase 5: Frontend UI Improvements (Days 31-90)

**Prioritized by conversion/activation impact:**

### Priority 1: Browser Extension (Days 61-90, ~10-12 hours)
**Trigger: 10+ activated users confirm core web app is valuable.**

Highest single conversion ROI. Removes workflow silo (researchers currently must leave Overleaf/Google Docs to upload draft). Without this, activation is structurally capped.

**Scope:**
- Chrome Manifest V3 extension
- Service worker for auth token storage (reads from `localStorage` where Supabase stores tokens)
- Sidebar injection into Overleaf (`overleaf.com` URL match)
- "Analyze in Noesis" button → sends current document to `POST /drafts/analyze`
- Display top 3 feedback items in sidebar with severity badges
- "Open in Noesis" deep link to full analysis

**Files to create:**
- `services/browser-extension/manifest.json`
- `services/browser-extension/background.js`
- `services/browser-extension/sidebar.html + sidebar.js`
- `services/backend/app/core/config.py` — add `chrome-extension://` to CORS origins

### Priority 2: WebSocket Progress Streaming (Days 31-45, ~6-8 hours)
**Trigger: Users complain about not knowing if analysis is running.**

Backend is complete (`GET /drafts/{draft_id}/analysis-stream`, Redis pub/sub via `progress_publisher.py`). Only frontend missing.

**Files to create:**
- `services/frontend/src/hooks/useAnalysisStream.ts` — WebSocket hook with reconnect logic
- **Modify:** `services/frontend/src/components/DraftAnalysisModal.tsx` — show step-by-step progress bar

```typescript
// useAnalysisStream.ts
const useAnalysisStream = (draftId: string) => {
  // Connect to ws://backend/drafts/{draftId}/analysis-stream
  // Emit: { step: "claim_extraction", progress: 30, message: "Extracting claims..." }
  // Update DraftAnalysisModal progress bar in real-time
}
```

### Priority 3: OnboardingTour Design Token Fix (Days 15-20, ~2 hours)
`OnboardingTour.tsx` uses old design tokens (`bg-surface`, linear gradients). Looks jarring vs. rest of app.

**File:** `services/frontend/src/components/OnboardingTour.tsx`
- Replace all `bg-surface` → `bg-bg-surface`
- Remove gradient backgrounds, use flat `bg-bg-surface` cards
- Replace any `rounded-2xl`/`rounded-3xl` → `rounded-xl`

### Priority 4: Empty State & Post-Signup UX (Days 15-20, ~3 hours)
New users land on Projects page with no context. Need warm welcome.

**Files:**
- `services/frontend/src/pages/Projects.tsx` — add "Getting started" checklist in empty state
- `services/frontend/src/components/EmptyStateGuide.tsx` — already exists, enhance with 3-step quick-start

### Priority 5: Remove User-Adjustable RAG Settings (Days 15-20, ~2 hours)
Flagged as CRITICAL in CLAUDE.md. User-adjustable chunking settings cause confusion and produce worse results.

**Files to remove/modify:**
- Delete: `services/frontend/src/components/RAGSettingsModal.tsx` (or find actual filename)
- `services/backend/app/api/routes/rag.py` — remove user-facing settings endpoints
- Keep backend adaptive chunking logic, just make it server-controlled

---

## Phase 6: Scaling Architecture (Month 3-4)

**Trigger: >50 concurrent users OR a documented production incident. Do not touch before this.**

### Current bottlenecks (prioritized by when they'll actually be hit)

**Month 3 (~100 users):**
1. **GROBID single instance** — memory-limited to 2 concurrent PDF processing jobs. Fix: Add second GROBID container with round-robin load balancing in `docker-compose.prod.yml`
2. **Celery concurrency** — currently 2 workers in prod. Fix: Add second Celery worker replica (`celery-worker-2` in compose)

**Month 4 (~500 users):**
3. **Backend single instance** — FastAPI behind Nginx. Fix: Add `backend-2` replica + Nginx upstream load balancing
4. **Redis memory** — currently 128MB limit. Fix: Upgrade to 512MB or separate Redis instances for task queue vs. cache

**Month 5+ ($5K MRR):**
5. **Database connection pooling** — add pgBouncer between backend and Supabase
6. **CDN for static assets** — move PDFs/analysis results to CloudFront
7. **Separate read replicas** — Supabase supports read replicas on Pro plan

**Files:**
- `infra/docker-compose.prod.yml` — GROBID + Celery scaling
- `infra/nginx.conf` — upstream load balancing when backend replicas added

---

## Future: Overleaf Integration (Month 4+)

**Sequencing:** Browser extension first (simpler, proves workflow demand) → then native Overleaf plugin.

### Phase A: Browser Extension (Month 2-3)
See Phase 5 above. This is the first step toward Overleaf integration.

### Phase B: Overleaf API Integration (Month 4+)
Overleaf has a Git-based export feature (Overleaf → GitHub sync). Possible integration path:
1. User connects Overleaf project via OAuth or Git sync
2. Noesis pulls `.tex` files directly
3. Auto-analysis triggered on each commit/save
4. Feedback surfaced in Overleaf sidebar (via extension) or email digest

**Technical approach:**
- `POST /integrations/overleaf/connect` — OAuth flow with Overleaf
- Webhook or polling on Overleaf Git repository changes
- Parse `.tex` files for draft content (simpler than PDF for structured data)

**Trigger:** Only build after browser extension has 50+ active users and Overleaf is the #1 requested integration.

---

## 90-Day Milestone Map

```
DAYS 1-3:    Deploy production + legal cleanup (unblock outreach)
DAYS 4-30:   100% outreach. No new features. 80+ cold emails sent.
             Fix bugs only as real users surface them.

MILESTONE 1 (Day 30): 10 email responses, 5 demo calls scheduled

DAYS 31-45:  Build if triggered:
             - Collaborative features (IF 5+ activated users)
             - WebSocket streaming frontend (IF users complain)
             - OnboardingTour + empty state fixes (low effort, always do)
             - Remove RAGSettingsModal

MILESTONE 2 (Day 45): 10 activated users (analyzed ≥1 draft, returned Day 7)

DAYS 46-60:  Complete Lab tier billing (member provisioning)
             Continue outreach + demo calls

MILESTONE 3 (Day 60): First paying customer

DAYS 61-90:  Browser extension MVP (IF 10+ activated, core loop validated)
             Overleaf sidebar injection

MILESTONE 4 (Day 90): $1K MRR, 3 authentic PI testimonials

MONTH 4+:    Scaling architecture (GROBID + Celery replicas)
             Overleaf API integration
             Seed fundraising conversations ($5K MRR target)
```

---

## Kill Conditions (When to Stop and Reassess)

| Checkpoint | Condition | Action |
|---|---|---|
| Week 4 | <5 responses from 80+ cold emails | Rewrite messaging entirely. Run 5 user interviews. Do not send more emails with the same copy. |
| Week 8 | 0 activated users after 20+ demo calls | Stop all development. Do in-person demos at Georgia Tech. The core loop is broken. |
| Week 12 | 0 paying customers from 50+ demo calls | Pricing or positioning rethink. Consider freemium-only pivot. Talk to 3 PIs who said no. |
| Month 4 | 0 lab adoptions despite 10+ solo users | Collaboration is not the unlock. Individual productivity features are. Pivot pricing to Pro-only. |

---

## What NOT to Build (Next 90 Days)

- Real-time collaborative editing (Google Docs-style presence/cursors)
- Mobile app
- Slack/email integrations
- Grant proposal mode
- Argument structure visualization
- Word document export
- Video tutorials
- Any new AI analysis features (the analysis is good enough — validate it first)
- Human-in-the-loop claim validation UI (backend supports it; build when users ask)
- Any infrastructure for hypothetical scale

---

## Files to Create/Modify (Summary)

| Track | File | Action |
|---|---|---|
| Deploy | `services/frontend/src/pages/Landing.tsx` | Remove unverified university claims |
| Deploy | `infra/db-migrations/009, 010, 012` | Run on Supabase |
| Collaboration | `services/backend/app/api/routes/projects.py` | Add 5 team member routes |
| Collaboration | `services/frontend/src/pages/ProjectDetail.tsx` | Add Invite button |
| Collaboration | New: `components/InviteMemberModal.tsx` | Invite flow |
| Stripe | `services/backend/app/services/stripe_service.py` | Lab member provisioning on webhook |
| Stripe | `services/frontend/src/pages/Pricing.tsx` | Price audit + conversion copy |
| UI | `services/frontend/src/components/OnboardingTour.tsx` | Fix design tokens |
| UI | `services/frontend/src/pages/Projects.tsx` | Empty state checklist |
| UI | Remove: `RAGSettingsModal.tsx` | Delete or disable |
| WebSocket | New: `src/hooks/useAnalysisStream.ts` | WebSocket hook |
| WebSocket | `src/components/DraftAnalysisModal.tsx` | Wire progress bar |
| Extension | New: `services/browser-extension/` | Chrome extension directory |
| Extension | `services/backend/app/core/config.py` | Add extension CORS origin |
| Scaling | `infra/docker-compose.prod.yml` | GROBID + Celery replicas (Month 3+) |
