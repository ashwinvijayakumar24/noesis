# Noesis Current State

Last updated: May 10, 2026

This is the live source of truth for Noesis product, engineering status, and next priorities. Update this file whenever product scope, production behavior, pricing, quotas, or outreach status changes.

## Product Position

Noesis is a draft-aware research intelligence platform for academics. Researchers build a project literature library, generate a Literature Map, discover missing papers, and analyze their own draft against the literature before submission.

Core rule: Noesis critiques and reviews. It does not auto-write or rewrite user drafts.

Current GTM stage: production hardening and outreach. We are starting direct outreach to labs now, with Georgia Tech researchers and labs as the first wedge before broader university expansion.

## Live Product Loop

1. User signs in.
2. User creates a project.
3. User builds a literature base with PDFs, BibTeX/Zotero imports, and saved recommendations.
4. User generates a Literature Map.
5. User uses Discover to find and save missing papers.
6. User uploads a draft with paper type and citation style.
7. Noesis runs Stage 1 editing checks plus reviewer-style analysis.
8. User revises, uploads a new draft, and compares progress.

Primary workspace: `services/frontend/src/pages/ProjectDetail.tsx`

Primary draft analysis view: `services/frontend/src/pages/DraftAnalysis.tsx`

## Stack

- Frontend: React 19, TypeScript 5.9, Vite 7.2, TailwindCSS 4 package with local `tailwind.config.js` tokens
- Backend: Python 3.11 in production, FastAPI 0.115, Pydantic v2
- Database/Auth/Storage: Supabase PostgreSQL 15, Supabase Auth, Supabase Storage
- Background jobs: Celery plus Redis, concurrency 4
- PDF processing: GROBID 0.7.0 plus PyMuPDF fallback
- AI: GPT-5.2 / `gpt-5.2-chat-latest` with `max_completion_tokens`; `gpt-5-mini` for Stage 1 editing
- Embeddings: RAG paths currently use `text-embedding-3-large` dimension-reduced to 1536 where needed; some comparison paths use `text-embedding-3-small`
- Payments: Stripe code exists, but production pricing/checkout is not finished
- Deployment: Vercel frontend, AWS backend, Supabase DB

## Critical OpenAI Rule

GPT-5.2 calls must use `max_completion_tokens`, not `max_tokens`. Do not revert to `gpt-4o`.

Correct:

```python
client.chat.completions.create(
    model="gpt-5.2",
    max_completion_tokens=2000,
    messages=[...],
)
```

Wrong:

```python
client.chat.completions.create(
    model="gpt-4o",
    max_tokens=2000,
    messages=[...],
)
```

## What Changed In The Last Two Weeks

### Product Shape

- Chat was removed from the core product. Noesis is no longer positioned as a chat-with-papers tool.
- `ProjectDetail` became the live workspace with `Literature`, `Literature Map`, `Discover`, and `Drafts`.
- "Insights" was renamed in product language to "Literature Map".
- The literature system was unified so PDFs, BibTeX/Zotero imports, and saved recommendations land in the same project library.
- Landing/pricing copy now reflects the project loop, privacy stance, and current quota model.

### Literature Map

- Literature Map generation is now a first-class project workflow.
- Free users are limited to 5 Literature Map refreshes/day via Redis key `daily_insights:{user_id}:{date}`.
- Pro/Team/Enterprise/Admin tiers are unlimited for Literature Map refreshes.
- Backend staleness detection now compares analyzed document count and latest document update time against the last map generation.
- Literature Map responses include quota state, progress state, stale state, and recommendation groupings.
- Inline/top-level recommendation context is wired through `paper_recommendations`.

### Discover

- The newer Discover surface uses `POST /paper-recommendations/projects/{id}/generate`, search, pagination, save, and quota-status endpoints.
- Free Discover quota is 5 actions/day; Pro is 50/day; Team/Enterprise/Admin are effectively unlimited.
- The Discover pool holds up to 30 recommendations and paginates 5 at a time in the UI.
- Save-to-literature uses `POST /paper-recommendations/projects/{id}/save-discovered/{recommendation_id}` and creates a discovered document that resolves through the BibTeX/PDF resolution path.
- The older `paper_discovery.py` route still exists and auto-adds papers. Treat it as legacy unless it is deliberately revived or removed.

