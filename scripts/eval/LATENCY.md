# Graph latency under load — the first measurement of a whole run

Measured 2026-07-31. Tool: `scripts/eval/loadgen/`. Results append to
`scripts/eval/results/loadgen.jsonl`, keyed by a config hash that includes the
load model. Spans from the calibration and fan-out runs are in
`scripts/eval/results/loadgen_fanout_spans.jsonl`.

Before this, nothing in this repo had measured how long a draft analysis takes.
`node_eval.py` measures one node replayed in isolation; `trace_report/` reads
spans from runs that were never made under load. Neither is a duration anybody
waits for, and neither says anything about what happens when two analyses run at
once.

---

## Read this before quoting any number below

**1. Every figure here is GRAPH-LEVEL latency.** It is the wall time of
`run_draft_analysis_workflow` from entry to return. Excluded, in full:

| excluded | why it matters |
|---|---|
| upload + Supabase Storage download | network, user-visible, unmeasured |
| **PDF parsing (Docling / GROBID)** | **not measured here, and not small: `CREATEX_PRESENTATION.md` puts the user-visible path at ~3.5 min against the 65 s of graph time measured below, so the excluded remainder is larger than what is included** |
| publish writes (`stage_only=True`) | suppressed deliberately |
| checkpoint writes (`checkpoint_enabled=False`) | suppressed deliberately |

A number from this harness is **not** user-visible end-to-end latency and must
never be labelled as one.

**2. Every figure states its load model.** Open or closed loop, λ or
concurrency, n, warmup discarded, stub or real LLM. A latency without its load
model is unquotable, so the load model is column 1 of every table and part of
the config hash on every stored record.

**3. Stubbed latencies are labelled STUB and are not observed API times.** They
are lognormal draws from a per-node distribution calibrated against a real run
(below). They are the right instrument for queueing behaviour and the wrong
instrument for "how fast is GPT-5.2 today".

**4. All of this is the no-corpus path.** The fixtures carry no project
documents, so `search_literature`, `map_citations`, `detect_gaps` and
`citation_judge_node` short-circuit and make **zero** LLM calls. A corpus-backed
run is strictly slower and strictly more expensive than anything measured here.

---

## The real-LLM calibration run

Three complete graph runs, real paid GPT-5.2 calls, on fixture `10eQ4Cfh8p`
(31,363 chars).

```
closed-loop concurrency=1, n=3 (warmup 0 discarded), LLM=real,
reviewers=parallel, SLO=60s, seed=1234, cfg=93afa3a22f4f
```

| | value |
|---|---|
| graph wall p50 | **63.75 s** |
| graph wall mean | 64.67 s |
| graph wall min / max | 63.11 / 67.15 s |
| n | 3 (p90/p95/p99 refused — see the n-floor) |
| LLM calls | 24 (8.0 per graph run) |
| prompt / completion tokens | 139,909 / 23,661 |
| **actual spend** | **$0.412157** total, **$0.1374 per graph run** |
| Supabase write attempts | **0** |
| Supabase reads | 3 |
| reviewer branches per run | 3.0 |

Ceilings in force: `NOESIS_LLM_MAX_CALLS=60`, `NOESIS_LLM_MAX_SPEND_USD=1.50`.
Neither tripped.

### Per-node wall time, in-graph, real LLM (n=3 runs)

This is the first per-node breakdown of a *complete* run. `node_eval.py` had
produced numbers for two of these nodes, in isolation, months apart.

| node | mean | LLM calls |
|---|---|---|
| `reviewer_panel_node[literature_positioning]` | 17.54 s | 1 |
| `reviewer_panel_node[methodology]` | 17.34 s | 1 |
| `reviewer_panel_node[clarity]` | 16.28 s | 1 |
| `extract_claims` | 12.28 s | 1 |
| `meta_reviewer_node` | 11.72 s | 1 |
| `structural_checks` | 10.83 s | 1 |
| `editor_pass_node` | 8.74 s | 1 |
| `reviewer_judge_node` | 3.04 s | 1 |
| `profile_manuscript` | 0.26 s | 0 |
| the other 10 nodes | ≤ 0.02 s each | 0 |

