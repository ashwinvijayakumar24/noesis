# First-stage recall — the 6,011, taken apart

`RERANK.md` measured that **6,011 of 6,944 misses (86.5%) are documents the first
stage never returned**, and concluded: *"the headroom is first-stage recall, not
ranking."*

The first half of that is arithmetic and it reproduces exactly. **The second half
is wrong, and this document is the measurement that says so.**

The 6,011 is not a coverage problem. It is the **50-chunk depth limit** turning a
ranking problem into something that looks like a retrieval problem. Remove the
depth limit — score every query against all 5,948 chunks of all 344 documents,
exactly, no approximation — and `retrieval_failure` collapses from **6,011 to
20**, `ranking_failure` rises from 933 to **6,922**, and recall@10 moves from
**0.2200 to 0.2227**.

**The candidate pool was never the constraint. The scoring function is.**

Everything here is on label snapshot **`230c6ea9d9b7e8fd`** (n = 338 scorable
queries · 8,554 relevant judgments · 15 of 15 topics) and corpus
**`5948c/344d` / `8d3edbe3f3b28cdb`**. Both are asserted by `firststage.py`,
which refuses to run on another, and the corpus digest is sampled before *and*
after every pass — one sample cannot detect a mid-run swap, only two can.

**Actual spend: $1.15388**, `unpriced_calls = 0`, against a $4.00
ceiling. All of it on one experiment (§2.2). Every other number in this document
cost **$0.00**: all 338 query embeddings were served from
`cache/retrieval_query_embeddings/text-embedding-3-large.json`.

---

## 1. The characterisation

`python3 -m scripts.eval.retrieval.firststage --mode characterise`

Shipped configuration: `k = 10`, `chunk_oversample = 5` → 50 chunks,
`plan: index`, `hnsw.ef_search = 80`. The totals reproduce `RERANK.md` from an
independent driver:

| | n |
|---|---|
| relevant judgments | 8,554 |
| hits@10 | 1,610 |
| **`retrieval_failure`** | **6,011** |
| `ranking_failure` | 933 |
| recall@10 | **0.2200** (ceiling 0.5199, 42.3% attainable) |

### 1.1 The three causes hiding inside one bucket

`metrics.attribute_failures` calls everything not in the pool a
`retrieval_failure`. That is three different problems with three different fixes:

| cause | misses | share of 6,011 | documents |
|---|---|---|---|
| **never ingested** — zero chunks in the index | **20** | **0.33%** | **1** |
| **indexed, but surfaces for no query at all** | **71** | **1.18%** | 3 cited, of 12 dark |
| **pooled for some *other* query, not this one** | **5,920** | **98.49%** | 300 |

**Ingestion is not the problem.** One label document out of 345 has no chunks;
it costs 20 of 8,554 judgments. Twelve indexed documents never appear in any of
the 338 pools, and only three of those are anybody's reference.

**98.5% of the "unreachable" misses are documents the retriever demonstrably
does return** — for a different query. Nothing about them is unreachable. They
simply did not score high enough *this time*, and the depth limit truncated them
out of the record before the failure could be attributed honestly.

### 1.2 Why: the pool holds fewer documents than the query has references

`chunk_oversample` counts **chunks**, and the relevance unit is **document**.
The 50 chunks max-pool to far fewer documents than 50, because a query's top
chunks cluster inside the same few documents:

| | value |
|---|---|
| chunks retrieved per query | 50 |
| **distinct documents in that pool** | **median 20, mean 19.74** (min 6, max 36) |
| chunks per distinct pooled document | mean 2.88 |
| **relevant documents per query** | **median 25, mean 25.31** (min 2, max 41) |
| queries where `|pool| < |rel|` | **230 / 338 (68%)** |
| queries with fewer than 10 relevant documents in the pool | **213 / 338 (63%)** |
| pool precision (relevant / pooled) | 0.381 (2,543 of 6,671) |

The pool is smaller than the ground truth for two queries in three. **61% of the
50-chunk budget is spent on repeat chunks from documents already in the pool.**

### 1.3 The number that bounds the whole reranking lane

Reranking is a permutation of a fixed pool, so
`mean(min(10, |pool ∩ rel|) / |rel|)` is a hard bound on every reranked arm.