### Draft Analysis

- Draft uploads now capture `paper_type` and `citation_style`.
- Stage 1 mechanical editing exists in `stage1_editing.py`, uses `gpt-5-mini`, and is stored canonically at `draft_analysis.analysis.editing_feedback`; the analysis API returns it as `editing_feedback`.
- The peer-review surface now shows the editor decision before the meta-review and four-reviewer panel.
- Draft-analysis structured-output schemas reject extra fields. Async structured OpenAI calls use shared validation retry/OpenAI retry helpers with the process-wide semaphore; legacy sync structured calls use the same validation/OpenAI retry helper without the async semaphore.
- Reviewer 1 strengths generation exists in `reviewer1_feedback.py`.
- The four-reviewer panel and meta-review are the main intellectual review path; legacy flat reviewer feedback remains for actionable issue lists and backwards compatibility.
- Draft analysis progress emits stepwise events over the analysis stream.
- External source discovery for weak claims/gaps was added to the LangGraph workflow and attaches external source candidates to claims/gaps when possible.
- Anchor QA and text anchoring helpers were added to improve feedback location and reliability.
- Privacy copy now appears on signup, privacy policy, document/draft analysis surfaces, and Literature Map surfaces.
- Reliability tests were added for anchor QA and external-source behavior.
- Internet scanner probes such as `/.env`, `.git`, WordPress/PHP probes, and path-traversal query attempts are blocked before protected routes and filtered out of Sentry noise.

### Quotas And Plan Awareness

- Canonical plan limits now live in `services/backend/app/services/quota_management.py`.
- Free: 3 projects, 30 PDFs/month total, 30 BibTeX refs/month total, 2 draft analyses/month, 5 Discover actions/day, 5 Literature Map refreshes/day.
- Pro: 10 projects, 100 PDFs/month total, 100 BibTeX refs/month total, 20 draft analyses/month, 50 Discover actions/day, unlimited Literature Map refreshes.
- Team/Enterprise/Admin: effectively unlimited usage with hard caps.
- `sync_user_quota_plan()` updates quota fields without resetting usage counters.
- Stripe webhook handlers call quota sync on checkout completion, subscription updates, and cancellation.
- Migration `016_user_quota_plan_alignment.sql` backfills and aligns quota rows.

Important caveat: Stripe pricing is not finished. Checkout/webhook code exists, but production Stripe price IDs, live webhook verification, pricing-page-to-app behavior, billing portal flow, and end-to-end paid upgrade testing still need to be completed before we claim payments are live.

### Production Hardening

- Sentry bot/scanner path traversal events against `/index.php?...` are now handled as clean JSON 400 responses instead of unhandled Starlette `ExceptionGroup`/500 errors.
- Security middleware now returns `JSONResponse` directly for validation failures inside middleware.
- Regression test added for the Sentry-style path traversal request.

### Testing

- Backend E2E suite lives in `services/backend/tests/e2e/`.
- Current documented E2E command:

```bash
cd services/backend
python3 -m pytest tests/e2e/ -v --timeout=120 -m "not slow"
```

- Targeted security middleware regression:

```bash
python3 -m pytest services/backend/tests/test_ci_api_contracts.py -q
```

## Mini-Plan Progress

The old curried-hedgehog audit and mini-plans were accurate as problem-finding docs. They are no longer the live truth. Use this progress list when deciding what to build next.

### Completed Or Mostly Completed

- Literature Map rename and main workspace integration.
- Literature Map daily quota enforcement.
- Backend Literature Map staleness state.
- Literature Map progress snapshots and error payloads.
- Plan-aware PDF/BibTeX/draft quota constants.
- Pro project limit changed from 999 to 10.
- Stripe webhook quota sync helpers added.
- Draft upload context: paper type and citation style.
- Stage 1 editing pass.
- Reviewer 1 strengths pass.
- Draft progress stream.
- External source discovery node for draft analysis.
- Privacy/not-used-for-training copy in major user-facing surfaces.
- Sentry/security middleware 400 handling for scanner requests.

