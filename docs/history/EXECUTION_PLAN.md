# EXECUTION_PLAN.md

**Status:** awaiting your go-ahead. Nothing built yet.
**Scope:** Tier 1 of `NOESIS_BUILD_PLAN.md` (N0–N6), executed with up to 5 parallel agents.
**Policy in force:** commit as I go on `dev/noesis-app-development`; all permissions granted.

---

## 0. What the forensic dump just resolved

Supabase is live (PostgreSQL 17.6). Read-only introspection answered four of the audit's seven open questions and **corrects four claims in `LEARNING_AUDIT.md`.**

| Question | Answer | Effect on the audit |
|---|---|---|
| Vector index type / params | `USING hnsw (embedding vector_cosine_ops)` on **both** `document_chunks` and `draft_chunks`. No explicit `m`/`ef_construction` → PG defaults (`m=16`, `ef_construction=64`) | **Correction.** Audit §1.1 said "you cannot state your index type." You can now: HNSW, cosine ops, default build params |
| Distance operator | `<=>` cosine, and `match_document_chunks` returns `1 - (embedding <=> query_embedding) AS similarity` | **Correction.** Similarity **is** bounded 0–1. The audit's worry that `<#>` might make ~40 thresholds meaningless is resolved — the thresholds are on a real scale |
| `ef_search` | **`SET LOCAL hnsw.ef_search = 80`** inside the RPC | **Correction.** Audit said "no `SET hnsw.ef_search` anywhere," which was true *of the Python* — it lives in SQL. Production value is 80, and it's now sweepable |
| Is `keyword_search_chunks` deployed? | **Yes**, plus `keyword_search_draft_chunks`. And `idx_document_chunks_fts USING gin (content_tsvector)` already exists | **Correction.** Audit speculated hybrid search "may have been pure semantic this entire time." It wasn't. The keyword leg works |

**What this changes for the plan:**

- **N7 gets cheaper.** tsvector column, GIN index, and the RPC already exist. The remaining work is only the RRF replacement of the scale-incoherent weighted sum — and the dump confirms the diagnosis exactly: `keyword_search_chunks` returns raw unbounded `ts_rank`, which `rag_retrieval.py:486-489` weighted-sums against a bounded 0–1 cosine.
- **N0.2 becomes "mirror, then diverge."** I now know production's exact schema, so the local schema starts as a faithful mirror (checked into `migrations/`) and *then* becomes the thing you sweep. Better than either recovering blindly or authoring blindly.
- **Six RPCs confirmed deployed:** `match_document_chunks`, `match_single_document_chunks`, `match_project_content`, `keyword_search_chunks`, `keyword_search_draft_chunks`, `find_similar_claims`.

`LEARNING_AUDIT.md` gets a correction block appended in Wave 0.

---

## 1. Environment: verified facts and one real constraint

| Fact | Value | Consequence |
|---|---|---|
| Docker | 28.5.1, **8.2 GB allocated** | **Constraint.** GROBID (~4 GB) + Docling (~4 GB) + backend + worker + redis + pgvector + observability will not co-exist. Compose profiles required — see §3.2 |
| Keys present in `services/backend/.env` | `OPENAI_API_KEY`, `COHERE_API_KEY`, `SUPABASE_URL` / `ANON` / `SERVICE_ROLE`, Stripe, Sentry | Cohere free tier means N7 gets an API reranker arm at zero cost (rate-limited → small subset only) |
| Eval assets on disk | 57 PDFs, 214 MB node fixtures, 74 MB matcher cache, 9.1 MB exports, 20 gold files, OpenReview JSONs | Nothing to re-scrape. Replay-first is viable |
| Supabase | live, PG 17.6 | Forensic source + fallback DB |

**Cost posture:** replay from cache before running live; stub the LLM for load testing; hard spend cap set by you in the OpenAI dashboard. Expected Tier-1 spend is dominated by N1's handful of real pipeline runs.

---

## 2. Branch decisions — every risky step has a fallback

I will not get stuck. Each of these is pre-decided.

### B1 — Database

