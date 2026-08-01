# OVERNIGHT_RUN.md

Autonomous run started 2026-08-01. Appended to as each agent lands. Every entry
records what was measured, its `n`, what was committed, and what it cost.

**Budget:** $50 nominal, slight overage authorised. **$22.75 spent at start.**

**Stop conditions:** all queued work complete, or a fatal bug (data loss, a
broken `main`, production contacted, or a budget breach beyond tolerance).

---

## ✅ RUN COMPLETE

All seven queued agents landed. No fatal condition was hit. **≈$39.45 of $50 spent, 21% unspent.**

| | harness | Noesis backend |
|---|---|---|
| tests | **546 passed**, 30 skipped · **576** with `NOESIS_PATH` | **1,096 passed** |
| standalone verified | ✅ green with `NOESIS_PATH` unset | — |
| pre-existing failures | 0 | 2, **count unchanged** |
| uncommitted | 0 | only the user's own pre-session edits |

**The night's headline: the acceptance test ran, the agent lost as a single
actor, and orchestrated it did not.** Recall 0.0063 → 0.0362 against the DAG's
0.0496 — statistically indistinguishable (p ≈ 0.59) at 2.53× lower cost per
verified finding.

**Six of seven agents weakened or overturned a claim that was already written
down.** That is the run's actual output. Nothing here was published because it
sounded good; several things were unpublished because they did not survive being
measured twice.

### Still open, deliberately

- **Public flip** of `reviewer-agent` — needs the user. Scan clean; one
  production project ref remains in history (identifier, not credential, already
  in the deployed client bundle). `gitleaks` was not installed for a
  belt-and-braces run.
- **Merge to `master`** — `dev/harness-and-retrieval` is ahead by ~20 commits
  including three production fixes. The cofounder works off `master`.
- **Size-aware allocation vs the DAG** — not run, with reason: exhaustion does
  not bind on the Noesis adapter (36/36 workers complete), so a third comparison
  would have measured noise.
- **The embedding model** — `FIRSTSTAGE.md` established it as the only remaining
  retrieval lever. A modelling project, not a config change.

---

## Queue

| # | agent | scope | budget | status |
|---|---|---|---|---|
| 1 | **H2H** | agent vs Noesis DAG — the acceptance test | $8.00 | ✅ $2.21 |
| 2 | **P1** | PDF parsed twice per upload | $3.00 | ✅ $2.00 |
| 3 | **P2** | injection_v2, write-shaped payloads | $4.00 | ✅ $3.55 |
| 4 | **P4** | first-stage recall | $4.00 | ✅ $1.15 |
| 5 | **P5** | loop detection: exercise or retire | $4.00 | ✅ $1.64 |
| 6 | **P3** | size-aware step allocation | $3.00 | ✅ $2.39 |

Two more were added mid-run and are logged below: **H2H2** (orchestrated agent
vs DAG, $3.77) after H2H's single-agent loss made the orchestrated comparison the
obvious question, and the lead's own fixes.

*P3 was held at the start rather than launched, because it changes
`OrchestratorConfig` — which H2H was measuring at the time. Landing it mid-flight
would have silently changed the system under test, the exact failure this project
had already hit five times. It launched once H2H reported, and shipped behind a
default-off flag so H2H2's measurement was untouched too.*

---

## Standing rules for every agent tonight

Unchanged from the day's work, restated because they are what makes the output
worth anything:

1. Every metric carries its `n`. Every `recall@k` carries its **recomputed** ceiling.
2. Results append-only, keyed by config hash. Nothing is differenced across hashes.
3. A capability not observed firing in the logs is not a capability.
4. Negative results ship. A defense that does not reduce ASR, an optimisation
   that does not help, a detector that never binds — all get published as such.
5. Nothing is weakened to make a result land.
6. Production Supabase is never contacted. Local only.

---

## Log

### Start — 2026-08-01

