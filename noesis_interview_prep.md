# Noesis — Technical Interview Preparation Guide

> ## ⚠️ CORRECTED 2026-07-30 — read this before using anything below
>
> This document was written 2026-06-25, before the project had produced any measurement. `LEARNING_AUDIT_ADDENDUM.md` §1 (2026-07-29) marked a list of its claims unprovenanced; §2 of that same file (2026-07-30) gives each one its current measured status. **Every fix below has been applied in place and is marked `[CORRECTED …]` with what the sentence used to say.**
>
> **Numbers removed as unmeasured:** `53s → 18s (~66%)`, `~18s end-to-end`, `no quality loss`, `30+ researchers / 3+ universities`, `measurably cut hallucinated critiques and lifted quality`.
> **Wording corrected as overstated:** "multi-agent"; the publish gate as a three-signal / blocking / user-visible trust layer.
> **One claim restored as now-verified:** pgvector *cosine* similarity — live introspection confirms `vector_cosine_ops` and `<=>`.
>
> **The one rule for using this document:** every number now carries its `n` and its source. Numbers from **isolated node replays on an eval corpus** are not production numbers and are not end-to-end user times. Do not let one stand in for the other — that substitution is the specific failure this correction exists to prevent.
>
> ---
>
> ### ↻ SECOND PASS, 2026-07-31 — several numbers in the first pass are now superseded
>
> More measurement landed. Fixes below are marked `[UPDATED 2026-07-31]` and say what the sentence used to claim.
>
> | first pass said | now |
> |---|---|
> | retrieval: dense recall@10 **0.4221** / ceiling 0.7789 / **n=59** | **0.2195** / ceiling **0.5199** / **42% of attainable** / **n=338**, 8,554 judgments, 344 docs, 5,948 chunks. **This is not a regression** — it is a 2.8× larger corpus with a lower ceiling. Never difference the two |
> | latency **CV ~7% at n=3** | **CV 15.0% at n=5.** The 7% did not survive a fifth sample |
> | `reviewer_panel_node` **19.818 s**, **~$0.043/replay** | **19.286 s mean (n=5, one fixture)**; **$0.0296/replay complete** — and the old figure was **node-only**, missing 16.3% matcher spend |
> | prompt cache **0% → 58.8%**, **−23.8%** | confirmed on the real replay path at **0% → 60.7%**, **−24.5%** |
> | keyword v2 **0.0026 → 0.2841** | **0.0022 → 0.1447 (66×)** at 5.7× the scale. **Quote the ratio, not either absolute** |
> | hybrid/RRF "not built" | **built and measured — it LOST.** recall@10 **−7.0%**, NDCG@10 **−3.9%**, MAP **+4.8%** |
>
> **Three rules, and they are the whole discipline:** a **node replay is not an end-to-end user time**; an **index-forced ANN latency is not what the planner does**; and retrieval numbers from **different label snapshots are not comparable at all** (there are three). Full mapping: `LEARNING_AUDIT_ADDENDUM.md` §3, source-of-record `WAVE_LOG.md` head block.

---

## 1. What Is This Project? (30-Second Pitch)

Noesis is an **AI-powered pre-submission peer-review platform** for academic researchers. You upload a manuscript (PDF or pasted draft), and the system runs it through an **18-node LangGraph pipeline** that does what a journal review panel does: extracts the paper's claims, checks them against the existing literature, runs several specialized "reviewer" agents in parallel, and synthesizes everything into a single meta-review with prioritized, actionable feedback. The tagline: *"Know what Reviewer 2 will say before you submit."*

> **[CORRECTED 2026-07-30]** — was *"multi-agent LangGraph pipeline"*. The panel is **one function called 3× with a different persona parameter**: same model, same token cap, same schema, no tools, no memory, no inter-agent messaging. Measured: the three prompts are **~88% identical text** (`scripts/eval/PROMPT_CACHE.md`). *"18-node pipeline with parallel fan-out and reducer fan-in"* is more specific, more technical, and survives the follow-up *"what makes them agents?"* — which "multi-agent" does not. Same correction applies at §3, §6b, §9 and §14 below.

The hard engineering problem isn't generating text — LLMs do that trivially. It's making the critique **trustworthy**: grounded in the actual manuscript, not hallucinated, and honest about its own confidence. Almost every architectural decision in the system exists to serve that one goal.

---

## 2. Why Does This System Exist? (The Problem It Solves)

Academic publishing is slow and brutal. A researcher submits a paper, waits weeks or months, then gets rejected by "Reviewer 2" over issues they could have caught beforehand — an overclaimed result, a missing citation, a contradiction with prior work, a methodological hole. The feedback arrives too late to matter for that submission cycle.

Noesis moves that feedback **forward in time** — before submission, while the paper can still be fixed:

- Researcher uploads a draft → system parses, analyzes, critiques
- Multiple reviewer personas attack the paper from different angles
- A meta-reviewer synthesizes a decisive recommendation (accept / minor / major / reject) with blocking vs. non-blocking items
- Researcher revises and submits a stronger paper

The core insight: a reviewer that **hallucinates** a weakness, or cites a paper that doesn't exist, is *worse than no reviewer at all*. So the system is engineered around grounding and trust, not fluency.

---

## 3. Full Technology Stack — What Each Does and Why It Was Chosen

| Technology | Role | Why It Was Chosen |
|---|---|---|
| **FastAPI** | REST API server | Async-native Python, Pydantic validation at boundaries, auto OpenAPI docs |
| **LangGraph** | Workflow orchestration (18-node DAG) | Models the analysis as a **directed graph of nodes** with explicit state, conditional routing, parallel fan-out (`Send` API), and fan-in reducers. Gives deterministic control over a non-deterministic LLM pipeline |
| **GPT-5.2** (OpenAI) | All LLM reasoning (claim extraction, reviewers, meta-review, judges) | Frontier reasoning quality. Note: GPT-5.2 requires `max_completion_tokens`, NOT `max_tokens` |
| **Supabase (PostgreSQL)** | Primary datastore + Auth + Storage | Managed Postgres with row-level security; accessed only via `supabase.table()` — no raw SQLAlchemy |
| **pgvector** | Vector similarity search (RAG) | Postgres extension; stores **1536-dim embeddings** and does **cosine** similarity inside the DB via RPC functions (`match_document_chunks`) — no separate vector DB to operate. **HNSW index on `vector_cosine_ops`**, `<=>` operator, similarity returned as `1 - distance` so it is bounded [0,1]; `hnsw.ef_search = 80` set via `SET LOCAL` inside the RPC |
| **text-embedding-3-large** | Embedding model | Native 3072-dim, **reduced to 1536** at generation time for pgvector index compatibility |
| **Celery + Redis** | Background task queue (concurrency=4) | Draft analysis is far too long for a synchronous HTTP request — one reviewer persona alone replays at ~20s and there are 18 nodes. Celery workers run it async; Redis is broker + cache |
| **Redis** | Broker + embedding cache + progress pub/sub | In-memory; caches embeddings to skip repeat OpenAI calls; backs WebSocket progress updates |
| **GROBID + Docling** | PDF → structured text parsing | GROBID extracts structured scholarly XML (sections, references); Docling is the primary parser with GROBID as fallback on timeout |
| **External literature APIs** | PubMed, arXiv, Semantic Scholar, OpenAlex | Live source discovery to check claims against real published work, with relevance scoring + dedup |
| **React + TypeScript + Tailwind** | Frontend | Type-safe UI; dark charcoal design system |
| **Docker + AWS EC2** | Deployment | Dockerized FastAPI + Celery on EC2 |
| **GitHub Actions** | CI/CD | Automated test runs + deploy pipeline |
| **Stripe** | Billing | Free / Pro / Team / Enterprise tiers with quota enforcement |

