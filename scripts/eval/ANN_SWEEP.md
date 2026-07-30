# HNSW sweep — the recall-vs-latency curve for the vector index

**Date:** 2026-07-30 · **Corpus:** 118 documents / 2124 chunks, project
`e7a1c0b0-0000-4000-8000-000000000001`, local pgvector (pg17) on host port 5433 ·
**n = 59 queries** for every metric below.

Production runs `idx_document_chunks_embedding` as HNSW / `vector_cosine_ops` at
pgvector defaults (`m = 16`, `ef_construction = 64`) and sets
`hnsw.ef_search = 80` inside `match_document_chunks` and
`match_single_document_chunks` (migration 036, lines 107–109 and 140). None of
those three numbers was chosen: two are library defaults and one is a value
someone typed once. This document turns them into a measured operating point.

Reproduce:

```
cd scripts/eval
python3 -m ann_sweep.run_ann_sweep --what all           # k = 50 (eval depth)
python3 -m ann_sweep.run_ann_sweep --what ef --k 10     # k = 10 (production depth)
```

Results append to `scripts/eval/results/ann_sweep.jsonl`, one record per
configuration, keyed by parameters + corpus fingerprint. Nothing is overwritten.

---

## 0. The headline, before the tables

**At `LIMIT ≥ 40`, Postgres declines the HNSW index entirely and runs an exact
sequential scan.** Not "the index is slow" — the index is not consulted. The
plan is `Seq Scan → Sort (top-N heapsort)`. Every `ef_search` value from 10 to
640 therefore produces byte-identical results and identical latency at that
depth, because `ef_search` is a parameter of a code path that never runs.

The crossover is between `LIMIT 30` and `LIMIT 40`. Production's real call sites
pass `match_count` of 3, 5, 6, or 10 (`rag_retrieval.py:164`,
`coverage_analysis.py:93,1019`, `citation_management.py:738`), which are **below**
the crossover — so production *does* use the index. The retrieval eval harness
asks for 50 chunks (k=10 × oversample 5), which is **above** it, so
`retrieval/BASELINE.md`'s "dense (pgvector HNSW, cosine)" numbers were in fact
measured against an exhaustive scan. That is a labelling error in the baseline,
not a wrong number: exact search is a legitimate retriever, it just is not HNSW.

---

## 1. Does the planner use the index? (`record_type: planner_choice`)

Measured at `ef_search = 80`, the production query body verbatim.

| LIMIT | plan |
|---|---|
| 1 | `Index Scan using idx_document_chunks_embedding` |
| 3 | `Index Scan using idx_document_chunks_embedding` |
| 5 | `Index Scan using idx_document_chunks_embedding` |
| 10 | `Index Scan using idx_document_chunks_embedding` |
| 15 | `Index Scan using idx_document_chunks_embedding` |
| 20 | `Index Scan using idx_document_chunks_embedding` |
| 25 | `Index Scan using idx_document_chunks_embedding` |
| 30 | `Index Scan using idx_document_chunks_embedding` |
| **40** | **Seq Scan — index NOT used** |
| **50** | **Seq Scan — index NOT used** |
| **100** | **Seq Scan — index NOT used** |

An HNSW index scan has a high startup cost and a low per-row cost; a sequential
scan is the reverse. On 2124 rows the lines cross around LIMIT 35.

`ef_search` moves the crossover too, because it raises the index scan's
estimated cost: at `LIMIT 10`, `ef_search ≤ 80` plans an index scan and
`ef_search ≥ 160` plans a sequential scan (table 3B below). Raising `ef_search`
past 80 does not buy more recall here — it buys a different plan.

---

## 2. Exact sequential scan — the recall = 1.0 ceiling

`SET LOCAL enable_indexscan = off; SET LOCAL enable_bitmapscan = off`. Plan
confirmed to contain no index scan (the harness refuses to record an "exact"
point whose plan used an index).

| | k = 50 | k = 10 |
|---|---|---|
| ANN recall vs exact | 1.0000 *by definition* | 1.0000 *by definition* |
| recall@10 vs labels | 0.3488 | 0.2054 |
| NDCG@10 vs labels | 0.6245 | 0.4461 |
| MRR vs labels | 0.8972 | 0.8927 |
| server p50 / p95 (ms) | 23.19 / 48.56 | 16.70 / 19.89 |
| client p50 / p95 (ms) | 25.47 / 52.79 | 18.35 / 22.08 |

The exact-scan p50 was measured three times across three sweep runs: **17.8,
23.2, 27.4 ms**. That ±25% spread is machine noise (a laptop under other load),
and it bounds how finely any latency claim here may be read. It does not touch
the conclusions, which turn on a 12–20× gap.

