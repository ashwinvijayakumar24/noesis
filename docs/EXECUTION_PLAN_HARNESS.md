# EXECUTION_PLAN_HARNESS.md

**Scope.** Two tracks run in parallel:

- **Track H** — `reviewer-agent`, a **new standalone GitHub repo**: Phases A + B + B.5 of `AGENT_HARNESS_PLAN.md`, plus Noesis N11 (durable checkpointer, the substrate B.5 needs) and a scoped N12 (injection defenses, the interlock that makes the approval gate a *measurable* mitigation).
- **Track R** — Noesis retrieval, in this repo: contentless-query filtering, the 50-chunk ceiling overshoot, and cross-encoder reranking. Contextual retrieval is **deferred** (needs a migration + full re-embed; does not parallelize).
- **Track E** — first user-visible end-to-end latency number, against the now-running local Supabase.

**Decisions locked before writing this.**

| Decision | Value |
|---|---|
| Coupling | Thin port layer; `adapters/fixture` ships in-repo, `adapters/noesis` imports via `NOESIS_PATH` |
| Harness scope | Phase A + B + B.5 (+ N11, + scoped N12) |
| Spend ceiling | **$50 total**, split and enforced per track |
| Track R scope | contentless filter · 50-chunk ceiling · cross-encoder rerank. **Not** contextual retrieval |
| Parallelism | up to 10 subagents, file-disjoint ownership |

---

## 0. Rules that govern every number produced here

These are not new. They are the existing house rules from `docs/BENCHMARKS.md` and the head of `docs/history/WAVE_LOG.md`, and they now apply to the harness repo too.

1. **Every metric carries its `n`.** No exceptions, including in the harness README.
2. **Every `recall@k` carries its construction ceiling**, or is reported as `unknown`. A ceiling never travels across label snapshots.
3. **Retrieval numbers from different label snapshots are never differenced.** Current snapshot: `230c6ea9d9b7e8fd` (338 queries, 344 docs / 5,948 chunks). Two older ones exist and are off-limits for comparison.
4. **Results are append-only, keyed by config hash.** Trends are drawn only between runs sharing a hash.
5. **Every cost figure is a lower bound** and renders with `>=` when any call is unpriced.
6. **A capability not observed firing in logs is not a capability.** Applies to compaction, loop detection, step-budget binding, error recovery, and the approval gate. Each must have a log line proving it bound at least once, and a bind-rate.
7. **Negative results ship.** If the agent loses to the DAG on cost-per-finding, that goes in the README.

**Spend split of the $50 ceiling** — enforced by `MAX_SPEND_USD` per track, ledgered in `docs/SPEND_LEDGER.md`:

| Track | Ceiling | Main line items |
|---|---|---|
| H — Phase A eval | $14 | ~20 trajectory runs × 4 context-ceiling arms |
| H — Phase B eval | $16 | orchestrator + N workers, worker-count study, DAG baseline re-runs |
| H — B.5 / N12 | $8 | injection eval, gate on/off arms |
| R — retrieval | $6 | re-ingest embeddings only; reranker is local and free |
| E — end-to-end | $4 | n=3–5 real pipeline runs |
| reserve | $2 | |

---

## Wave 0 — foundations (serial, no agents)

Nothing parallel starts until Wave 0 lands, because every Wave 1 harness agent codes against the port contract.

| Step | Action | Verification |
|---|---|---|
| **0.1** | `gh repo create ashwinvijayakumar24/reviewer-agent --private`, scaffold at `../reviewer-agent`, initial commit, push | `gh repo view` returns the repo; `git log origin/main` shows the commit |
| **0.2** | **`harness/ports.py`** — `SearchPort`, `DraftPort`, `AnchorPort`, `CitationPort`, `ArtifactPort` as `typing.Protocol`. This is the whole decoupling story and it is authored once, by me, before anything imports it | `mypy` clean; a test asserts the fixture adapter satisfies every Protocol |
| **0.3** | Fixture corpus in-repo: derived artifacts only (section titles, structure, short excerpts, atomized label units) from the 15 OpenReview papers. **No full third-party PDFs are committed** — licensing, and repo size | `pytest` passes on a clone with `NOESIS_PATH` unset; repo < 20 MB |
| **0.4** | Spend guardrails: `MAX_SPEND_USD` per track, `NOESIS_LLM_MAX_LLS`, and `docs/SPEND_LEDGER.md` | A deliberate over-budget run aborts and is logged, not silently truncated |
| **0.5** | Branch `dev/harness-and-retrieval` in Noesis; confirm local Supabase reachable at `127.0.0.1:54322` | `psql` connects; `SELECT count(*) FROM document_chunks` returns |