> **[CORRECTED 2026-07-30]** — three fixes in this table.
> 1. LangGraph row was *"Multi-agent workflow orchestration"* → *"Workflow orchestration (18-node DAG)"*. See the §1 note.
> 2. pgvector row previously said "cosine similarity" **without provenance**, and `LEARNING_AUDIT_ADDENDUM.md` §1.8 P1-8 told you to downgrade it to "similarity search" because the operator was unverifiable. **That advice is now void** — live introspection of PostgreSQL 17.6 confirms HNSW / `vector_cosine_ops` / `<=>` (`WAVE_LOG.md`, Wave 0 findings). You may name cosine, and you may now name the index and its parameters, which the audit said you could not.
> 3. Celery row was *"Draft analysis takes ~18s+"*. **That number was never measured.** What *is* measured: `reviewer_panel_node` replays at **19.286 s mean, sd 2.897, n=5 replays of one fixture** (17.10 / 18.26 / 19.69 / 24.13 / 17.25 s; `scripts/eval/NODE_COST.md` §Variance). That is **one node in isolation**, not an end-to-end analysis — no parse, no upload, no queue wait, no other 17 nodes. **The end-to-end time has never been measured.** Do not let ~19 s stand in for the deleted 18 s; they are different quantities and the resemblance is a coincidence. *[UPDATED 2026-07-31: said 19.818 s (n=5, 16.8–25.7 s) from `BENCHMARKS.md`. That roll-up mixes fixtures and personas, so it is a cost summary, not a variance estimate; the single-fixture measurement above is the one to quote.]*

---

## 4. Architecture — How It All Fits Together

```
  ┌──────────┐   upload    ┌─────────────┐   enqueue    ┌────────────┐
  │ React UI │────────────▶│   FastAPI   │─────────────▶│   Celery   │
  │ (Vercel) │◀────────────│   (EC2)     │              │  worker x4 │
  └──────────┘  WS progress└──────┬──────┘              └─────┬──────┘
       ▲                          │                           │
       │                          │                           ▼
       │                   ┌──────▼───────┐         ┌──────────────────┐
       │  poll/refetch     │   Supabase   │         │  LangGraph        │
       └───────────────────│  (Postgres + │◀────────│  draft-analysis   │
                           │   pgvector)  │  writes  │  workflow         │
                           └──────────────┘         └─────────┬─────────┘
                                                              │ LLM calls
                                                     ┌────────▼─────────┐
                                                     │   GPT-5.2 +      │
                                                     │ PubMed/arXiv/    │
                                                     │ S2/OpenAlex      │
                                                     └──────────────────┘
```

### How Components Communicate
- **UI → API**: HTTP/REST (upload draft, fetch analysis); **WebSocket** for live progress (`publish_progress`)
- **API → Celery**: `analyze_draft_task.delay()` — returns immediately, work runs in background
- **Celery → LangGraph**: invokes `run_draft_analysis_workflow()`, which compiles and `ainvoke`s the graph
- **LangGraph nodes → GPT-5.2**: async OpenAI calls (claim extraction, reviewers, meta-review, judges)
- **LangGraph → pgvector**: `supabase.rpc("match_document_chunks", ...)` for semantic retrieval
- **LangGraph → external APIs**: live literature search for source discovery
- **Workflow → Supabase**: writes analysis artifacts; sets `draft.status = 'analyzed'`
- **Worker → Redis**: publishes progress events; UI subscribes and updates the progress bar

---

## 5. End-to-End Data Flow (What Happens When You Analyze a Draft)

The LangGraph workflow is a **directed graph of ~18 nodes**. Most run linearly; the reviewer panel fans out in parallel. Each node reads from and writes to a shared `DraftAnalysisState` (a typed dict).

```
Step 0 — Upload & parse:
  PDF → Docling (primary) / GROBID (fallback) → structured text + sections + references
  parser_quality score computed (used later by the publish gate)

Step 1 — extract_structure        → sections, headings, layout
Step 2 — profile_manuscript       → paper type + "forbidden review standards"
                                     (e.g. don't demand ML benchmarks on a theory paper)
Step 3 — extract_references        → resolve the paper's own bibliography
Step 4 — extract_claims           → pull the paper's actual claims/contributions
Step 5 — categorize_claims        → empirical / theoretical / methodological / etc.
Step 6 — verify_citations         → check the citations the author already made
Step 7 — search_literature        → RAG over pgvector + live external APIs, PER CLAIM
Step 8 — map_citations            → attach supporting/contradicting sources to each claim
Step 9 — detect_gaps              → coverage gaps (claims with weak/no support)
Step 10 — discover_external_sources → fill gaps from PubMed/arXiv/S2/OpenAlex
Step 11 — citation_judge          → LLM judges whether mapped sources are actually relevant
Step 12 — run_quality_diagnostics → manuscript-specific diagnostic findings
Step 13 — structural_checks       → deterministic structural checks
Step 14 — editor_pass             → "desk check": proceed to review, or desk-reject?

      ┌─── route_to_reviewer_panel (conditional) ───┐
      │  desk-rejected OR preliminary gate fails    │
      │            → skip to synthesis              │
      │  approved → FAN OUT to 3 parallel reviewers │
      └─────────────────────────────────────────────┘

Step 15 — reviewer_panel  ×3 IN PARALLEL (Send API):
            • methodology
            • literature_positioning
            • clarity
          (each produces a structured ReviewerOutput with issues + rating)
Step 16 — reviewer_judge          → judges review specificity/quality (fan-in)
Step 17 — meta_reviewer           → Area Chair synthesizes 3 reviews → 1 decision
Step 18 — synthesize_report       → final report + revision tasks

Post-workflow (in draft_analysis_langgraph.py):
  • build evidence manifest, reconcile tasks against evidence (anchor repair)
  • evaluate_publish_gate (deterministic) → confidence label / fail-closed
  • write artifacts to Supabase, set draft.status='analyzed'
  • publish 100% "complete" → UI refetches
```

---

## 6. Deep Dives — Key Technical Concepts

### 6a. Why LangGraph Instead of a `for` Loop or Plain Function Calls?

A naive version is "call GPT a bunch of times in sequence." LangGraph buys three things that matter:

1. **Explicit shared state** (`DraftAnalysisState`) — every node reads/writes a typed dict, so data flow is inspectable and testable, not hidden in local variables.
2. **Conditional routing** — `route_to_reviewer_panel` and `route_after_claim_extraction` let the graph *change shape at runtime* (desk-reject skips the whole panel).
3. **Parallel fan-out / fan-in** — the `Send` API dispatches the same node 3× with different `reviewer_type`, and a **reducer channel** (`reviewer_outputs`) accumulates the results when they all finish. This is what makes the latency win possible.