### Still Open

- Stripe production pricing is not complete and must be connected/tested end to end.
- Collaboration/team project features are not built, despite Team pricing copy.
- Overleaf/inline editing is not built. Next expected direction: browser/Overleaf workflow with inline feedback/editing context rather than forcing PDF export/upload.
- PDF text extraction still needs stronger parsing. Figures, tables, captions, section positions, and page anchors remain weak.
- Claim extraction and evidence grounding need another quality pass, especially for exact text anchors, claim granularity, and support strength.
- Discover still needs cleanup around the legacy `paper_discovery.py` auto-add route, dismissal/no-repeat behavior, and clearer save-accounting semantics.
- Draft revision tracking exists in backend comparison logic, but per-item resolved/still-open UX needs to be stronger.
- Collaboration needs a concrete product shape: shared projects, lab workspaces, roles, invites, comments, and advisor/student review flows.
- Structured frontend errors are still inconsistent across upload, BibTeX, quota, and analysis failures.

## Outreach Status

We are no longer waiting for a perfect product before market contact. Start reaching out to labs now.

Immediate outreach target:

- Georgia Tech labs, PhD students, postdocs, and PIs.
- Ask for draft-review workflow pain, not generic AI-tool interest.
- Demo the project loop: literature library, Literature Map, Discover, draft review.
- Be explicit that payments are not fully finished yet if pricing comes up.

Near-term proof goals:

- 100-500 signups in 30 days.
- Meaningful lab conversations and repeated draft uploads.
- First signs of willingness to pay before polishing billing too deeply.
- $5K MRR remains the Month 3 ambition, but only after Stripe is actually connected and validated.

## Next Build Priorities

### P0 Before Serious Paid Launch

1. Finish Stripe production connection:
   - verify live price IDs
   - verify webhook endpoint and signature secret
   - test Pro checkout from pricing page through quota upgrade
   - test cancellation/downgrade behavior
   - ensure Team copy does not overpromise collaboration before it exists
2. Run outreach to labs in parallel with product hardening.
3. Improve PDF parsing and anchors enough that draft feedback reliably jumps to the right text.
4. Tighten claim extraction/evidence grounding quality.

### P1 Product Differentiators

1. Collaboration:
   - shared projects
   - invite flow
   - roles for owner/editor/viewer or PI/student
   - comments or assignment on reviewer feedback
2. Inline editing and Overleaf workflow:
   - first pass can be browser extension/sidebar
   - later pass can use Overleaf Git/API sync if demand is proven
3. Stronger PDF/document parsing:
   - evaluate PyMuPDF4LLM for markdown/section structure
   - keep GROBID where citation extraction is stronger
   - consider pdffigures2 only if figure critique becomes demo-critical
4. Better claims:
   - fewer vague claims
   - better claim spans
   - better support/contradiction scoring
   - more transparent reason for each unsupported-claim finding

### P2 Cleanup

1. Decide whether to delete or fully deprecate `api/routes/paper_discovery.py`.
2. Remove or archive stale root docs once this file is accepted as the source of truth.
3. Reconcile old migration docs with the current migration list.
4. Keep `here-is-the-comprehensive-curried-hedgehog.md` as a historical audit, not a live plan.

## Current Documentation Map

- `current_state.md`: live source of truth
- `README.md`: concise repo overview and developer entrypoint
- `AGENTS.md`: agent-specific operating guide
- `claude.md`: Claude/Cursor context and engineering rules
- `docs/current-architecture.md`: architecture snapshot
- `mini-plans/`: historical mini-plan status and remaining work
- `here-is-the-comprehensive-curried-hedgehog.md`: historical architecture audit
- `docs/historical/`: fundraising, roadmap, and old planning material only