**Wave 0 acceptance:** a fresh `git clone` of `reviewer-agent` on a machine with no Noesis checkout runs `pytest` green. That single test is what makes this a standalone resume item rather than a Noesis subdirectory.

**Commit:** `chore: scaffold reviewer-agent, port contract, fixture adapter` (repo B) + `chore: spend ledger, harness branch` (repo A).

---

## Wave 1 — 9 agents in parallel

**Ownership rule:** each agent owns an exclusive file set. **Shared entry points (`run_retrieval_eval.py`, `Makefile`, `benchmarks.py`) are owned by me** and wired after the agents land. No agent edits a file another agent owns.

### Track H — harness core (4 agents, repo `reviewer-agent`)

| Agent | Build | Owns | Verification criteria |
|---|---|---|---|
| **A1** tools | 4 tools against the ports: `search_literature`, `get_draft_section` (**paginated**), `verify_anchor`, `check_citation`. Namespacing, response-format enums, **error messages written as prompts**, token-efficient responses | `harness/tools/*`, `adapters/fixture/*` | Unit test per tool: happy path · empty result · malformed input · raised exception. Every error path returns a *model-readable* string, asserted by regex (no stack traces). Token-count assertion: no tool returns > 2k tokens by default |
| **A2** loop | ReAct loop. Step budget enforced · loop detection (identical repeats, no-result repeats, two-tool oscillation) · termination distinct from budget exhaustion · error recovery that adapts | `harness/loop.py`, `harness/trace.py` | Deterministic stub-model tests: budget binds and is logged · each of 3 loop patterns is detected · each of 4 tools broken in turn and the loop still completes (**error-recovery rate**) · termination-reason enum recorded on every run |
| **A3** context | Budget accounting · compaction · structured note-taking that survives compaction · **artificial context ceiling as a swept dial** (16k/32k/64k/uncapped) | `harness/context.py` | Test proves compaction **fires** at 32k on a long-horizon fixture and that a note recorded pre-compaction is still present post-compaction. Ceiling is a parameter, not a constant |
| **A4** eval scaffold | `eval/labels.py` (shared atomized units) · `eval/trajectory.py` (tool-selection accuracy, wasted-call rate, steps-to-completion) · `eval/report.py` (**append-only, config-hash keyed**, same house rules as Noesis) | `eval/*` | Report writer test: two runs with identical config produce the same hash and append two rows; a changed config produces a different hash. Rejects any metric submitted without `n` |

### Track R — Noesis retrieval (3 agents, this repo)

| Agent | Build | Owns | Verification criteria |
|---|---|---|---|
| **R1** contentless | Classify the query set into contentful/contentless. Recompute every arm **both ways** | `scripts/eval/retrieval/contentless.py`, `.../tests/test_contentless.py` | **Zero LLM calls** — asserted by the budget counter reading 0. Output reports *both* numbers with both `n`s and both ceilings. A hand-labeled sample of 50 queries measures classifier agreement; report it, don't assume it |
| **R2** 50-chunk ceiling | `MAX_CHUNKS_PER_DOCUMENT = 50` at `rag_chunking.py:119` — characterize the overshoot, fix, keep the old path behind a flag as a measured arm | `services/backend/app/services/rag_chunking.py`, `services/backend/tests/test_rag_chunking*.py` | A test reproduces the overshoot **before** the fix (red), passes after. Re-ingest produces a **new snapshot id** with its own ceiling — never differenced against `230c6ea9d9b7e8fd`. Both arms reported |
| **R3** rerank | `bge-reranker-v2-m3` local cross-encoder over the dense candidate pool. Arms: dense (control) · dense→rerank · oversample×N→rerank. Optional Cohere arm on a rate-limit-sized subset | `scripts/eval/retrieval/rerank.py`, `.../tests/test_rerank.py` | Measured on snapshot `230c6ea9d9b7e8fd` against the **0.2195 / ceiling 0.5199 / n=338** baseline. Reports Δrecall@10, ΔNDCG@10, **and p50/p95 added latency** — a reranker without its latency cost is half a result. $0.00 spend asserted (local model) |

