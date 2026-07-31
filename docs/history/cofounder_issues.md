# Cofounder Issue Pack

Scope guardrails (apply to **every** issue below):
- **Do NOT touch** the draft-analysis UI, the eval pipeline (`scripts/eval/*`), the RAG pipeline (`rag_*`, `draft_rag_integration.py`), or anything affecting model output quality / prompts / LangGraph nodes.
- Follow existing design patterns: Supabase via `supabase.table()` only (no SQLAlchemy), GPT‑5.2 with `max_completion_tokens`, Tailwind tokens from `tailwind.config.js`, dark charcoal theme, `rounded-xl` max.
- **Every** issue requires: unit tests + integration tests, green CI, and a PR that the maintainer reviews personally. No merge on red or skipped tests.

---

## Issue 1 — Wire Stripe checkout + billing into the frontend

**Labels:** `feature`, `frontend`, `billing`, `P0`

### Problem
The Stripe **backend** is complete (`services/backend/app/api/routes/subscriptions.py`, `stripe_service.py`) — checkout, cancel, customer portal, usage, webhooks all exist. But the **frontend has no integration**: `services/frontend/src/lib/api.ts` has no `subscriptions`/`checkout`/`portal` client, and there is no Account/Billing page. Users literally cannot start a paid subscription from the app.

### Scope
- Add a `subscriptions` namespace to `api.ts`:
  - `getPlans()` → `GET /subscriptions/plans`
  - `createCheckout(token, { plan_tier, success_url, cancel_url, team_seats? })` → `POST /subscriptions/checkout`
  - `cancel(token, { cancel_immediately })` → `POST /subscriptions/cancel`
  - `getUsage(token)` → `GET /subscriptions/usage`
  - `getPortalSession(token, return_url)` → `GET /subscriptions/portal-session`
- New `AccountSettings.tsx` (or `Billing.tsx`) page + route: shows current plan, usage bars (reuse quota-summary), Upgrade buttons (redirect to `checkout_url`), Manage Billing (portal), Cancel.
- Wire `Pricing.tsx` "Upgrade" CTAs to `createCheckout` for authed users; redirect anon users to signup.
- Handle the `success_url`/`cancel_url` round-trip (toast on return).

### Out of scope
Backend Stripe logic (already done), pricing copy/numbers (already correct in memory), draft-analysis UI.

### Acceptance criteria
- [ ] Authed user can click Upgrade → land on Stripe Checkout → return to success state.
- [ ] Account page renders current plan + usage from live endpoints.
- [ ] Cancel and Manage Billing (portal) both work end-to-end against Stripe **test mode**.
- [ ] Unit tests (vitest) for the `api.subscriptions.*` client (mocked fetch) and for the Account page render/states (loading/error/free/pro/team).
- [ ] Integration test: checkout button → asserts correct payload POSTed and redirect to returned `checkout_url`.
- [ ] `npx tsc --noEmit` clean; `npm run lint` clean; `npm run build` passes.

---

## Issue 2 — Harden Stripe webhooks: idempotency + remove insecure fallback

**Labels:** `bug`, `security`, `billing`, `P0`

### Problem
`POST /webhooks/stripe` (`subscriptions.py:178`) has two real risks:
1. **No idempotency.** Stripe retries deliver the same event multiple times. Handlers (`handle_checkout_completed`, `handle_subscription_updated`, `handle_subscription_deleted`) run every time with no dedup, so duplicate deliveries can re-process upserts/quota syncs.
2. **Insecure fallback.** When `STRIPE_WEBHOOK_SECRET` is unset the endpoint parses raw JSON with **no signature verification** — anyone can POST a forged `customer.subscription.deleted` and downgrade/alter any account.

### Scope
- New table `stripe_webhook_events` (migration): `event_id text primary key`, `type text`, `processed_at timestamptz default now()`. Insert before processing; if `event_id` already present, return `{"status":"duplicate"}` without re-running handlers.
- Require signature verification **always** in non-dev environments. If `STRIPE_WEBHOOK_SECRET` is missing while `ENVIRONMENT != "development"`, reject with 500/misconfig — never fall back to unsigned JSON.
- Keep handler bodies unchanged in behavior; only add the dedup guard around them.