Sum of node time = 64.32 s against a 64.67 s graph wall. **Non-LLM,
non-node orchestration overhead in this graph is ~0.35 s, about 0.5%.** The
graph is a sum of LLM calls and essentially nothing else.

`editor_pass_node` in-graph is 8.74 s against the 7.43 s the isolated replays
reported — the replay number was 15% low.

---

## Stub fidelity

Same load model, same fixture, LLM replaced by the calibrated stub:

| | real LLM | stubbed LLM | error |
|---|---|---|---|
| graph wall p50 | 63.75 s | 65.60 s | +2.9% |

n=3 measured in both cases. The stub reproduces the graph's *duration*; it
reproduces nothing about the graph's *output*, and no output-quality claim is
made anywhere from a stub run.

The calibrated profile (`loadgen/calibration.json`) covers all six nodes that
make an LLM call on this path. The twelve remaining nodes carry a labelled
ASSUMED distribution that is never exercised here, because they make no calls.

---

## Time compression

The sweeps below run with `--speedup 20`: every stubbed service time is divided
by 20, so a graph run takes ~3.2 s instead of ~64.7 s and a 110-request sweep
point finishes in minutes instead of hours.

Ratios are preserved exactly. Absolute seconds are not, and **every compressed
number below is marked ×20**. To read a compressed second as a real second,
multiply by 20. The one distortion: the ~0.35 s of real orchestration overhead
does not compress, so it rises from 0.5% of a run to ~10% of a compressed run.
That inflates compressed latencies slightly and therefore *understates*
the sweep's measured degradation, in the safe direction.

---

## Open loop — Poisson arrivals at rate λ

```
open-loop Poisson, n=110 per point (warmup 10 discarded, 100 measured),
LLM=stub (calibrated), reviewers=parallel, ×20 time-compressed,
SLO=5 s compressed (=100 s real), seed=1234
```

Compressed seconds. Multiply by 20 for real seconds; λ_real = λ/20.

| λ (comp) | λ real | p50 | p90 | p95 | p99 | throughput | **goodput** | SLO met | max in-flight |
|---|---|---|---|---|---|---|---|---|---|
| 0.25 | 0.0125/s | 5.48 | 9.75 | 10.34 | 11.51 | 0.300 | **0.126** | 42% | 8 |
| 0.50 | 0.025/s | 17.87 | 28.29 | 30.07 | 30.24 | 0.587 | **0.029** | 5% | 21 |
| 1.00 | 0.05/s | 122.95 | 140.39 | 141.21 | 142.42 | 0.581 | **0.000** | 0% | 98 |
| 1.50 | 0.075/s | 145.53 | 156.45 | 157.00 | 157.42 | 0.574 | **0.000** | 0% | 106 |
| 2.00 | 0.10/s | 157.04 | 164.72 | 165.79 | 168.03 | 0.563 | **0.000** | 0% | 109 |

n=100 measured at every point, so p99 is reported rather than refused. Zero
failed requests at every point.

### The λ where throughput still rises and goodput collapses

**λ = 0.25 → 0.50.** Throughput rises **+96%** (0.300 → 0.587 req/s) while
goodput falls **−77%** (0.126 → 0.029 req/s) and SLO attainment goes 42% → 5%.
The service is doing nearly twice as much work and delivering a quarter as much
value. Past λ=0.5 throughput is flat-to-declining (0.587 → 0.581 → 0.574 →
0.563) while goodput is identically zero.

A throughput-only chart of this sweep would show a system scaling smoothly to
capacity and then holding. It is in fact useless to every user from λ=1.0
onward. **λ_real ≈ 0.025 req/s — about 1.5 analyses per minute — is where this
process stops being able to serve anyone within the SLO.**

Sustained capacity is ~0.58–0.61 req/s compressed = **~0.03 req/s real, ~110
graph runs per hour, in one Python process**.

---

## Closed loop — fixed concurrency

Same workload, same stub, same compression. The only change is how work arrives.

| workers | p50 | p90 | p95 | p99 | throughput | goodput | SLO met | max in-flight |
|---|---|---|---|---|---|---|---|---|
| 1 | 3.62 | 4.15 | 4.48 | 4.58 | 0.270 | 0.270 | 100% | 1 |
| 2 | 4.44 | 5.07 | 5.25 | 6.22 | 0.437 | 0.363 | 83% | 2 |
| 4 | 7.26 | 8.28 | 8.70 | 9.22 | 0.545 | 0.022 | 4% | 4 |
| 8 | 12.90 | 14.29 | 14.32 | 17.45 | 0.614 | 0.000 | 0% | 8 |