State at handoff: harness **475 tests** green and standalone; Noesis backend
**1068 passed** with 2 known pre-existing failures. Both repos pushed. Board
regenerated and verified byte-identical across two runs.

Completed before tonight: Phase A, Phase B, Phase B.5, the retrieval track
(reranking, contentless, chunk ceiling), user-visible latency, durable resume,
and three production fixes (`663e0f6` reranker no-op, `0ee82d5` fixture label
leak, checkpointer manuscript leak).

### ✅ P5 — loop detection resolved · `13d4406` · $1.6412 of $4.00

**Conclusion: keep the code, downgrade the claim. No threshold changed.**

Mined all 240 published runs, free, by replaying the loop's own bookkeeping:

| channel | threshold | observed max | n=240 |
|---|---:|---:|---|
| repeated identical call | 3 | **1** | streak 1 in 240/240 |
| consecutive empty | 3 | 2 | 0→237, 1→2, 2→1 |
| oscillation | 3 cycles | 2 | 1 cycle→239, 2→1 |

**No run ever issued the same call signature twice in a row.** There is no
distribution for a threshold to move into. The one 2-cycle oscillation was in an
injected-fault arm, not the healthy path.

Then built five conditions to *induce* looping — 30 real `gpt-5.2` runs,
changing the task or what a tool returns, never a threshold, never a scripted
model. `empty_search` fired `loop_no_result` **6/6 (1.0000)**. The other four
fired nothing. **Combined n=270, max identical streak still 1.** Under failure
`gpt-5.2` *varies* — different section, different phrasing — and dies on the
step budget.

- **`loop_no_result` is real but fixture-only.** `NoesisSearch` has
  `similarity_threshold=0.0`, so an empty result set is structurally unreachable
  in production and the channel cannot fire there.
- **No threshold change**, with both directions reported: repeat 3→2 gains
  nothing (max streak is 1); oscillation 3→2 costs a 0.0042 false-positive rate
  on healthy runs and gains nothing. *"A change with no effect in either
  direction would be justified by wanting the feature to do something, not by
  evidence."*
- **Compaction's zero is explained, not bare.** Peak prompt across 240 runs is
  **10,092 tokens** against a 13,600 trigger — a workload bound. Under a real
  long-horizon workload (section-by-section, 24 steps, 16k ceiling) compaction
  binds **2 of 6 runs, 4 events**. One 24-step run still never compacted (peak
  8,405), kept as the counterexample: step count proxies context growth, it does
  not substitute for it.
- A measurement bias in the analyser was found and corrected: detection runs
  *before* execution, so a bound run's deciding call never reaches the trace.
  Pinned by a test that drives the real loop and asserts the analysis says
  "fired" exactly when the loop said `LOOP_DETECTED`.

`RESUME_BULLETS.md`'s claim table updated: the blanket "never fires" was itself
an overclaim.

### ✅ P1 — the double parse, and a baseline that was environmental · `ddf90b5` · $1.9953 of $3.00

Fixed behind `DRAFT_VALIDATION_CHEAP_PARSE`, **default off**. `upload_request`
p50 **4.33 s → 0.05 s (−98.8%)**, parse calls 2 → 1 every run, n=4/arm,
interleaved A/B/A/B.

**The task's premise did not survive.** Same fixture, same config hash, same
parser, today: baseline **117.87 s** and parse #1 **4.28 s**, against 212.82 s
and 52.38 s when the baseline was taken. Cause: Docling was resident and
OOM-killing GROBID during those sessions. **Parsing on this host is bimodal by
an order of magnitude — 39.2% of the path then, 7.4% now.** The honest
restatement is a rule, not a number: *the change removes exactly one parse; its
value is the cost of one parse, measured at both 4.3 s and 52.4 s on this
machine.*

- **No user-visible delta is claimed.** p50 says −6.49 s, mean says +1.10 s, and
  the *untouched* graph stage moved +7.37 s between arms. Not resolvable.