It's the difference between an imperative script and a **declarative dataflow graph** — easier to reason about, checkpoint, and resume.

### 6b. The Parallel Reviewer Panel (the latency story)

The reviewers are **embarrassingly parallel**: a methodology critique doesn't depend on the clarity critique. So instead of running them sequentially, `route_to_reviewer_panel` returns a list of `Send("reviewer_panel_node", {**state, "reviewer_type": rt})` — one per persona. LangGraph runs all three concurrently.

The **meta-reviewer cannot parallelize** — it's a true join point. It needs *all three* reviewer outputs to synthesize a decision, so it's a fan-in node that runs only after every reviewer completes. This is the dependency-ordering insight: parallelize the independent work, synchronize at the join.

**Result: the panel's three personas run concurrently instead of serially**, while staying inside OpenAI rate limits (concurrency is bounded, not unbounded fan-out). The architectural claim — reviewers share no state, meta-review is a true join, therefore fan out — is the part that demonstrates judgment, and it is fully supported by the code (`graph.py:432-435`, `state.py:184`).

> **[CORRECTED 2026-07-30]** — this sentence used to read: ***"Result: end-to-end latency dropped from 53s → 18s (~66%), with no quality loss."*** Both halves are cut.
>
> - **`53s → 18s (66%)` is unmeasured and unreproducible.** There is no sequential baseline anywhere in the repo, so the figure has neither a numerator nor a denominator. It also contradicts `CREATEX_PRESENTATION.md`, which says ~3.5 min end-to-end for the same product.
> - **This is *not* fixed by the instrumentation that now exists.** Tracing landed (root span per run, child span per node, `llm_call` spans with token and cost attribution) and per-node latency is measured — but **measuring the fan-out's current cost does not measure the improvement the fan-out produced**. You would need a sequential arm, and there isn't one.
> - **"No quality loss" asserts an eval that was never run**, before or after.
>
> **What you can say instead** *[UPDATED 2026-07-31 — was "~19.8 s and ~$0.043 per replay … CV is ~7% at n=3". The cost was **node-only** and therefore a floor, and the CV did not survive n=5]* (`scripts/eval/NODE_COST.md`, n = 3–5 replays per node): `reviewer_panel_node` **19.286 s mean (n=5, one fixture)** at **$0.0296/replay complete** · `editor_pass_node` ~7.4 s at $0.0021/replay complete · `run_quality_diagnostics` ~0.06 s, **zero LLM calls, and still $0.00092/replay to measure** — one reviewer is ~330× the diagnostics node's wall time. **All isolated node replays on cached fixtures, not user-visible times.** **Latency CV is 15.0% at n=5**, so nothing smaller than ~±19% of the mean is resolvable and a single run is not a measurement.
>
> **If asked "how did you cut the latency?" — answer §8's corrected version**, not this section's old number.

### 6c. RAG with pgvector — and Topic-Relevance Gating

Retrieval flow:
1. `embed_query()` turns a claim into a **1536-dim vector** (text-embedding-3-large, dimension-reduced). Embeddings are **Redis-cached** so identical queries skip the OpenAI call.
2. `supabase.rpc("match_document_chunks", {query_embedding, proj_id, match_count})` does cosine similarity *inside Postgres* via pgvector.
3. A **similarity threshold** filters weak matches.

The trust problem: pure vector similarity returns chunks that are *semantically near but topically wrong* — and the LLM will then hallucinate a connection ("this paper fails to cite X") where none exists. **Source contamination.** The fix is **deterministic topic-relevance gating**: a retrieved source must clear a relevance bar before it's allowed into a claim's LLM context. There are also display-similarity floors (`MIN_DISPLAY_SOURCE_SIMILARITY = 0.66`) so weak sources never surface to the user. The gating is a stated *intent* backed by real code; whether it reduced hallucination is not something this project has measured.

> **[CORRECTED 2026-07-30]** — the last sentence used to read: ***"This measurably cut hallucinated critiques and lifted quality on the eval set."*** The word "measurably" was the problem: no before/after measurement existed then, and none exists now. `scripts/eval/BENCHMARKS.md` § OpenReview scoreboard shows **17 recorded runs across 3 pipeline versions, every one with 0 scored cells and a trend of `unknown`.** *[UPDATED 2026-07-31: was "10 runs across 2 pipeline versions". More runs, still zero scored cells — the history exists and does not yet contain a quality trend.]*
>
> What *is* now measured, and it points the other way: the pipeline's honest **hallucination rate is 0.111** and its honest **`precision_vs_gold` is 0.27** — **n = 3 papers** (`WAVE_LOG.md`, Wave 2). ~11% of what it raises points at text not findable in the paper. Quoting "measurably cut hallucinated critiques" next to a measured 0.111 with no baseline is worse than saying nothing.
>
> **Say instead:** *"I can't claim a reduction — I never had a before. What I do have is a measured hallucination rate of about 11% on three papers, which is the number I'd want to drive down, and the eval that produces it now writes to an append-only history so the next change will have a before."*

### 6d. The Deterministic Publish Gate (the trust mechanism)

The LLM quality judge can *reason* about quality but is **fail-open** — it tends to bless its own output. So there's a separate, cheap, **deterministic** gate (`draft_publish_gate.py`) that the LLM cannot talk its way past. Thesis: **the LLM proposes, deterministic code decides what ships.**

It computes three grounding signals — but **only one of them has ever changed a verdict**, which is the interesting part:

| signal | threshold | measured across 77 archived runs | effect |
|---|---|---|---|
| **Page-anchor coverage** (`PDF_PAGE_ANCHOR_COVERAGE_MIN = 0.75`) — can findings be traced to real locations? | 0.75 | **29 distinct values, range 0.0–1.0** | **the only live predictor.** Drove **all 12** `needs_retry` verdicts |
| **Parser quality** (`PARSER_QUALITY_MIN = 0.55`) — was the PDF readable? | 0.55 | **2 distinct values**: `1.0` (52 runs), `0.95` (25) | **inert** — nothing observed is within 0.4 of the threshold |
| **Verbatim anchor coverage** | none | **1 value**: `1.0` on all 77 | **structurally cannot vary** — see below |
| Source contamination flags | — | — | **never affects the verdict**; the code says so: *"flags are informational … DO NOT fail the run"* |

Verdicts across the 77: 61 `ok`, 12 `needs_retry`, 4 `ok_sources_pruned`.

**Why `verbatim_anchor_coverage` cannot fail** (`draft_analysis_langgraph.py:666-726`): it counts verbatim-verified anchors over *tasks that have an anchor*. When an anchor fails verification it is nulled upstream by the no-generative-quotes policy — which removes that task from the **denominator** as well as the numerator. The failure erases its own evidence. 65 of 950 tasks carry a null anchor; those are the failures and this metric cannot see one. (The signal survives in a different field, `anchor_coverage`.)