---

## 3. `ef_search` sweep

Query-time knob, existing production index, no rebuilds.
**n = 59 queries.** Latency: 3 timed repetitions per query = 177 samples, 59
warmup executions discarded, server-side `EXPLAIN (ANALYZE, TIMING OFF)`
"Execution Time". Percentiles are nearest-rank (`ceil(q·n)`), so every value is
an observed execution. **No p99** — with 177 samples the 99th percentile is one
sample from the maximum.

Two recalls, deliberately in separate columns:
* **ANN@k** — overlap with exact search's top-k. A property of the **index**.
* **R@10 / NDCG@10 / MRR** — against citation labels. A property of the **whole
  system**; its ceiling is far below 1.0 by construction (see
  `retrieval/BASELINE.md` §"recall@k is capped well below 1.0").

### 3A. k = 50 — planner free (what the eval harness executes)

| ef_search | ANN@50 | ANN@10 | R@10 | NDCG@10 | MRR | p50 ms | p95 ms | plan |
|---|---|---|---|---|---|---|---|---|
| 10 | 1.0000 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 20.78 | 28.59 | seq scan |
| 20 | 1.0000 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 20.99 | 30.92 | seq scan |
| 40 | 1.0000 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 20.62 | 32.71 | seq scan |
| **80 (PROD)** | 1.0000 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 20.06 | 29.44 | seq scan |
| 160 | 1.0000 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 20.47 | 31.32 | seq scan |
| 320 | 1.0000 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 23.80 | 50.04 | seq scan |
| 640 | 1.0000 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 23.25 | 43.09 | seq scan |

Seven identical rows. `ef_search` is inert at this depth because no HNSW search
happens.

### 3B. k = 50 — index forced (`enable_seqscan = off`, other indexes dropped inside a rolled-back transaction)

This is the actual HNSW curve. It describes the **index**, not what production
executes at this depth.

| ef_search | ANN@50 | ANN@10 | R@10 | NDCG@10 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|
| 10 | 0.2000 | 0.8898 | 0.2081 | 0.4468 | 0.8559 | 0.68 | 1.84 |
| 20 | 0.4000 | 0.9458 | 0.2853 | 0.5496 | 0.8571 | 0.80 | 1.84 |
| 40 | 0.7983 | 0.9797 | 0.3410 | 0.6175 | 0.8806 | 1.29 | 2.12 |
| **80 (PROD)** | **0.9844** | 0.9932 | 0.3500 | 0.6277 | 0.8972 | **1.64** | **2.36** |
| 160 | 0.9986 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 5.27 | 17.78 |
| 320 | 1.0000 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 3.90 | 7.57 |
| 640 | 1.0000 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 5.49 | 9.36 |

`ANN@50` below 1.0 at low `ef_search` is expected: `ef_search` bounds the
candidate list, and pgvector cannot return 50 good neighbours from a list of 10.
The rule of thumb `ef_search ≥ 2k` is visible here — `ef_search = 10` returns
only 20% of the true top-50.

Note `ef_search = 80` scores *higher* label recall (0.3500) than exact search
(0.3488). That is not the index beating the ground truth; it is a ±0.001
coincidence of which near-tied chunk landed in the top 10. Do not read it as a
win.

### 3C. k = 10 — production's real depth, planner free

| ef_search | ANN@10 | R@10 | NDCG@10 | MRR | p50 ms | p95 ms | plan |
|---|---|---|---|---|---|---|---|
| 10 | 0.8898 | 0.2081 | 0.4468 | 0.8559 | 0.36 | 0.65 | HNSW |
| 20 | 0.9458 | 0.2024 | 0.4414 | 0.8559 | 0.46 | 0.70 | HNSW |
| 40 | 0.9797 | 0.2050 | 0.4465 | 0.8757 | 0.66 | 1.13 | HNSW |
| **80 (PROD)** | **0.9932** | 0.2071 | 0.4505 | 0.8927 | **1.03** | **1.61** | HNSW |
| 160 | 1.0000 | 0.2054 | 0.4461 | 0.8927 | 16.94 | 19.48 | **seq scan** |
| 320 | 1.0000 | 0.2054 | 0.4461 | 0.8927 | 15.88 | 18.93 | **seq scan** |
| 640 | 1.0000 | 0.2054 | 0.4461 | 0.8927 | 15.90 | 27.96 | **seq scan** |

