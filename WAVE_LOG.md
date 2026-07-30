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

## Wave 1 — not started

Gate to enter: none outstanding. Awaiting go-ahead.