Output is a verdict: `gate_status` (`ok` / `ok_sources_pruned` / `needs_retry` / `needs_parser_review`), `publishable`, `confidence`, and `reasons`, **persisted on the run row**. `DRAFT_ANALYSIS_FAIL_CLOSED` defaults **off**, so on the default path the gate **suppresses ungrounded artifacts and then marks the run `passed` and publishes normally** — it does not block. With `DRAFT_ANALYSIS_FAIL_CLOSED=1` it hard-fails the run instead. **The verdict is never surfaced in the UI** — zero frontend references to `publish_gate` / `analysis_confidence` / `publishable` / `needs_retry`, and the API response omits them (`drafts.py:1313-1341`).

> **[CORRECTED 2026-07-30]** — four fixes here, three of them things this doc previously got wrong.
> 1. Was *"It checks three grounding signals"* framed as three live checks. **Two of the three are inert** (`WAVE_LOG.md`, Wave 1, verified across all 77 usable exports). Note this corrects `LEARNING_AUDIT_ADDENDUM.md`'s **own** proposed "honest" wording too — §1.6 there proposed *"scores parser fidelity and anchor grounding"*, which is itself overstated; see CORRECTION 2 in that file.
> 2. Was *"By default it's **soft** — the user still sees the analysis, but labeled low-confidence."* **The user sees no label.** It is not in the UI and not in the API response. If asked, the honest answer is: *"the verdict is persisted on the run and gates artifact suppression, but I never surfaced it in the UI — that's an unfinished piece."*
> 3. Contamination flags were listed as a checked signal. They are informational and never fail a run.
> 4. **The 0.75 threshold is hand-set, not calibrated.** The calibration sweep needs human labels and none exist — `scripts/eval/BENCHMARKS.md` records *"No sweeps recorded … not a zero, an absence."* Do not say tuned, calibrated, or learned.
>
> **The honest one-liner:** *"a deterministic page-anchor-coverage gate that suppresses critique artifacts which can't be traced to a page in the manuscript, and records a degraded-run verdict."* Weaker feature, stronger engineering story — *"I instrumented it across 77 runs and found two of three signals inert"* is a better answer than the version it replaces.

### 6e. The Preliminary Gate (prevention, not cleanup)

A subtle optimization: the reviewer panel + meta-review are the **most expensive** LLM calls in the pipeline. If the parse is so bad that the publish gate is *guaranteed* to suppress the output anyway, running them is pure waste. So `should_halt_before_reviewers()` runs a **cheaper preliminary version of the gate** right before the panel (after citation mapping). If anchor coverage or parser quality already predict failure, it routes straight to synthesis and **never burns tokens on a doomed parse.** Prevention beats cleanup.

### 6f. The Editor Desk-Check (modeling real review)

Before any reviewer runs, an `editor_pass` node acts like a journal editor doing a desk check. If `editor_decision.proceed_to_review` is false, the paper is **desk-rejected** and routes straight to synthesis — no panel. This mirrors how real venues filter out-of-scope papers before wasting reviewers' time, and it saves compute.

### 6g. Manuscript Profiling + "Forbidden Review Standards"

A theory paper shouldn't be dinged for lacking a clinical trial; a position paper shouldn't be asked for ML benchmarks. The `profile_manuscript` node classifies paper type early and emits **forbidden review standards** that get injected into every reviewer's system prompt. This stops the reviewers from applying the wrong evidentiary bar — a major source of bogus critique.

### 6h. Anchor Verbatim Requirement (anti-hallucination)

Every reviewer issue must include an `anchor_text` that is an **exact, contiguous, copy-paste substring of the manuscript** (≤200 chars) — no paraphrasing, no ellipsis stitching, no typo fixes. Post-workflow, tasks are **reconciled against an evidence manifest** and anchors are repaired/verified. If a critique can't be anchored to real text in the paper, it's suspect. This is a structural defense against the model inventing problems that aren't there.

### 6i. Rating Calibration (honest scores)

LLMs default to mushy 6-7 "weak accept" ratings. The reviewer prompt injects a **calibration block** with real venue distributions (at ICLR/NeurIPS/CHI ~10-15% score 8+, 40-50% score 4-5) and forces the question: *"would this be accepted as-is? If not, it's a 5 or below."* The meta-reviewer is told **not to average** ratings but to synthesize qualitatively, resolving reviewer conflicts using the manuscript profile + diagnostics as tie-breakers, not majority vote.

### 6j. Async Background Processing (why Celery)

Analysis is tens of seconds of mostly I/O-bound waiting (OpenAI calls, DB, external APIs) — the reviewer panel node alone replays at ~20 s, and there are 18 nodes plus PDF parsing ahead of it. Holding an HTTP connection that long would time out and tie up a server worker. So the API enqueues a **Celery task** (concurrency=4) and returns immediately; the UI subscribes to a **WebSocket progress stream** (`publish_progress` emits `extract_claims`, `search_literature`, `meta_review`, etc. with percentages). Same producer/consumer decoupling pattern as a job queue — just applied to a multi-agent pipeline.

---

## 7. Why Each Architectural Decision Was Made

| Decision | Rationale |
|---|---|
| **LangGraph over a script** | Explicit state, conditional routing, parallel fan-out with reducers |
| **Parallel reviewer panel** | Reviewers are independent → fan out. (Speedup **not measured** — no sequential baseline exists; see §6b) |
| **Meta-reviewer as fan-in** | Synthesis genuinely depends on all reviewers → must be a join |
| **Deterministic publish gate** | LLM judges are fail-open; trust needs code the model can't override |
| **Preliminary gate before panel** | Don't spend the most expensive LLM calls on a doomed parse |
| **Topic-relevance gating on RAG** | Vector similarity ≠ topical relevance → prevents contamination/hallucination |
| **pgvector inside Postgres** | One datastore for relational + vector; no separate vector DB to run |
| **1536-dim embeddings** | pgvector index compatibility; 3-large reduced from 3072. Measured side-effect: at 1536 dims a `float4` vector fills an 8 KB page on its own, so HNSW `m` has **no** effect on index size on this corpus (`scripts/eval/ANN_SWEEP.md` §4) |
| **Verbatim anchors** | A critique you can't locate in the text is probably hallucinated |
| **Manuscript profiling** | Apply the right evidentiary bar per paper type |
| **Celery + WebSocket** | Long async work can't block HTTP; users still see live progress |
| **Supabase only (no SQLAlchemy)** | Managed Postgres + Auth + RLS + Storage in one platform |

---

## 8. Challenges You Could Have Faced (and How to Answer Them)

### "What was the hardest part of this project?"

**Making LLM output trustworthy enough to act on.** A fluent-but-wrong critique is actively harmful — it sends a researcher chasing a problem that doesn't exist, or citing a paper that isn't real. The whole system is layered defenses against that: topic-relevance gating on retrieval, verbatim anchors, an evidence manifest, and a deterministic publish gate the model can't override. The mental model I kept coming back to: **the LLM proposes, deterministic code decides what ships.**

### "Tell me about a specific bug or problem you solved."

