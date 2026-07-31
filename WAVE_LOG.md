# WAVE_LOG.md

Running record of each wave from `EXECUTION_PLAN.md`: what was built, what was verified, and what was found. Numbers here are measured, not estimated. Anything unverified says so.

---

## 📌 WHAT IS NOW MEASURED — state of play as of 2026-07-31

Read this instead of every wave. **Every number carries its `n` and its source document.** Four rules govern all of them:

1. **A node replay is not an end-to-end user-visible time.** The end-to-end path has never been measured, not once.
2. **An index-forced ANN latency is not what the planner does**, and an eval-corpus retrieval number is not a production retrieval number.
3. **Retrieval numbers from different label snapshots are not comparable at all.** There are **three** (`019bee4a06eb2d39` · `425df789a844f1f3` · `230c6ea9d9b7e8fd`). Directions reproduce; absolutes do not.
4. **Every cost figure produced before the matcher fix is a lower bound** by a margin that cannot be recovered — the matcher's caches store no usage data.

### Retrieval — current snapshot `230c6ea9d9b7e8fd`

**n = 338 scorable queries · 8,554 relevant judgments · 344 indexed documents / 5,948 chunks · 345-document pooled label corpus · 15 of 15 topics.** Source: `scripts/eval/BASELINE_15.md` §3 (corroborated by `scripts/eval/BENCHMARKS.md`, run `5ca19da1d093`).

| arm | R@10 | ceiling | % attainable | NDCG@10 | MRR |
|---|---|---|---|---|---|
| **dense** (oversample ×5, `plan: index`) | **0.2195** | **0.5199** | **42%** | **0.5191** | **0.7328** |
| dense (×12, `plan: seqscan` — deeper, confounded with depth) | 0.2227 | 0.5199 | 43% | 0.5221 | 0.7436 |
| keyword **v1** (`plainto_tsquery`) | 0.0022 | 0.5199 | 0% | 0.0110 | 0.0311 |
| keyword **v2** (OR of lemmas) | **0.1447** | 0.5199 | 28% | 0.3830 | 0.6675 |
| RRF(dense, keyword v2), k=60 | 0.2042 | 0.5199 | 39% | 0.4989 | 0.7335 |

- **The ceiling travels with the number or the number is misleading.** Every query inherits its manuscript's entire reference list, so a query with 37 relevant documents cannot exceed recall@10 = 10/37.
- **`0.4221 → 0.2195` is NOT a regression.** That is the old snapshot (118 docs / 4 topics / 59 queries) versus the new one: 2.8× the chunks, more distractors, and the average query now inherits 25.3 relevant documents instead of 15.3, which dropped the ceiling from 0.7789 to 0.5199. **Never difference the two.**
- **Keyword fix:** zero-row queries **321/338 → 0/338**; recall@10 **66×**. Behind `KEYWORD_SEARCH_V2`, **default OFF**. Nothing shipped to production.
- **RRF loses to dense:** recall@10 **−7.0%**, NDCG@10 **−3.9%**, MAP **+4.8%**. Best coverage (retrieval failures 5,144 vs 6,010), worst ranking (1,885 vs 936). `k_rrf` has no gradient across a 60× span. Measured with the keyword leg forced on, which is **not** what production runs.
- **Standing caveat:** these labels measure *"would we have found what the author cited"*, not *"what is relevant"* — every precision-like metric is a **lower bound** and recall is the sounder number. The query set also contains a large population of contentless claims that no retriever can serve; filtering them would raise every arm and improve nothing.
- Local pgvector, PyMuPDF extraction, basic chunking. **Not** production's Docling → GROBID section-aware chain.

### Cost — first complete figure · `scripts/eval/NODE_COST.md`

**$0.20016 total** across 4 runs: node **$0.16761 (83.7%)** + matcher **$0.03255 (16.3%)**. The matcher share is what every earlier figure omitted, and it scales with how many items a node emits, not with what the node cost.

| node | n | node $ | matcher $ | matcher share |
|---|---|---|---|---|
| `reviewer_panel_node[methodology]` @ `10eQ4Cfh8p` | 5 | $0.12098 | $0.02682 | 18.1% (**$0.0296/replay complete**) |
| `editor_pass_node` | 3 | $0.00339 | $0.00297 | 46.7% |
| `run_quality_diagnostics` | 3 | $0.00000 | $0.00277 | **100%** |