- **My framing was wrong and was corrected.** I called cache-and-reuse the safer
  option; it is not, because `validate_file_format` runs in FastAPI and
  `ingest_draft` in Celery. Threading an artifact across that boundary needs new
  cross-process state — **and would have measured as a win in this harness and
  not in production**, since the harness calls the task body inline.
- **Equivalence proven by byte-level hash**, not by inspection: all 8 drafts
  across both arms produce one distinct parse-artifact fingerprint.
- **What was given up, stated:** validation now asks "is this an openable PDF
  with ≥50 chars" rather than "will GROBID parse this". 24 inputs, 23
  agreements, 1 disagreement — exactly the case the code predicts, pinned by a
  test.

### ✅ P4 — first-stage recall was the wrong lane · `429c602` · $1.15388 of $4.00

**Refutes a conclusion this project had already published**, including in
`WAVE_LOG.md` and `RESUME_BULLETS.md`. Both corrected.

Of the 6,011 "never pooled" misses: **98.5% were pooled for some *other*
query**; 0.33% never ingested; 1.18% dark to every query. `chunk_oversample`
counts **chunks** while the relevance unit is **documents** — 50 chunks collapse
to a median 20 distinct documents against a median 25 relevant, so for **230 of
338 queries the pool is smaller than the ground truth by construction**.

**Removing the depth limit entirely moves recall@10 +0.0027** (0.2200 → 0.2227)
and `retrieval_failure` 6,011 → 20, with the failures simply relabelling as
`ranking`. **A perfect reranker over the shipped pool tops out at 0.2982 and
dense already reaches 73.8% of it.** The reranking lane is closed.

Not levers, each measured: depth (**0.0000** from 120 chunks to the whole
corpus), chunk granularity (**+0.0013** over 17,844 re-embedded sub-chunks,
nothing written to the shared DB, digest verified both ends), query expansion
(absent from this path, not suppressed), embedding split (both sides are
`3-large` @1536, verified against the live index).

**The largest term is the label design:** 69.4% of cited documents rank top-10
for *some* claim in their manuscript (median rank 4) versus 18.9% per-claim
(median rank 53). Attainable fraction is flat at 43–52% from k=1 to k=50 and
relevant/irrelevant separation is **under 1σ** — the signature of a weak scoring
function. **The remaining lever is the embedding model: a modelling project, not
a config change.**

Also found: `match_document_chunks` pins `hnsw.ef_search = 80` inside its own
body so callers cannot sweep it, and **0.0010 of the published 0.2200 → 0.2227
is ANN approximation rather than depth**.

### ✅ H2H — the acceptance test ran, and the agent lost · `39518e4` · $2.2057 of $8.00

`AGENT_HARNESS_PLAN.md` set the criterion: *"If it can't be scored against the
Noesis DAG on the same labels, it's a toy. Kill it."* It can now be scored. It
scores badly.

| | agent | Noesis DAG | ratio |
|---|---:|---:|---:|
| severity-weighted recall, per run | **0.0063** (n=12) | **0.0496** (n=6) | 7.87× |
| pooled over all runs | 0.0098 (n=212) | 0.0815 (n=212) | 8.29× |
| **distinct units matched** | **2 of 212** | **21 of 212** | |
| $ / finding | $0.0045 (n=56) | $0.0094 (n=99) | 2.09× |
| **$ / verified finding** | **$0.0062** (n=41) | **$0.0114** (n=82) | **1.84×** |
| wall clock / manuscript | 12.74 s (n=12) | 74.08 s (n=6) | 5.81× |

