# Noesis — Historical State Snapshot (pre-debugging baseline)

> Single archival record of what Noesis and its draft-analysis pipeline looked like, and the
> problems known, **before** the June 2026 eval/debugging overhaul and the OpenReview pivot.
> Replaces the old `plan/archive/` docs (00–05 eval plan-of-plans + pipeline_refactor_plan +
> README_EVAL_AND_FEATURES). Kept for context only — NOT an active plan. Current active plan:
> `plan/openreview_eval_plan.md`.

## 1. Product & stack
- **Noesis** — draft-aware research-intelligence platform for academics ("Know what Reviewer 2 will say before you submit" / pre-submission peer review). First target: Georgia Tech researchers.
- **Stack:** React + FastAPI + LangGraph + GPT-5.2 + pgvector (1536-dim, text-embedding-3-small) + Celery/Redis + Stripe + Supabase. Deployed Vercel (FE) + AWS (BE) + Supabase (DB/Auth/Storage).
- **Hard rules:** GPT-5.2 only (`model="gpt-5.2"`/`gpt-5.2-chat-latest`, `max_completion_tokens`, never `max_tokens`/gpt-4o); Supabase via `supabase.table()` only (no SQLAlchemy); embeddings always 1536-dim (never `-large`/3072).

## 2. Draft-analysis pipeline (the core feature)
A ~17–20-node LangGraph workflow over an uploaded manuscript
(`services/backend/app/services/draft_analysis_langgraph.py`, nodes under
`services/backend/app/workflows/draft_analysis/nodes/`). Node order (as mapped):

1. extract_structure → 2. profile_manuscript (routing_domain, lenses) → 3. extract_references →
4. extract_claims → 5. categorize_claims → 6. verify_citations → 7. search_literature (RAG) →
8. map_citations → 9. detect_gaps → 10. discover_external_sources → 11. citation_judge →
12. run_quality_diagnostics → 13. structural_checks → 14. editor_pass → 15–17. reviewer_panel
(×3 parallel: methodology, literature_positioning, clarity) → 18. reviewer_judge →
19. meta_reviewer → 20. synthesize_report.

**Emits:** anchored revision tasks (`RevisionTask`: anchor_text/evidence_quote, severity, suggested_action),
coverage gaps (`GapItem`), citation verdicts (`SuggestedCitationVerdict`), a 3-reviewer panel
(`ReviewerOutput`: rating 1–10, confidence), a meta-review (`MetaReviewOutput`: overall_recommendation,
must_address[]), and a deterministic readiness_score (0–100) + editorial recommendation. Readiness is
computed in `revision_tasks.py::calculate_revision_task_readiness_score` and clamped to the meta-review
recommendation band (`apply_meta_review_readiness_guardrail`).

All LLM nodes: `gpt-5.2-chat-latest`, temperature=0, structured Pydantic outputs via
`parse_chat_completion_with_retries` (`retry_utils.py`), shared OpenAI semaphore (cap 20).

## 3. Known problems before debugging (the bottlenecks)
**Validated thesis:** the reviewer-panel + meta-reviewer *reasoning* scored 8–9/10 on every eval —
every lost point was in the **deterministic orchestration layer** (task assembly → dedup → anchors →
publish gate), which mangled already-excellent LLM output. Fix the plumbing, not the model. No custom
model training, no pivot.

1. **Meta priorities dropped from tasks (#1 bottleneck).** `build_revision_tasks` never received the
   meta-review; `must_address` priorities were discarded for durable tasks (only used for the legacy
   `reviewer_feedback` table). Proven by `scripts/proof_meta_owns_tasks.py` on the run-9 sodium-ion
   export: the meta-reviewer's top priority was absent from the 9 durable tasks.
2. **Synthesis tail leak.** `synthesize_report` dropped computed signal (citation passages, external
   sources, meta priorities) before reaching the researcher — features existed but died at the tail.
3. **Brittle coverage matching.** Token-overlap coverage was fragile (0.47 vs 0.50 wrongly flipped
   coverage) → needed embeddings as primary, token-overlap only as no-key fallback.
4. **Mechanical claim→citation loop** emitted citation demands no reviewer asked for; author-coined-term
   extraction over-captured field acronyms (CRISPR/XRD/FIGURE).
5. **Post-hoc anchors.** LLM-paraphrased then regex-checked → verbatim anchor coverage stuck 0.5–0.78,
   breaking frontend highlight.
6. **Contamination = run failure.** `draft_publish_gate` marked clean runs `publishable=False` purely
   because RAG retrieved off-domain sources (already pruned upstream).

## 4. The eval system before the pivot
- `scripts/eval/`: `judge.py --bootstrap-gold` made GPT write a "gold critique" per draft, then scored
  Noesis output against it across 6 dimensions (grounding, hallucination_free, coverage,
  citation_accuracy, actionability, architecture_integrity). `run_harness.py` ran the full pipeline per
  draft; `run_eval.py` orchestrated the draft×corpus matrix; gold used a dual-file pattern
  (`draftN.gold.draft.md` candidate → `draftN.gold.md` approved).
- **Why it failed:** circular (GPT measuring GPT-likeness), slow (full pipeline per cell, 2–3 hrs),
  and `coverage` structurally broken (corpora held 1–3 papers so RAG found nothing). Mean stuck
  ≈6.97/10 against an uncalibrated 8.5 target for ~three weeks, worsened by operational rot (stale
  `.pyc`, `docker cp` silently not overwriting, fixes not live during the run that scored them).

## 5. Plans that existed at this point (now superseded)
- **Pipeline refactor (5 phases):** (1) guarantee meta `must_address` into durable tasks via embedding
  coverage; (2) defang mechanical claim→citation loop + tighten acronym/deductive guards; (3) verbatim
  anchors at generation + `repair_anchor`; (4) contamination ≠ publish failure; (5) meta-reviewer
  authors the structured ranked task spine directly (real destination). Target: stable re-eval ≥8.5.
- **Eval automation plan-of-plans (00–05):** 00 headless eval harness + judge; 01 synthesis-tail fix;
  02 refs extraction ("you forgot to cite X"); 03 external discovery + OpenAlex citation graph;
  04 citation misrepresentation ("cited paper doesn't support claim"); 05 determinism gates + eval
  thresholds. Opus wrote plans, Sonnet built in fresh per-plan sessions.

## 6. What came next
The circular GPT-gold eval was abandoned in favor of measuring Noesis against **real human peer
reviews from the OpenReview API** as ground truth — see `plan/openreview_eval_plan.md`. The honest
target was reset from the uncalibrated 8.5 to defensible human-ground-truth numbers (severity-weighted
weakness recall ≈0.35–0.55, decision correlation ρ≈0.3–0.6, hallucination rate <5%).