### Out of scope
New event types (covered by Issue 3), refunds, any pricing change.

### Acceptance criteria
- [ ] Replaying the same event id twice processes it once (second call returns duplicate, DB state unchanged).
- [ ] Unsigned request in non-dev env is rejected.
- [ ] Invalid signature → 400 (already true; keep a regression test).
- [ ] Unit tests for dedup + signature-required paths; integration test using `stripe.Webhook` test fixtures / `stripe trigger`.
- [ ] Backend CI green.

---

## Issue 3 — Stripe dunning: handle failed payments, past_due, and seat changes

**Labels:** `feature`, `billing`, `P1`

### Problem
Only `checkout.session.completed`, `customer.subscription.updated`, `customer.subscription.deleted` are handled. We have no story for **failed payments** (involuntary churn) or **team seat quantity changes**.

### Scope
- Handle `invoice.payment_failed` → mark subscription `status="past_due"`, record a `last_payment_failed_at`, trigger a notification hook (email is Issue 6 — emit an event/log placeholder if email not yet built).
- Handle `invoice.payment_succeeded` → clear past_due back to `active` and re-sync quota.
- Handle `customer.subscription.trial_will_end` (no-op log + notification hook) if trials are ever enabled.
- In `handle_subscription_updated`, also persist **seat count** for team plans (`items.data[0].quantity`) into a `seats` column so the app knows how many seats are paid for.

### Out of scope
Building the email transport itself (Issue 6), grace-period UI.

### Acceptance criteria
- [ ] `past_due` and recovery transitions update DB + quota tier correctly (past_due keeps access per existing `enforced_tier` logic; document the decision).
- [ ] Team seat changes (2↔3) are reflected in `subscriptions.seats`.
- [ ] Unit tests for each new event handler with representative Stripe payloads.
- [ ] Migration for `seats`, `last_payment_failed_at`.
- [ ] Backend CI green.

---

## Issue 4 — Replace `print()` with structured logging across billing/services

**Labels:** `chore`, `observability`, `P2`

### Problem
`stripe_service.py` swallows webhook handler errors with `print(f"Error ...")`. These are billing-critical failures that must be visible in logs/Sentry, not stdout prints. Sentry is already initialized in `main.py`.

### Scope
- Introduce a module logger (`logging.getLogger(__name__)`) in `stripe_service.py` and replace `print(...)` with `logger.exception(...)` / `logger.error(...)`.
- Ensure exceptions in webhook handlers are captured by Sentry (explicit `capture_exception` if the handler must not re-raise).
- Audit other services for stray `print()` in error paths **only within billing/subscriptions/quota scope** — do not touch draft-analysis, eval, or RAG files.

### Acceptance criteria
- [ ] No `print()` remains in `stripe_service.py`.
- [ ] A simulated handler failure emits a log record (assert via `caplog`) and is reported to Sentry (mock/spy).
- [ ] Backend CI green.

---

## Issue 5 — Make frontend CI blocking (type-check + lint + build + tests)

**Labels:** `chore`, `ci`, `P1`

### Problem
`.github/workflows/ci.yml` frontend job runs lint, `tsc --noEmit`, and build with `|| echo "⚠ ... non-blocking"`. TypeScript errors and build failures merge silently. There is also no vitest run in CI despite tests existing (`DraftAnalysis.test.ts`, `components/__tests__`).

### Scope
- Make `npx tsc --noEmit` and `npm run build` **blocking** (remove `|| echo`).
- Add a vitest step (`npm run test -- --run`) as a blocking step.
- Keep lint non-blocking **only if** the current tree has lint warnings; otherwise make it blocking too. Document the choice in the PR.

### Out of scope
Backend CI changes; new test content (just run what exists). Do not edit draft-analysis tests' assertions.