| | recall@10 | n |
|---|---|---|
| **pool oracle** — a *perfect* reranker over the shipped 50-chunk pool | **0.2982** | 338 |
| dense ×5 control (measured) | 0.2200 | 338 |
| bge-reranker-v2-m3 (`RERANK.md`) | 0.2270 | 338 |
| label ceiling | 0.5199 | 338 |

**The dense first stage already achieves 73.8% of everything a perfect reranker
could reach over its own pool.** The cross-encoder captured 0.0070 of a maximum
possible 0.0782 — 9% of its headroom — for 13.3 s/query. `RERANK.md` was right
that reranking is not the lever; this is the number that says by how much.

### 1.4 By topic — concentrated, not uniform

| topic | `retrieval_failure` / judgments | rate |
|---|---|---|
| `eR4W9tnJoZ` | 22 / 24 | 0.917 |
| `H9DYMIpz9c` | 770 / 984 | 0.783 |
| `miGpIhquyB` | 1,766 / 2,255 | 0.783 |
| `jx6njBKH8E` | 249 / 333 | 0.748 |
| `rhgIgTSSxW` | 1,335 / 1,836 | 0.727 |
| `9ceadCJY4B` | 206 / 296 | 0.696 |
| `cXs5md5wAq` | 124 / 180 | 0.689 |
| `10eQ4Cfh8p` | 125 / 192 | 0.651 |
| `gYcft1HIaU` | 101 / 160 | 0.631 |
| `ApjY32f3Xr` | 195 / 319 | 0.611 |
| `rp5vfyp5Np` | 396 / 663 | 0.597 |
| `kKRbAY4CXv` | 52 / 88 | 0.591 |
| `qBL04XXex6` | 474 / 850 | 0.558 |
| `BQvbL2sFQx` | 102 / 192 | 0.531 |
| `eUgS9Ig8JG` | 94 / 182 | 0.516 |

The spread is 0.52 to 0.92, but read the denominators: the rate tracks reference
list length almost mechanically. `eR4W9tnJoZ` has 12 queries and 24 judgments —
2 references per query, so a single query dominates it. The two topics carrying
36% of all misses between them (`miGpIhquyB`, `rhgIgTSSxW`) are the two largest.
**This is a size effect, not a topic effect**, and no topic is anywhere near
clean.

### 1.5 Interaction with the contentless population — no double-counting

`CONTENTLESS.md` reports that 21.0% of queries (71 of 338) name nothing outside
their own manuscript and reach only 31% of their own ceiling. If that population
drove the 6,011, it would show a much higher retrieval-failure rate. It does not:

| half | n | judgments | `retrieval_failure` rate | recall@10 | own ceiling | own pool oracle | % of pool oracle |
|---|---|---|---|---|---|---|---|
| classifier-servable | 267 | 6,753 | **0.697** | 0.2273 | 0.5231 | 0.3103 | **73.3%** |
| classifier-contentless | 71 | 1,801 | **0.722** | 0.1925 | 0.5077 | 0.2530 | **76.1%** |

Every ceiling and oracle is recomputed for its own subset.

**The two populations fail the same way, at the same rate, and contentless
queries actually extract a slightly *larger* fraction of what their pool
contains.** Contentlessness lowers the quality of the pool the query assembles;
it is not a second, separate cause of the 6,011, and the two must not be added.

---

## 2. Hypotheses, in the order they were tested

Each was measured. Two of the five had a live-looking case going in and neither
survived it.

### 2.1 Oversample depth — **REJECTED.** Beyond 120 chunks, depth buys 0.0000.

The existing record has `dense ×5 (plan: index)` at 0.2200 and `dense ×12 (plan:
seqscan)` at 0.2227, which confounds pool depth with the planner flipping to a
sequential scan. This sweep **forces the plan** (`SET enable_seqscan=off` /
`SET enable_indexscan=off`) and issues the k-NN query directly, so the two are
separated by construction.

> A caller-side `SET hnsw.ef_search` cannot sweep `match_document_chunks`: the
> RPC pins `SET LOCAL hnsw.ef_search = 80` **inside its own body**. That is why
> this driver issues the ORDER BY directly, and it is a fact worth knowing
> independently — the shipped ANN path asks the graph for at most 80 candidates
> no matter what the caller requests.

