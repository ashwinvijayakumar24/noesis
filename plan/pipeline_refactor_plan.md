# Noesis Draft-Analysis Pipeline — Architecture Refactor Plan

> **Thesis (validated, runs 6-9 + offline proof):** the reviewer panel + meta-reviewer
> reasoning scores 8-9/10 ("Scholarly Depth") on EVERY Gemini eval. Every lost point is in
> the **deterministic orchestration layer** (task assembly → dedup → anchors → gate), which
> mangles already-excellent LLM output. Fix the plumbing, not the model. NO custom-model
> training, NO company pivot, do NOT touch reviewer/meta reasoning prompt *substance*.
>
> **Proof:** `scripts/proof_meta_owns_tasks.py` on the run-9 sodium-ion export shows the
> meta-reviewer's #1 priority ("add a literature-selection methodology") is absent from the
> 9 durable tasks. The proof ALSO showed lexical (token-overlap) coverage matching is
> brittle (0.47 vs 0.50 wrongly flips coverage) → Phase 1 MUST use embeddings, and Phase 5
> (meta authors tasks) is the real destination.

**Constraints (apply to every phase):**
- GPT-5.2 only: `model="gpt-5.2"` or `"gpt-5.2-chat-latest"`, `max_completion_tokens` (NEVER `max_tokens`/gpt-4o).
- Supabase only. Embeddings are **1536-dim** (`text-embedding-3-small`) — never default to `-large` (3072-dim).
- No DB schema change unless required (only Phase 5 needs one → migration in `services/backend/migrations/`).
- All **347 unit tests must stay green** (`cd services/backend && python3 -m pytest tests/ -q --timeout=60 --ignore=tests/e2e`).
- Prefer DELETING guards over adding. Note net line-count change per phase.
- Each phase = one fresh implementation context (Opus/Sonnet). Rebuild Docker after Phases 2 and 4, then re-eval.

---

## Phase 0 — Verified APIs / anchors (DISCOVERY, DONE)

Confirmed against the live tree (cite these; do NOT invent variants):

| Symbol | Location | Signature / fact |
|--------|----------|------------------|
| `build_revision_tasks` | `revision_tasks.py:848` | kwargs: `diagnostic_findings, reviewer_outputs, claims, gaps, structural_feedback, structure=None, parser_quality=None, manuscript_profile=None`. Returns at `:983` after `rescue_critical_diagnostics` (`:979`) + `final_pairwise_dedup` (`:982`). |
| claims→citation loop | `revision_tasks.py:910-938` | `for claim in claims`; gate at `:912` `needs_missing_citation_task`; self-ref skip `:917`; `task_type="citation"` `:922`; severity `:925`. |
| `_cosine_similarity` | `revision_tasks.py:275` | `(left: list[float], right: list[float]) -> float`. Reuse — do not re-implement. |
| `_task_similarity_text` | `revision_tasks.py:286` | builds task text for embedding. |
| `_embedding_clusters` | `revision_tasks.py:296` | calls `embed_chunks([...], model="text-embedding-3-small")`; **returns `{}` if `PYTEST_CURRENT_TEST` set OR no `OPENAI_API_KEY`** (so embeddings are OFF in unit tests). |
| `embed_chunks` | `rag_ingest.py:138` | `(chunks: List[str], model="text-embedding-3-large") -> List`; **MUST pass `model="text-embedding-3-small"`** to match 1536-dim infra. Returns objects with `.embedding`. |
| `MetaReviewOutput` | `schemas.py:312` | fields: `overall_recommendation, decision_rationale, must_address: list[str], nice_to_address, consensus_strengths, consensus_weaknesses, reviewer_agreement_level, score_summary`. |
| `ReviewerOutput` / `ReviewerIssue` | `schemas.py:293` / `:273` | `ReviewerIssue` has `issue_type, section_reference, anchor_text, problem, why_it_matters, suggested_action, confidence` — usable as anchor donors. |
| meta-review in state | `draft_analysis_langgraph.py:1341,1493` | key is **`final_state["meta_review"]`** (singular dict), NOT `meta_reviews` (DB list). |
| `_is_deductive_synthesis` / `_DEDUCTIVE_SYNTHESIS_RE` | `claim_extraction.py:54` / `:44` | deductive-thesis guard. |
| `_extract_author_coined_terms` / `_COMMON_ACRONYMS` / `_ACRONYM_RE` | `manuscript_profile.py:97` / `:74` / `:94` | repeated-acronym branch uses `_ACRONYM_RE`. |
| `_detect_references` | `draft_evidence_manifest.py:250` | **only detects a references SECTION exists — NOT a parsed author+year list.** No deterministic citation matcher available → Phase 2 cannot rely on a ref-list check. |
| contamination gate | `draft_publish_gate.py:138` | `if contamination_flags:` → sets `publishable=False`. |
| `verify_absence_claims` / `_ABSENCE_MARKERS` | `draft_task_evidence.py:302` / `:243` | grounding downgrade. |
| `_is_verbatim_anchor` / `_classify_task_anchors` | `draft_analysis_langgraph.py:620` / `:632` | post-hoc verbatim check. |