### Acceptance criteria
- [ ] CI fails on a deliberately introduced type error (demonstrate in PR, then revert).
- [ ] vitest runs in CI and is required.
- [ ] Existing tree passes the now-blocking checks (fix only trivial blockers caused by enabling, escalate anything non-trivial).

---

## Issue 6 — Transactional email provider + core lifecycle emails

**Labels:** `feature`, `infra`, `P1`

### Problem
There is no product email transport (only Supabase auth emails). We can't send payment receipts, payment-failure notices, quota-warning emails, or a welcome email. Issues 3 emits notification hooks that currently no-op.

### Scope
- Add a thin email service (recommend **Resend**) behind an interface so it's swappable and testable; config via env (`RESEND_API_KEY`, `EMAIL_FROM`).
- Templates: welcome (on first subscription/signup), payment succeeded receipt, payment failed / past_due, quota 80% warning.
- Wire the notification hooks from Issue 3 to this service.

### Out of scope
Marketing/drip campaigns, HTML design system overhaul, anything touching draft-analysis content.

### Acceptance criteria
- [ ] Email service has a `send(template, to, context)` API with a no-op/test transport in `ENVIRONMENT=test`.
- [ ] Unit tests assert correct template + recipient + context per trigger (transport mocked — **no real sends in CI**).
- [ ] Integration test wiring at least the payment-failed path end-to-end with the mock transport.
- [ ] Backend CI green.

---

## Issue 7 — Per-user rate limiting on expensive authed endpoints

**Labels:** `security`, `infra`, `P2`

### Problem
Rate limiting (`slowapi`) is keyed by `get_remote_address` (IP). Behind Vercel/load balancers this is unreliable and lets a single authed user hammer expensive endpoints. We need per-user limits on costly operations (uploads, BibTeX import, discovery) — **not** the draft-analysis pipeline.

### Scope
- Add a per-user key function (use the authenticated user id when present, fall back to IP) and apply sensible limits to: document upload, BibTeX import, paper discovery/search endpoints.
- Make limits configurable per plan tier where it makes sense (reuse quota tiering).

### Out of scope
Draft-analysis endpoints, eval, RAG. No changes to the global IP limiter defaults unless needed.

### Acceptance criteria
- [ ] Per-user limiter triggers 429 in tests for the targeted endpoints.
- [ ] Anonymous requests still fall back to IP limiting.
- [ ] Unit/integration tests for limit-exceeded and under-limit paths.
- [ ] Backend CI green.

---

## Issue 8 — Deepen `/health` into a real readiness probe

**Labels:** `chore`, `infra`, `P2`

### Problem
`/health` (`main.py:170`) is shallow. For AWS deploys we want a readiness check that verifies critical dependencies (Supabase reachable, Redis/Celery broker reachable, Stripe key configured) so a half-broken deploy is caught.

### Scope
- Add `/health/ready` returning per-dependency status (db, redis, stripe-config) with overall 200/503.
- Keep the existing shallow `/health` as a fast liveness probe.

### Out of scope
Eval/RAG/draft-analysis subsystems in the readiness check.

### Acceptance criteria
- [ ] `/health/ready` returns 503 when a dependency is down (simulated) and 200 when all green.
- [ ] Unit tests mock each dependency up/down.
- [ ] Backend CI green.

---

## Ready-to-run `gh` commands (after `gh auth login -h github.com`)

```bash
gh issue create --title "Wire Stripe checkout + billing into the frontend" --label "feature,frontend,billing,P0" --body-file <(sed -n '/^## Issue 1/,/^---$/p' plan/cofounder_issues.md)
# ...repeat per issue, or create labels first:
gh label create P0 --color B60205 2>/dev/null; gh label create P1 --color D93F0B 2>/dev/null; gh label create P2 --color FBCA04 2>/dev/null
gh label create billing --color 0E8A16 2>/dev/null; gh label create observability --color 1D76DB 2>/dev/null
```