`python3 -m scripts.eval.retrieval.firststage --mode depth`, **n = 338, ceiling
0.5199 throughout**:

| arm | plan (observed) | chunks | mean pool docs | recall@10 | pool oracle@10 |
|---|---|---|---|---|---|
| ×5, ef 80 (**as shipped**) | `index` | 50 | 19.74 | **0.2200** | 0.2982 |
| ×12, ef 80 | `index` | 120 | 42.41 | 0.2227 | 0.3709 |
| ×25, ef 300 | `index` | 250 | 75.07 | 0.2227 | 0.4148 |
| ×50, ef 600 | `index` | 500 | 122.20 | 0.2227 | 0.4554 |
| ×5 exact | `seqscan` | 50 | 20.35 | 0.2210 | 0.3025 |
| ×12 exact | `seqscan` | 120 | 42.41 | 0.2227 | 0.3709 |
| ×25 exact | `seqscan` | 250 | 75.07 | 0.2227 | 0.4148 |
| ×50 exact | `seqscan` | 500 | 122.20 | 0.2227 | 0.4554 |
| ×100 exact | `seqscan` | 1000 | 186.12 | 0.2227 | 0.4839 |
| **whole corpus, exact** | `seqscan` | 5948 | **344.00** | **0.2227** | **0.5133** |

Four things fall out, all at n = 338:

1. **From 120 chunks to the entire corpus — a 50× increase in depth and an 8×
   increase in pool documents — recall@10 does not move by one ten-thousandth.**
   A document enters the top 10 only if its best chunk beats the incumbents'
   best chunks, and every candidate added past rank ~120 scores below them by
   construction. Depth is a dead knob.
2. **The published 0.2200 → 0.2227 "depth gain" is mostly not depth.** Exact ×5
   — same 50 chunks, no approximation — already reads **0.2210**. So **0.0010 of
   the 0.0027 is the HNSW approximation at ef 80**, and only 0.0017 is depth,
   fully exhausted by 120 chunks. Neither is worth a plan flip.
3. **The pool oracle climbs steeply — 0.2982 → 0.5133 — while measured recall is
   flat.** The reranking headroom nearly doubles with depth and the first stage
   cannot touch any of it. This is the cleanest statement of the finding: the
   candidates are there, the *scores* are wrong.
4. The plan flip is real and it is confounding: the shipped ×5 arm runs `index`,
   every deeper arm the planner picks runs `seqscan`. Any depth comparison that
   does not stamp the plan is attributing a planner decision to a retrieval idea.

### 2.2 Chunk granularity — **REJECTED.** Thirding every chunk buys +0.0013.

Chunks here are enormous: **5,948 chunks, median 5,789 characters, mean 5,983**,
35.58 M characters total. `MAX_CHUNKS_PER_DOCUMENT = 50` caps 8 of 344 documents
(median 15 chunks/document, max 55). A relevant passage sitting inside a 6,000-
character chunk is plausibly diluted below threshold, and `CHUNK_CEILING_GEOMETRY
= exact` exists as a flag, so this was the strongest remaining hypothesis.

**It was measured rather than argued, and it does not hold.** Every chunk was
split into 3 contiguous, non-overlapping, whitespace-aligned pieces — 5,948 →
**17,844 sub-chunks**, median ~1,930 characters — re-embedded with the *same*
`text-embedding-3-large` @ 1536, and scored **entirely in memory**.

> **Nothing was written to the database.** The eval database is shared with other
> agents on this branch, and a re-ingest mints new chunk ids: that has already
> invalidated a day of measurements once (`CONTENTLESS.md` §3e–g). Corpus
> identity `8d3edbe3f3b28cdb` is unchanged, verified before and after.

Control and arm are the same exact whole-corpus max-pool through the same scoring
code, differing in granularity and nothing else. The control reproduces the
database's own exact reading of **0.2227** to four decimals, which is what makes
the arm trustworthy.

| arm | n | chunks | recall@10 | ceiling | % attainable |
|---|---|---|---|---|---|
| control — 5,948 chunks, exact, whole corpus | 338 | 5,948 | **0.2227** | 0.5199 | 42.8% |
| **thirded — 17,844 sub-chunks, exact, whole corpus** | 338 | 17,844 | **0.2240** | 0.5199 | 43.1% |
| Δ | | | **+0.0013 (+0.6%)** | — | +0.3 pts |