### Track E + N11 (2 agents)

| Agent | Build | Owns | Verification criteria |
|---|---|---|---|
| **E1** end-to-end | The first **user-visible** end-to-end latency: upload → parse → analyze → publish, against local Supabase. Explicitly includes what the 63.75 s graph number excludes (upload, storage, PDF parsing, publish writes) | `scripts/eval/e2e_latency.py`, `scripts/eval/E2E_LATENCY.md` | n ≥ 3 real runs, p50 + mean + per-stage breakdown, spend logged. States plainly which stages are included — the existing graph number's caveat is what made it not-user-visible |
| **N11** checkpointer | Real LangGraph checkpointer with `thread_id`; `interrupt`/resume; resume mid-graph without re-running completed nodes. Replaces the run-status row that `minimize_workflow_checkpoint` guts | `services/backend/app/workflows/draft_analysis/checkpoints.py`, `graph.py` | Induced mid-graph failure → resume completes → **tokens and $ saved vs a cold re-run**, measured. `resume_draft_analysis_workflow` no longer raises by design |

**Wave 1 acceptance:** every agent's tests green; `make benchmarks` regenerates cleanly; Track R numbers land in the append-only sinks with snapshot ids attached.

**Commits:** one per agent, conventional format, each carrying its own measured numbers in the body where it produced any.

---

## Wave 2 — Phase B, orchestration + baselines (5 agents)

Depends on Wave 1 A1–A4. Repo `reviewer-agent`.

| Agent | Build | Verification criteria |
|---|---|---|
| **B1** triage + spawn | Cheap manuscript profile → enumerated concerns → **worker count decided at runtime**, not a constant | **Worker-count distribution across ≥15 manuscripts must be non-degenerate.** If N is the same every time, the build failed its own thesis and that gets reported |
| **B2** isolation + budget | Per-worker scope (a concern *and only the sections it needs*) · per-worker token/step budget · exhaustion policy · worker-failure policy (retry / reassign / degrade) | **Context tokens per worker vs the DAG's per-reviewer tokens** — the isolation claim is this number or it is nothing. Worker failure rate measured, and the failure path must not silently inject a synthetic vote (the exact bug at `reviewer_panel.py:872-891`) |
| **B3** synthesis | Orchestrator synthesizes over context it never saw. Decides whether to spend a step verifying a worker summary | Hand-labeled decomposition quality (n ≥ 15): was the split sensible *before* the first worker call? Report verification-step rate |
| **B4** DAG baseline | `eval/baseline.py` runs the Noesis 18-node graph on the same papers, same labels, via `NOESIS_PATH` | Baseline reproduces the recorded severity-weighted recall within its known variance (CV 95% at n=5 — **so any quality delta below that is reported as unresolvable, not as a win**) |
| **B5** run + write up | Executes the Phase A + B measured runs and writes results | Every Phase A benchmark in `AGENT_HARNESS_PLAN.md` has a number with an `n`, or an explicit "not measured" line. **The tool-description A/B** (rewrite one description, hold all else fixed, report Δ steps-to-completion) is run here |

**Wave 2 acceptance:** all six minimum-bar items from `AGENT_HARNESS_PLAN.md` demonstrated **with log evidence**, compaction observed firing, and a published agent-vs-DAG comparison **including the cases where the agent loses**.

---

## Wave 3 — Phase B.5, the gated side-effecting tool (4 agents)

Depends on N11 (Wave 1) and Wave 2.

