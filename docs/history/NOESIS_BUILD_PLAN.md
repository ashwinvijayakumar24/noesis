# NOESIS_BUILD_PLAN.md

**What this is.** The complete, ordered Noesis work program: every build, what it teaches, what number it produces, and how you know it's done. Consolidates the build decisions from `LEARNING_AUDIT.md`, its addendum, and the roadmap coverage mapping.

**What it is not.** Not the evidence base — that stays in `LEARNING_AUDIT.md` (778 lines of `file:line` forensics, interview questions, and the resume-claim audit). Not the claims-correction work — that stays in `LEARNING_AUDIT_ADDENDUM.md` §1. Not the agent work — that's `AGENT_HARNESS_PLAN.md`. Inference engine and serving layer are out of scope here by your instruction.

**Scope note.** Build IDs are renumbered `N0`–`N15` in execution order. Earlier conversations used a different numbering; these IDs are now canonical.

---

## Ground rules

1. **No claim without a number.** Every build below terminates in a metric. If a build produces no number, it isn't done.
2. **Ruler before change.** `N2` (retrieval eval) precedes every retrieval change. `N1` (tracing) precedes every cost or latency claim. Non-negotiable.
3. **Append, never overwrite.** `run_eval.py:385` overwrites `scoreboard.json` in place, which is why you have no eval history. Every new result file appends.
4. **Fix only what blocks measurement.** The audit found ~14 bugs. Four block learning and are scheduled below. The rest stay documented-and-unfixed — the product is frozen, nobody is harmed, and "I found and documented these" is a good interview answer.
5. **Honest attribution.** Where a Noesis build is an *analog* of a GPU/serving concept, say "analog" out loud. Marked **ANALOG** below.
6. **Whiteboard test.** If you can't reproduce it on a whiteboard, it doesn't go on the resume.

---

## Dependency graph

```
N0 (blockers) ──┬─→ N1 tracing ──┬─→ N5 load generator
                │                 ├─→ N6 prompt caching
                │                 └─→ N13 cascade sweep
                ├─→ N2 retrieval eval ─┬─→ N3 ANN sweep
                │                       ├─→ N7 RRF + contextual
                │                       ├─→ N9 vector precision
                │                       └─→ N15 semantic cache
                └─→ N4 gate calibration   (independent — no DB, no Docker)
N8 judge calibration ── independent
N10 reliability ─────── independent
N11 checkpointer ─────→ (harness Phase B.5)
N12 injection ────────← (mandatory once harness Phase A ships)
N14 eval-in-CI ───────← needs N2 + N8
```

---

# TIER 1 — the spine (≈62 h Noesis-only)

## N0 — Foundations and unblocking (6 h)

Nothing downstream is measurable until this is done. Four independent sub-tasks.

### N0.1 — Apply the claims-correction pack (2.5 h, do first, zero dependencies)

Follow the checklist at `LEARNING_AUDIT_ADDENDUM.md` §1.9. Not repeated here. Summary: replace the six resume bullets, fix ~20 lines in `noesis_interview_prep.md`, reconcile the `18s` vs `3.5 min` contradiction with `CREATEX_PRESENTATION.md`, correct the embedding-model entry in project memory.

**Do this before any code.** It's the only item with an external deadline.

### N0.2 — Author a local vector schema (3 h)

`infra/docker-compose.yml` has redis, GROBID, docling, backend, worker, frontend — **no Postgres**. The DB is Supabase-only and Supabase is unreachable (`list_tables` and `select 1` both timed out, 2026-07-29). Production DDL for the six similarity RPCs was never in the repo (`migrations/034_document_domain.sql:7-9` admits it).

**Decision: author a new schema rather than recover production's.** Recovery would only tell you what someone picked in a dashboard. Authoring means you can *state* index type, `m`, `ef_construction`, distance operator — and sweep them.

Steps:
1. Add `pgvector/pgvector:pg16` service to `infra/docker-compose.yml`.
2. Write `migrations/036_vector_schema.sql`: `CREATE EXTENSION vector`, `document_chunks.embedding vector(1536)`, `CREATE INDEX ... USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64)`.
3. Write the RPCs **in the repo**: `match_document_chunks`, `match_single_document_chunks`, `keyword_search_chunks`. Pick and document the distance operator explicitly.
4. Point the eval harness at this DB directly — it does **not** go through the app's Supabase client.
5. Re-ingest the eval corpus locally.

**Go/no-go, <30 min:** `docker compose up pgvector`, apply the migration, ingest one PDF, run one similarity query, confirm non-empty ordered results. Pass → all retrieval work is unblocked. Fail → N4 and N8 are still available (they need neither DB nor Docker).

