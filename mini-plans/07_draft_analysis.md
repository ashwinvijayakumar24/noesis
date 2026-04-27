# 07 — Draft Analysis (Peer-Review Analysis) — THE CORE FEATURE

**Scope:** Two-stage review, Reviewer 1 / Reviewer 2 personas, pre-upload questions, external paper pull, revision tracking, privacy copy.
**Source:** `arch_plan.md` §7, §9.5.

---

## Your Intent
Mimic a real peer review. Two stages:
- **Stage 1 — General editing:** spelling, grammar, formatting. Pre-upload questions about citation style + paper type (thesis, dissertation, journal).
- **Stage 2 — Peer review:**
  - **Reviewer 1:** highlights pros of the paper.
  - **Reviewer 2:** major and minor critiques, organized by section / type / suggested fix.
- Pulls from project literature, insights, and **≥10 external papers** to critique.
- If draft analysis runs before discovery, populates discovery with 5 most relevant papers.
- **Revision tracking:** v2 upload shows which v1 critiques were resolved.
- **Privacy:** draft uploads are secure, private, explicitly not used to train AI.

## Current Tech
- Services:
  - `services/backend/app/services/draft_processing.py:401-700` — orchestrator.
  - `services/backend/app/services/claim_analysis.py` — claim extraction (15-25 per 10 pages, categorized by type/subtype/level).
  - `services/backend/app/services/coverage_analysis.py` — gap detection via semantic sim.
  - `services/backend/app/services/reviewer_feedback.py` — GPT-5.2 prompt producing feedback objects with 7 types (positioning/argumentation/coverage/methodology/evidence/clarity/logic) and 4 severities (critical/major/minor/suggestion).
  - `services/backend/app/services/draft_comparison.py:1-425` — v1/v2 diff with improvement score.
- Workflow: LangGraph in `services/backend/app/workflows/draft_analysis/`.
- Frontend: `services/frontend/src/pages/DraftAnalysis.tsx` + `components/draft-analysis/*`.
- Quota: 5 drafts/month for everyone (not plan-aware).

## How It Works
```
POST /drafts (upload)
  ↓
GROBID extract → structure (sections, refs, claims hints)
  ↓
claim_analysis.extract_claims() → 15-25 claims/section, categorized
  ↓
coverage_analysis.detect_gaps() → compares each claim's embedding against match_document_chunks RPC over project literature
  ↓
reviewer_feedback.generate_feedback() → GPT-5.2 produces feedback_items[]
  ↓
UPDATE draft_analysis SET claims=..., gaps=..., feedback=...
```

## Value to Researchers
This is the feature that justifies the tool. "Peer review before peer review" is a legitimate wedge. But right now what's shipped is closer to "AI critique" than the layered, adversarial two-reviewer experience you described.

## What's Working
- ✅ Claim extraction is well-structured (type, subtype, level, importance score 0.0-1.0).
- ✅ Feedback schema is rich (7 types, 4 severities, specific suggestions, example fixes).
- ✅ `draft_comparison.py` produces a real v1→v2 diff including `claims_added/removed/improved/worsened`, `feedback_addressed`, `gaps_resolved`, and `improvement_score` 0-100.
- ✅ AI narrative: evolution_summary, key_improvements, remaining_gaps, reviewer_readiness.
- ✅ Reviewer feedback prompt (`reviewer_feedback.py:37-193`) is exceptionally well-written — 150+ lines of examples and guardrails against auto-writing. **Your best prompt in the codebase.**

## Problems

### 7a. No Stage 1 / Stage 2 split
- Currently: one pass, one output. No separate grammar/formatting stage.
- Your spec is correct on product intuition — Stage 1 is *mechanical* (grammar, formatting, citation-style compliance), Stage 2 is *intellectual* (peer review).
- Using GPT-5.2 for grammar is overkill and dilutes the reviewer persona.
- **Fix:** Stage 1 uses `gpt-5-mini` or even a dedicated grammar check; Stage 2 uses GPT-5.2 for deep critique.
- **Today:** users pay GPT-5.2 prices for grammar corrections, and reviewer output is cluttered with "consider comma placement" notes sitting next to "your methodology is unjustified."

### 7b. No Reviewer 1 / Reviewer 2 split (P0 — core product promise)
- The feedback schema has `feedback_type` (positioning, coverage, etc.) and `severity`, but no *persona*. All feedback is delivered in one voice.
- Your spec is adversarial-by-design: Reviewer 1 finds what's good (pros), Reviewer 2 is the skeptic (cons). This is how real journals structure reviews.

**Implementation note:** Two GPT-5.2 calls, different system prompts:
- **R1:** "You are an encouraging senior reviewer. Highlight the strongest arguments, most novel contributions, and best evidence. Be specific."
- **R2:** The existing reviewer_feedback prompt.