| Agent | Build | Verification criteria |
|---|---|---|
| **C1** artifact tool + authz | `write_review_artifact(draft_id, artifact)` · `policy.py` with **per-resource authorization** — the caller must prove ownership of `draft_id`. Never writes the manuscript itself | Negative test: a caller without ownership is denied. This is the same shape as the live Noesis IDOR at `drafts.py:2304-2310`, so the test is written against that shape deliberately |
| **C2** approval gate | propose → **durable pause** (on N11) → approve/deny → resume. Survives process death | Kill the process mid-pause; resume completes. Approval latency and **deny-path correctness** both logged |
| **C3** injection set | Scoped N12: injection corpus targeting the harness's own tools plus the two highest-value Noesis sites (`analysis_quality_judge.py:94-96`, which feeds the publish gate, and third-party abstracts entering reviewer/gap prompts) | Attack set is versioned and hash-keyed. Report attack success rate **and utility regression** — a defense that tanks recall is not a defense |
| **C4** interlock benchmark | **Attack success rate with vs without the approval gate** | Both arms, same attack set, same `n`. This is the number that makes B.5 and N12 worth more together than apart |

**Wave 3 acceptance:** the gate is shown to bind, the authz denial is shown to fire, and the with/without-gate attack numbers are published side by side.

---

## Wave 4 — ship (3 agents + serial)

| Step | Action | Verification |
|---|---|---|
| **D1** | `reviewer-agent/README.md` + `BENCHMARKS.md` — every number with `n`, **negative results included**, honesty note on sandboxing kept verbatim from the plan | A reader with no context can tell what was measured, at what `n`, and what was not measured |
| **D2** | Update `docs/history/WAVE_LOG.md` head block · run `make benchmarks` · commit the board | `git diff` on `docs/BENCHMARKS.md` is non-empty and regenerates byte-identically on a rerun |
| **D3** | **Secret scan of the full `reviewer-agent` history** (`gitleaks`), then flip to public | Scan clean. Flip is a separate, explicit step — I will confirm with you before making anything public |
| **D4** | Resume bullets, **each traced to a specific measured number in a specific file** | Any bullet without a traceable number is deleted, not softened. This is the whole lesson of `LEARNING_AUDIT_ADDENDUM.md` |

---

## What this is expected to yield on the resume

Written after the numbers exist, not before. The *shape* is fixed now so the measurements are aimed at something:

1. **Agent harness (own repo).** A ReAct critique agent with runtime tool selection, enforced step budgets, loop detection, and context compaction under a swept context ceiling — benchmarked head-to-head against an 18-node LangGraph DAG on identical ICLR review labels.

> ⚠️ **Correction, applied during Wave 1.** Earlier drafts of this plan said *"human-authored labels."* That is an overclaim. The reviews are human; the **segmentation into atomic units was performed by GPT-5.2** (`atomize_reviews_v1`), and a different segmentation would move every recall number computed against it. The honest phrase is **"human reviews, model-segmented."** Found by the fixture agent while recovering the paper→label mapping; recorded here because this is precisely the class of claim `LEARNING_AUDIT_ADDENDUM.md` exists to catch, and it had already reached a README before it was caught.
2. **Orchestration.** Runtime-decided worker count with per-worker context isolation, and the measured token-cost multiplier — reported including where the agent loses.
3. **Agent security.** Per-resource authorization and a durable approval gate on a side-effecting tool, with attack success rate measured with and without the gate.
4. **Retrieval.** Cross-encoder reranking on a 338-query, ceiling-bounded benchmark, with latency cost reported alongside the recall delta.
5. **Reliability.** Durable checkpointing and mid-graph resume, with tokens and dollars saved measured against a cold re-run.

---

## Known risks, pre-decided

| Risk | Response |
|---|---|
| 9 agents, 2 repos, concurrent writes | Exclusive file ownership per agent; shared entry points owned by me and wired after |
| R2's re-ingest invalidates R3's corpus | R3 measures on `230c6ea9d9b7e8fd`. R2 emits a **new** snapshot with its own ceiling. Never crossed. A combined run happens last, as its own third snapshot |
| Compaction never fires (the silent failure) | Both forcing functions implemented: paginated reader over a long fixture **and** the artificial ceiling. A test asserts firing |
| Worker count comes out constant | Reported as a negative result, not hidden. The build's thesis is falsifiable on purpose |
| Quality deltas below noise | Known CV is 95% at n=5. Anything smaller is reported **unresolvable**, never as a win |
| Spend overrun | Per-track `MAX_SPEND_USD`; over-budget aborts loudly |
| Secrets in the new repo's history | Repo starts **private**. Public flip only after a clean scan and your explicit go-ahead |
