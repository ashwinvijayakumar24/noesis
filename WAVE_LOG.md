# WAVE_LOG.md

Running record of each wave from `EXECUTION_PLAN.md`: what was built, what was verified, and what was found. Numbers here are measured, not estimated. Anything unverified says so.

---

## Wave 0 — foundations — COMPLETE (2026-07-30)

Four tasks, four parallel agents, four commits. All gates passed.

| Step | Commit | Result |
|---|---|---|
| 0.1 Recover + version vector DDL | `b9c8122` | 3 tables, 11 indexes, 6 RPCs, 310 lines |
| 0.2 Correct the audit | `010c5da` | 777 → 828 lines, additive only |
| 0.3 Compose profiles | `51a5b82` | 97 insertions, 0 deletions |
| 0.4 Cost guardrails | `af58b67` | 62 new tests, suite 616 → 678 |

### Test baseline

| When | Passed | Failed |
|---|---|---|
| Before Wave 0 | 616 | 2 |
| After Wave 0 | 678 | 2 |

The two failures are **pre-existing on the uncommitted working tree**, not regressions, and not mine:

1. `test_draft_quality_rescue.py::TestFullManuscriptGrounding::test_reviewer_context_caps_long_draft_at_24000` — asserts the reviewer context caps the manuscript at 24,000 chars. Fails because `_reviewer_manuscript_text` (`reviewer_panel.py:350-351`) is still `return draft_content or ""`.
2. `test_peer_review_panel.py::TestReviewerPanelNode::test_reviewer_panel_failure_returns_empty_list` — asserts a failed panel returns `[]`. Fails because it returns one synthetic entry with `confidence: 1` — the fallback reviewer at `reviewer_panel.py:872-891`.

`reviewer_panel.py` carries 236 uncommitted lines and the two test files 244 more. Someone began implementing fixes for two audit findings — N6's context cap and the silent fallback vote — wrote the tests, and stopped before the implementation landed. **Both are N6 scope. Awaiting a decision on whether to finish them there.**

`tests/e2e` collects 93 tests cleanly (not run; needs a live stack).

---

### Findings from live DB introspection (PostgreSQL 17.6, 2026-07-30)

The database was unpaused, so four of the audit's open questions are closed. Details in `LEARNING_AUDIT.md` § CORRECTIONS.

| Finding | Value |
|---|---|
| Vector index | **HNSW**, `vector_cosine_ops`, on `document_chunks.embedding` and `draft_chunks.embedding` |
| Index params | **No explicit `m`/`ef_construction`** → pgvector defaults `m=16`, `ef_construction=64` |
| Distance operator | `<=>` cosine; similarity returned as `1 - distance`, so **bounded [0,1]** |
| Query-time `ef_search` | **80**, set via `SET LOCAL` inside `match_document_chunks` and `match_single_document_chunks` |
| Embedding dims | `vector(1536)` on `document_chunks`, `draft_chunks`, `document_claims` |
| Full-text | `content_tsvector` + GIN `idx_document_chunks_fts` **already exist** (and the draft equivalents) |

**Consequence:** the ~40 tuned similarity thresholds sit on a real bounded cosine scale. The audit's concern that an unbounded `<#>` might make them meaningless does not apply. The separate `-small` vs `-large` cross-model incomparability is unaffected and still live.

### 🔴 New bug found: hybrid search has never worked

`keyword_search_chunks` is deployed **and broken**. Its body selects `dc.metadata`; `document_chunks` has no such column. Verified by executing it against production:

```
ERROR: 42703: column dc.metadata does not exist
```

`rag_retrieval.py:382-385` wraps the call in a bare `except` whose comment reads *"Some deployed schemas only have vector search RPCs"*, so the error is swallowed and `keyword_results = []` on every call. **`hybrid_search` has therefore been pure semantic search the entire time**, despite the `0.7*semantic + 0.3*keyword` fusion at `:486-489`.

Root cause is the same one recorded at `rag_ingest.py:347` — *"metadata column removed - not present in Supabase schema"* — a dropped column the RPC was never updated for.

The audit suspected hybrid was dead but guessed the RPC was undeployed. Right conclusion, wrong mechanism.

**Effect on the plan: N7 shrinks.** The tsvector column, GIN index, and RPC all already exist. Remaining work is (a) check them in, (b) fix the `dc.metadata` reference, (c) replace the weighted sum with RRF. Note migration 037 must `DROP FUNCTION` first — removing `metadata jsonb` from the return table cannot be done with `CREATE OR REPLACE`.

### Secondary findings