Generator-side queue delay is **exactly 0.000 s at every point**, by
construction. That is the tell.

Unloaded reference: closed c=1 p50 = 3.62 compressed = **72.4 s real**, against
65.6 s measured uncompressed and 63.75 s measured with a real LLM. The ~10%
excess is the non-compressing orchestration overhead described above.

---

## The open-vs-closed p99 gap — coordinated omission, measured

Compared at matched throughput, which is the only fair comparison:

| | load model | throughput | **p99** |
|---|---|---|---|
| closed loop | 8 workers | 0.614 req/s | **17.45 s** |
| open loop | λ=1.0 | 0.581 req/s | **142.42 s** |
| open loop | λ=2.0 | 0.563 req/s | **168.03 s** |

**A closed-loop benchmark reporting p99 = 17.45 s understates the p99 an
open-loop arrival process produces at the same throughput by 8.2× to 9.6×.**

The mechanism is visible in the in-flight column. Closed loop caps in-flight at
its worker count — 8 — because a worker cannot issue request k+1 until request
k returns. Open loop at λ=2.0 reaches **109 in flight, mean 73**: arrivals keep
coming while the service falls behind, and every one of them waits behind the
backlog. The closed-loop generator, faced with a slowing service, quietly slows
down with it and never samples that wait.

This is why the harness implements both. Either number alone is misleading:
closed loop understates tail latency by an order of magnitude, and open loop
past capacity measures a transient rather than a steady state (see caveats).

---

## The reviewer fan-out — what it actually buys

`route_to_reviewer_panel` emits three `Send` objects. That fan-out is the **only
real parallelism in the 18-node graph**; every other edge is sequential.

A serial counterfactual is constructible, so it was constructed: `fanout.py`
wraps `reviewer_panel_node` in a lock keyed by `draft_id`, serializing the three
branches of one graph run while leaving the prompts, the node bodies, the
scheduler and the LLM latency draws identical.

```
closed-loop concurrency=1, n=24 (warmup 4 discarded, 20 measured),
LLM=stub (calibrated), ×20 time-compressed, seed=1234
```

| | p50 | p90 | mean | min | max | throughput |
|---|---|---|---|---|---|---|
| reviewers **parallel** | 3.55 | 4.15 | 3.70 | 3.35 | 4.44 | 0.2700 |
| reviewers **serial** | 5.26 | 5.54 | 5.35 | 4.70 | 6.44 | 0.1870 |

**Graph-level speedup 1.48× on p50** (5.26 → 3.55), a **32.5% reduction**.
Throughput improves by the same factor, 1.44×.

Per-node spans isolate the reviewer stage itself (n=24 runs each):

| | reviewer-stage wall | sum of branch spans |
|---|---|---|
| parallel | 0.958 s (19.2 s real) | 2.647 s |
| serial | 2.668 s (53.4 s real) | 5.401 s |

**Stage-level speedup 2.79×** against a theoretical ceiling of 3.0× for three
branches. The 7% shortfall is the reviewer-judge retry path (which can
re-dispatch a branch) plus dispatch overhead.

### Cross-checked against the real-LLM run

The calibration run gives the same answer independently, with no stub involved.
Per graph run, from real spans (n=3):

| | value |
|---|---|
| reviewer stage, parallel (max of 3 branches) | 17.71 s |
| reviewer stage, serial (sum of 3 branches) | 51.15 s |
| **saving** | **33.44 s** |
| graph wall, parallel (measured) | 64.67 s |
| graph wall, serial (arithmetic) | 98.11 s |
| **speedup** | **1.52×, 34.1% reduction** |

The stub's compressed measurement (1.710 s saved × 20 = 34.2 s) and the real
run's arithmetic (33.44 s) agree to within 2%.

---

## Adjudicating "53s → 18s (~66%) via parallel reviewer fan-out"

**The claim as written is not supported, and this is the first evidence in the
project that can say so with numbers rather than by absence.**

**1. The direction and the mechanism are real.** Three independent reviewer
calls with a genuine fan-in join at meta-review. Making them parallel is the
right call and it measurably helps.