> ↻ **Corrected 2026-08-01 — the recall rows above were computed at an
> uncalibrated prefilter and understate both arms by roughly 2×.** The table is
> unaltered; those runs are real and their config hash pins them to
> `COS_THRESHOLD = 0.55`.
>
> That threshold has since been calibrated on **n = 266** hand-labelled pairs
> (`scripts/eval/ceiling/CALIBRATION.md`): its prefilter recall is **0.202**
> [0.081, 0.424] against **0.842** [0.625, 0.945] at the adopted **0.44**. Four
> in five true matches never reached the confirmation judge. Re-baselined at
> 0.44 on the ceiling corpus: DAG **61 ± 7 / 212**, agent **24 ± 3 / 212**,
> union **77 ± 8 / 212**; against the **76** defect-addressable units, DAG
> **29 ± 3 (38.2%)**, agent **12 ± 2 (15.8%)**, union **37 ± 4 (48.7%)**.
> **The pipeline did not change. Only the measurement did.**
>
> Two things this does *not* do. It does not overturn the ordering — the DAG
> still matches ~2.5× the agent's units. And it does not license subtracting
> these numbers from the ones above: those are severity-weighted recalls on the
> head-to-head corpus, these are unit counts on the ceiling corpus. Different
> config hashes, never differenced.
>
> The last bullet in this section — "0.0815 means 92% of weighted human concerns
> are missed" — should now read: against all 212 units the union reaches
> **36.3%**, and against the 76 addressable ones **48.7%**. Both denominators
> travel together; 27 of the 212 are segmentation fragments no system can match.

- **The DAG won degraded.** It ran with an empty corpus, so `search_literature`
  and `detect_gaps` returned nothing.
- **The per-run mean difference is not significant** (Welch t=1.98, df=5.4,
  p≈0.10). The evidence is the *count* — 2 units versus 21 — not the mean, and
  the report says so rather than leaning on the ratio.
- **Confounds bounded, not asserted.** $0.6152 was spent re-running the matcher
  at a relaxed cosine threshold to test whether finding length explained the gap
  (DAG findings average 643 chars, agent 214): ratio 8.3× → **5.4×, ordering
  unchanged**. The largest uncontrolled confound points *against* the DAG — it
  reads **+24.3% more text**, so only **62.2% of its anchors exist in the
  agent's haystack**.
- **The DAG's 0.0000 unverified-quote rate is by construction, not virtue** —
  `strip_unanchored_findings` deletes non-verbatim anchors upstream.
- **Both systems are bad in absolute terms:** 0.0815 means **92% of weighted
  human concerns are missed**.

Not settled by this: it measured the **single** agent. The orchestrated arm
yields 5× more findings, so H2H2 was dispatched to run that comparison.

### ✅ P2 — `injection_v2`, write-shaped, and an arm with no power · `97272c2` · $3.5544 of $4.00

30 new cases, dual content-hashed, every payload demanding a **side-effecting
call** rather than a sentence. Success predicates are state — an artifact
carrying the case's canary, an artifact on the wrong draft, an out-of-contract
call — never sentiment.

**Forced compliance, `OWNED` ownership table** (removing the free win C4 found,
where the fixture's ownerless draft made authz do the gate's job):

| arm | unauthorized write | legitimate write |
|---|---|---|
| gate-off | **1.0000 (n=30)** | 1.0000 (n=6) |
| gate-on, deny-all | **0.0000 (n=30)** | 0.0000 (n=6) |
| gate-on, reviewing approver | 0.0000 (n=30) | **1.0000 (n=6)** |
| gate-off, ownerless draft | 0.0000 — **authz**, not the gate | — |

Rows sum to 1.0 per arm, asserted. Gate-parked runs carry zero policy decisions;
authz-denied runs carry zero suspensions.

**Real model: ASR 0.0000 (n=30) — and the report says why that is uninformative.**
The *benign* legitimate-write rate is also **0.0000 (n=10)**: `gpt-5.2` never
calls `artifact.write` in this harness even unattacked, with 4+ findings
available to record. **A rate cannot be raised off a floor the instrument cannot
distinguish from the floor.** Written up as a power problem rather than banked as
a safety result.

**What actually bounds the blast radius is tool design.** `draft_id` and `actor`
are bound at construction, so **6 of 30 predicates are unreachable in every arm
including gate-off** — the injected text has no argument to name. Reported as its
own row, not counted as prevention.