| Branch | Trigger | Consequence |
|---|---|---|
| **B1-A (default): local pgvector**, schema mirroring production DDL | `pgvector/pgvector:pg17` starts on arm64 | Full plan available, including N3's `ef_search`/`m` sweep |
| **B1-B: `ankane/pgvector` or `postgres:17` + `CREATE EXTENSION vector`** | image pull or arch failure on B1-A | Identical outcome; different base image |
| **B1-C: Supabase with an isolated `eval` schema** | local Postgres unworkable | N2/N4/N7 still run. **N3 is deferred** — a recall/latency curve measured over network RTT is meaningless, and I'd rather defer the build than publish a bad number |

### B2 — Tracing backend

| Branch | Trigger | Consequence |
|---|---|---|
| **B2-A (default): Langfuse v2 self-hosted** (single Postgres, light) | RAM allows | Full trace tree + cost rollups + dataset primitives; **manuscript text never leaves your machine** |
| **B2-B: Langfuse Cloud free tier** | v3's ClickHouse/MinIO stack too heavy, or v2 unavailable | Same features. **Privacy tradeoff — I will scrub span payloads to metadata-only (no manuscript text) before enabling this** |
| **B2-C: OTel SDK → local Jaeger** | Langfuse blocked entirely | Spans and latency yes; cost rollups and dataset primitives hand-rolled |
| **B2-D: JSONL span writer + pandas analysis** | everything else fails | Ugly but sufficient — every N1 metric is still computable. Never blocks the plan |

Spans carry **OTel GenAI semantic-convention attribute names** in all four branches, so the vocabulary transfers regardless.

### B3 — PDF parsing for eval ingest

| Branch | Trigger | Consequence |
|---|---|---|
| **B3-A (default): existing Docling → GROBID → PyMuPDF chain** | RAM allows, one service at a time | Matches production behavior |
| **B3-B: GROBID + PyMuPDF only, Docling disabled** | RAM contention | Parse quality differs from production. **Documented as a variable in every result file**, not silently swapped |

### B4 — Reranker arms (N7, Tier 2)

Local `bge-reranker-v2-m3` (free, CPU, carries the latency lesson) is the primary arm. Cohere free tier is an optional quality-ceiling arm on a rate-limit-sized subset. Existing `gpt-5-mini` reranker is the third arm.

---

## 3. Wave 0 — serial, me, no agents (~1.5 h)

| Step | Action | Commit |
|---|---|---|
| 0.1 | Write `migrations/036_recovered_production_ddl.sql` — the six RPC bodies, index definitions, and column types dumped above, checked in with a header explaining provenance | `chore(db): check in recovered production vector DDL` |
| 0.2 | Append a corrections block to `LEARNING_AUDIT.md` §1.1/§1.2 and Open Questions 1–3 | `docs: correct audit findings resolved by live introspection` |
| 0.3 | Split `infra/docker-compose.yml` into profiles: `core` (redis, pgvector), `parse` (grobid, docling), `app` (backend, worker, frontend), `obs` (langfuse). Verify each profile starts inside 8.2 GB | `chore(infra): compose profiles for 8GB memory ceiling` |
| 0.4 | Add cost guardrails: a token-spend accumulator + `NOESIS_LLM_KILL_SWITCH` env var honored in `retry_utils`, and `EVAL_REPLAY_ONLY` to force cache-only runs | `feat(cost): spend accumulator and LLM kill switch` |
| 0.5 | Baseline snapshot: current test suite green, `git status` clean of my changes | — |

**Gate:** all four profiles start; kill switch demonstrably blocks a live call.

---

## 4. Wave 1 — five agents in parallel (~12 h wall-clock, ~30 h of work)

**Conflict control: strict file ownership. No two lanes touch the same file.**

### Lane A — Database and schema
**Owns:** `infra/docker-compose.yml` (pgvector service), `services/backend/migrations/037_*`, `scripts/eval/db.py` (new)

1. Stand up local pgvector (B1-A → B1-B → B1-C ladder)
2. Apply `036` mirror: `vector(1536)`, HNSW `vector_cosine_ops`, GIN on `content_tsvector`, all six RPCs verbatim including `SET LOCAL hnsw.ef_search = 80`
3. `037`: parameterize `ef_search`, `m`, `ef_construction` so N3 can sweep them; add an IVFFlat variant index behind a flag
4. `scripts/eval/db.py`: a direct psycopg connection for the harness that **bypasses the app's Supabase client**
5. Ingest the 57-PDF eval corpus locally; verify a similarity query returns ordered, non-empty results
6. Parity test: same query, same embedding, local vs Supabase → cosine scores agree within tolerance