**Topics closed:** pgvector index tuning setup, distance-metric choice, the fact that un-normalized truncated vectors make `<#>` non-comparable (`draft_task_evidence.py:373-377` normalizes only at compare time).

### N0.3 — Stop discarding token usage (1 h)

`_normalize_parsed_chat_completion` (`retry_utils.py:71-91`) returns only `.parsed` and throws `response.usage` away — on the *only* path the whole LangGraph pipeline uses. Meanwhile `drafts.py:1096-1097` inserts `prompt_tokens=800,  # Estimated`.

Return `(parsed, usage)`; thread it up through the node wrappers. **Every cost metric in this document is downstream of this one hour.**

### N0.4 — Fix the sentence splitter (1 h)

`rag_chunking.py:334` — `content.replace('! ','!|').replace('? ','?|').replace('. ','.|').split('|')` shatters on `et al.`, `Fig. 3`, `p. 12`, `p < 0.05.` — i.e. on every academic PDF. Replace with `pysbd` or a scientific-abbreviation-aware regex. **Keep the old path behind a flag** so it becomes a measured arm in N7 rather than a silent fix.

**Acceptance for N0:** local pgvector answers a similarity query; one LLM call returns a usage object you can log; the splitter keeps `et al.` intact in a unit test.

---

## N1 — Tracing, cost, and latency instrumentation (12 h)

**Goal.** Answer "which node is slowest, and what does one run cost?" — currently unanswerable.

**Why here.** Zero tracing exists: no OpenTelemetry, no Langfuse (`langsmith==0.1.147` is a LangChain transitive dep with zero call sites in `app/`), no request/correlation IDs, no per-run cost. `setup_logging()` (`logging_config.py:6-31`) is **never called**, Celery uses bare `print()`, and Sentry is initialized in the API process only (`main.py:96-104`) — so all the expensive, failure-prone work is invisible. An 18-node graph with a 3-way fan-out is the ideal shape for learning this; a flat single-call app teaches nothing.