**+0.0013 against 0.2972 of headroom is 0.4% of the gap.** Tripling chunk
granularity is not the lever for *retrieval*. (It may still matter for the
cross-encoder, which reads only the first ~512 tokens of a median 5,789-character
chunk — that is a separate claim about a separate stage and this arm does not
test it.)

Cost of this arm: **$1.15388**, 17,844 embeddings, `unpriced_calls = 0`.

### 2.3 Query formulation — **NOT IN PLAY on this path, and worth fixing anyway.**

Keyword v1 failed because `plainto_tsquery` ANDs every lemma, so a ~20-word claim
had to match all ~20 — 321 of 338 queries returned zero rows. The analogous dense
question is whether the query is malformed for the index.

`expand_query()` exists in `rag_retrieval.py:383` and is called from **exactly one
place**: `hybrid_search()` at line 560, the weighted-sum fusion. That function is
**not** on the path this eval measures, which goes through
`match_document_chunks`. So `expand_query` is not suppressing anything here — it
is simply absent, and adding it is untested rather than rejected.

The measurable asymmetry that *is* present: **queries are median 142 characters,
chunks are median 5,789 — a 41× length mismatch.** A 20-word claim is embedded
into the same space as a 1,000-word passage. §2.2 is the closest available test
of that asymmetry (it halves the mismatch to ~14×) and it moved recall by 0.0013,
which is weak evidence that the asymmetry is not the binding constraint either.
It is not a clean test and is reported as such.

### 2.4 The embedding model split — **CONFIRMED CONSISTENT. Not a cause.**

| | |
|---|---|
| index chunks | `rag_ingest.embed_chunks(..., model="text-embedding-3-large")`, `dimensions=1536` |
| stored vectors | `vector_dims(embedding) = 1536`, verified against the live index |
| queries | `adapters.production_embed_fn(model="text-embedding-3-large")`, cache file `text-embedding-3-large.json`, 338 entries, dim 1536 |

Index and query use the same model at the same dimensionality. `-small` appears
on some draft paths, and its similarity thresholds are documented as
incomparable, but **it is not in play here**. This hypothesis is closed as a
verification, not as a finding.

### 2.5 Document-level ceiling artefacts — **CONFIRMED, and it is the largest single term.**

Every query inherits its manuscript's **entire** resolved reference list. A claim
about one method is therefore scored against the ~24 references it has nothing to
do with. The question is how much of the 6,011 that accounts for.

Measured by asking a different question of the same data: **can *any* claim in a
manuscript rank a given cited document into the top 10?** The unit is the
distinct `(topic, cited document)` pair, so a document cited by a 55-query
manuscript counts once, not 55 times.

Whole-corpus exact pool, k = 10, **n = 330 topic-document pairs / 8,534
query-document pairs**:

| | p25 | p50 | p75 | p90 | in top 10 |
|---|---|---|---|---|---|
| **best-of-manuscript rank** of a cited document | 1 | **4** | 14 | 32 | **229 / 330 = 69.4%** |
| per-query rank of a cited document | 15 | **53** | 132 | 220 | 1,612 / 8,534 = 18.9% |

**The retriever puts 69.4% of the corpus's cited documents into the top 10 for at
least one claim from the manuscript that cites them — median rank 4.** The same
documents sit at median rank 53 of 344 when scored per-claim.

That gap is the label design, not the retriever. The benchmark asks each claim to
retrieve the whole bibliography; the retriever retrieves the part of the
bibliography that claim is about. **A large fraction of the 6,011 is a document
being correctly *not* returned for a claim it is unrelated to, and counted as a
miss.**

This is not a reason to change the labels. `docs/BENCHMARKS.md`'s standing caveat
already says these labels measure *"would we have found what the author cited"*,
and recall is the sounder number under them. It **is** a reason to stop reading
0.2200-against-0.5199 as "the retriever finds 42% of what it should".

The recall curve makes the same point from the other side (whole-corpus exact,
n = 338, every ceiling recomputed for its own k):