**`run_quality_diagnostics` makes zero LLM calls and still costs $0.00277 to measure.** Still outside the accounting: `atomize_reviews.py` (contributed $0.00 here by cache luck, not by design), usage lost on validation retries, and ~$0.02 of real spend lost to a killed process with no usage log.

### Variance — `scripts/eval/NODE_COST.md` §Variance

- **Latency: CV 15.0% at n=5** on one fixture — 17.10 / 18.26 / 19.69 / 24.13 / 17.25 s, mean 19.286, sd 2.897, 95% CI 19.29 ± 3.60 s. **The earlier ~7% came from n=3 and did not survive.** Nothing smaller than ~±19% of the mean is resolvable here.
- **Quality: unresolvable. No delta may be reported.** Severity-weighted recall over the same 5 replays: 0.0463 / 0.0232 / 0.0000 / 0.0116 / 0.0116 (4, 2, 0, 1, 1 matched of 79 gold units), CV 95%, quantised at 1/79 of its own range. Cause: `temperature` is stripped for every `gpt-5.2*` model and no seed exists.
- `BENCHMARKS.md`'s roll-up (`reviewer_panel_node` 19.307 s, n=12) **mixes fixtures and personas** — a cost summary, not a variance estimate.

### Prompt caching — `scripts/eval/NODE_COST.md`, `scripts/eval/PROMPT_CACHE.md`

Cross-persona hit rate **0% → 60.7%** on the real replay path (16,128 cached of 26,578 prompt tokens, cold 3-persona panel), **24.5% cheaper per cold panel** ($0.10387 counterfactual uncached vs $0.07847 measured). The purpose-built A/B on a different paper read 58.8% / 23.8%; both reproduce within ~2 points. Shared prefix is **8,064 tokens ≈ 87.4% of the prompt**, quantised to OpenAI's 128-token cache block. **n = 2 papers, one cold panel each.** `--repeat` inflates the rate (98.5%) and must never be quoted as production. This did **not** turn caching on — OpenAI's automatic prefix cache already worked; what was added is reuse *across* personas.

### Publish gate — Wave 1, across all 77 usable exports

`parser_quality_score` takes exactly **2 values** (1.0 ×52, 0.95 ×25) against a 0.55 bar → **inert**. `verbatim_anchor_coverage` is **1.0 on all 77** and **structurally cannot vary** (a failed anchor is nulled upstream, removing the task from the denominator too). **`page_anchor_coverage` is the only signal that has ever driven a verdict** — all 12 `needs_retry` results. Threshold 0.75 is **hand-set, not calibrated**: the sweep needs human labels and `BENCHMARKS.md` records *"No sweeps recorded … not a zero, an absence."*

### Eval precision — Wave 2

The shipped `mean_precision: 1.0` was structural. Honest **`precision_vs_gold` 0.27**, **hallucination rate 0.111**, groundedness 0.889, weakness recall 0.187 — **n = 3 papers**. A pair-based numerator would read 0.554 and double-counts. **0.27 is a lower bound** by the standing caveat; the 0.111 is the unambiguous number. Recomputed from cached exports with zero LLM calls. **There is still no before/after**: `BENCHMARKS.md` shows 17 OpenReview runs across 3 pipeline versions, every one at `no data (n=0)` scored cells.

### ANN / vector index — `scripts/eval/ANN_SWEEP.md`, `BASELINE_15.md` §2

The HNSW crossover moved **~35 → 103** as the corpus grew **2.80×** (2,124 → 5,948 chunks) — crossover ×2.96, verified by binary search over `EXPLAIN` across 10 query vectors. It is **not a constant** and must never be cached as one; `plan` is now stamped into every retrieval record. `ef_search = 80` sits on the knee at production's k=10 (ANN recall 0.9932 @ 1.03 ms p50); **raising it past 80 makes a k=10 query 16× slower** — because the plan flips to a sequential scan, not because the index slowed. **Every ANN latency number is from the 2,124-chunk corpus and has not been re-measured**; `BASELINE_15.md` reports no latency at all.

### Corpus — `scripts/eval/BUILD_REPORT.md`

**333 / 544 references resolved = 61.2%** across 15 of 15 topics; buckets sum exactly (333 + 78 + 81 + 52), zero `pending`, PDFs on disk equal `resolved` in all 15 directories. Measured build cost $0.3520. **The denominator is understated:** 60 of 544 parsed entries (11%) are merged blocks containing two or more distinct works, so the true bibliography is larger than 544 and the true rate is **lower** than 61.2%. Never quote it as *"we resolve 61% of the references in these papers."* For the retrieval label snapshot the rate is **unknown** — 11 of 26 corpora have no `references.json` sidecar, and it is reported as unknown rather than substituted.