This is a significant UX upgrade and makes the "two reviewers" story concrete on the marketing site.

### 7c. No pre-upload questions
- Your spec: before upload, ask about citation style + paper type (thesis/dissertation/journal).
- Matters a lot for Stage 1 (which citation rules — APA vs. Chicago vs. IEEE vs. Vancouver) and for tuning Stage 2's expectations (a thesis is judged differently from a journal submission).
- Not implemented. Probably a 2-3 field modal before the upload dropzone.

### 7d. External paper pulling doesn't happen
- Coverage analysis compares the draft's claim embeddings against `match_document_chunks` over the project's literature. If a claim is not covered, it's flagged as a gap.
- Your spec: analysis should "pull at least 10 external papers to help critique the draft."
- Reality: zero external search during draft analysis. The coverage gap detection tells you *what's missing* but doesn't actually go find those papers.
- **Fix:** when a gap is detected, trigger a targeted Discover search (using the gap description as the query) and attach 3-5 suggested papers to each gap. This completes the cross-pollination loop (draft → discovery pre-population; also see `06_discover_papers.md` §6f).

### 7e. Revision tracking is half-built
- `draft_comparison.py` is solid; the backend computes everything.
- Frontend (`DraftAnalysis.tsx`) has a comparison view but doesn't render a per-feedback-item "resolved ✓" / "still open" badge against v1's items.
- User can't see "of my 12 critiques from v1, 8 are resolved and 4 remain."
- **Core value proposition of iterating** in Noesis. Without visible resolution state, users don't see the incremental improvement arc.

### 7f. No privacy copy (P0 — trust)
- You specifically called this out. Nowhere in the UI (draft upload, analysis results, settings, pricing) is there a sentence that says "Your drafts are private and are never used to train AI models."
- For researchers whose work is confidential pre-publication, this is a **deal-breaker** for adoption. Competitors (Thesify, Elicit) make this prominent.
- **Minimum:** upload modal footer + a legal page.
- **Better:** a badge on the draft page that reads "End-to-end private · Not used for training."

### 7g. Image/figure handling for drafts
Same gap as `03_literature_upload_pdf.md` §3b. A draft with a results figure can't be critiqued on the figure.

### 7h. Draft quota is not plan-aware
5/month for everyone. Pro users who pay $12/mo get the same draft cap as free users. See `08_quotas_and_plan_tier.md`.

### 7i. "What do researchers want before peer review?" (your question)
Web research summary: peer reviewers evaluate work on **validity, significance, originality**, and flag inaccuracies, methodological issues, and gaps in reasoning (Wiley, Taylor & Francis, NIH). Decisions fall into reject / major amendments / minor amendments / accept.

**Canonical critique categories (ordered by impact on reject decisions):**
1. **Methodological validity** — is the experimental design sound? are confounds controlled? is statistical analysis appropriate?
2. **Novelty / positioning** — is the contribution clear? is prior work engaged honestly?
3. **Evidence strength** — do claims match what the data actually shows? overclaim risk?
4. **Reproducibility** — can another researcher follow this? enough detail in methods?
5. **Literature coverage** — key citations missing? recent work ignored?
6. **Clarity / structure** — can a peer in the field follow the argument?
7. **Limitations acknowledged** — or swept under the rug?

Your current 7 feedback types (positioning, argumentation, coverage, methodology, evidence, clarity, logic) map well onto this list. You're covering 6/7. **Missing: reproducibility / limitations acknowledgment** as explicit categories. Consider adding `reproducibility` and `limitations` as feedback types.

## Competitive Quotas (Recommendation)
See `10_answered_questions.md` §9.8 for details.
- **Free:** 2/month (5 is too generous — this is your core paid feature; 5 gives away the whole product)
- **Pro:** 20/month
- **Team:** unlimited

Rationale: draft analysis is the *wedge*; giving 5 free means a grad student finishes their thesis on the free tier. 2 lets them try once, see value, pay.

## Priority
- **P0 (trust):** Privacy copy everywhere draft upload appears.
- **P0 (core feature):** Reviewer 1 / Reviewer 2 persona split.
- **P1:** Stage 1 (mechanical) vs. Stage 2 (intellectual) split; use `gpt-5-mini` for Stage 1.
- **P1:** Pre-upload questions (citation style, paper type).
- **P1:** External paper pull (draft analysis triggers Discover queries for each gap).
- **P1:** Per-item resolution state in revision view.
- **P2:** Plan-aware draft quota.
- **P2:** Add `reproducibility` + `limitations` as feedback categories.
- **P2:** Figure/table extraction for drafts.