**Gate:** parity test passes, or B1-C engaged with N3 explicitly deferred.

### Lane B — Surgical measurement-blocking fixes
**Owns:** `retry_utils.py`, `rag_chunking.py`, `rag_retrieval.py` (`expand_query` only)

1. **N0.3:** `_normalize_parsed_chat_completion` returns `(parsed, usage)`; thread usage to every caller. This is the single most load-bearing hour in the plan
2. **N0.4:** `pysbd` sentence splitter replacing `.replace('. ','.|')`, **old path behind `CHUNKING_SPLITTER=legacy`** so it becomes a measured arm in N7 rather than a silent fix
3. `expand_query` fix (`rag_retrieval.py:345-352`) — the prompt asks for a JSON array and the code calls `.get()` on a list, so the documented 4× fan-out is a permanent no-op. ~20 min; stops a documented feature from being fictional
4. Unit tests: `et al.` / `Fig. 3` / `p < 0.05.` survive splitting; usage is non-null on a mocked response

**Gate:** tests green; one real call logs a token count.

### Lane C — Gate calibration (fully independent: no DB, no Docker, no LLM)
**Owns:** `scripts/eval/gate_calibration/` (new)

1. Write the **labeling rubric first** — operational definition of "degraded," with tie-break rules
2. Labeling CLI over the 79 exports in `scripts/eval/results/`: shows the critique, records a label, resumes where it left off
3. Metrics module: PR curve (not ROC — degraded is the rare class), AUC-PR, reliability diagram, ECE, Brier
4. Threshold sweep over `parser_quality_score` (0.55) and `page_anchor_coverage` (0.75) under asymmetric cost
5. Add `verbatim_anchor_coverage` (computed at `draft_analysis_langgraph.py:666-726`, compared against **no threshold at all**) as a candidate predictor
6. Leaves ~60 labels for you or me to fill in Wave 3

**Gate:** rubric written, CLI runs, metrics validated on synthetic labels.

### Lane D — Tracing module
**Owns:** `services/backend/app/core/tracing.py` (new), `infra/docker-compose.observability.yml` (new), `services/backend/app/core/logging_config.py`

1. Backend-agnostic span API with adapters for all four B2 branches
2. OTel GenAI semantic-convention attribute names throughout
3. `SpanKind` helpers: run / node / llm_call / retrieval / tool
4. **The hard part, isolated here:** parent-context propagation across a LangGraph `Send` superstep, so the three reviewer branches nest under one parent. Includes a standalone test proving it
5. Stand up the chosen backend; fall down the ladder on failure
6. Fix `setup_logging()` — never called, and its hand-rolled `%`-format string would emit invalid JSON — then call it; initialize Sentry in the Celery worker
7. Correlation ID: HTTP → Celery → LLM call

**Gate:** a synthetic 3-way fan-out produces a correctly nested trace in the chosen backend.

### Lane E — Retrieval eval harness
**Owns:** `scripts/eval/retrieval/` (new)

1. Label builder: each draft's OpenAlex reference list → corpus doc IDs (reuse `build_corpus.py` output)
2. **Decide and document the unit of relevance** — chunk / section / document. This moves NDCG more than any model swap; it gets a written justification, not a default
3. Query-set builder: claims from the 15 OpenReview papers + 10 gold drafts
4. Metric math via `ranx` (correctness over re-derivation; the learning is in labels and relevance units)
5. **Retriever adapter interface** so this lane builds without waiting on Lane A — adapters for dense, keyword, hybrid, and later RRF
6. Append-only results writer keyed on the pipeline-version hash (`pipeline_cache.py:26-66` pattern)
7. Also fix the precision definition at `judge_openreview.py:307-324`, which admits an LLM grounding verdict as a positive and makes `precision = 1.0` near-tautological

**Gate:** harness runs end-to-end against a mock retriever and emits a metrics file.

**Wave 1 commits:** one per lane on completion, plus a merge commit.

---

