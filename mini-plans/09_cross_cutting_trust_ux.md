# 09 — Cross-Cutting: Trust, UX, Infrastructure

**Scope:** Privacy copy, error messages, progress visibility, OpenAI rate limits.
**Source:** `arch_plan.md` §10.

---

## 10.1 Plan-tier awareness
See `08_quotas_and_plan_tier.md`. Paying users currently get free-tier limits due to missing Stripe-webhook → quota-upgrade wiring.

## 10.2 OpenAI rate limits
- You've noted this. The 3 req/min free tier is crippling for batch uploads.
- Tier 1 requires $50 pre-paid.
- **Do this before any demo.** Without it, a user uploading 5 PDFs will see half of them stall.
- Long-term: monitor usage against tier limits; auto-request tier upgrade at thresholds.

## 10.3 Frontend error surfaces are thin
Multiple places return HTTP 400/403 with detail strings, but the frontend toast is generic. For a trust-sensitive product, specific errors matter.

**Examples of current vs. needed:**
| Current toast | What it should say |
|---|---|
| "Bad Request" | "We couldn't parse 3 of your 20 BibTeX entries. Entries 7, 12, 15 had missing required fields." |
| "Forbidden" | "You've used 30 of your 30 monthly PDFs. Upgrade to Pro for 100/month." |
| "Failed" (on doc) | "Upload failed during GPT analysis. Click retry to try again." |

**Implementation note:** backend errors should return structured JSON (`{ code, message, details }`), not string details. Frontend toast reads `.message` and optionally expands `.details`.

## 10.4 No "what the site is doing right now" indicator
- Upload → processing → analyzing → analyzed takes 30-90s per paper. Users see a spinner.
- Without stepwise visibility ("Parsing PDF", "Generating embeddings", "Running GPT-5.2 analysis"), bouncing feels likely.
- **LangGraph supports streaming** via its StateGraph events. Surface via WebSocket or Server-Sent Events.
- Minimum: a status ladder in the UI that reads the current `documents.status` + an estimated progress bar based on typical timing.

## 10.5 Privacy / not-used-for-training copy
- See `07_draft_analysis.md` §7f for the full analysis.
- Addresses the single biggest objection a PhD has before uploading an unpublished draft.
- **Surface locations:**
  - Draft upload modal footer.
  - Dedicated `/privacy` legal page.
  - Sidebar badge: "End-to-end private · Not used for training."
  - Signup page copy: "Your research stays yours."

## Priority
- **P0:** Privacy copy on draft upload (see `07_draft_analysis.md` §7f).
- **P1:** OpenAI Tier 1 upgrade (infra prerequisite for demo).
- **P2:** Stepwise progress visibility via LangGraph stream.
- **P2:** Structured backend errors + specific frontend toasts.