| k | measured | ceiling | % attainable |
|---|---|---|---|
| 1 | 0.0351 | 0.0694 | 50.5% |
| 5 | 0.1369 | 0.2939 | 46.6% |
| 10 | 0.2227 | 0.5199 | 42.8% |
| 20 | 0.3420 | 0.7599 | 45.0% |
| 50 | 0.5204 | 1.0000 | 52.0% |
| 100 | 0.6858 | 1.0000 | 68.6% |

The attainable fraction is **flat at 43–52% from k = 1 to k = 50**. A retriever
with a coverage problem improves as k grows; this one does not. It is uniformly
half-right at every depth, which is the signature of a scoring function with real
but weak signal, not of a pool that is missing things.

The underlying separation confirms it. On the whole-corpus pool, max-pooled
cosine similarity reads **0.4415 mean for relevant documents (n = 7,346) against
0.3821 for irrelevant (n = 55,562)** — a gap of **0.0593** against standard
deviations of 0.0718 and 0.0646. **Under one standard deviation of separation.**
That is the whole story in one number: the signal is real, and it is weak.

---

## 3. What was changed, and what is recommended

### 3.1 Changed

**Nothing in production, and nothing in the shared corpus.** The indicated
changes are all in `services/backend/app/`, which this lane does not edit. Three
new files, all owned here:

- `scripts/eval/retrieval/firststage.py` — the driver. Five modes
  (`characterise`, `depth`, `subchunk`, `reachability`, `cost`), asserts the
  snapshot and the corpus digest before and after every pass, appends nothing to
  the results sink, and refuses to spend without `--allow-spend`.
- `scripts/eval/retrieval/tests/test_firststage.py` — 25 tests. The DB-gated ones
  pin the published `(6011, 933, 1610)` and `(20, 71, 5920)` splits and the
  0.0000 depth flatness, so a number here cannot decay silently.
- this document.

### 3.2 Recommended, with the evidence that supports each

**Do not** raise `chunk_oversample`. Measured: 0.0000 from 120 chunks to the
whole corpus, n = 338. It costs latency and buys nothing. The one exception is
if a reranker is in front of it — the pool oracle rises 0.2982 → 0.5133 across
that range, so depth is a **reranker** dial, not a retrieval dial. `RERANK.md`
prices that at ~2.6 ms per candidate, which makes a 500-candidate pool two
minutes per query.