### Still unmeasured

End-to-end / user-visible latency (never, not once) · `53s → 18s` and `66%` (no sequential baseline exists) · "no quality loss" (and **any** quality delta — unresolvable at present n) · "lifted quality on evals" · user counts · whether 0.75 is the right gate threshold · production retrieval quality · the section-aware chunking arm · ANN latency at the current corpus size · RRF as a first-stage pool feeding a reranker · whether non-gold items are findings or hallucinations (unmeasurable under this label design).

> The full claim-by-claim mapping, with each figure's source document and the corrections it forced, is `LEARNING_AUDIT_ADDENDUM.md` §3.

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

## Wave 2b — COMPLETE (2026-07-30) — **the board has numbers**

| Task | Commit | Result |
|---|---|---|
| Production bugs: NUL bytes, backwards progress | `af4997a` | 35 tests |
| Trace analysis tooling | `9153484` | 48 tests |
| Measured node replay + `llm_call` spans | `3d350f8` | 18 tests |
| First retrieval baseline | `cdbeb93` | 123 tests |

Suites: **895 backend** (2 deferred failures), **365 eval**.

---

## 📊 BENCHMARK BOARD — measured, not estimated

> ⚠️ **Superseded 2026-07-31 — see "WHAT IS NOW MEASURED" at the head of this file.** This board is snapshot `019bee4a06eb2d39` (59 queries, 118 docs) plus a node-cost table taken before the matcher was inside the accounting. Specifically: the retrieval numbers below belong to a label snapshot that no longer exists and **must not be differenced against the current ones**; every `$` below is node-only and therefore a **floor** (matcher spend is 16.3% of the true total); and **latency CV ~7% at n=3 is false — it is 15.0% at n=5**. The prompt-cache 29.3% figure is a repeat-path number that the cross-persona reorder later replaced with 60.7%. Left in place as the record of what was known that day.

### Retrieval (document unit, k=10, 59 queries, 903 judgments, 118 docs / 2,124 chunks)

| metric | dense | keyword | ceiling |
|---|---|---|---|
| recall@1 | **0.0896** | 0.0034 | 0.106 |
| recall@5 | **0.3051** | 0.0040 | 0.531 |
| recall@10 | **0.4221** | 0.0040 | 0.779 |
| recall@20 | **0.5299** | 0.0040 | 0.880 |
| MRR | **0.8836** | 0.0339 | — |
| NDCG@10 | **0.6526** | 0.0112 | — |
| MAP | **0.4391** | 0.0040 | — |

**recall@k is capped by construction** — a query inherits its manuscript's entire reference list, so one with 37 relevant documents cannot exceed recall@10 = 10/37. Dense achieves 84% / 58% / 54% / 60% of what is attainable. **Quote the ceiling with the number or the number is misleading.**

### Cost and latency (per replay)

| node | wall | LLM calls | input (cached) | $ |
|---|---|---|---|---|
| `reviewer_panel_node[methodology]` | ~19.8s | 1–2 | ~18k (varies) | **~$0.043** |
| `editor_pass_node` | ~7.1s | 1 | ~894 | $0.00133 |
| `run_quality_diagnostics` | ~0.06s | 0 | 0 | $0.00 |

One reviewer is **~330× the wall time** of the entire diagnostics node. The conditional domain-trigger audit branch doubles calls and takes input to 53.5k — the largest single cost variable measured.

### Reliability

| | |
|---|---|
| latency CV (same node, same fixture, n=3) | **~7%** |
| **quality CV** (recall 0.0, 0.0116, 0.0) | **~172%** |
| prompt-cache hit rate on repeats | **29.3%** (27,264 / 27,510 tokens) |

**Any single-run node score on this pipeline is noise.** Consistent with `retry_utils.py:33-46` stripping `temperature` for every `gpt-5.2*` model with no seed anywhere.

The cache number reframes N6: OpenAI's **automatic** prefix caching is already working without any `cache_control`, so that work is about raising a measured 29.3%, not switching caching on.

---

### 🔴 Nothing had ever emitted an `llm_call` span

