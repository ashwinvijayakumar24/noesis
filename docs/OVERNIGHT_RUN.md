# OVERNIGHT_RUN.md

Autonomous run started 2026-08-01. Appended to as each agent lands. Every entry
records what was measured, its `n`, what was committed, and what it cost.

**Budget:** $50 nominal, slight overage authorised. **$22.75 spent at start.**

**Stop conditions:** all queued work complete, or a fatal bug (data loss, a
broken `main`, production contacted, or a budget breach beyond tolerance).

---

## Queue

| # | agent | scope | budget | status |
|---|---|---|---|---|
| 1 | **H2H** | agent vs Noesis DAG on shared labels — the project's own acceptance test, never run | $8.00 | 🔄 running |
| 2 | **P1** | PDF parsed twice per upload — 68.66 s p50, 39.2% of the user-visible path | $3.00 | 🔄 running |
| 3 | **P2** | `injection_v2` with write-shaped payloads — makes the gate's real-model factor measurable | $4.00 | 🔄 running |
| 4 | **P4** | first-stage recall — 86.5% of misses were never in the candidate pool | $4.00 | 🔄 running |
| 5 | **P5** | loop detection: exercise it under real pressure, or retire the claim | $4.00 | 🔄 running |
| 6 | **P3** | size-aware step allocation — 19/30 workers still starve | $3.00 | ⏸ held |

**P3 is held deliberately.** It changes `OrchestratorConfig`, which H2H is
measuring right now. Landing it mid-flight would silently change the system
under test — the exact failure this project hit five times already. It launches
when H2H reports.

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

### 🔧 Lead — the sixth identity collision, closed

P1 found that `e2e_latency.py`'s `config_hash` did not cover
`DRAFT_VALIDATION_CHEAP_PARSE`: both arms hashed to `670fccc87731` while
differing 98.8% in `upload_request` p50. Fixed — a `_MEASURED_FLAGS` tuple now
feeds the hash, verified separating (`b4e905dbf974` vs `11486242f717`), with a
regression test that iterates the tuple so new flags are covered without a new
test being written.