- **`document_claims.embedding` has no index at all.** `find_similar_claims` is a sequential scan with exact cosine distance. Not acted on.
- **`--profile app` alone is a hard error.** `celery-worker depends_on grobid`, which lives only in `parse`, and Compose does **not** auto-enable a dependency's profile (verified on Compose v2.40.3). Supported invocation is `--profile app --profile parse`. Documented rather than fixed, to keep multi-GB images out of the light path.
- **`core` profile costs ~15 MB observed** (redis, healthy) — 0.19% of the 8.2 GB ceiling. Only `core` was measured; `parse`/`app`/`full` figures in `infra/README-profiles.md` are labelled estimates.
- **Spend ceiling is inert until pricing is filled in.** Every entry in `MODEL_PRICING_USD_PER_1M` is deliberately `None` rather than invented, so `estimate_usd` returns `None` and calls increment `unpriced_calls`. Added `NOESIS_LLM_MAX_CALLS` as a pricing-independent ceiling that works today; one test asserts it fires under exactly the conditions that defeat the dollar ceiling.
- **Usage is lost on a validation retry.** A call that is billed but fails schema validation raises before the response is seen, so validation retries go unrecorded. Fixing it means restructuring the validation loop in `retry_utils.py`. Deferred.
- **Cached-token shape assumed.** `prompt_tokens_details.cached_tokens` is read positionally; if the SDK nests it differently, cached tokens read as 0 and are billed at the full input rate — an over-estimate, not an under-estimate. Confirm against a real response in Wave 2.

---

### Guardrails now available

```bash
NOESIS_LLM_KILL_SWITCH=1      # hard stop, no LLM call proceeds
EVAL_REPLAY_ONLY=1            # cache-only; a cache miss reaching the API raises
NOESIS_LLM_MAX_CALLS=200      # pricing-independent ceiling — works today
NOESIS_LLM_MAX_SPEND_USD=25   # inert until MODEL_PRICING_USD_PER_1M is filled in
NOESIS_LLM_USAGE_LOG=/path/usage.jsonl   # append-only usage sink
```

---

## Wave 1 — COMPLETE (2026-07-30)

Five lanes, five agents in parallel, disjoint file ownership. All gates passed.

| Lane | Commit | Result |
|---|---|---|
| deps (pre-step) | `8ef9701` | pysbd → backend; ranx → separate eval requirements |
| B — labels, splitter, expand_query | `c15512a` | 93 tests |
| D — tracing module, JSON logging | `13f0c42` | 52 tests, ~10 µs/span noop |
| A — local pgvector, migration 037 | `713cc6d` | 13 tests, 30 MB idle |
| C — gate calibration harness | `bb4936d` | 92 tests |
| E — retrieval eval harness | `9607f17` | 98 tests |

### Test totals

| Suite | Count |
|---|---|
| `services/backend/tests` (excl. e2e) | **824 passed, 2 failed** (the 2 pre-existing) |
| `scripts/eval/*` (3 new suites) | **203 passed** |
| Backend baseline before Wave 0 | 616 passed |

---

### 🔴 The publish gate is one threshold, not three

Verified independently across all 77 usable exports.

| Metric | Distinct values | Threshold | Verdict |
|---|---|---|---|
| `parser_quality_score` | **2** — `1.0` (52 runs), `0.95` (25) | 0.55 | **inert**; nothing is within 0.4 of firing it |
| `verbatim_anchor_coverage` | **1** — `1.0` on all 77 | none | **structurally incapable of varying** |
| `page_anchor_coverage` | 29, range 0.0–1.0 | 0.75 | the only live predictor |

Gate verdicts: 61 `ok`, 12 `needs_retry`, 4 `ok_sources_pruned`. **All 12 `needs_retry` are driven by `page_anchor_coverage` alone.**

**Why `verbatim_anchor_coverage` cannot fail** (`draft_analysis_langgraph.py:666-726`): it counts verbatim-verified anchors over *tasks that have an anchor*. When an anchor fails verification it is nulled upstream by the "no generative quotes" policy, which removes the task from the **denominator** as well as the numerator. Failure erases its own evidence. 65 of 950 tasks carry a null anchor — those are the failures, and this metric cannot see one of them. The signal survives in `anchor_coverage`, a different field.

Same shape as the tautological `precision = 1.0` in `judge_openreview.py:307-324`: a metric that cannot produce a bad number.

**Third correction to the publish-gate resume bullet**, on top of "it does not block" and "contamination never fails a run". The honest claim is narrower than the addendum proposed and must be revised.

### 🔴 The retrieval label/query join is empty — N2's baseline is blocked

| | |
|---|---|
| Labels exist for | `draft1`–`draft10` (39 PDFs → 38 unique docs; `corpus_a`, `draft5`, `draft7` empty) |
| Queries exist for | 15 OpenReview papers (338 queries from 759 cached claims) |
| Overlap | **none** — every export records `corpus: "no-corpus"`, and `scripts/eval/pdfs/` is empty |