## 5. Wave 2 — integration, serial (~4 h)

| Step | Depends on | Action |
|---|---|---|
| 2.1 | B + D | Wire spans into the `_*_with_progress` wrappers (`graph.py:60-303` — every node passes through them, one injection point). Replace hardcoded progress constants with measured completion |
| 2.2 | A + E | Point the retrieval harness at local pgvector; ingest; smoke-test |
| 2.3 | 2.1 | **First traced run.** Produces the first real `$/run`, per-node p50/p95, and the LLM-I/O share of wall-clock |
| 2.4 | 2.2 | **Baseline retrieval metrics.** recall@{1,5,10,20}, MRR, NDCG@10, plus miss breakdown by failure mode |

**Gate — the plan's midpoint:** you can answer *"which node is slowest and what does a run cost?"* and *"what's your recall@10?"* with real numbers. Both currently unanswerable.

---

## 6. Wave 3 — measurement builds, 4 agents parallel (~12 h)

| Lane | Build | Notes |
|---|---|---|
| F | **N3 ANN sweep** | `ef_search` ∈ {10,40,80,160,320} × `m` ∈ {8,16,32}; IVFFlat `probes` sweep. Recall@10 vs p95, index size, build time. Production's `ef_search=80` becomes a labeled point on your own curve |
| G | **N4 completion** | Label ~60 runs, produce FP/FN/AUC-PR/ECE, sweep thresholds, decide `FAIL_CLOSED`, surface the verdict in the API response (`drafts.py:1313-1341` currently omits it) |
| H | **N5 load generator** | Poisson arrival sampler + completion tracking (HTTP load tools don't fit an async Celery workload). Open **and** closed loop, report the p99 gap. **Stub LLM with latency sampled from N1's distribution — near-zero cost** |
| I | **N6 prompt caching + compaction** | Reorder prefixes (invariant calibration block + manuscript first, persona last), measure `cached_tokens`, wire up the dead `_section_excerpts`, establish a real token budget |

**Gate:** every row of the `NOESIS_BUILD_PLAN.md` benchmark board for N1–N6 has a value.

---

## 7. Wave 4 — consolidation (~3 h)

1. Fill the benchmark board
2. Rewrite resume bullets with real numbers (templates already in `NOESIS_BUILD_PLAN.md`)
3. Update `noesis_interview_prep.md` — the `18s` vs `3.5 min` contradiction gets resolved by N1+N5 measurements
4. `RESULTS.md`: every number, its method, and its load model
5. Tier 2 (N7–N15) and the agent harness re-scoped against what was learned

---

## 8. Agent orchestration

- **5 concurrent max**, as instructed. Wave 1 uses all five; Wave 3 uses four.
- **Shared working tree, disjoint file ownership** — not worktrees, since you want incremental commits on one branch.
- Each agent gets: its file allowlist, its gate, its fallback ladder, and an instruction to **stop and report rather than touch a file it doesn't own**.
- I integrate and commit; agents don't commit.
- If a lane fails its gate, its fallback branch engages automatically; if all fallbacks fail, that lane's build is deferred and the rest proceed. **No lane can block another.**

---

## 9. What I will not do without asking

- Write to production Supabase (read-only introspection only)
- Enable Langfuse Cloud without first scrubbing manuscript text from spans
- Make any repo public — see the security checklist from our discussion; recommendation stands that the **agent harness repo** goes public first and Noesis waits for a history scan and credential rotation
- Touch `master` or anything your cofounder owns
- Fix the WebSocket IDOR or CORS wildcard (out of Tier 1 scope, documented, product frozen)

---

## 10. Estimated totals

| Wave | Wall-clock | Work |
|---|---|---|
| 0 | 1.5 h | serial |
| 1 | ~12 h | ~30 h across 5 agents |
| 2 | 4 h | serial |
| 3 | ~12 h | ~28 h across 4 agents |
| 4 | 3 h | serial |

**OpenAI spend:** dominated by Wave 2.3's real runs and Wave 3's N6 measurements. Everything else replays cache or stubs the model. Set your dashboard cap at $25 and N1 will tell you the true per-run cost on the first execution.

---

**Awaiting go-ahead. Say go and I start at Wave 0.1.**