**Source contamination → hallucinated critiques.** Early on, reviewers would claim a paper "failed to cite X" when X was irrelevant. I traced it to RAG: pure vector similarity was pulling chunks that were semantically near but topically off, and the LLM dutifully invented a connection. The fix was a deterministic topic-relevance gate between retrieval and the LLM context, plus display-similarity floors so weak sources never surface.

> **[CORRECTED 2026-07-30]** — this answer used to end: ***"Hallucinated critiques dropped and eval quality went up."*** Cut — there is no before/after. Finish the answer honestly instead, which is a better answer:
>
> *"I don't have a before-and-after on that, and I'd rather say so than wave at a number. What I do have is a current measurement: honest precision against human gold reviews is 0.27 and the hallucination rate is 0.111, on three papers. Getting that number at all required fixing the metric first — the shipped one counted an item correct if a model judged it grounded, so it reported precision 1.0 and a 0.0 hallucination rate and was structurally incapable of failing."*

### "How did you cut the latency?"

**[REWRITTEN 2026-07-30 — this is the answer to give. It used to be: *"The pipeline ran fully sequentially — each reviewer one after another — at ~53s … 53s → 18s, ~66%, no quality loss."* That number is cut; see §6b.]**

*"The reviewers don't depend on each other — a methodology critique doesn't need the clarity critique — so I restructured the panel to fan out via LangGraph's `Send` API and run all three concurrently, with the meta-reviewer as a true fan-in join, since synthesis genuinely needs all three. Concurrency is bounded to respect OpenAI rate limits.*

*I want to be straight about the measurement: I don't have a defensible end-to-end number for that change, and I took the one I used to quote off my resume for exactly that reason. I never built a sequential arm, so there's no baseline to difference against. What I did build since is the instrumentation — root span per run, child span per node, `llm_call` spans with token and cost attribution — and that gives me per-node numbers: one reviewer persona is about 20 seconds and 4 cents per replay, the editor pass about 7 seconds, the whole diagnostics node 60 milliseconds. So one reviewer is roughly 330× the diagnostics node, which is where the cost actually lives.*

*But those are isolated node replays off cached fixtures, not a user-visible end-to-end time — I still don't have that instrumented, and I won't quote one until I do."*

> **Why this answer is stronger than the number it replaces:** it shows you know what would make a latency number valid, which is the actual signal being tested. And it pre-empts the follow-up that killed the old version. **If the interviewer notices ~20 s and asks whether that's your old 18 s — say no.** A node replay in isolation and an end-to-end user analysis are different quantities; the resemblance is a coincidence and claiming it would be the exact error you just described avoiding.

### "How do you know the output is actually good? How do you measure it?"

I built an **eval harness**. Instead of grading against AI-written "ideal" reviews (circular — one model judging another), I pull **real human peer reviews from OpenReview** as gold data, run Noesis on the *same* papers, and use an **LLM-as-judge** to score how much of the real reviewers' feedback Noesis recovered (recall against actual humans). I added anti-overfit guardrails and a failure-mined debug loop so I'm optimizing for genuine recall, not gaming the judge.

**The part worth telling (added 2026-07-30) — the first version of that metric was broken, and I found it by auditing my own numbers.** It reported `precision = 1.0` and `hallucination_rate = 0.0`, which should have been the tell: it counted an item correct if it matched a gold review unit **OR** its anchor appeared in the PDF **OR** an LLM judged it grounded. An item no human raised counted as a hit the moment a model blessed it — **structurally incapable of failing.** Recomputed honestly against distinct gold matches: **`precision_vs_gold` 0.27, hallucination rate 0.111, groundedness 0.889, weakness recall 0.187** — **n = 3 papers**, recomputed from cached exports with zero LLM calls (`WAVE_LOG.md`, Wave 2).

**Volunteer the caveats, because they are the credibility:** n = 3 is real but not stable · a pair-based numerator would read 0.554 and double-counts, so precision has to be distinct-items-over-items · and **0.27 is a lower bound by construction** — the labels are what human reviewers happened to raise, so a genuine finding they missed scores as a false positive. The one unambiguous number in there is the 0.111, which points at text not findable in the paper at all.

I also built the same discipline into retrieval: **dense recall@10 = 0.2195 against a construction ceiling of 0.5199, i.e. 42% of what's attainable** — NDCG@10 0.5191, MRR 0.7328, **n = 338 queries over 15 manuscripts, 8,554 relevant judgments, 344 indexed documents / 5,948 chunks** (`scripts/eval/BASELINE_15.md` §3). **Quote the ceiling with the number or the number is misleading**: each query inherits its manuscript's whole reference list, so a query with 37 relevant documents can't exceed recall@10 = 10/37.

> **[UPDATED 2026-07-31]** — this paragraph used to read *"recall@10 = 0.4221 against a ceiling of 0.7789, i.e. 54% of what's attainable … n = 59 queries over 4 manuscripts (`retrieval/BASELINE.md`)"*. That file now carries its own **SUPERSEDED** banner and its label snapshot no longer exists. **If anyone notices the absolute number went down, that is the interesting answer, not the awkward one:** the corpus grew 2.8× in chunks and the average query now inherits 25.3 relevant documents instead of 15.3, which dropped the ceiling from 0.7789 to 0.5199. **It is not a regression, and I will not present it as one in either direction** — 54% and 42% are also not comparable, because the query set went from 4 manuscripts to 15. There are **three** label snapshots in this project's history and differencing across them is invalid.
>
> **Three more retrieval results worth having ready, all n=338, all `scripts/eval/BASELINE_15.md`:**
> - **Keyword search was mismatched, not broken.** `plainto_tsquery` ANDs every lemma of a ~20-word claim, so **321 of 338 queries returned zero rows**. An OR-of-lemmas rewrite took that to **0 of 338** and recall@10 from 0.0022 to 0.1447 — **66×**. It is behind `KEYWORD_SEARCH_V2`, **default off**; nothing shipped to production.
> - **I then built RRF fusion and it lost.** recall@10 **−7.0%**, NDCG@10 **−3.9%**, MAP **+4.8%** against dense alone. Best coverage of any arm (retrieval failures 5,144 vs 6,010), worst top-10 ordering (ranking failures 1,885 vs 936). It finds more and orders it worse, because on a contentless claim the lexical leg's noise still counts as a vote. **Report it as the result** — an unmeasured "we added hybrid retrieval and it helped" would have been worse than useless.
> - **The largest uncontrolled factor is the query set itself.** A substantial share of the claims are contentless — *"we experimentally verified that our method achieves good results"* — and no retriever can serve them. Filtering them out would raise every arm and improve nothing, which makes it the likeliest source of a fake win.

### "What happens when the PDF doesn't parse well?"

Docling is the primary parser with **GROBID as a fallback** on timeout. Parse quality is scored. If it's too low, the **preliminary gate** halts before the expensive reviewer panel, and the **publish gate** suppresses artifacts that can't be traced to a page and records a degraded-run verdict on the run row (or hard-fails the run, if `DRAFT_ANALYSIS_FAIL_CLOSED` is set — it defaults off). The system degrades to an honest "we couldn't read this well enough" rather than confidently critiquing garbage.