Running the analyser against the first real span file showed latency but **$0.00 for everything**. The span kind existed, the GenAI attribute helper existed, the analyser attributed cost to the nearest node ancestor of each `llm_call` — and **no producer existed anywhere in the repo**. Every `$/run` the tool could print would have been `$0.00`, silently and forever.

Fixed at the source: both `retry_utils` wrappers now emit one, inside the validation-retry loop with `noesis.llm.attempt`, so retried calls are separable. Verified end to end at $0.0353/run against hand arithmetic.

### 🔴 Keyword retrieval is mismatched, not broken

`keyword_search_chunks` uses `plainto_tsquery`, which **ANDs every lemma**, against ~20-word claim queries. Reproduced directly: `'job shop scheduling'` → **38 rows**; `'we highlight the superior generalizability of our approach trained on small-scale instances'` → **0 rows**. 55 of 59 queries return nothing.

**A hybrid built today would fuse dense with almost nothing.** Fix query formulation before implementing RRF.

### 🔴 A silent join bug that would have reported flat zeros

`labels.py` identified documents by `sha256[:16]`; `ingest.py` by `uuid5(ns, sha256_hex)`. The id spaces never overlap, so **every DB-backed run would have reported 0.0 on every metric while looking perfectly healthy.**

### Other findings

- **`tiktoken` raises on the literal `<|endoftext|>`** under its default `disallowed_special="all"`, and one corpus paper contains it. **Production has the identical bug** (`rag_ingest.py:121`, `rag_chunking.py:380`) — that paper would fail production ingestion.
- **Label matcher inflated recall**: unresolved 44 → 65. The title-token matcher credited 21 never-downloaded references by matching titles against filenames.
- **NUL bytes also break `jsonb`**, so `documents.metadata` fails too — and the "mark document failed" path would itself throw on the same text, leaving documents stuck with no error recorded.
- **The progress bar went backwards four times per run**, not two.
- **`match.py` bypasses the budget system** — it calls the OpenAI client directly, so its calls are neither recorded nor bounded by the ceilings.
- **`get_pdf_page_count` fabricates `10` on any exception**, and that value feeds the adaptive chunking tier.
- Hand-checked two queries rather than trusting aggregates. Explains why MRR 0.88 reads so much better than recall 0.42: one strongly on-topic paper dominates rank 1 while the other 7–36 cited references never surface.

### Caveats that travel with every number above

n=59 queries across only **4 of 15 topics** · measures "would we have found what the author cited", not "what is relevant", so **MAP/NDCG are lower bounds — never quote MAP as precision** · PyMuPDF extraction means this is the **basic-chunking arm**, not production's section-aware one · distractors come from topically distant areas, so retrieval is easier here than reality and every metric is optimistic · no human made a relevance judgment.

---

## Wave 3 — not started

Candidates, now that measurement exists: N3 ANN sweep (`ef_search`/`m`, unblocked — corpus is ingested), N6 prompt caching against the 29.3% baseline, N7 hybrid + RRF (**blocked on the query-formulation finding**), gate calibration labelling.

> ↻ **Status correction, 2026-07-31.** Three of those four have since landed and are documented in `scripts/eval/`, though this log never recorded their waves:
>
> | candidate | outcome | document |
> |---|---|---|
> | N3 ANN sweep | **done** — `ef_search = 80` on the knee; `m`/`ef_construction` not a lever; crossover 35 → 103 as the corpus grew | `ANN_SWEEP.md`, `BASELINE_15.md` §2 |
> | N6 prompt caching | **done** — cross-persona 0% → **60.7%**, cold panel **24.5%** cheaper. The 29.3% baseline named above was a *repeat-path* number and is not the quantity that moved | `PROMPT_CACHE.md`, `NODE_COST.md` |
> | N7 hybrid + RRF | **unblocked and done — and the result is a negative.** Keyword v2 fixed the query formulation (321/338 zero-row → 0/338, 66× recall@10), then RRF **lost** to dense at the top of the list | `KEYWORD_QUERY.md`, `BASELINE_15.md` §5 |
> | gate calibration labelling | **not started.** `BENCHMARKS.md` still reports *"No sweeps recorded … not a zero, an absence"* | `BENCHMARKS.md` |
>
> Also landed and unrecorded here: the corpus build to 15/15 topics and its ingestion (344 docs / 5,948 chunks), and the matcher being brought inside the cost accounting. Both are in the head-of-file block.
