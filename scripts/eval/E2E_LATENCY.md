# User-visible end-to-end latency — the first measurement

Measured 2026-07-31 / 2026-08-01. Tool: `scripts/eval/e2e_latency.py`. Results
append to `scripts/eval/results/e2e_latency.jsonl`, keyed by a config hash that
covers the fixture, the parser, the LLM mode and the eval skip flags. Tests:
`scripts/eval/tests/test_e2e_latency.py` (25 tests).

`docs/ENGINEERING_LOG.md` says it twice: *"A node replay is not an end-to-end
user-visible time. The end-to-end path has never been measured, not once."*
This is that measurement. It starts the stopwatch when the user's file arrives
at the upload route and stops it when the analysis JSON is in the user's hand.

---

## Read this before quoting any number below

**1. `n = 7`.** Seven complete, successful, real-GPT-5.2 runs of the whole path,
across two sessions at the same config hash `670fccc87731`, each session
discarding one warmup run. **No p90, p95 or p99 appears anywhere in this
document, and the harness refuses to compute one** — `trace_report.metrics`
requires n≥10/20/100 for those, which is the same code the graph-level harness
uses. A "p95" over seven runs is the maximum wearing a percentile's name.

**2. The spread is large and it is honest.** CV on the user-visible total is
**36.3% at n=7** — worse than the project's previously measured 15.0% at n=5 on
a single node, and for a specific reason: this path contains PDF parsing, and
PDF parsing on this host is the noisiest thing in the pipeline by a wide
margin. sd = 77.8 s on a 214.5 s mean. A 95% interval on the mean is roughly
**214.5 ± 71.9 s**. Nothing smaller than about ±34% of the mean is resolvable
from these seven runs.

**3. This ran against LOCAL Supabase, not production.** Postgres, PostgREST,
GoTrue and Storage all on loopback. Production Supabase is a network hop away.
Section *What is still unmeasured* estimates the size of that difference; it is
not zero and it is not included.

**4. Docling was not used; GROBID was.** Production compose defaults to
`PDF_PARSER=docling` with GROBID for reference extraction. That configuration
was measured, failed, and is reported below — but it could not be run
repeatedly on this host, so the seven-run measurement uses `PDF_PARSER=grobid`.
This is a documented variable, not a silent swap.

---

## The headline

| | value | n |
|---|---|---|
| **user-visible p50** | **212.82 s** | 7 |
| user-visible mean | 214.53 s | 7 |
| user-visible min / max | 126.81 / 352.41 s | 7 |
| sd / CV | 77.81 s / **36.3%** | 7 |
| LLM calls per complete run | **13** (identical in all 7) | 7 |
| spend per complete run | $0.2021 mean ($0.1784–$0.2452) | 7 |

"User-visible" = `upload_request` + `ingest` + `graph` + `first_read`. The
graph flips `drafts.status` to `analyzed` as its last act, so the task's
bookkeeping tail runs *after* the page could already paint and is excluded from
the headline while still being measured and reported.

Two things a reader will want immediately, both with their own sections below:

- 🔴 **The PDF is parsed twice and the first result is discarded.** Parsing is
  39.2% of the mean path; parsing once instead of twice is *estimated* to
  remove 15–25% of the user-visible p50. See
  [The PDF is parsed twice](#-the-pdf-is-parsed-twice-and-the-first-result-is-thrown-away).
- ⚠️ **The `graph` stage reads 112.51 s p50 here against the recorded
  graph-level 63.75 s. This is not a regression measurement** — the two were
  taken with different inputs, different persistence settings and on different
  days. See
  [Relationship to the existing 63.75 s graph number](#relationship-to-the-existing-6375-s-graph-number).

---

## Per-stage

Seconds. Every row carries its `n`. Pooled over both sessions.

| stage | n | p50 | mean | sd | CV | min | max | what happens in it |
|---|---|---|---|---|---|---|---|---|
| `upload_request` | 7 | 53.30 | 50.25 | 39.22 | 78.0% | 5.69 | 122.17 | the real `drafts.upload_draft`: format validation — **which parses the whole PDF** — then the Storage write and the `drafts` insert |
| `ingest` | 7 | 48.65 | 50.83 | 35.39 | 69.6% | 14.80 | 99.87 | `ingest_draft`: Storage download, **the PDF parsed a second time**, structure build, anchor map, parse-artifact write, Stage-1 editing LLM call, `draft_analysis` insert |
| `graph` | 7 | **112.51** | **113.07** | 13.34 | **11.8%** | 96.02 | 130.23 | `analyze_draft_with_langgraph`: all 18 nodes, the 3-way reviewer fan-out, the publish gate, and every publish write |
| `task_tail` | 7 | 0.17 | 0.45 | 0.78 | 173.1% | 0.02 | 2.18 | quota increment + usage tracking, after the user can already see results |
| `first_read` | 7 | 0.14 | 0.38 | 0.44 | 117.3% | 0.01 | 1.19 | the real `GET /drafts/{id}/analysis` the frontend polls |
| **to first visible** | 7 | **212.82** | **214.53** | 77.81 | 36.3% | 126.81 | 352.41 | |
| wall (incl. tail) | 7 | 213.00 | 214.99 | 78.12 | 36.3% | 126.83 | 352.62 | |

Cross-cutting, measured by httpx event hooks on the Supabase transports rather
than by wrapping call sites, so nothing is missed:

| | n | p50 | mean | min | max |
|---|---|---|---|---|---|
| PDF parse, both calls | 7 | 68.66 | 84.03 | 12.72 | 205.71 |
| — parse #1 (in `upload_request`) | 7 | 52.38 | 48.67 | 5.61 | 120.33 |
| — parse #2 (in `ingest`) | 7 | 33.17 | 35.36 | 0.09 | 85.37 |
| Supabase HTTP, all of it | 7 | 4.65 | 7.93 | 0.52 | 28.50 |
| — inside the `graph` stage (37 calls, every run) | 7 | 2.29 | 5.08 | 0.33 | 20.68 |
| Supabase Storage HTTP | 7 | 1.12 | 1.97 | 0.16 | 4.84 |

**PDF parsing is 39.2% of the mean user-visible time. The graph is 52.7%.**
Supabase — every read, every write, both storage transfers — is 3.7%.

---

## 🔴 The PDF is parsed twice, and the first result is thrown away

**This is the largest actionable finding in the measurement.** PDF parsing is
**39.2% of the mean user-visible path**, and roughly half of that is the same
work done a second time.

### It is the same call, not a cheap check and a full parse

Two call sites, same function, same arguments, no lightweight variant:

`services/backend/app/services/draft_processing.py:740`, inside
`validate_file_format`, reached from `routes/drafts.py:546` during
`POST /drafts/upload`:

```python
    if validation_result["valid"]:
        try:
            extracted_data = await extract_text(file_bytes, file_type)
            sample_text = extracted_data["full_text"]

            if len(sample_text.strip()) < 50:
```

`services/backend/app/services/draft_processing.py:507`, inside `ingest_draft`,
reached from `routes/drafts.py:_run_draft_analysis_task` — the Celery worker
body:

```python
        # 3. Extract text based on file type (structured data for PDFs via GROBID)
        logger.info(f"[INGEST] Step 4: Extracting text from {file_type} file...")
        extracted_data = await extract_text(file_bytes, file_type)
        full_text = extracted_data["full_text"]
```

Same `extract_text(file_bytes, file_type)`. `extract_text` dispatches straight
to `extract_text_from_pdf`, which runs the full Docling-or-GROBID document
pipeline; there is no header-only or first-page path anywhere in it. The
harness instrumented the function itself, so both invocations were timed
independently, and **in all 7 runs the two returned identical output** — same
character count (32,999 or 41,010 depending on which parser served the run),
same section count, same reference count. The first result is used for exactly
one thing, `len(sample_text.strip()) < 50`, and is then discarded; `ingest_draft`
re-downloads the file from Storage and re-parses it from scratch.

### What it costs

| | n | p50 | mean | share of mean user-visible |
|---|---|---|---|---|
| parse #1 — in `upload_request`, result discarded | 7 | 52.38 s | 48.67 s | 22.7% |
| parse #2 — in `ingest`, result used | 7 | 33.17 s | 35.36 s | 16.5% |
| both together, per run | 7 | 68.66 s | 84.03 s | 39.2% |

A note on the two stage totals: `upload_request` p50 + `ingest` p50 is 101.95 s,
but those stages also contain the Storage write, the Storage download, the
structure build, the anchor map, the parse-artifact write, the Stage-1 editing
LLM call and two DB writes. **The parsing alone is 68.66 s p50**, and that is
the number the double-parse finding is about.

### Estimated effect of parsing once — an ESTIMATE, not a measurement

**No single-parse run was ever executed.** What follows is arithmetic on the
seven measured runs: subtract one parse's measured wall time from that same
run's measured total, then re-derive p50 and mean over the seven results. It
is a counterfactual and it is labelled as one everywhere it appears.

| scenario | p50 | mean | saving vs measured p50 |
|---|---|---|---|
| **measured, as the code stands** | **212.82 s** | 214.53 s | — |
| *estimate:* validation's parse cached and reused by `ingest_draft` | 179.81 s | 179.18 s | **−33.01 s, −15.5%** |
| *estimate:* validation stops parsing at all (cheap check), `ingest_draft` unchanged | 160.41 s | 165.86 s | **−52.41 s, −24.6%** |

The two rows differ because the two parses did not cost the same on this host:
the second parse often ran against a GROBID that was already warm from the
first. The honest reading is a **range: parsing once instead of twice removes
an estimated 15–25% of the user-visible p50**, and the true figure depends on
which of the two parses survives.

Three things the estimate assumes, all of which could move it:

1. that removing a parse removes exactly its measured wall time (safe here —
   the stages are sequential and the parse is synchronous inside them);
2. that the surviving parse costs what it cost when it ran second, which on a
   host where GROBID's cost varied 5.61–120.33 s is not guaranteed;
3. that nothing downstream depends on the parse happening twice. Nothing in the
   read of these two functions suggests it does, but that was not tested.

Even at the bottom of the range this is larger than any parallelisation result
this project has measured.

**This was not fixed.** `draft_processing.py` and `routes/drafts.py` belong to
other agents and were not modified. It is reported, with its call sites, for
whoever owns them.

---

## What is IN

Stated positively, because the previous number's fatal caveat was that its
exclusions were larger than its inclusions.

- **Upload route.** The real `drafts.upload_draft` function, including format
  validation, the file-size and extension checks, and the rate-limit decorator
  (disabled — see below).
- **PDF parsing.** Both calls. GROBID over HTTP, full document, real TEI
  parsing, the anchor map, the parse-quality assessment, and the local PyMuPDF
  fallback when GROBID fails (which it did — see *Variables*).
- **Supabase Storage write** on upload and **Storage download** in ingest.
- **Every Supabase database call**, timed individually and attributed to the
  stage that made it. 37 of them happen inside the graph stage in every run.
- **Stage-1 editing**, an LLM call that runs inside `ingest_draft`.
- **The whole 18-node graph**, including the 3-way reviewer `Send` fan-out, the
  meta-reviewer, the publish gate and the diagnostic pass.
- **The publish writes.** `stage_only` is *not* set. The runs wrote real rows:
  across every session on this database, 9 `draft_analysis_runs` reached
  `status='published'`, with 27 `reviewer_panel_outputs`, 9 `meta_reviews`,
  103 `draft_claims` and 121 `draft_revision_tasks` behind them.
- **The status transition to `analyzed`** and the first `GET
  /drafts/{id}/analysis` a browser would make.
- **Quota and usage bookkeeping** (`task_tail`) — measured, reported, and
  excluded from the headline because it lands after visibility.

## What is OUT, and how big each one is

| excluded | why | estimated size |
|---|---|---|
| Browser→server transfer of the 440 KB PDF | the route function is called in-process; no socket is involved | 0.4–4 s on a 1–10 Mbit uplink. Not modelled. |
| Celery broker enqueue + worker pickup | `analyze_draft_task.delay` is replaced by a no-op and the task body is called inline. A broker hop is not a thing this harness can measure honestly on one machine. | Redis enqueue is sub-millisecond; **worker pickup under a queue backlog is not, and is unbounded.** `docs/MEASUREMENTS.md` §Graph latency under load shows queueing dominating past λ=0.5. |
| Production network latency to Supabase | everything here is loopback | 37 DB calls + 2 storage calls per run. At a 30–80 ms RTT instead of ~1–5 ms, **+1.1 to +3.1 s**, i.e. ~0.5–1.5% of the user-visible total. Small, but not zero. |
| OpenAlex / Unpaywall external source discovery | `EVAL_SKIP_EXTERNAL_SOURCE_DISCOVERY=1`, the same flag the graph-level measurement used, so the two `graph` numbers stay comparable | unmeasured; a real external dependency, and strictly additive |
| The preliminary-halt gate | `EVAL_DISABLE_PRE_REVIEWER_HALT=1`, same reason | it can only *shorten* a run, so its absence is conservative |
| Frontend render after the JSON arrives | not a backend measurement | unmeasured |
| LangGraph checkpoint writes | `NOESIS_CHECKPOINT_ENABLED` is unset — **which is also the production default** | zero, correctly |
| Corpus-backed retrieval | the fixture project has no documents, so `search_literature`, `map_citations`, `detect_gaps` and `citation_judge` short-circuit | a corpus-backed run is strictly slower and strictly more expensive than this |
| Rate limiting | `limiter.enabled = False`; 5 uploads/minute would truncate the run | a policy gate, not a latency |

Nothing on this list is larger than what is included. That is the difference
between this number and the one it supersedes.

---

## Variables — things that moved between runs and are not stochastic noise

**1. GROBID failed on 2 of the 7 measured runs** and the pipeline degraded to
the local PyMuPDF text fallback. The two regimes are distinguishable in the
record by section count (13 sections + 33 references when GROBID succeeds; 0
and 0 when it does not), so they are reported apart rather than averaged
together:

| | n | visible p50 | visible mean | graph mean |
|---|---|---|---|---|
| GROBID succeeded | 5 | 212.82 | 193.89 | 112.58 |
| GROBID failed → local fallback | 2 | 179.90 | 266.15 | 114.31 |

The fallback is *not* faster overall: the failure is discovered only after
GROBID has been given its time, so the run pays the timeout **and** the
fallback. The graph stage is unaffected by which parser produced the text.

**2. The two sessions are not the same population.** Session A (n=3):
user-visible p50 141.03 s. Session B (n=4): p50 219.59 s. Identical config
hash, same fixture, ~90 minutes apart. The graph stage barely moved
(110.43 → 114.86 p50); the parse stages did all of it. **Pooling them is
reported here because the config hash is the same, but the pooled parse
distribution is bimodal and should be read as such.**

**3. Both parsers run under x86-64 emulation on Apple Silicon.**
`infra/docker-compose.yml` pins `platform: linux/amd64` for both `grobid` and
`docling-serve`. On this host that means QEMU. **Every parse number in this
document is an emulated-x86 number and is not a production parse time.** It is
the right instrument for "what fraction of the path is parsing on this
machine" and the wrong one for "how long does GROBID take in production".

**4. Docling could not be measured.** Production's default `PDF_PARSER=docling`
was tried first. One complete run under Docling is in the sink
(`run_id cd8bb67ec9fe`, config `0c5f37759ef3`): parse #1 **247.5 s**, parse #2
**250.6 s**, and Docling returned 0 sections and 0 references, so the pipeline
fell through to the local fallback anyway. That run then failed at the publish
step on a transient PostgREST schema-cache error. With `docling-serve-cpu`
resident, GROBID was OOM-killed twice and a standalone GROBID request died
after 456 s; with Docling stopped, the same request completed in 53 s. **Docker
on this host has 7.654 GiB and cannot hold local Supabase, Docling and GROBID
at once.** Docling is therefore excluded from the seven-run measurement and
this is the documented variable it becomes.

**5. Redis hostname.** `progress_tracking.REDIS_URL` is hard-coded to the
compose hostname `redis`, which does not resolve from the host. Left alone,
every progress publish spends a DNS failure plus a connect timeout inside the
measured path — an artefact of running off the compose network. The harness
rewrites the hostname to `localhost` and runs a real Redis. Only the hostname
changes.

---

## Is the instrumentation itself correct?

The stages are sequential and non-overlapping and are timed with
`time.perf_counter()`, so `sum(stages)` should equal the wall clock. It does:

**The largest unaccounted fraction across all 7 runs is 6×10⁻⁵ — 0.006% of the
wall time.** The declared tolerance is 1%, chosen because the graph-level
measurement found node time was 99.5% of graph wall and a larger gap would be a
finding rather than a rounding error. There is no gap here.

`tests/test_e2e_latency.py` asserts this property three ways: on synthetic
clocks, on the declared stage list (a stage the harness times but `STAGES` does
not list would silently inflate the residual), and on **every successful run in
the real sink**, which will fail the suite if a future run breaches the
tolerance.

The same suite asserts that warmup runs cannot reach a statistic, that failed
runs are counted but never averaged, that p90/p95/p99 are refused at n=7, and
that `assert_local_only` — which has no override flag — rejects every
non-loopback Supabase URL.

---

## Relationship to the existing 63.75 s graph number

`docs/MEASUREMENTS.md` §Graph latency under load reports **graph p50 63.75 s,
mean 64.67 s, n=3**, and says of itself that it excludes upload, storage, PDF
parsing and publish writes, and that *"parsing is larger than what is
included."*

That warning is now quantified, and it was right:

| | value | n |
|---|---|---|
| graph-only, `loadgen`, `stage_only=True`, no publish writes | p50 63.75 s / mean 64.67 s | 3 |
| **graph stage, this harness**, publish writes ON | p50 112.51 s / mean 113.07 s | 7 |
| **the whole path a user waits through** | **p50 212.82 s / mean 214.53 s** | 7 |

Two separate statements, and they should not be conflated:

- **The old number was 30% of the user-visible time.** 64.67 s against 214.53 s
  mean. The excluded remainder was indeed larger than what was included, exactly
  as that document warned.
- **The `graph` stage here reads 113.07 s mean against its 64.67 s** — ~75%
  higher. Read on before drawing the obvious conclusion.

### ⚠️ 112.51 s vs 63.75 s is NOT a regression measurement

Nothing in this project got 75% slower, and no such claim is made here. These
are **two different measurements of two differently-configured things, taken on
different days, with different inputs, at different `n`**. Differencing them is
the same mistake as differencing two retrieval label snapshots, and the same
rule applies: they are not comparable, and no delta between them should be
quoted.

Every difference that is known:

| | `loadgen` (63.75 s p50, n=3) | here (112.51 s p50, n=7) |
|---|---|---|
| what is invoked | `run_draft_analysis_workflow` | `analyze_draft_with_langgraph` — the **publish path**, which wraps the graph |
| persistence | `stage_only=True` — every node's persistence path is gated off | **off**: real publish gate, real writes, 37 Supabase calls per run |
| input | cached `extract_structure.json` fixture, 31,363 chars, parsed elsewhere at some earlier time | freshly GROBID-parsed text from the same paper's PDF, **32,999 chars** |
| LLM calls | 8.0 per graph run | 13 per **complete run** (this harness counts per run, not per stage) |
| when | 2026-07-31, one session | 2026-07-31 / 2026-08-01, two sessions |
| `n` | 3 | 7 |

### How much of the 48.4 s gap can be accounted for

| | size | status |
|---|---|---|
| Supabase writes the other measurement suppressed | 5.08 s mean (37 calls) | **measured** — so persistence is at most ~10% of the gap |
| extra LLM calls on the publish path | ≤ 5 calls | **not attributable** — this harness counts LLM calls per run, not per stage. At least one of the 13 is Stage-1 editing inside `ingest`, so the graph made ≤ 12 against the other measurement's 8. At the per-node latencies that document records (reviewer ~17.5 s, editor ~8.7 s, judge ~3.0 s), four additional calls would plausibly cover 30–45 s of the gap — **plausible, unverified, and not claimed as the cause.** |
| 5.2% more manuscript text | unknown | not modelled |
| different day, shared API | unknown | not modelled |

**Roughly 10% of the gap is measured; the rest is not accounted for.** A
like-for-like A/B — same fixture, same persistence setting, same session, both
harnesses — was not run and would be the only thing that settles it. Recorded
here as an open question, not as a finding.

### On `53s → 18s`

Already adjudicated elsewhere: parallel fraction 52%, Amdahl ceiling 52%,
measured speedup 1.48× / 32.5%. Nothing here reopens that. One relationship is
worth recording, and only as arithmetic:

**the graph is 52.7% of the mean user-visible path (113.07 s of 214.53 s,
n=7)**, so the measured 32.5% graph-time reduction is **≈17.1% of what a user
waits for** — 36.7 s off a 214.5 s mean. Amdahl applies twice: once inside the
graph, and again to the graph's share of the whole path.

---

## Cost

| | |
|---|---|
| LLM calls per complete run | **13**, identical across all 7 runs |
| spend per complete run | mean $0.2021, p50 $0.1996, range $0.1784–$0.2452 |
| **total actual spend, every session** | **$2.1431** of a **$4.00** track ceiling |
| unpriced calls | 0 |

Everything charged to this track, from the sink. Nothing is omitted — the
failed Docling attempt and both discarded warmup runs cost real money and are
counted:

| session `run_id` | config | runs offered | measured / ok | LLM calls | spend |
|---|---|---|---|---|---|
| `cd8bb67ec9fe` | Docling | 1 | 0 — **failed** at the publish step | 13 | $0.2692 |
| `fbd8d25f7493` | GROBID | 4 (1 warmup) | 3 | 52 | $0.8387 |
| `1a61c82402e4` | GROBID | 5 (1 warmup) | 4 | 65 | $1.0352 |
| **total** | | **10** | **7** | **130** | **$2.1431** |

Per-session ceilings were `NOESIS_LLM_MAX_SPEND_USD` 1.00 / 2.50 / 2.00 and
`NOESIS_LLM_MAX_CALLS` 30 / 90 / 100. **None tripped.** $1.8569 of the $4.00
track allocation is unspent; no further runs were made, because the spread in
these numbers is environmental (an emulated parser) rather than sampling, and
more samples on this host would not narrow it.

Standing project caveat applies unchanged: **every cost figure in this project
is a lower bound**, because `match.py` bypassed the spend guardrails and its
calls were never recorded in any sink.

---

## Hardware and environment

| | |
|---|---|
| Machine | Apple M4, 10 cores, 16 GB, macOS 15.6.1 (24G90) |
| Docker | 28.5.1, **7.654 GiB allocated**, 10 CPUs |
| Python | 3.13.7, on the host (not in the backend container) |
| Supabase | local CLI stack — API `127.0.0.1:54321`, DB `127.0.0.1:54322`. **Production was never contacted.** |
| Parser | GROBID `lfoppiano/grobid:0.7.0`, `platform: linux/amd64` under emulation |
| Redis | `redis:7-alpine`, compose `core` profile |
| Model | `gpt-5.2` / `gpt-5.2-chat-latest` |
| Fixture | `scripts/eval/openreview/ICLR.cc_2024_Conference/10eQ4Cfh8p.pdf`, 440,085 bytes — **the PDF the 63.75 s graph measurement's cached fixture came from** |

### The local database is a reconstruction

Migrations `001`–`021` do not exist in this repository; only `022`–`039` do,
and each of those `ALTER`s tables it assumes already exist. The base tables
were therefore rebuilt from the application code that reads and writes them —
every column present because some line of `app/` writes it, filters on it or
orders by it. That DDL lives in `e2e_latency.py::bootstrap_sql()`, is labelled
`NOT PRODUCTION DDL`, and is applied by `--bootstrap` followed by `022`–`039`
in order.

Three RPCs the pipeline calls have no definition anywhere in the repo —
`match_draft_chunks`, `increment_quota_field`, `reset_quota_if_needed` — and
are stood up locally as minimal stand-ins so a PostgREST 404 does not change
the shape of the measured path. **Their production bodies are unknown and these
are not a reconstruction of production behaviour.** Column *types* are the
widest thing that works; production's constraints, RLS policies and triggers
are absent except where `022`–`039` create them.

**Consequence for the numbers:** the DB is only 3.7% of the measured path, so
schema fidelity cannot move the headline much. But the local schema is not
production's, and a query plan difference on a real production table is not
captured here.

---

## What is still unmeasured

- **Production Supabase latency.** Estimated at +1.1–3.1 s above; not measured.
- **Queue wait.** The single largest unbounded term on the real path, and the
  one this harness structurally cannot see. Under load, `docs/MEASUREMENTS.md`
  shows response time dominated by queueing well before capacity.
- **Production parse time.** Every parse number here is emulated x86.
- **Docling**, i.e. production's actual default parser, on a host that can run
  it alongside the rest of the stack.
- **A corpus-backed run.** All seven are no-corpus; four graph nodes
  short-circuit.
- **Concurrency.** All seven are c=1, one analysis at a time. This is a
  best-case number.
- **Why the graph stage is 75% slower here than in `loadgen`.**
- **Whether 13 LLM calls per run is stable across manuscripts.** It was
  identical in all 7 runs *of one fixture*.
- **n beyond 7.** More runs would tighten the confidence interval on a
  distribution whose spread is environmental, not sampling — the fix is a host
  that can run the parsers natively, not more samples on this one.

---

## Reproducing

```bash
cd scripts/eval

# 0. Local Supabase must be up: `supabase start`. GROBID + Redis:
#    (cd ../../infra && docker compose --profile parse up -d grobid
#                    && docker compose --profile core  up -d redis)
#    Docling must be STOPPED on a host with <8 GB of Docker memory.

# 1. Always dry-run first. No app import, no call, no write.
python3 e2e_latency.py --dry-run

# 2. Local schema + storage bucket + fixture user/project. Idempotent.
#    Refuses to run against anything but loopback.
python3 e2e_latency.py --bootstrap

# 3. The measurement. REAL paid calls; --yes is required.
python3 e2e_latency.py --n 3 --warmup 1 --parser grobid --yes \
    --max-spend 2.5 --max-calls 90

# 4. The instrument's own tests, including the accounting check against
#    every run in the real sink.
python3 -m pytest tests/test_e2e_latency.py -q
```