**Build:**
1. Langfuse self-hosted. Use **OpenTelemetry GenAI semantic-convention attribute names** on every span so the vocabulary transfers.
2. Root span per run keyed on `analysis_run_id` (already exists, `draft_analysis_runs.py:34-55`).
3. Child span per graph node. The `_*_with_progress` wrappers (`graph.py:60-303`) already wrap every node — inject there, one change point.
4. Grandchild span per LLM call: model, input/output/**cached** tokens, latency, retry count.
5. Retrieval spans: query, `k`, returned doc IDs, similarity scores.
6. **The hard part:** the three `Send` branches must share a parent span across a superstep boundary. LangGraph does not hand you that — you propagate context manually through the `Send` payload.
7. Correlation ID from HTTP → Celery → LLM call. Today the only join key is `draft_id` inside `print()` lines.
8. Call `setup_logging()`, and fix its hand-rolled `%`-format string (`logging_config.py:14`) which would emit invalid JSON.
9. Initialize Sentry in the Celery worker.
10. Replace the hardcoded progress constants (`graph.py:64-178`) with measured node completion.

**Topics closed:** observability & LLMOps in full; structured tracing and nested spans across handoffs; OTel GenAI/OpenInference; percentile computation; cost attribution; RED; catching swallowed errors and silent retries. **ANALOG:** bottleneck identification — the traces will show Noesis is API-latency-bound, not compute-bound, which is the same *reasoning shape* as the roofline (identify the binding resource before optimizing) on a different resource.

**Benchmarks:** per-node p50/p95/p99 · tokens in/out per node · **$/run** · % of wall-clock in LLM I/O vs local compute · silent-fallback rate · retry rate per node.

**Acceptance:** a trace tree for one run, in a UI, with a dollar figure attached. You can name the slowest node and its share of wall-clock.

---

## N2 — Retrieval evaluation harness (12 h)

**Goal.** The first retrieval metric in the repo's history.

**Why here.** Grep for `ndcg|NDCG|MRR|recall_at|recall@|precision@` across the whole repo returns **zero hits**. For a product whose core is literature grounding, the retrieval layer is entirely unmeasured — while `top_k=5` (`rag_retrieval.py:89`) and ~40 similarity thresholds across six files rest on nothing. And you already own the labels without knowing it: `build_corpus.py` downloads each draft's own reference list from OpenAlex, which is human-authored ground truth for "what should retrieval have surfaced."

**Build `scripts/eval/retrieval_eval.py`:**
1. **Query set:** claims from `extract_claims` over the 15 OpenReview papers + 10 gold drafts.
2. **Label set:** each draft's true reference list resolved to corpus doc IDs.
3. **Decide the unit of relevance** — chunk, section, or document. Document this choice prominently; it moves NDCG more than any model swap you will ever make.
4. Compute recall@{1,5,10,20}, MRR, NDCG@10 against both `retrieve_relevant_chunks` (`rag_retrieval.py:89`) and `retrieve_relevant_chunks_hybrid` (`:576`).
5. Reuse the content-hash embedding cache (`match.py:77-118`) and the pipeline-version cache-key pattern (`pipeline_cache.py:26-66`).
6. **Append** results; never overwrite.
7. Failure-mode attribution per miss: retrieval failure / ranking failure / chunk-boundary failure / topic-gate rejection (`literature_search.py:76-78` drops anything below 0.72 similarity with zero lexical overlap — a correct hit in different vocabulary is discarded).

**Also fix while here:** the precision definition at `judge_openreview.py:307-324` counts an item correct if it matched gold **OR** its anchor appears in the PDF **OR** an LLM says it's grounded — which is why `mean_precision = 1.0` and `hallucination_rate = 0.0` (`:325`) are near-tautological. **Do not quote either number until this is fixed.**

**Topics closed:** retrieval component metrics (P/R@k, MRR, NDCG); binary vs graded relevance and the log discount; label construction; query-set design; train/test contamination; the four retrieval failure modes; cache-key hygiene.

**Benchmarks:** baseline recall@{1,5,10,20} · MRR · NDCG@10 · miss breakdown by failure mode.

**Acceptance:** a committed baseline number. Everything after this is measured rather than asserted.

---

## N3 — ANN index sweep: HNSW vs IVFFlat (4 h)

**Goal.** Be able to answer "what index, what parameters, what's your recall/latency curve?" — the question that currently ends the interview.

**Why here.** Cheap (4 h), rides N2's harness, and closes a named `[C]` topic nothing else touches. Only possible because N0.2 had you author the index. No `SET hnsw.ef_search` or `SET ivfflat.probes` appears anywhere in the Python today, consistent with there having been no ANN index at all in production.

**Build:** sweep `ef_search` over the HNSW index; build a parallel IVFFlat index and sweep `probes`; record recall@10 vs p95 query latency for each point; record index build time and on-disk size. Plot the curve. Pick an operating point and write down why.

**Topics closed:** HNSW internals (`M`, `ef_construction`, `ef_search`, layer assignment, beam search at layer 0); IVFFlat (`lists`, `probes`); recall as a *tunable*, not a guarantee; pgvector index tuning; exact vs approximate tradeoff.

**Benchmarks:** recall@10 vs p95 latency curve · index size · build time · chosen operating point with justification.

**Acceptance:** you can state your index type and parameters from memory and defend the operating point.

---

## N4 — Publish-gate calibration study (12 h)

**Goal.** Convert your most-overstated resume claim into a measured one.

**Why here.** The gate **does not block**: `FAIL_CLOSED` defaults off (`draft_publish_gate.py:38`, comment: *"Off by default so production keeps shipping feedback"*); on a non-publishable verdict the default path suppresses artifacts (`draft_analysis_langgraph.py:1742-1755`), then marks the run `passed` (`:1758`) and publishes normally (`:1769`). Contamination never affects the verdict, and the code says so (`draft_publish_gate.py:141-145`). The verdict is never surfaced to the user — zero frontend hits for `publish_gate`/`analysis_confidence`/`publishable`/`needs_retry`, and the API response omits them (`drafts.py:1313-1341`). **And this build needs no DB and no Docker** — it runs off the 79 per-run exports already on disk, so it's your fallback if N0.2 fails.

**Build:**
1. Write a labeling rubric **before** labeling. Define "degraded" operationally.
2. Label ~60 runs from `scripts/eval/results/*.json`.
3. Plot gate decisions against labels: FP rate, FN rate, PR curve (PR not ROC — degraded runs are the rare class).
4. Reliability diagram + ECE for `parser_quality_score` (threshold 0.55, `draft_publish_gate.py:33`) and `page_anchor_coverage` (0.75, `:31`).
5. Sweep both thresholds; find the operating point under *asymmetric* error cost (shipping a bad critique vs withholding a good one are not equally bad).
6. Test whether `verbatim_anchor_coverage` — computed at `draft_analysis_langgraph.py:666-726` and **compared against no threshold at all** — is a better predictor than what you're using.
7. Decide `FAIL_CLOSED` on the evidence, and surface the verdict in the API response.

**Topics closed:** operational definition of confidence; PR vs ROC and when each is honest; calibration ≠ accuracy (reliability diagrams, ECE, Brier); operating-point selection under asymmetric cost; label noise and why the rubric precedes the labels; fail-open vs fail-closed as a product decision.

**Benchmarks:** FP rate · FN rate · AUC-PR · ECE · thresholds before vs after · which predictor won.

**Acceptance:** you can state the gate's false-positive rate and defend both thresholds. The resume bullet becomes true.

---

## N5 — Load generator and goodput under SLO (8 h)

**Goal.** A defensible latency number, and the methodology that makes it defensible.

**Why here.** This is the build that answers *"how did you generate load?"* — the exact question that currently kills the `53s → 18s` claim. Concurrency surfaces are real: `asyncio.Semaphore(20)` (`retry_utils.py:30`, never acquired by the sync path at `:156-161`, and per-event-loop rather than per-process because `async_utils.py:30-38` spawns a thread + `asyncio.run` per call), Celery gevent pool at `--autoscale=3,1` (`docker-compose.prod.yml:164`), `worker_prefetch_multiplier=1` (`celery_app.py:61`), soft 600 s / hard 900 s limits where **the hard limit is unenforceable** because `task_time_limit` SIGKILLs a prefork child and the pool is gevent.

**Build:**
1. A load generator: **open-loop, Poisson arrivals**, configurable λ. Also implement closed-loop fixed-concurrency so you can show the difference.
2. Discard warmup explicitly.
3. Define an SLO up front (e.g. "analysis completes within 5 min"). Compute **goodput** = requests meeting SLO per unit time, alongside raw throughput.
4. Sweep λ. Plot goodput vs offered load; find where goodput collapses while throughput keeps rising.
5. Instrument queue depth (Celery) as your saturation signal — currently unmonitored.
6. Derive queue depth from measured λ and service time; compare to observed. **ANALOG for Little's Law** — at λ≈3 the numbers are small, so claim the *methodology*, not queueing-theory depth.
7. Re-derive the reviewer-parallelism speedup honestly, with a stated load model, and update the resume if it's defensible.

**Topics closed:** open vs closed loop load generation; Poisson arrivals vs fixed concurrency; warmup; percentile computation; **goodput under SLO vs throughput**; queue depth as a saturation signal; backpressure and admission control at task level. **ANALOG:** Little's Law.

**Benchmarks:** goodput vs offered load curve · p50/p95/p99 under load · queue depth vs λ · the honest speedup number with its load model stated.

**Acceptance:** you can say "open-loop, Poisson arrivals at λ=X, warmup discarded, p95 = Y, goodput collapses at λ=Z" without hesitating.

---

## N6 — Prompt caching and context compaction (8 h)

**Goal.** Cut cost measurably, and build the prefix-cache intuition your serving layer depends on.

**Why here.** Zero caching today (`cache_control`, `prompt_cache`, `cached_tokens`, `ephemeral`: zero hits). Meanwhile: the ~60-line `RATING_CALIBRATION` block (`reviewer_panel.py:48-108`) is f-string-interpolated verbatim into all three personas (`:137,170,191`), and the **full manuscript is sent four times per run** — three reviewers (`:391-392`) plus the methodology trigger audit (`:627-630`) — uncapped, because `_reviewer_manuscript_text` is literally `return draft_content or ""` (`:350-351`). For a 30k-token manuscript that's ≥120k input tokens for the panel alone, ~95% identical. And a correctly-written compaction helper, `_section_excerpts` (`:316-347`, 1400 chars/section × max 7 sections), is **dead code**.

**Build:**
1. Reorder every reviewer prompt: invariant prefix (calibration block + shared manuscript) first, variable persona block last.
2. Measure `cached_tokens` from the response — requires N0.3.
3. Establish an explicit **token budget** per call, replacing the ~20 scattered ad-hoc truncations (`editor_pass.py:90` `[:1200]`, `reviewer_judge.py:188` `[:500]`, `citation_judge.py:194` `[:6000]`, `analysis_quality_judge.py:97` `_clip(...,5000)`, `draft_analysis_langgraph.py:1390` `[:8000]`, `reviewer_panel.py:494` `[:24000]`).
4. Wire up `_section_excerpts` behind a flag; measure whether critique quality survives via `node_eval.py` severity-weighted recall.
5. Reposition the "search this entire text before claiming anything is missing" instruction (`reviewer_panel.py:391`) — it currently sits immediately *before* 30k tokens, exactly where attention degrades.

**Topics closed:** prompt caching mechanics (cache key = exact token prefix; one early dynamic token zeroes the hit rate); TTLs and breakpoints; the cached-vs-uncached cost model; compaction vs summarization vs offload; building a real context budget; lost-in-the-middle and instruction positioning. **Bridge:** prompt caching ≡ radix prefix caching at a different altitude — build this before your serving layer's radix phase.

**Benchmarks:** cached-token hit rate · % input-cost reduction · $/run before vs after · p50 latency delta · quality delta from compaction.

**Acceptance:** a hit-rate number, a dollar delta, and a one-sentence explanation of why prefix caching is brittle.

---

# TIER 2 — December onward, roughly in this order

## N7 — Hybrid BM25 + RRF, then contextual retrieval (16 h)

Deferred from Tier 1 to make room for the agent harness. Two builds in one because they share the harness and the migration.

**Why.** `hybrid_search` (`rag_retrieval.py:413-502`) fuses `0.7*semantic + 0.3*keyword` (`:417-418`, `:486-489`) — a bounded cosine weighted-summed against an unbounded `ts_rank`. This is the *canonical motivating example for RRF*, sitting in your own repo. Worse, the keyword leg calls an RPC that may never have been deployed, wrapped in a bare `except` (`:382-385`) — so hybrid may have been pure semantic this entire time, invisibly. Separately, `chunk_by_sections` computes `section_title`/`section_type`/`chunk_index_in_section` (`rag_chunking.py:324-330`) and `rag_ingest.py:316-317` throws all of it away (`:347`: *"metadata column removed"*).

**Build:** tsvector + GIN index and a real `keyword_search_chunks` RPC, both checked in · replace the weighted sum with RRF `score = Σ 1/(k + rank_i)`, sweep `k` around 60 · restore the metadata column · three contextual arms: (a) raw chunk, (b) `"{doc_title} — {section_title}: {chunk}"` prepended before embedding, (c) LLM-written 50–100 token situating blurb per chunk, batched with prompt caching on the document prefix · also sweep chunk_size × overlap × {fixed, sentence-aware, section-structural}, with the old splitter as one arm so you can quantify what N0.4 bought · fix the silent no-op in the reranker (`:571-573` returns unranked results on parse failure, uncounted) and the `min_similarity` default of `0.0` (`:581`) that only one caller overrides (`literature_search.py:154`).

**Topics closed:** BM25 internals (`k1` tf saturation, `b` length norm); inverted indexes; score-scale incoherence; rank fusion and what RRF costs you (no post-fusion thresholding, which breaks the `min_similarity` floor at `:610-618`); contextual retrieval and its economics; chunking strategy; bi-encoder vs cross-encoder vs LLM rerank and cascade design.

**Benchmarks:** recall@10 for dense / BM25 / RRF · per-query-type breakdown showing where lexical wins (method names, dataset names, gene symbols) · Δrecall@10 per contextual arm · $/doc ingest per arm · recall vs chunk_size curve · NDCG@10 and p95 across rerank arms.

## N8 — Judge calibration and the matcher threshold study (8 h)

**Why.** Track A is gpt-5.2 judging gpt-5.2 output against **gpt-5.2-written gold**: `judge.py:211-238` bootstraps gold and prints *"Edit it, then rename to `.gold.md` to approve"* (`:236-237`); `draft1`/`draft2` show 534 and 659 diff lines vs bootstrap, but `draft3`–`draft10` are **byte-identical**. The judge sets no temperature and no seed (`judge.py:87-95`). And `match.py:34-36` specifies a calibration study in a code comment — *"30 labeled pairs with agreement >=0.85; update this comment with precision/recall"* — that was never run.

**Build:** swap in a different model family as judge · pairwise with position swap · hand-label 100–200 candidate pairs and calibrate, reporting Cohen's κ · sweep `COS_THRESHOLD` (currently 0.55) and plot precision/recall, choosing the point that matches your cost asymmetry (false merges corrupt recall accounting; false splits inflate it) · measure judge drift across reruns · address the held-out contamination (`heldout/manifest.json` lists 4 papers whose PDFs all come from `corpora/draft4|8|9|10/`, already used by Track A; `check_heldout.py:44-46` guards field distribution but not this).

**Benchmarks:** Cohen's κ vs human labels · position-bias delta · judge drift across reruns · calibrated `COS_THRESHOLD` with its precision/recall curve.

## N9 — Vector precision and quantization (5 h) **ANALOG**

**Why.** The only handle Noesis has on numerics and quantization at all. `vector(1536)` is fp32 ≈ 6 KB/row. `halfvec` halves it; binary quantization with rescoring shrinks it ~32×.

**Build:** three arms — `vector`, `halfvec`, `bit` + rescore — measured on N2's harness. Also reconcile the two-embedding-model problem: retrieval uses `text-embedding-3-large` @1536 (`rag_ingest.py:138,161`) while `draft_task_evidence.py:392,1048` uses `-small`, so `DRAFT_SOURCE_RELEVANCE_MIN=0.42` (`-small`) and `BROAD_FALLBACK_MIN_SIMILARITY=0.45` (`-large`) are **incomparable numbers sitting in the same mental bucket**. Plot score-distribution histograms per model.

**Topics closed:** range vs precision as a real decision; the outlier/scaling problem in a different domain; storage/latency/quality tradeoffs. Say **analog** — this is not fp16 arithmetic in a kernel.

**Benchmarks:** index size · p95 latency · Δrecall@10 per precision arm · per-model score histograms.

## N10 — Reliability and idempotency hardening (6 h)

**Why.** The best distributed-systems handle in the repo. `autoretry_for=(Exception,)`, `countdown=60`, backoff→600 s (`tasks/draft_analysis.py:18-22`) retries the **entire 18-node pipeline** on any exception including non-retryable ones, with **no jitter and no circuit breaker**. `publish_analysis_artifacts` writes 8 tables (`draft_analysis_runs.py:112-204`) and `:27-31` carries a destructive legacy fallback for unapplied migrations. Deploy has no health gate and no rollback — `sleep 10`, a `docker compose ps` whose output is never checked, then an unconditional `✓ Deploy complete` (`ci.yml:151-157`).

**Build:** classify exceptions into retryable/non-retryable · exponential backoff **with jitter** · a circuit breaker on the OpenAI path · make publish idempotent under retry · health-gated deploy with rollback · cache-stampede protection on the embedding cache (7 d TTL, `embedding_cache.py:27`; also note it uses **pickle** at `:70`, a deserialization surface, and `@cache_embeddings` at `:112` plus `clear_embedding_cache` at `:167` have zero callers).

**Topics closed:** timeouts, retries, backoff with jitter, circuit breakers; idempotency and at-least-once vs exactly-once; health checking, graceful draining, failover; cache TTL/invalidation/stampede.

**Benchmarks:** duplicate-run rate under an induced retry storm · failed-deploy detection rate · recovery time · cache hit rate and $ saved.

## N11 — Durable checkpointer, interrupt, resume (8 h)

**Why.** Resume is **dead by construction**. The graph compiles with no checkpointer (`graph.py:549`, bare `workflow.compile()`) and `ainvoke` passes no `config`/`thread_id` (`:653`). The bespoke `PostgresCheckpointSaver` (`checkpoints.py:25-265`) is called twice per run from *outside* the graph (`graph.py:639-645`, `:665-671`) and is a run-status row, not a checkpointer — its payload goes through `minimize_workflow_checkpoint` (`checkpoints.py:88` → `core/privacy.py:84-109`) which drops everything substantive, so `resume_draft_analysis_workflow` raises on purpose (`graph.py:724-727`), and rows are deleted on success anyway (`:673`).

**Build:** a real LangGraph checkpointer with `thread_id` · `interrupt`/resume · resume from mid-graph failure without re-running completed nodes.

**Why it matters beyond Noesis:** this is the substrate for the harness's durable approval gate (Phase B.5) — you cannot hold a human-in-the-loop decision in a process that dies.

**Benchmarks:** resume success rate · tokens and $ saved resuming after an induced mid-graph failure.

## N12 — Injection eval set and defenses (10 h) — *mandatory once harness Phase A ships*

**Why.** Seven sites interpolate untrusted text into prompts with no delimiter, no escaping, no instruction hierarchy: `draft_processing.py:393`, `claim_extraction.py:295` (full manuscript, untruncated), `reviewer_panel.py:391-392`, `:627-630` (a present/absent checklist that manuscript text can simply assert "present" to), `analysis_quality_judge.py:94-96` (**the highest-value target — its output feeds the publish gate at `draft_analysis_langgraph.py:1707`**), `draft_citation_verification.py:161-173` (guessable `--- PAIR i ---` delimiters), `draft_multimodal_parser.py:150` (page **images** — OCR'd instructions in figures are unfiltered). The worst part isn't the user's own manuscript: **third-party abstracts fetched from OpenAlex and Semantic Scholar** enter reviewer and gap prompts, so an attacker who gets a paper indexed controls your prompt content without touching your product. Blast radius is bounded today only because nothing can act — **the harness changes that.**

**Build:** 30-manuscript injection eval set targeting each site · nonce-delimited untrusted spans · an explicit instruction-hierarchy system statement · trust tiering (own draft > fetched third-party text) · output validation extending `draft_evidence_gate.py:35-54`, closing the short-anchor exemption at `:26-27` that lets a 2-word fabricated quote through unchecked · report attack success rate **and** utility regression on N2/N4's metrics.

**Topics closed:** direct vs indirect injection; why structured output is not a defense (schema constrains shape, not semantics — and `retry_utils.py:58-68` feeds the model its own validation error, widening the loop); defense/utility tradeoff.

**Benchmarks:** attack success rate before/after per site · utility regression.

## N13 — Model cascade and distillation sweep (6 h)

**Why.** One principled routing decision already exists — `gpt-5-mini` for the editor pass (`editor_pass.py:94`) and reranker (`rag_retrieval.py:511`), `gpt-5.2-chat-latest` for judgment. Nothing establishes where the cliff is.

**Build:** per node, swap to `gpt-5-mini` and measure quality loss on N2/N4's metrics against $/run from N1. Plot the cliff.

**Topics closed:** model routing and cascades; the fine-tune-vs-RAG-vs-prompting decision framework, answered empirically; distillation reasoning without training data.

**Benchmarks:** $/run and severity-weighted recall per node per model · which nodes tolerate the cheap model.

## N14 — Eval in CI with a real gate (6 h)

**Why.** `.github/workflows/ci.yml` contains **zero** references to `scripts/eval`, `run_eval`, `check_heldout`, or `make eval-*`. The only gate is `pytest tests/` (`:31-38`); `security` is `|| true` (`:82`); frontend is `|| echo`'d to success (`:105,109,112`). Meanwhile the eval gate has been **red since 2026-06-20** — `mean_overall 6.97` against `min_overall: 8.5` (`config.yaml:29-32`, enforced at `run_eval.py:82-125`) — and nobody noticed, because nothing runs it.

**Build:** nightly job on a frozen 10-paper subset with thresholds actually blocking · fix the precision definition first (N2) · make history append (N2) · close the trace→eval loop: `mine_failures.py:296-311` already clusters missed gold units and proposes the responsible node, `node_eval.py` already replays any of 18 nodes from 214 MB of fixtures (`Makefile:16`, `EVAL_STATE_DIR`) — wire one into the other so a low-scoring trace becomes a fixture automatically.

**Topics closed:** the LLMOps feedback loop end to end; regression gating; prompt/pipeline versioning (`pipeline_cache.py:26-66` is already the primitive).

**Benchmarks:** gate pass/fail history (append-only) · failures auto-converted to fixtures per week.

## N15 — Semantic cache with near-miss measurement (3 h, optional)

Only worth building if you measure the **wrong-answer rate on near-miss hits** — that's the entire lesson. You already have the embeddings.

**Benchmarks:** hit rate · near-miss wrong-answer rate.

---

# TIER 3 — deliberately not building

Reasons, not hedges.

1. **Rationalizing the ~40 sprawled thresholds** (0.25/0.42/0.45/0.56/0.65/0.68/0.70/0.72/0.82/0.86 across six files, two embedding models, three incomparable scales). Pure labor. N9 fixes only the two that block measurement.
2. **Fixing all 14 audited bugs.** The four that block learning are scheduled (N0.3 usage, N0.4 splitter, N0.2 DDL, `expand_query`). Leave the WebSocket IDOR (`drafts.py:2304-2310` — *unless* the harness acts on drafts, in which case it moves into scope), the `chrome-extension://.*` CORS wildcard (`security_middleware.py:333`), the orphaned `nodes/reviewer_feedback.py` (506 lines, imported only by tests), the dead `_enrich_feedback_payload_with_anchors` path (`drafts.py:192-220` reads `structure.sections[].content`, which `core/privacy.py:126` pops), and the Reviewer A/B/D naming with no C. Documented-and-unfixed is a fine interview answer on a frozen product.
3. **LoRA fine-tuning in Noesis.** No clean training data (8 of 10 gold records are unedited GPT output), no uncontaminated held-out set, no metric that could demonstrate improvement. You would fine-tune blind.
4. **Rebuilding the eval harness.** The scaffolding is genuinely good — real human ICLR ground truth (61 reviews, 15 papers, validated at `fetch_openreview.py:220-228`), deterministic severity weighting (`atomize_reviews.py:131-137`), a properly built matcher with recursive bisection (`match.py:219-233`), pipeline-version-hashed caching, per-node replay. The *science* is missing, not the code. Fix, don't rewrite.
5. **HyDE / query transformation beyond the 20-minute `expand_query` fix.** `rag_retrieval.py:345-352`: the prompt asks for a JSON array, the code calls `result.get("queries", ...)` on it, `list.get` raises, the bare `except` returns `[query]` — so the documented 4× fan-out (`:441-443`) is a permanent no-op. Fix it so the feature stops being fictional; don't build HyDE.
6. **Draft-side RAG.** `ingest_draft_for_rag` (`draft_rag_integration.py:30`) has **zero callers**, so `draft_chunks` is never populated and the entire draft-aware retrieval branch (`rag_retrieval.py:126-177,215-223,247-269`) is unreachable. Delete or document; don't revive.
7. **Streaming for app-layer TTFT.** Low value here; TTFT is properly learned in your serving layer.

---

# What Noesis deliberately does not teach

Say so plainly in interviews; don't stretch for an analog.

1. Attention internals, GQA/MQA, RoPE, RMSNorm, SwiGLU → inference engine
2. Roofline proper, KV-cache arithmetic, FLOP counting → inference engine
3. GPU execution model, occupancy, coalescing, warp shuffles, tensor cores → inference engine
4. Quantization *arithmetic* (int8/int4 kernels, GPTQ/AWQ/SmoothQuant) → inference engine; N9 is an analog only
5. PagedAttention, chunked prefill, P/D disaggregation → serving layer
6. Continuous batching / iteration-level scheduling → serving layer (Noesis has request-level batching only)
7. Load balancing and prefix-aware routing → serving layer
8. TTFT/TPOT and token-level streaming → serving layer
9. Multi-GPU: TP/PP, NCCL, ring all-reduce, interconnect → **nothing you own.** Separate ~10 h 2-GPU exercise, optional, October+
10. Queueing theory at scale — λ≈3 here. N5 teaches the methodology; the theory needs large λ
11. Sandboxed code execution → harness Phase D, or conceptual
12. Training and post-training → conceptual forever

---

# Benchmark board — the numbers this plan produces

Fill in as they land. This table *is* the resume.

| Metric | Build | Value |
|---|---|---|
| Per-node p50/p95/p99 latency | N1 | |
| Tokens in/out per node | N1 | |
| **$ per analysis run** | N1 | |
| % wall-clock in LLM I/O vs local compute | N1 | |
| Silent-fallback rate (synthetic rating-5 reviewer) | N1 | |
| **Baseline recall@10 / MRR / NDCG@10** | N2 | |
| Miss breakdown by failure mode | N2 | |
| recall@10 vs p95 latency curve over `ef_search` | N3 | |
| Index size / build time | N3 | |
| **Gate FP rate / FN rate / AUC-PR / ECE** | N4 | |
| Thresholds before vs after calibration | N4 | |
| **Goodput vs offered load; p95 under load** | N5 | |
| Queue depth vs λ | N5 | |
| Honest reviewer-parallelism speedup + load model | N5 | |
| **Cached-token hit rate; % input-cost reduction** | N6 | |
| Quality delta from compaction | N6 | |
| Δrecall@10: dense / BM25 / RRF | N7 | |
| Δrecall@10 per contextual arm; $/doc ingest | N7 | |
| recall@10 vs chunk_size curve | N7 | |
| NDCG@10 + p95 across rerank arms | N7 | |
| **Cohen's κ, judge vs human** | N8 | |
| Calibrated `COS_THRESHOLD` + PR curve | N8 | |
| Index size / latency / recall per precision arm | N9 | |
| Duplicate-run rate under retry storm | N10 | |
| Resume success rate; tokens saved | N11 | |
| Attack success rate before/after | N12 | |
| $/run and quality per node per model | N13 | |
| pass^k variance | N1+N6 | |

---

# The resume this produces

Fill the blanks from the board. Every number is generated by a build above.

> - Instrumented an 18-node LLM pipeline with per-node distributed tracing and token attribution; identified `___` as the p95 bottleneck at `___`% of wall-clock and cut cost per analysis from `$___` to `$___` via prompt-prefix restructuring at a `___`% cache hit rate.
> - Built the system's first retrieval evaluation harness (recall@k, MRR, NDCG@10) against `___` human-authored reference lists; raised recall@10 from `___` to `___` through reciprocal-rank fusion of BM25 and dense retrieval plus section-contextualized chunking, and tuned an HNSW index across a measured recall/latency curve.
> - Calibrated a deterministic quality gate against `___` hand-labeled runs, moving thresholds from a-priori guesses to a cost-weighted operating point: `___`% false-positive rate at `___`% recall.
> - Benchmarked the pipeline under open-loop Poisson load, reporting goodput under a stated SLO and identifying the point at which throughput rises while goodput collapses.

---

# Ordering rules that must not be broken

1. **N0.1 before everything.** External deadline.
2. **N0.3 before N1, N6, N13.** No `usage`, no cost metric.
3. **N0.2 before N2, N3, N7, N9, N15.** No database, no retrieval work.
4. **N2 before N3, N7, N9, N15.** Retrieval changes without a ruler are indistinguishable from noise. *"I measured reranking and it didn't help"* is a stronger answer than *"I added reranking."*
5. **N1 before N5, N6.** Percentiles and cache hit rates need spans and usage.
6. **N6 before your serving layer's radix-cache phase.** The prompt-caching intuition transfers directly; building radix caching first wastes the lesson.
7. **N4 is the Docker-independent fallback.** If N0.2 fails, do N4 and N8 while you fight the stack.
8. **N12 becomes mandatory the moment the harness gets tools.** Read-only tools bound the blast radius; a write tool removes that bound.