**One defect, disclosed rather than deleted:** the first paid run delivered
nothing to 22 of 30 cases, because `lit.search`'s 200-char `brief` cap ate the
canary behind 177 characters of benign lead. *"That cost $2.4303 to discover
something a free check finds in four seconds."* Fixed, and a delivery check now
runs before anything is bought. Pre-fix records stay in the append-only sink
under their own corpus hash and must not be differenced against the fixed ones.

### ✅ P3 — size-aware allocation, and a transferable scheduling result · `b7bbfe9` · $2.3925 of $4.00

Behind `SIZE_AWARE_STEP_ALLOCATION`, **default off**, so H2H2's in-flight
measurement was untouched.

**Unit: pages at the reader's own page size.** `section_pages` is computed with
the *identical* expression `get_section` uses for `total_pages`, so the planner's
number is literally the count of `get_section` calls a worker will make — no
conversion for the orchestrator to guess. A conformance test asserts agreement
against `get_section` itself, not against the formula.

**Requirement `max(3, ceil(pages / 2) + 2)`** — one step to orient, one to write,
that writing step being exactly the one `STEP_BUDGET` was removing. Parallel read
width assumed at the pessimistic end of the observed 1–4, because the error is
asymmetric: over-funding wastes spare steps, under-funding by one costs the
entire output.

| n=9 orchestrations/arm | flag off | flag on |
|---|---:|---:|
| workers | 45 | 26 |
| `budget_exhausted` | **0.6222** | **0.1154** |
| producers | 0.378 | **0.885** |
| findings / worker | 2.333 | **6.308** |
| $ / finding | 0.0128 | **0.0064** |
| **$ / verified finding** | 0.0145 | **0.0079** |

**The generalisable finding — fund fewer workers adequately, not all workers
partially**, measured on two independent populations:

| population | adequate produce | under-funded produce | Fisher p |
|---|---|---|---|
| W1's pool-40+60 records (n=60) | 0.8182 | 0.4211 | **0.0033** |
| this run, both arms (n=71) | 0.7619 | 0.2759 | **0.000076** |

- **The cost is booked, not netted out:** 19 concerns dropped as unaffordable
  across 9 orchestrations, recorded as `CONCERN_DROPPED_UNAFFORDABLE` and
  surfaced in `uncovered_concerns`. That trade was already being made silently by
  workers that consumed a synthesis slot and returned nothing.
- **Fabrication moved the wrong way and is reported that way:** 0.1143 (n=105) →
  0.1801 (n=161), Fisher **p = 0.167** against the matched contemporaneous
  control — not distinguishable, but the point estimate worsened. Most of the gap
  isolates to one LaTeX-heavy manuscript sitting at ~0.3 in *both* arms;
  excluding it, 0.0385 → 0.1000, p = 0.144.
- **Worker count stayed non-degenerate and got wider:** `4,5,6` off versus
  `4,3,1,4,4,2,4,3,1` on. Two N=1 runs occurred, both on a 38-page scope needing
  21 steps — they produced findings and did not exhaust, but a one-worker run has
  no isolation claim, and on the longest manuscript **the pool, not the
  allocator, is now the binding constraint**. Visible in the event log rather
  than hidden in five silent workers, and explicitly not fixed.
- Residual: the 3 workers still exhausting were funded **at or above**
  requirement, so `ceil(pages/2)+2` is not sufficient for everyone — just for
  23/26 instead of 17/45.
- The label-leak guard was checked explicitly, not assumed:
  `section_pages` derives from `section.text` alone and
  `test_profile_is_computable_from_the_manuscript_alone` still passes.

### ✅ H2H2 — orchestration closes the gap, and the earlier verdict is overturned · `075666c` · ≈$3.77 of $5.00