Raising `ef_search` above 80 at k=10 makes the query **16× slower**, because the
cost model abandons the index. The forced-index variant of the same grid
(3B's method at k=10) shows what the index alone would have done: 1.66 ms at
160, 2.29 at 320, 3.36 at 640 — i.e. even without the plan flip, everything past
80 is pure cost for +0.007 ANN recall.

---

## 4. `m` × `ef_construction` sweep

Each candidate is built under its own name on the **same** table, measured with
every other index dropped inside a transaction that is always rolled back, then
dropped. `ef_search = 80` held fixed. `enable_seqscan = off` throughout, because
the planner declines every one of these indexes at k = 50 — without forcing,
all eleven rows would be the same sequential scan.

Grid points with `ef_construction < 2m` are skipped (pgvector does not honour
them as specified). **n = 59 queries**, k = 50.

| m | ef_construction | build s | index size | ANN@50 | ANN@10 | R@10 | NDCG@10 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|
| 8 | 32 | 0.92 | 16.6 MB | 0.9647 | 0.9881 | 0.3473 | 0.6254 | 0.8960 | 2.22 | 4.49 |
| 8 | 64 | 1.10 | 16.6 MB | 0.9749 | 0.9932 | 0.3473 | 0.6250 | 0.8972 | 1.21 | 2.73 |
| 8 | 128 | 1.22 | 16.6 MB | 0.9793 | 0.9949 | 0.3500 | 0.6271 | 0.8972 | 1.14 | 1.52 |
| 8 | 256 | 1.92 | 16.6 MB | 0.9831 | 0.9983 | 0.3500 | 0.6272 | 0.8972 | 1.24 | 1.63 |
| 16 | 32 | 0.80 | 16.6 MB | 0.9773 | 0.9831 | 0.3506 | 0.6258 | 0.8816 | 1.33 | 1.92 |
| **16** | **64 (PROD)** | **1.14** | **16.6 MB** | **0.9837** | 0.9915 | 0.3506 | 0.6288 | 0.8972 | 1.28 | 1.80 |
| 16 | 128 | 1.56 | 16.6 MB | 0.9902 | 0.9983 | 0.3515 | 0.6269 | 0.8972 | 1.35 | 1.72 |
| 16 | 256 | 2.32 | 16.6 MB | 0.9936 | 0.9983 | 0.3488 | 0.6246 | 0.8972 | 1.44 | 2.61 |
| 32 | 64 | 1.94 | 16.6 MB | 0.9973 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 1.69 | 2.59 |
| 32 | 128 | 2.71 | 16.6 MB | 0.9973 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 1.81 | 2.59 |
| 32 | 256 | 3.98 | 16.6 MB | 0.9980 | 1.0000 | 0.3488 | 0.6245 | 0.8972 | 4.10 | 7.50 |

Three things worth saying plainly:

1. **Index size is identical — 17,408,000 bytes — at every point.** Not
   approximately: exactly. 17,408,000 / 8192 = 2125 pages for 2124 vectors, i.e.
   one page per vector. A 1536-dimensional `float4` vector is 6 KB, so it and its
   neighbour list share an 8 KB page whatever `m` is. **`m` has no effect on
   index size at 1536 dimensions on this corpus.** Any claim that raising `m`
   "costs disk" is unsupported here.
2. **Build time is the only real cost that moves**, and it moves modestly:
   0.80 s to 3.98 s, a 5× span over the whole grid. At 2124 chunks all of it is
   noise against a single OpenAI embedding call.
3. **The label metrics barely move at all.** R@10 spans 0.3473–0.3515 across the
   entire grid — a range of 0.004, which on 59 queries is well inside noise. The
   build parameters are not where this system's retrieval quality lives.

---

## 5. Index-set restoration — before and after

Before the sweep:

```
Indexes:
    "document_chunks_pkey" PRIMARY KEY, btree (id)
    "idx_document_chunks_document_id" btree (document_id)
    "idx_document_chunks_embedding" hnsw (embedding vector_cosine_ops)
    "idx_document_chunks_fts" gin (content_tsvector)
    "idx_document_chunks_project_id" btree (project_id)
```

After the sweep: **identical, byte for byte, definitions included.** The CLI
compares `pg_indexes` snapshots (name *and* `indexdef`) and exits non-zero if
they differ; it also refuses to leave any `ann_sweep_hnsw_*` index behind and
sweeps up strays from an interrupted previous run before starting.

The production index is never dropped outside a transaction that is rolled back.
Postgres DDL is transactional, so the isolation trick that makes the build sweep
meaningful (drop every other index so the planner has no choice) costs nothing
and risks nothing: an aborted backend rolls it back for us.

Corpus after: 118 documents / 2124 chunks — unchanged.

---

## 6. Recommended operating point

**Keep `ef_search = 80`. It is defensible — by luck rather than by design, and
only because production queries shallowly.**

At k = 10, the depth production actually uses, `ef_search = 80` sits exactly on
the knee: ANN recall 0.9932 at 1.03 ms p50, versus 0.9797 at 0.66 ms (40) and
1.0000 at 16.94 ms (160, where the plan flips). Nothing in the grid dominates
it. The honest summary is that a defensible value was reached by accident, and
it is now measured rather than assumed.

**Keep `m = 16`, `ef_construction = 64`.** ANN@50 0.9837 for 1.14 s of build and
no disk cost difference. `m = 32` buys ANN@50 0.9973 for 1.7× the build time and
30% more query latency, and buys **nothing** on the label metrics. At this corpus
size the build parameters are not a lever.

**The one change actually worth making** is not a parameter. It is the retrieval
depth: the eval harness's k = 50 sits past the planner's crossover, so it
measures exhaustive search and calls it HNSW. Either drop the oversample to keep
k under ~30, or stop describing that path as HNSW. Right now
`retrieval/BASELINE.md`'s dense row is an exact-scan result wearing an index's
name.

---

## 7. Does any of this generalise? Mostly no.

**2124 chunks is far too small for these numbers to transfer.** Specifically:

* The crossover at LIMIT ≈ 35 is a property of *this* row count. On 10× the
  corpus the sequential scan gets 10× more expensive while the HNSW scan barely
  changes, so the crossover moves far above any realistic k and the index gets
  used everywhere. **The "Postgres won't use the index" finding is a small-corpus
  finding and should be expected to disappear.**
* ANN recall reaching 1.0000 at `ef_search ≥ 320` is trivially achievable when
  the whole graph is 2124 nodes. On a large corpus, recall at fixed `ef_search`
  falls, and the knee moves right.
* Index size being flat in `m` is a consequence of 1536 dimensions filling an
  8 KB page on its own, which *does* generalise — but the build-time ordering
  does not; HNSW build is super-linear and the 5× span here would widen.
* Sub-2 ms latencies are dominated by fixed per-query overhead at this size, so
  the *ratios* between rows are more trustworthy than the absolute values.

What does survive scaling: the *method*. The sweep is re-runnable
(`--what all`), results are append-only and stamped with the corpus fingerprint,
so re-running after the corpus grows produces a comparable curve beside this one
rather than replacing it.

---

## 8. Measurement method, in full

* **Queries:** 59, from `retrieval/queries.py` over the four manuscripts whose
  reference PDFs are the 118 documents in the index (`10eQ4Cfh8p`, `9ceadCJY4B`,
  `ApjY32f3Xr`, `BQvbL2sFQx`). Other directories exist under `corpora/` because
  another lane is downloading PDFs; those are not ingested and are excluded.
* **Query embeddings:** `text-embedding-3-large` at 1536 dims — the same model
  `ingest.py` built the index with — computed once and cached to
  `cache/ann_sweep_embeddings/`, so every sweep point sees byte-identical
  vectors and no API jitter enters the latency.
* **Query under test:** the body of `match_document_chunks` verbatim (same
  SELECT list, same `INNER JOIN documents`, same WHERE, same ORDER BY, same
  LIMIT), issued directly. The RPC itself cannot be swept: it hard-codes
  `SET LOCAL hnsw.ef_search = 80` in its own body.
* **Latency clock:** server-side, `EXPLAIN (ANALYZE, TIMING OFF, FORMAT JSON)` →
  `"Execution Time"`. Excludes planning and the client round trip. A client-side
  round-trip figure is recorded alongside in every record
  (`latency_client_ms`); on this corpus the loopback RTT is ~1–3 ms, i.e. the
  same order as an HNSW query, so the server-side number understates what the
  application waits for.
* **Repetitions:** 1 warmup execution per query, discarded, then 3 timed
  executions per query → 177 samples per configuration.
* **Percentiles:** nearest-rank, `ceil(q·n)`, no interpolation. p50 = 89th
  sample, p95 = 169th. **p99 is not computed or reported.**
* **Label metrics:** `retrieval/metrics.py` (ranx), document relevance unit,
  k = 10, binary relevance, via the mandatory
  `sha256(pdf)[:16] ↔ uuid5(namespace, sha256)` id translation.
* **Label-set drift:** `retrieval/BASELINE.md` reports dense recall@10 = 0.4221
  with labels fingerprint `019bee4a06eb2d39`. This sweep measures 0.3488 with
  fingerprint `425df789a844f1f3`. The difference is the label set, not the
  retriever — another lane added PDFs under `corpora/` between the two runs.
  Comparisons **within** this document are all against the same fingerprint and
  are valid; comparisons against BASELINE.md's absolute numbers are not.