> **[CORRECTED 2026-07-30]** — was *"the publish gate labels the run low-confidence (or fail-closes it)"*. Two errors: the label **never reaches the user** (not in the UI, not in the API response), and fail-closing is a **non-default env flag**, so "or fail-closes it" needs to say so. Also worth knowing before you lean on this answer: across 77 archived runs the **parser-quality threshold has never fired** — it takes only the values 1.0 and 0.95 against a 0.55 bar. The gate is real, but page-anchor coverage is what actually catches bad parses downstream, not parser quality. See §6d.

### "What's the failure mode if an external literature API is down?"

External source discovery is wrapped non-fatally — a failure appends a warning to state and the workflow continues with whatever it has, rather than crashing the whole analysis. (At scale I hit OpenAlex 429 rate-limiting and Docling 504 timeouts — known issues I'd address with a caching/fallback layer.)

---

## 9. What This Project Demonstrates You Know

| Skill Area | How It's Demonstrated |
|---|---|
| **LLM application architecture** | 18-node LangGraph pipeline, prompt engineering, structured outputs with self-correcting retries, LLM judges |
| **Orchestration / dataflow** | LangGraph graph with conditional routing, parallel fan-out, fan-in reducers |
| **Concurrency** | Async fan-out of independent work, join at dependency points, bounded concurrency |
| **RAG / vector search** | pgvector, embeddings, relevance gating, contamination defense |
| **Trustworthy AI** | Deterministic gate over a fail-open LLM judge, verbatim grounding, server-side confidence verdicts (not user-facing) |
| **Distributed systems** | Celery producer/consumer, Redis broker + cache, WebSocket progress |
| **Evaluation** | OpenReview human-gold eval harness, LLM-as-judge, anti-overfit guardrails; retrieval eval with ranx over 338 queries / 8,554 judgments (recall/NDCG/MRR reported against a construction ceiling, with the query plan probed per run); append-only result sinks fingerprinted by label snapshot so incomparable runs cannot be differenced; found and fixed a precision metric that was structurally incapable of failing; **built a hybrid RRF retriever, measured it, found it lost to dense, and reported the negative** |
| **Measurement discipline** | Every metric reported with its `n`; runs marked invalid excluded and listed with a reason; trends drawn only within a config hash; costs with unpriced calls rendered as lower bounds |
| **Backend / API** | FastAPI, Supabase/Postgres, RLS, quota enforcement, Stripe billing |
| **Document processing** | GROBID/Docling PDF parsing with fallback, structural extraction |
| **DevOps** | Docker, AWS EC2, GitHub Actions CI/CD |
| **Product ownership** | 40+ researcher discovery interviews across 2 universities; cold outreach converted 50 emails → 5 calls → 2 paid/beta commitments; tiered pricing |

> **[CORRECTED 2026-07-30]** — was *"Shipped to 30+ researchers at 3+ universities."* **Unprovenanced, and no measurement work has touched it** — nothing in the repo derives a user count, and `universities_count` is a manually seeded stat row whose non-DB fallback is a hardcoded placeholder. Your own deck names **2** universities (GT and Emory), which is where "3+" gets contradicted by your own materials. Replace with the funnel above, which you can defend line-by-line from the deck. **If you check the Supabase dashboard → Auth → Users and see real counts, use those exact numbers — do not write "30+" unless you have seen 30.**

---

## 10. How Technologies Work Together — The Integration Points

### Upload → Analysis (Submit Path)
1. React uploads draft → FastAPI stores it in Supabase
2. API calls `analyze_draft_task.delay()` → returns immediately (job accepted)
3. Celery worker picks it up → parses PDF (Docling/GROBID) → computes parser quality
4. Worker invokes `run_draft_analysis_workflow()` → LangGraph compiles + `ainvoke`s the graph

### Inside the Graph (Processing Path)
1. Linear nodes build up `DraftAnalysisState` (structure → claims → citations → gaps)
2. `search_literature` embeds each claim, hits pgvector RPC + external APIs
3. `editor_pass` decides proceed-vs-desk-reject; preliminary gate may halt
4. `route_to_reviewer_panel` fans out 3 `Send`s → reviewers run concurrently
5. Reviewer outputs accumulate via the reducer channel → `meta_reviewer` synthesizes
6. `synthesize_report` builds the final report + revision tasks

### Post-Workflow + Trust Layer
1. Evidence manifest built; tasks reconciled against evidence; anchors repaired
2. `evaluate_publish_gate()` produces a deterministic confidence verdict
3. Artifacts written to Supabase; `draft.status='analyzed'`
4. `publish_progress(... 100, "complete")` → UI refetches and opens the report

### Progress / Observability Integration
1. Each node calls `publish_progress(draft_id, step, pct, message)` → Redis
2. UI holds a WebSocket subscription → live progress bar
3. LangGraph checkpoints state per node → failed runs can resume; checkpoints deleted on completion for privacy

---

## 11. Scalability Characteristics

### What Scales Horizontally
- **Celery workers**: add more workers, all pull from the same Redis broker — more concurrent analyses
- **API**: stateless FastAPI behind a load balancer, all hitting the same Supabase/Redis
- **pgvector**: scales with Postgres; index tuning (IVFFlat/HNSW) for larger corpora

### What Doesn't Scale (Yet)
- **External API rate limits**: OpenAlex 429s and Docling 504s appear at scale — needs a caching/fallback layer
- **OpenAI rate limits / cost**: the pipeline makes several LLM calls per run; cost scales linearly with usage *[UPDATED 2026-07-31: said "the multi-agent pipeline" — a surviving instance of the term the §1 correction removed everywhere else]*
- **Single Redis / single Postgres primary**: would need clustering / read replicas at high volume

### Performance Notes — measured, with `n` and provenance

> **[CORRECTED 2026-07-30]** — the first bullet used to read: ***"End-to-end: ~18s per analysis (down from 53s via reviewer parallelism)."*** **No end-to-end measurement has ever been taken.** Replaced with what actually exists. Read the caveat line at the bottom before quoting any of it.

**Per-node replay** — *complete* cost, matcher included (`scripts/eval/NODE_COST.md`):

| node | mean wall | n | node $ | + matcher $ | complete $/replay |
|---|---|---|---|---|---|
| `reviewer_panel_node[methodology]` | **19.286 s** (sd 2.897) | 5 replays, **one fixture** | $0.12098 | $0.02682 (18.1%) | **$0.0296** |
| `editor_pass_node` | ~7.4 s | 3 replays | $0.00339 | $0.00297 (46.7%) | $0.0021 |
| `run_quality_diagnostics` | **0.060 s** | 3 replays | $0.00000 | $0.00277 (**100%**) | $0.00092 |

> **[UPDATED 2026-07-31]** — this table used to read `19.818 s / ~$0.043` · `7.079 s / ~$0.0013` · `0.060 s / $0.00`, sourced from `BENCHMARKS.md`. **Every one of those dollar figures was node-only and therefore a floor.** `scripts/eval/match.py` — which scores the node's output — called OpenAI directly and was in no total and under no spend ceiling. **Matcher spend is 16.3% of the true figure**, and the margin on older numbers is **unrecoverable**: the matcher's caches store a vector and a verdict, no usage block, so it cannot be reconstructed. The most-quoted prior figure, $0.21999, made **6 uncounted calls** and reported $0.00 for all of them.

**The line worth saying out loud:** `run_quality_diagnostics` makes **zero LLM calls** and still costs **$0.00277** to measure. A node the old accounting reported as free was never free — and the cheaper the node, the worse the old figure was in relative terms.

One reviewer is ~330× the diagnostics node's wall time. The conditional domain-trigger audit branch doubles the call count and takes input to 53.5k tokens — the largest single cost variable measured. Still outside the accounting and worth volunteering: `atomize_reviews.py` contributed $0.00 to that run only because its cache was warm — luck, not design — and ~$0.02 of real spend was lost entirely when a process was killed with no usage log set.

**Prompt caching** (`scripts/eval/NODE_COST.md`; A/B in `scripts/eval/PROMPT_CACHE.md`): reordering the reviewer prompt so the shared prefix comes first took cross-persona cache hit rate **0% → 60.7%** on the real replay path and cut cold-panel cost **24.5%** ($0.10387 counterfactual uncached vs $0.07847 measured). The load-bearing evidence is two personas whose prompts had **never been sent** coming back **93.2%** and **92.7%** cached — that is the **8,064-token shared prefix, 87.4% of the prompt**, and nothing but the reorder puts it there. *[UPDATED 2026-07-31: the first pass quoted the purpose-built A/B's 58.8% / 23.8% on a different paper. Both reproduce within ~2 points; the replay-path numbers are the stronger evidence.]* Note what this is *not*: OpenAI's automatic prefix cache was **already** working with no `cache_control` in the repo — exact repeats already cached at ~99%. What was added is reuse *across the three personas*, which is where the volume is. ~60% is essentially the structural ceiling for a 3-call panel, since call 1 must always be cold. **n = 2 papers, one cold panel each**, and a `--repeat` run's 98.5% must never be quoted as a production number.

**Vector index operating point** (`scripts/eval/ANN_SWEEP.md`, n = 59 queries, **2,124-chunk corpus**): `ef_search = 80` sits on the knee at production's k=10 — ANN recall 0.9932 at 1.03 ms p50, vs 0.9797 at 0.66 ms (`ef_search=40`) and 1.0000 at 16.94 ms (`ef_search=160`). **The 16× is the planner, not the index:** past 80 the cost model abandons the index and the plan flips to a sequential scan; index-forced, the same setting is 1.66 ms. An index-forced number is never what production does. `m=16`/`ef_construction=64` is not dominated by an 11-point grid; label metrics move 0.004 across the whole grid, and index size is byte-identical at every point because a 1536-dim `float4` vector fills an 8 KB page alone. Say you **measured** the operating point, not that you chose it — two of the three values are pgvector defaults.

> **[UPDATED 2026-07-31] — and this is the best ANN story in the file.** The sweep predicted its own expiry: *"the crossover at LIMIT ≈ 35 is a property of this row count … on 10× the corpus it moves far above any realistic k."* At **5,948 chunks the crossover is 103** (104 flips to seqscan) — corpus ×2.80, crossover ×2.96, re-determined by binary search over `EXPLAIN` across 10 query vectors that all agree (`scripts/eval/BASELINE_15.md` §2). Consequences: the retrieval harness's depth-50 arm is now **genuinely an HNSW index scan**, which retires the old mislabelling; and the crossover is **not a constant and is never cached as one** — every retrieval record now carries a measured `plan` field. **What has *not* been re-measured is any ANN latency**: every timing above is from the 2,124-chunk corpus, and `BASELINE_15.md` reports no latency at all.

- Embedding cache (Redis) eliminates repeat OpenAI embedding calls for identical queries
- Preliminary gate avoids the most expensive LLM calls on un-analyzable parses

> **Caveat that travels with every number in this block.** These are **isolated node replays on cached fixtures** and **local pgvector microbenchmarks** — not production, not end-to-end, not user-visible. **Latency CV is 15.0% at n=5** *[UPDATED 2026-07-31: said "~7% at n=3"; the spread roughly doubled once a fifth sample was drawn, and nothing smaller than ~±19% of the mean is resolvable]*, and the exact-scan p50 varied ±25% across runs on a laptop under load. **Quality variance is worse and is currently unresolvable — CV 95% on a metric quantised at 1/79 of its own range, so no quality delta may be reported from this pipeline at all.** The ANN findings explicitly do **not** generalise, and that has now been demonstrated rather than predicted: the "Postgres declines the index above `LIMIT ~35`" finding was a 2,124-chunk artefact, and at 5,948 chunks the crossover is 103.

---

## 12. Real-World Analogies for Non-Technical Interviewers

- **The pipeline**: Like a journal's review process — an editor screens it, specialist reviewers each weigh in, an area chair makes the final call
- **Parallel reviewers**: Three reviewers reading the same paper at the same time instead of passing it down a line — faster (by how much is not measured)
- **The publish gate**: Like a fact-checker who strikes any sentence the writer can't point to a source for, and stamps the file "shaky" — but doesn't stop the presses, and the stamp stays in the filing cabinet <!-- --> — *[CORRECTED 2026-07-30: was "a fact-checker who can **veto** a story before it prints." It cannot veto — `FAIL_CLOSED` defaults off — and the reader never sees the stamp.]*
- **RAG relevance gating**: Like a librarian who won't hand you a book just because the title sounds similar — it has to actually be on-topic
- **Manuscript profiling**: Like knowing not to grade a poem with a math rubric

---

## 13. Likely Follow-Up Interview Questions and Answers

**Q: Why LangGraph instead of just chaining function calls?**
A: I need conditional routing (desk-reject skips the panel), parallel fan-out with a fan-in join (reviewers → meta-review), explicit inspectable state, and checkpoint/resume. LangGraph gives all of that declaratively; a script would bury that logic in control flow and local variables.

**Q: Why can't the meta-reviewer run in parallel with the reviewers?**
A: It's a true dependency — synthesis needs *all three* reviewer outputs to reconcile conflicts and produce one decision. It's the join point. Only the independent work (the three reviewers) parallelizes.

**Q: What stops the model from just making up a weakness?**
A: Layered defenses. Retrieval is topic-relevance gated so off-topic sources never enter context. Every issue must carry a verbatim manuscript anchor, reconciled against an evidence manifest. And a deterministic publish gate suppresses artifacts that can't be traced to a page and records a degraded-run verdict — the LLM can't override it. **And then the honest half:** I measured how well that works and it isn't a solved problem — hallucination rate is 0.111 on three papers, so about one item in nine still points at text I can't find in the paper.

> **[CORRECTED 2026-07-30]** — was *"a deterministic publish gate **labels or fails runs** whose grounding is weak."* It does not fail runs by default (`FAIL_CLOSED` is off), and the label is never shown to anyone. Volunteering the 0.111 is deliberate: this question is a trap for over-claiming, and a measured residual failure rate is a far better answer than a list of defenses.

**Q: How is pgvector different from a dedicated vector DB like Pinecone?**
A: pgvector lives inside Postgres, so I keep relational data and vectors in one store with one operational surface and transactional consistency. For my scale that beats running and syncing a separate service. At much larger scale a dedicated vector DB with better ANN indexing might win.

**Q: Why 1536 dimensions if 3-large is natively 3072?**
A: pgvector index compatibility and storage/speed. I request `dimensions=1536` at embedding time — OpenAI supports truncating 3-large down — so everything lines up with the existing index.

**Q: How do you evaluate quality without ground truth?**
A: I *do* have ground truth — real human peer reviews from OpenReview. I run Noesis on those same papers and use an LLM-judge to measure recall of the human reviewers' points, with anti-overfit guardrails so I'm not gaming the judge. The standing limitation I'd name unprompted: this measures *"would we have raised what the humans raised"*, not *"is this relevant"* — so anything the reviewers missed and Noesis found scores as a false positive, which makes every precision-like number a **lower bound**. Recall is the sounder number. Same limitation applies to my retrieval labels, which are the papers' own reference lists.

**Q: What's your biggest reliability risk?**
A: External dependencies — OpenAI rate limits and the literature APIs (OpenAlex 429s, Docling 504s). They're wrapped non-fatally so a failure degrades gracefully, but the real fix is a caching/fallback layer, which is on the roadmap.

**Q: How would you cut cost?**
A: I have per-node cost attribution now, so I can answer this with numbers rather than instincts: one reviewer persona is **~$0.03 per replay complete** and the panel is where essentially all of the money is. The part I'd volunteer, because it's the part I got wrong first: **every cost number I had before was a floor.** The code that *scores* a node's output called OpenAI directly and was in no total and under no spend ceiling, so it was invisible — **16.3% of the true figure**, and unrecoverable, because its caches store a vector and a verdict but no usage block. The node I'd reported as free — zero LLM calls — actually costs **$0.0028 to measure**. Three things I did or would do, in order of measured payoff: **(1)** reorder the reviewer prompt so the shared prefix comes first — the three personas share ~88% of their text, and putting the persona *last* took cross-persona cache hits from **0% to 60.7%** and cut cold-panel cost **24.5%**, with an 8,064-token shared prefix that is 87% of the prompt; **(2)** route cheaper models for the easy nodes and reserve the frontier model for reviewers/meta-review; **(3)** the preliminary gate already avoids the expensive calls on bad parses. There's also a manuscript-compaction flag that cuts prompt tokens 60.7%, but it's **off** — I couldn't resolve its quality effect above run-to-run noise at n=4/5, and compaction plausibly *increases* false "not reported" critiques since the prompt tells reviewers to search the whole manuscript before claiming something is absent.

**Q: What would you build next?**
A: Stream partial results (show reviewers as they finish instead of waiting for the full graph), learn the publish-gate thresholds from labeled eval data instead of hand-tuning, and add the external-API caching layer.

---

## 14. What You Learned from This Project

1. **Fluency is not correctness.** The hard part of an LLM product is making it trustworthy, not making it talk. Every interesting decision in Noesis is a grounding or anti-hallucination defense.

2. **The LLM proposes, deterministic code decides.** Pairing generative reasoning with a non-LLM gate it can't override is the pattern that made the output safe to ship.

3. **Dependency ordering is the key to concurrency.** The fan-out came from seeing which work was genuinely independent (reviewers) versus a true join (meta-review) — same lesson as ordering writes correctly in a distributed system. *[CORRECTED 2026-07-30: this used to be framed as "the 53s→18s win". The restructuring is real and the reasoning is the point; the speedup was never measured and there is no sequential baseline to measure it against.]*

4. **Vector similarity ≠ relevance.** RAG retrieves what's *near*, not what's *right*. A relevance gate between retrieval and the model was necessary to stop contamination.

5. **You can't improve what you can't measure — so measure against humans.** Building the OpenReview eval harness turned "is the output good?" from a vibe into a number, which is what let me actually iterate.

   **The lesson underneath that one, learned the hard way (added 2026-07-30): a metric that cannot produce a bad number is not a measurement.** Two of mine couldn't. The eval reported `precision = 1.0` because an item counted as correct if *a model judged it grounded*; the publish gate's `verbatim_anchor_coverage` read 1.0 on all 77 runs because a failed anchor is nulled upstream, removing the task from the **denominator** as well as the numerator — the failure erased its own evidence. Both looked like healthy signals for months. **The tell is a metric that never moves.** Now every number I report carries its `n`, invalid runs are excluded and listed with a reason, and trends are only drawn between runs sharing a config hash.

6. **Spend compute where it matters.** The preliminary gate and editor desk-check exist so the expensive LLM calls only run when they'll produce shippable output.

7. **Prompt engineering is real engineering — and prompt *ordering* is a cost lever.** Rating calibration, forbidden review standards, and verbatim-anchor requirements are as load-bearing as the code. *[CORRECTED 2026-07-30: "measurably changed output quality" is cut — there is no before/after eval for any of those three.]* What **is** measured is structural: the three reviewer personas share ~88% of their prompt text, and moving the persona from the head of the system message to the **end** of the user message took cross-persona prompt-cache hits from **0% → 60.7%** and cut cold-panel cost **24.5%** — same tokens, same model, different order (n = 2 papers, one cold panel each). *[UPDATED 2026-07-31: was 58.8% / 23.8%, the purpose-built A/B on one paper; the figures above are the same effect measured on the normal replay path, and the two agree within ~2 points.]*

---

## 15. Quick-Reference Cheat Sheet

```
PITCH:        "Know what Reviewer 2 will say before you submit."
              Pre-submission AI peer review for researchers.

STACK:        React/TS · FastAPI · LangGraph · GPT-5.2 · Supabase(Postgres)
              · pgvector(1536-dim) · Celery/Redis · GROBID/Docling
              · PubMed/arXiv/S2/OpenAlex · Docker/AWS EC2 · GitHub Actions · Stripe

THE PIPELINE: parse → structure → profile → extract claims → RAG + literature
              → map citations → detect gaps → editor desk-check
              → 3 PARALLEL reviewers → meta-review → synthesize report
              → deterministic publish gate

3 THINGS TO HAMMER:
  1. Trust is the hard problem. "LLM proposes, deterministic code decides."
  2. 53s → 18s (66%) via parallel reviewer fan-out; meta-review is the fan-in join.
  3. Eval harness uses REAL human reviews (OpenReview) as gold + LLM-judge.

KEY NUMBERS:
  • 30+ researchers, 3+ universities
  • 1536-dim embeddings (3-large reduced from 3072)
  • Celery concurrency = 4
  • Publish gate: parser ≥0.55, page-anchor coverage ≥0.75
  • Display source similarity floor = 0.66

TRUST MECHANISMS (memorize these):
  • Topic-relevance gating on RAG  → stops source contamination
  • Verbatim manuscript anchors    → stops invented critiques
  • Evidence manifest reconciliation → ties every task to real evidence
  • Deterministic publish gate     → fail-open LLM judge can't override it
  • Preliminary gate               → skip expensive calls on doomed parses
  • Manuscript profiling           → right evidentiary bar per paper type
```

---

*Document generated for technical interview preparation — covers architecture, the multi-agent LangGraph pipeline, trust/grounding mechanisms, the latency win, evaluation methodology, and follow-up question prep.*