**Anti-patterns to refuse:** inventing a GROBID parsed-citation matcher (doesn't exist); using `embed_chunks` default model; assuming embeddings run in tests; reading meta-review from `meta_reviews`.

---

## Phase 1 — Meta-review priorities guaranteed into durable tasks (HIGHEST LEVERAGE)

**Problem:** `build_revision_tasks` never receives the meta-review; `must_address` priorities (the meta-reviewer's synthesized ranking) are discarded for tasks (only used for the legacy `reviewer_feedback` table at `meta_reviewer.py:117`). Proof: 2+ run-9 priorities missing.

**What to implement (COPY the embedding pattern from `revision_tasks._embedding_clusters:296-315`):**
1. `revision_tasks.py` — add `ensure_must_address_coverage(tasks, must_address, reviewer_outputs, *, structure=None, parser_quality=None) -> list[dict]`:
   - For each `must_address` string, compute max coverage vs each task. Use **embedding cosine** (embed must_address items + `_task_similarity_text(task)` via `embed_chunks(..., model="text-embedding-3-small")`, score with `_cosine_similarity`), threshold **≥0.60 = covered**.
   - **Deterministic fallback** (when embeddings unavailable — `PYTEST_CURRENT_TEST` or no key): token-overlap ≥0.5 OR `SequenceMatcher` ratio ≥0.55 (same as `scripts/proof_meta_owns_tasks.py`). Mirror that script exactly.
   - Uncovered item → build via `_base_task(source_type="meta_must_address", task_type=_task_type(...inferred...), severity="major", problem=<item>, suggested_action=<item>, ...)`; borrow `anchor_text` from the reviewer `issue` with highest similarity, else leave empty (→ `anchor_type="global"` later). Set `task["undroppable"] = True`.
2. `revision_tasks.py:979-982` — call `ensure_must_address_coverage` AFTER `rescue_critical_diagnostics`, BEFORE `final_pairwise_dedup` (so a must_address task duplicating an existing one still merges, keeping the anchored/higher-severity copy — and `undroppable` protects genuine new ones, per existing `final_pairwise_dedup` guard).
3. `build_revision_tasks` signature (`:848`) — add `meta_review: dict | None = None`; extract `must_address = (meta_review or {}).get("must_address") or []`.
4. `draft_analysis_langgraph.py:1257-1266` — pass `meta_review=final_state.get("meta_review") or {}`.

**Verification checklist:**
- `python3 scripts/proof_meta_owns_tasks.py` logic now yields 0 uncovered (re-run offline against run-9 export after wiring — or add a test fixture).
- New unit tests (≥3): (a) uncovered must_address → promoted + `undroppable=True`; (b) covered must_address (fallback path) → NOT duplicated; (c) `meta_review=None` → no-op.
- `grep "meta_review=" draft_analysis_langgraph.py` shows it passed to `build_revision_tasks`.

**Anti-pattern guards:** do NOT use token-overlap as the PRIMARY metric (proof showed 0.47/0.50 brittleness — embeddings primary, tokens only as the no-key fallback); do NOT pass `embed_chunks` default model; do NOT promote a must_address item that an existing task already covers (creates the dups you're trying to kill).

**Tests that break:** none expected (additive + guarded). **Risk:** low. **Rollback:** drop the call + arg.

---

## Phase 2 — Defang the mechanical claim→citation loop + tighten guards

**Problem:** the `claims` loop (`revision_tasks.py:910-938`) emits citation demands no reviewer asked for (run-9 Task 1 "SIBs play a commercial role"; run-8 Task 4 transitional). `author_coined_terms` over-captures field acronyms (CRISPR/XRD/FIGURE).

**What to implement:**
1. `revision_tasks.py:910-938` — gate citation-task creation: emit ONLY if **corroborated** — a reviewer `issue.anchor_text` OR a `must_address` item overlaps this claim's `claim_text`/`text_snippet` (reuse `_anchor_overlap` / `_token_set`, overlap ≥0.3). Uncorroborated claims are still staged to the `citation_suggestions` table (already built at `draft_analysis_langgraph.py:1230-1251`) — visible as a suggestion, NOT a durable "missing citation" task.
   - **NOTE:** there is NO parsed GROBID author+year list (`_detect_references` only flags a references section) — do NOT add a ref-list-match condition; corroboration is the gate.
2. `claim_extraction.py:44` — extend `_DEDUCTIVE_SYNTHESIS_RE` with a modal-future branch matching anywhere in the sentence: `needs to be explored|should be investigated|remains to be|warrants further|could be explored|merits investigation|future work|to be determined`.
3. `manuscript_profile.py:97-118` — DELETE the bare repeated-acronym branch (the `_ACRONYM_RE` count≥3 loop); keep ONLY cue-introduced terms (`_COINED_TERM_CUES`). Add `FIGURE, TABLE, EQUATION, SCHEME, SECTION` to `_COMMON_ACRONYMS` (`:74`).

**Verification checklist:**
- New test: uncorroborated background claim ("SIBs play a commercial role") → NO citation task; corroborated claim → citation task survives.
- New test: "An alternate approach … needs to be explored" → `_is_deductive_synthesis` True.
- Updated test: `_extract_author_coined_terms` on a CRISPR/XRD-heavy text → returns only cue-introduced names (e.g. SALIENT), NOT CRISPR/XRD/FIGURE.

**Tests that break:** FIX-4 author-coined tests + deductive tests in `test_draft_quality_rescue.py` — update expectations (cue-only coined terms; new modal cases). **Risk:** medium (citation recall) — mitigated by corroboration gate + suggestions table fallback. **Rollback:** revert the gate condition.

---

## Phase 3 — Verbatim anchors at generation (not post-hoc)

**Problem:** anchors are LLM-paraphrased then regex-checked → verbatim coverage stuck 0.5-0.78 (breaks frontend highlight).

**What to implement:**
1. `reviewer_panel.py` (REVIEWER_PROMPTS) + `citation_mapping.py` prompt — add hard line: *"`anchor_text` MUST be an exact, contiguous, copy-paste substring of the manuscript (≤200 chars). No paraphrase, no ellipsis, no summarization."*
2. `draft_task_evidence.py` — add `repair_anchor(task, raw_text) -> dict`: if `anchor_text not in raw_text` (whitespace/glyph-normalized), attempt deterministic locate (longest common substring ≥40 chars over normalized text) and replace with the exact located span; if irreparable, set `task["anchor_type"]="global"` (already exempt from the verbatim metric via existing `_classify_task_anchors`).
3. `draft_analysis_langgraph.py` — call `repair_anchor` on every task immediately BEFORE `_classify_task_anchors` (`:632` call site).

**Verification checklist:** `verbatim_anchor_coverage ≥ 0.9` on re-run of run-8 AND run-9 exports; new unit tests for `repair_anchor` (exact hit, fuzzy-repair, irreparable→global).

**Tests that break:** existing verbatim tests should pass (metric semantics unchanged). **Risk:** low. **Rollback:** drop `repair_anchor` call + prompt lines.

---

## Phase 4 — Contamination ≠ run failure

**Problem:** `draft_publish_gate.py:138` marks an otherwise-excellent run `publishable=False` purely because RAG retrieved off-domain sources (already pruned by `sanitize_revision_task_sources`). Run-9 was a clean analysis flagged `needs_reparse`.

**What to implement:**
1. `draft_publish_gate.py:138-` — contamination flags set a confidence note + `gate_status="ok"` (or new `"ok_sources_pruned"`) with **`publishable=True`**. Only parser-quality (`:119`) and page-anchor (`:129`) failures keep `publishable=False`.
2. `draft_analysis_langgraph.py` — the `needs_reparse`/`suppress_unreliable_task_artifacts` branch must fire ONLY on real parse/anchor failure, not contamination (sources already stripped upstream).

**Verification checklist:** re-run run-9 export path → `publishable=True`, status not `needs_reparse`; tasks/reviewers/meta retained.

**Tests that break:** gate tests asserting contamination ⇒ not publishable — update them. **Risk:** low-medium (ensure `sanitize_revision_task_sources` truly strips contaminated sources before the gate; it does). **Rollback:** restore the `publishable=False` line.

---

## Phase 5 — Meta-reviewer authors the structured ranked task spine (REAL DESTINATION)

**Why:** any post-hoc free-text `must_address`→task mapping is inherently fuzzy (proof). The clean fix: the meta-reviewer (which already ranks priorities) emits structured, anchored, ranked tasks directly; the fragment layer (claims/gaps/diagnostics) becomes pure enrichment.

**What to implement:**
1. `schemas.py:312` — add to `MetaReviewOutput`: `ranked_tasks: list[MetaRankedTask] = Field(default_factory=list)` where `MetaRankedTask(StrictOutputModel)` has `problem, suggested_action, anchor_text (verbatim), severity: Literal["critical","major","minor"], task_type, rank: int`.
2. `meta_reviewer.py` (`META_REVIEWER_PROMPT:41`) — instruct: output `ranked_tasks` = the deduplicated, prioritized action list (1 = most blocking), each with a verbatim `anchor_text`. Keep `must_address` for backward-compat. Do NOT change the synthesis reasoning guidance (the 9/10 depth).
3. `draft_analysis_langgraph.py` — when `meta_review.ranked_tasks` present, use them as the durable-task SPINE; run fragment-derived tasks only as enrichment merged in via existing dedup (they no longer drive priority). Phase 1's `ensure_must_address_coverage` becomes a safety net.
4. **Migration** (`services/backend/migrations/0NN_meta_ranked_tasks.sql`) only if `meta_reviews` needs a `ranked_tasks jsonb` column; if it rides in `analysis_metadata`, no migration. Decide by checking how `meta_reviews` persists.

**Verification checklist:** on a live run, ≥80% of durable tasks trace to `meta_review.ranked_tasks`; run-9-style priority drop cannot recur; full re-eval ≥8.5.

**Tests that break:** meta-review schema/serialization tests — update. **Risk:** higher (schema + prompt + assembly) — that's why Phases 1-4 ship first to validate. **Rollback:** feature-flag `ranked_tasks` consumption.

---

## Final Phase — Verification & re-eval

1. `cd services/backend && python3 -m pytest tests/ -q --timeout=60 --ignore=tests/e2e` → all green (≥347, +new).
2. Anti-pattern greps: `grep -rn "max_tokens\b" app/` (none), `grep -rn "text-embedding-3-large" app/workflows/draft_analysis/` (none), confirm `meta_review=` passed to `build_revision_tasks`.
3. `cd infra && docker-compose up --build -d`; re-run draft analysis on the CRISPR + sodium-ion drafts; export via `scripts/export_latest_draft_analysis.py`.
4. Re-run `scripts/proof_meta_owns_tasks.py` on the NEW exports → 0 uncovered.
5. Send exports to Gemini; target stable ≥8.5 with Prioritization ≥7 and no dropped must_address.

## Execution notes
- One phase per fresh context. Order: **1 → 2 → 3 → 4 → 5.** Rebuild Docker + re-eval after Phase 2 and after Phase 4.
- Use `claude-mem:do` to execute phases with subagents (keeps each diff small + test-gated — directly counters the week of whack-a-mole).
- Phases 1-4 are net-negative or net-neutral on line count; Phase 5 adds schema but removes the fragile mapping.