**Do not** re-chunk the production corpus for retrieval reasons. Measured:
+0.0013 at 3× granularity, n = 338. Re-chunking has other justifications (the
cross-encoder's 512-token window; `MAX_CHUNKS_PER_DOCUMENT` capping 8 documents)
and they should be argued on their own terms, not on this one.

**Fix, cheaply and with real evidence behind it —**
`app/services/rag_retrieval.py`, recommended not implemented:

1. **The RPC's `hnsw.ef_search = 80` is a hidden ceiling on every caller.**
   `match_document_chunks` sets it `LOCAL` inside its own body, so a caller
   asking for 120 candidates cannot get 120 from the graph and the planner falls
   back to a sequential scan over 5,948 rows. That is fine at this corpus size
   and will not be at production scale. At minimum it should be a parameter, and
   it should be stamped on every eval record. *(Evidence: §2.1; ×5 index 0.2200
   vs ×5 exact 0.2210, and the plan flip between 50 and 120.)*
2. **Oversample by document, not by chunk.** 61% of the 50-chunk budget is spent
   on repeat chunks from documents already in the pool (2.88 chunks/document),
   and the relevance unit downstream is document. `DISTINCT ON (document_id)`
   would put ~50 documents in the pool for the same 50 rows. *(Evidence: §1.2.
   Note this does **not** move recall@10 on its own — §2.1 shows the top 10 is
   unchanged by pool composition — it makes the pool worth reranking. Expected
   effect is on the oracle, from 0.2982 toward 0.37+, not on the measured arm.)*

**The thing actually worth building.** Every cheap knob is measured and dead. The
gap between 0.2227 and 0.5133 is a **scoring** gap: max-pooled cosine over
`text-embedding-3-large` separates cited from uncited by 0.85σ. Closing it means
changing what the score is — a domain-adapted or fine-tuned embedding, a
citation-aware objective, or a cheap second-stage feature (title/abstract match,
author overlap, venue, year) fused with the vector score. All of those are real
projects. None of them is a config change, and **the roadmap should stop looking
for one.**

**Correct the record in `RERANK.md`.** Its failure-attribution table is right and
its conclusion sentence is not. Suggested:

> ~~If you want a bigger number than +3.2%, it is not in the reranker. It is in
> the 6,011, which is a first-stage recall problem: deeper retrieval, better
> chunking, or a better embedding.~~
>
> **If you want a bigger number than +3.2%, it is not in the reranker — and it is
> not in the pool either. The 6,011 is an artefact of the 50-chunk depth limit:
> scoring the whole corpus exactly turns 6,011 retrieval failures into 20, moves
> recall@10 by +0.0027, and leaves 6,922 ranking failures. Deeper retrieval buys
> 0.0000 past 120 chunks and 3× finer chunks buy +0.0013 (both n = 338, ceiling
> 0.5199). The remaining lever is the embedding.** See `FIRSTSTAGE.md`.

---

## 4. The honest summary

**Most of this is structural and is not fixable by retrieval tuning.** Of the
0.2972 gap between the measured 0.2227 and the 0.5199 label ceiling:

- **~0** is ingestion (1 document, 20 judgments).
- **~0** is pool depth (0.0000 from 120 chunks to the whole corpus, n = 338).
- **0.0013** is chunk granularity at 3× (n = 338).
- **0.0070** was reranking, at 13.3 s/query (`RERANK.md`, n = 338).
- **A large but unquantified majority** is the per-manuscript label design: the
  same documents the benchmark counts as missed are ranked top-10 by *some*
  claim in their own manuscript 69.4% of the time (n = 330 pairs), median rank 4.
- **The remainder is the embedding's discriminative power**, which measures at
  0.0593 mean separation against ~0.07 standard deviation — under 1σ.

The first four are measured and closed. The fifth is a property of the ruler and
should change how the number is *read*, not what is built. The sixth is the only
one with real headroom in it, and it is a modelling project rather than a
parameter.

---

## 5. Not claimable

- Any recall here without its `n` and its **own recomputed** ceiling. Ceilings in
  this document range 0.4549–0.5231 across subsets; carrying one across silently
  rescales every arm.
- Any number here alongside `0.2195` or `0.2186`. Those belong to corpora that no
  longer exist. The control on `8d3edbe3f3b28cdb` is **0.2200**.
- Any comparison with snapshots `019bee4a06eb2d39` or `425df789a844f1f3`.
- "Chunking does not matter." Measured: 3× granularity, contiguous, no overlap,
  same embedding model, in-memory scoring, n = 338. A different chunker with
  section awareness, overlap, or a different size is **not** tested by this.
- "The retriever is fine." It reaches 43% of attainable at k = 10 and separates
  relevant from irrelevant by under 1σ. It is weak. What is established is that
  the weakness is in the *score*, not in the pool.
- That any of this is a production retrieval number. Local pgvector, PyMuPDF
  extraction, basic chunking — not production's Docling → GROBID section-aware
  chain.
- The 69.4% reachability figure as a claim about product quality. It is measured
  under the same per-manuscript labels as everything else and inherits the same
  caveat; it is evidence about *where the misses come from*, not about how good
  retrieval feels to a user.

---

## 6. Reproducing

```bash
# the characterisation — no DB writes, no LLM calls, $0.00
python3 -m scripts.eval.retrieval.firststage --mode characterise

# depth sweep with the query plan FORCED, 10 arms, $0.00  (~2 min)
python3 -m scripts.eval.retrieval.firststage --mode depth

# whole-corpus pool, recall curve, reachability, $0.00
python3 -m scripts.eval.retrieval.firststage --mode reachability

# what a granularity arm would cost before running one
python3 -m scripts.eval.retrieval.firststage --mode cost

# the granularity arm. COSTS MONEY. 17,844 embeddings, ~$1.15, cached after the
# first run. Writes nothing to the database.
python3 -m scripts.eval.retrieval.firststage --mode subchunk --n-parts 3 --allow-spend

python3 -m pytest scripts/eval/retrieval/tests/ -q   # 244 tests
```

Sub-chunk embeddings are cached in
`scripts/eval/cache/retrieval_subchunk_embeddings/`, keyed by
`sha256(text)[:24]`, so a re-run of the granularity arm costs $0.00.