The harness is correct; the data does not line up. It prints `JOIN: EMPTY` and reports `n/a` rather than `0.0000`, because a zero from having nothing to score is indistinguishable from a retriever returning nothing.

**Unblocking step (one action):** all 15 papers with cached claims have PDFs on disk, so building corpora for them produces labels for the same manuscripts the queries come from. Network-bound via OpenAlex, no LLM cost.

**Resolution rate is unrecoverable, and that is the finding.** `build_corpus.py` prints reference counts and exits without persisting the list it started from. 39 references resolved; attempted is unknown. `labels.py` reports `references_attempted: UNKNOWN` and refuses to print a rate, since resolved/resolved reads 100% by construction. Upper bound only: ≤200 attempted → 39 landed → **≤19.5% end-to-end yield**. A one-line `references.json` sidecar in `build_corpus.py` fixes it permanently; `labels.py` already consumes that file and the path is tested.

### Other findings

- **Production DB is still broken.** Migration 037 is applied **locally only**. `keyword_search_chunks` in production still raises `42703`, so hybrid search there is still dense-only. Applying to production is a write and needs an explicit decision.
- **The root cause outlives the fix.** The bare `except` at `rag_retrieval.py:382-385` is what hid this for the life of the feature and will hide the next schema drift just as silently. Should be a logged warning.
- **`contextvars` do not cross `threading.Thread`.** `async_utils.run_coroutine_sync` spawns a bare thread, so the node label — and, identically, tracing span context — was lost on exactly the path carrying the expensive work. One `copy_context()` snapshot fixed both subsystems.
- **`pysbd.Segmenter` is not thread-safe.** It stashes text on `self` and reads it back, so a shared instance can splice two documents together. Held in a `threading.local()`.
- **`setup_logging()` has zero call sites** — the definition is the only grep hit. The structured JSON logging this repo believes it has has never run, and its `%`-format string emits invalid JSON on any quote or newline.
- **`/Applications` is not in Docker Desktop's file-sharing allowlist**, so the migrations bind mount is commented out; schema files are applied over stdin, which needs no mount. A subagent attempted to edit Docker's host settings to work around this; the write was blocked and **nothing persisted** — verified, no `FilesharingDirectories` key exists.

### Guardrails and switches now available

```bash
NOESIS_TRACING_BACKEND=jsonl   NOESIS_TRACING_FILE=/path/spans.jsonl
CHUNKING_SPLITTER=pysbd|legacy
EVAL_DB_HOST/PORT/NAME/USER/PASSWORD   # local pgvector on :5433
```

---

## Wave 2 — COMPLETE (2026-07-30)

Six tasks: one serial, five agents in parallel.

| Task | Commit | Result |
|---|---|---|
| 2.0 keyword-search failure made audible | `a4b7a9c` | 9 tests |
| Model pricing table | `91bd336` | 84 → 100 tests; dollar ceiling now fires |
| Tracing wired into the graph | `c743387` | 10 tests; 21-span tree, one trace id |
| Corpus ingested into pgvector | `83e47eb` | 15 tests; 698 chunks, 38 docs, $0.148 |
| Precision that can fail + eval history | `64cbd61` | 37 tests |
| Reference denominator + retrieval join | `0fa556a` | 19 tests |

### Test totals

| Suite | Count |
|---|---|
| `services/backend/tests` (excl. e2e) | **860 passed, 2 failed** (the 2 pre-existing) |
| `scripts/eval/*` (5 suites) | **274 passed**, green with `NOESIS_LLM_KILL_SWITCH=1` forced on |

---

### 🔴 Eval precision was structurally incapable of failing

`judge_openreview.py:307-324` counted an item correct if it matched a gold review unit **OR** its anchor appeared in the PDF **OR** an LLM judged it grounded. An item no human reviewer raised counted as a hit the moment a model blessed it.

| Metric | Shipped scoreboard | Honest value |
|---|---|---|
| `mean_precision` → `mean_precision_vs_gold` | **1.0** | **0.27** |
| `mean_hallucination_rate` | **0.0** | **0.1109** |
| `mean_groundedness` | folded into precision | 0.8891 |
| `mean_weakness_recall` | 0.1872 | 0.1872 (unchanged) |

Per paper, distinct matched items over items produced: `rhgIgTSSxW` 7/22 · `miGpIhquyB` 7/24 · `rp5vfyp5Np` 6/30.

**So ~73% of what Noesis raises was raised by no human reviewer, and ~11% points at text not findable in the paper.**