**2. The magnitude is roughly half what is claimed, and 66% is out of reach.**
Measured two independent ways, the fan-out buys **1.48×–1.52×, a 32–34%
reduction** in graph time.

Work through Amdahl on the measured serial baseline. Reviewer work is 51.15 s of
a 98.11 s serial run — a parallel fraction of **52%**. Three-way parallelism
therefore predicts

```
speedup = 1 / (0.48 + 0.52/3) = 1.53×   →   34.7% reduction
```

which is what was measured (1.48–1.52×, 32–34%). And the **ceiling**, if the
reviewer stage took literally zero time, is a **52% reduction**. So 66% is not
merely unmeasured: **no amount of reviewer parallelism can produce it**, because
48% of the graph is sequential work the fan-out never touches. The claimed
number is arithmetically unreachable for this architecture.

**3. Both absolute numbers are wrong for what they claim to describe.** With
parallel reviewers the graph takes **64.67 s**, not 18 s. Serialized, it would
take about **98 s**, not 53 s. And 64.67 s is graph-only: add parsing, upload
and the publish writes and the user-visible figure moves further from 18 s, in
the direction of the ~3.5 min in `CREATEX_PRESENTATION.md`. The 18 s figure is
closest in magnitude to a *single reviewer node* (17.05 s measured here), which
is likely where it came from.

**4. Was a "before" constructible?** Yes — but it is a counterfactual built
today, not a recovered historical baseline. There is no commit in this repo that
runs the reviewers sequentially, no recorded timing from one, and no artefact
anywhere claiming to be the 53 s baseline. `fanout.py` serializes today's code;
it does not reconstruct whatever was measured, if anything ever was.

### What the owner may and may not now claim

**May claim, with this document as the citation:**

* "Parallelizing the reviewer panel cuts graph time by **32–34%** (1.48–1.52×),
  measured two independent ways: a controlled serial-vs-parallel A/B at n=20 per
  arm, and per-node span arithmetic on a real-LLM run."
* "The reviewer stage itself goes **2.79× faster** against a 3.0× ceiling."
* "One draft analysis is **~65 s of graph time** and **$0.137** in LLM spend, at
  n=3 with real calls, on the no-corpus path."
* "The slowest node is `reviewer_panel_node` at 17.5 s; the graph is 99.5% LLM
  wait."
* "Under open-loop Poisson load this process saturates at ~0.03 req/s and
  goodput collapses to zero at roughly twice that."

**May NOT claim:**

* **66%.** It is not achievable from a 27% parallel fraction and was not
  measured.
* **18 s, or 53 s.** Neither corresponds to any measured quantity here.
* **Any end-to-end or user-visible latency.** Parsing, upload and storage are
  excluded, and parsing is not small.
* **A production capacity number.** See caveats.
* **Anything about output quality.** Every load figure comes from a stub whose
  output text is placeholder.

---

## Caveats, in descending order of how much they could change a number

**1. Parsing is excluded and is not small.** The single largest gap between this
document and user-visible latency.

**2. The load generator is in-process and shares the event loop with the system
under test.** Generator-side schedule slip is therefore not zero under load:
max 1.72 s at λ=0.25 rising to 10.44 s at λ=2.0 (compressed). It is **included**
in the reported response times — the honest choice, since a user waits through
it, but it is partly an artefact of the harness rather than of the service. In
closed loop it is exactly zero. A separate-process generator would separate the
two; this one cannot.

**3. Open loop past capacity has no steady state.** At λ ≥ 1.0 the backlog grows
monotonically for the whole run, so the reported percentiles describe a
*transient over exactly 110 requests* and would keep rising with n. They are
correct as "what the 110th arrival experienced", not as a steady-state tail.

**4. One Python process, on a laptop, CPU-saturated at ~100% during the
sweeps.** Production runs Celery with `--autoscale=3,1` gevent workers. The
capacity figure (~0.03 req/s) is a property of *this process on this host*, and
some of the degradation at high λ is CPU contention from the harness itself
rather than from the modelled LLM wait. Do not quote it as production capacity.

**5. The no-corpus path.** Four LLM nodes short-circuit. A real user's project
has documents; their run is strictly slower and strictly more expensive.

