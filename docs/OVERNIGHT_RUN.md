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

### 🔧 Lead — the sixth identity collision, closed

P1 found that `e2e_latency.py`'s `config_hash` did not cover
`DRAFT_VALIDATION_CHEAP_PARSE`: both arms hashed to `670fccc87731` while
differing 98.8% in `upload_request` p50. Fixed — a `_MEASURED_FLAGS` tuple now
feeds the hash, verified separating (`b4e905dbf974` vs `11486242f717`), with a
regression test that iterates the tuple so new flags are covered without a new
test being written.