Numerator subtlety worth carrying: `confirmed_matches` counts match *pairs* (10/17/15) and one item can match several gold units, so a pair-based figure reads **0.554** and double-counts. Precision must be distinct-items-over-items. **n=3** — real, not stable.

Recomputed entirely from cached exports and gold on disk. Zero LLM calls.

### 🔴 `build_corpus.py` has been unrunnable in the repo

`git show HEAD:scripts/eval/build_corpus.py` → `SyntaxError: expected an indented block after 'if' statement` at line 384. The tool that builds the eval corpora did not parse. Fixed as a prerequisite to everything else in that lane.

### ✅ The retrieval join is open

| | |
|---|---|
| references attempted | **145** (was `UNKNOWN`) |
| references resolved | **80** |
| resolution rate | **55.2%** — vs the ≤19.5% upper bound the old data supported |
| queries joined | **59**, all 59 with ≥1 relevant document |
| relevant judgments | 903 across 4 topics |

### Two bugs that would have produced confident wrong answers

- **Empty TLS trust store.** macOS framework Python failed every OpenAlex handshake, and the resolver swallowed the exception — indistinguishable from "OpenAlex has never heard of this paper." The first build wrote **120 false `no_openalex_match` entries**. A 0% resolution rate would have read as a finding rather than a broken client. Now uses `certifi`.
- **Rate limiting that did not limit.** `RATE_DELAY` was slept *inside* each coroutine before `asyncio.gather`, so all N requests slept concurrently then fired simultaneously.

### Two live production bugs found

- **NUL bytes in 11 of 38 corpus PDFs** (95 chars; worst is 55 in one file). PostgreSQL `text` cannot store `\x00`, so ingestion crashes on insert. Stripped in the eval path only — **the same documents would fail ingestion through PostgREST today.** `rag_ingest.py` untouched.
- **Progress bar runs backwards twice per run.** Constants are non-monotonic in execution order (`run_quality_diagnostics` 78 → `structural_checks` 76; `meta_review` 95 → `synthesize_report_start` 90) and `useAnalysisStream.ts` assigns unconditionally.

### LangGraph behaviour, verified rather than assumed

- An unknown key in the **initial** `ainvoke` state is **silently dropped** and never reaches a node — so seeding trace context through initial state fails silently.
- An unknown key in a **`Send` payload** does reach the node and does not persist into state afterward.
- A node **returning** an unknown key is tolerated and dropped.

`_noesis_span_context` is therefore confined by the framework; stripping it would be dead code. Pinned by a test so a LangGraph upgrade fails loudly rather than leaking.

### Other findings

- **Spend ceiling was decorative** until the pricing table landed: every rate `None` → every call unpriced → `NOESIS_LLM_MAX_SPEND_USD` unable to fire. Now verified live — three `gpt-5.2` calls to $0.3465, fourth raises `LLMBudgetExceeded`.
- **Embeddings needed `output_per_1m = 0.0`, not `None`.** The endpoint emits no completion tokens, so zero is a *verified* rate; `None` would have scored every embedding call as unpriced and silently dropped its cost.
- **Ingest extractor is PyMuPDF, not production's Docling/GROBID chain**, so results describe the basic-chunking arm. Recorded per manifest row.
- **Tier assignment is by page count, which does not track content length** — a 9-page/39,880-token paper lands in SHORT tier and yields 34 chunks where similar MEDIUM papers yield ~15. Confounds cross-document comparison.
- **`labels.py` title-token matching is lenient**: it counted 44 unresolved where the sidecar records 65, leniently matching 21 to downloaded filenames. Inflates recall slightly. Not yet addressed.
- **A mocked test must not depend on ambient env.** Six ingest tests failed under `NOESIS_LLM_KILL_SWITCH=1` despite spending nothing, because the guard reads env at call time. Fixed with an autouse fixture.

### Blocked

**OpenAlex is now a metered paid API.** Free tier $0.10/day ≈ 100 lookups; 544 parsed references need ~600–1000. 4 of 15 papers built; 11 remain (399 more references) plus 19 `pending`. Budget had not reset as of the last check (~3.9h to midnight UTC). Fully resumable — re-running built papers costs 1.2s and zero network calls.

Options: fund ~$1 for a single ~40-minute run · re-run after each daily reset for ~10 days · build a Crossref + Unpaywall fallback (free, unmetered, but a different id space and match semantics than the sidecar schema assumes).

---

## Wave 2b — not started

The wave that turns the benchmark board into numbers: first traced run (per-node p50/p95, `$/run`, fallback-invocation rate) and first retrieval baseline over the 59 joined queries.

Gate to enter: none for the traced run. The retrieval baseline can run on 4 topics now, or on all 15 once OpenAlex is unblocked.