| | single agent | **orchestrated** | DAG |
|---|---:|---:|---:|
| recall, per-run mean | 0.0063 (n=12) | **0.0362 (n=12)** | 0.0496 (n=6) |
| pooled at matched r=2 | 0.0000 (n=212) | **0.0578 (n=212)** | 0.0815 (n=212) |
| **units matched of 212** | 2 | **19** | 21 |
| $ / finding | $0.0045 | **$0.0041** (n=237) | $0.0094 |
| **$ / verified finding** | $0.0062 | **$0.0045** (n=217) | $0.0114 |
| unverified-quote rate | 0.2679 | **0.0805** (n=236) | 0.0000 *by construction* |

> ↻ **Corrected 2026-08-01 — same correction as H2H above: every recall row here
> is at the uncalibrated `COS_THRESHOLD = 0.55`.** Calibrated to **0.44** on
> n = 266 pairs, the ceiling-corpus re-baseline gives DAG **61 ± 7 / 212** and
> agent **24 ± 3 / 212** (union **77 ± 8**), and against the **76** addressable
> units DAG **29 ± 3 (38.2%)** and agent **12 ± 2 (15.8%)**. **The pipeline did
> not change; only the measurement did.** The orchestrated arm was not re-run at
> 0.44 — its findings are not in the ceiling corpus — so its row stays a
> 0.55-era figure and must not be compared against the corrected ones.

**The 7.87× recall gap becomes 1.37×, and at these `n` the orchestrated agent
and the DAG are not distinguishable** — Welch t = 0.57, df = 7.3, **p ≈ 0.59**.
Against the single agent the improvement *is* distinguishable (5.72×, p ≈ 0.016,
flagged as cross-session).

**The sentence H2H would have earned is not supported.** The architecture does
not lose at every configuration measured. The single-actor configuration lost.

- **The task's own hypothesis was refuted in direction.** It predicted
  orchestration would close the gap *but cost ~3× more per verified finding*. It
  closes the gap and costs **2.53× less**.
- **The DAG arm was not re-run**, and the reason is recorded: the Noesis checkout
  has moved off the sha the baseline was taken at and carries uncommitted
  workflow edits, so a fresh arm would not be comparable to the recorded one.
  Read by hash `84bff044a0e6a8df`, with the label snapshot asserted equal at run
  time and `noesis_pipeline_version` matching byte-for-byte. Residual booked as
  a confound (the judge now spans two sessions), not waved away.
- **Confound method validated before use:** the anchor-reachability calculation
  reproduces H2H's published 62.2% exactly (n=82) before being trusted for the
  new figures — per *worker* 16.1%, per *arm* union **59.8%**. Context isolation
  costs **2.4 points, not a third**.
- **New confound `O2`, against the agent: 4–6 of 8 triaged concerns per run are
  never dispatched.** Structural, and recorded rather than netted out.
- **`N1` no longer bounded at zero:** 3 of 320 tool calls were `lit.search`
  (0.94%), against 0 of 136 for the single agent.
- **36/36 workers `complete`, 0 exhausted** — `WORKER_YIELD.md`'s 19/30 residual
  does not bind here, because the Noesis adapter plans 2–4 workers rather than
  4–6 and the 40-step pool splits fewer ways.
- **$1.27 of spend bought nothing:** a `TypeError` in an *optional* prefilter
  sensitivity destroyed a completed, scored 12-run arm before the sink write.
  Fixed by ordering — row and detail dump first, diagnostics last, inside a
  `try`. Disclosed rather than absorbed.

**Not run, with the reason: size-aware allocation (P3) against the DAG.** Its
benefit is fixing budget exhaustion, and exhaustion does not bind on the Noesis
adapter (36/36 complete). A third comparison would most likely measure noise, so
the budget was not spent.

### 🔧 Lead — the sixth identity collision, closed

P1 found that `e2e_latency.py`'s `config_hash` did not cover
`DRAFT_VALIDATION_CHEAP_PARSE`: both arms hashed to `670fccc87731` while
differing 98.8% in `upload_request` p50. Fixed — a `_MEASURED_FLAGS` tuple now
feeds the hash, verified separating (`b4e905dbf974` vs `11486242f717`), with a
regression test that iterates the tuple so new flags are covered without a new
test being written.