**6. Stubbed latency does not vary with input size.** The stub samples per node
from a fixed distribution, so a 141k-char manuscript and a 26k-char one draw the
same service time. Real latency grows with token count. Load-point comparisons
are unaffected (identical fixture rotation by request index); absolute
latencies for large manuscripts are understated.

**7. Six nodes are CALIBRATED from n=3 graph runs on one fixture.** Small n, one
manuscript, one time of day, one API-load condition.

**8. ×20 time compression** inflates compressed latencies by ~10% via
non-compressing orchestration overhead, in the conservative direction.

**9. `extract_claims` blocks the event loop.** `extract_claims_node` is a plain
`def` called directly from an async wrapper (`graph.py:160`), and the sync path
in `retry_utils.py:159-189` is **not** covered by `openai_semaphore` (which
guards only the async path at `:129`). While that call is in flight, every other
in-flight graph run in the process is stalled. The stub reproduces this by
blocking too. It is a real cap on per-process concurrency and it is not visible
in any single-request measurement — only under load.

---



---

## Zero Supabase writes — how that was verified

Four independent checks, not one:

1. **The real client was never in the process.**
   `app.core.supabase_client.supabase` is replaced with
   `loadgen.stubs.WriteGuardSupabase` *before* `graph.py` is imported — which
   matters, because every node does `from app.core.supabase_client import
   supabase` at module scope and would otherwise hold a reference to the real
   client. `create_client` is never called; there is no live connection to
   write through.
2. **Any write raises.** The guard raises `SupabaseWriteAttempted` naming the
   table on `insert`, `update`, `upsert` and `delete`. Every run asserted
   `write_attempts == []` at the end; the recorded value is `0` on every record
   in `results/loadgen.jsonl`. A write that had escaped the `stage_only` gate
   would have failed the run loudly, not slipped through.
3. **`stage_only` is re-asserted at graph exit**, so a node that flipped it
   mid-run would fail the request even if it never got as far as a write.
4. **`checkpoint_enabled=False`.** This one is separate on purpose — see below.

### One write path does NOT sit behind `stage_only`

The brief said every `insert`/`delete`/`update` in the graph nodes is gated on
`stage_only`. In the *nodes*, that holds. It does not hold for the graph
function itself:

```
graph.py:754   checkpoint_saver.save_checkpoint(...)   # before ainvoke
graph.py:780   checkpoint_saver.save_checkpoint(...)   # after ainvoke
graph.py:788   checkpoint_saver.delete_checkpoints(draft_id)
graph.py:806   checkpoint_saver.update_status(draft_id, "failed")
```

These run an `insert`, a `delete` and an `update` against the
`workflow_checkpoints` table (`checkpoints.py:100`, `:208`, `:249`) and are
gated on the **`checkpoint_enabled` parameter, which defaults to `True`** — not
on `stage_only`, which they never consult. A load harness that set
`stage_only=True` and trusted it would have written four rows per graph run to
production Supabase.

This harness passes `checkpoint_enabled=False`, so nothing was written. Flagged
rather than fixed: `graph.py` and `checkpoints.py` belong to another lane.

`publish_progress` also writes, to Redis rather than Supabase, at roughly 40
node boundaries per run. Stubbed to a no-op — left live it would have added ~40
failed Redis connections per run to every latency measured here.

---

## What is in the harness

```
scripts/eval/loadgen/
  loadmodel.py       Poisson arrivals; open- and closed-loop schedulers; warmup; config hash
  stats.py           summaries; percentiles imported from trace_report.metrics
  latency_profile.py per-node service times, tagged CALIBRATED / MEASURED / ASSUMED
  calibration.json   the real-LLM calibration output
  stubs.py           stubbed LLM, Supabase write guard, structured-output synthesis
  workload.py        one graph run; fixture loading
  fanout.py          the serial-reviewer counterfactual
  runner.py          CLI
  tests/             61 tests
```

Percentiles come from `trace_report.metrics.percentiles`, unchanged, so the
n-floor (`p90` needs n≥10, `p95` n≥20, `p99` n≥100) is literally the same code
this repo already uses. Below the floor the value is printed as
`n/a (n=X < 100)` rather than as a number with a caveat, because caveats get
dropped when numbers are copied into a slide.
