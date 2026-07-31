# Measurements

Every measurement this project has made, in one file. Each section below is a
former standalone document, moved here **verbatim** — the numbers, their sample
sizes and their caveats are exactly as their authors wrote them.

## How to read a number in this file

These four rules govern everything below and are not repeated in every section.
A number quoted without the rule that governs it is a wrong number.

1. **Retrieval numbers belong to a label snapshot and are not comparable across
   snapshots.** There have been three: `019bee4a06eb2d39` (118 documents, 4
   topics, 59 scorable queries), `425df789a844f1f3` (the ANN-sweep and
   keyword-query runs) and `230c6ea9d9b7e8fd` (344 documents / 5,948 chunks, 15
   topics, 338 scorable queries — the current one). Dense `recall@10` reads
   0.4221 under the first and 0.2195 under the third. **That is not a
   regression**: the corpus is 2.8× larger in chunks, the average query inherits
   25.3 relevant documents rather than 15.3, and the construction ceiling fell
   from 0.7789 to 0.5199 with it. Do not difference them.
2. **`recall@k` is capped by construction, well below 1.0.** A query inherits
   its manuscript's whole reference list, so a query with 37 relevant documents
   cannot exceed `recall@10 = 10/37`. Quote the ceiling and the percent of
   attainable alongside the measurement, or quote neither.
3. **Every cost figure produced before the matcher fix is a lower bound** — low
   by a margin that cannot be reconstructed. `match.py` issued OpenAI calls
   outside the spend guardrails until 2026-07-30, so they were metered into no
   sink and appear in no total. This holds even where a record's own
   `unpriced_calls` counter reads zero.
4. **A node replay is not end-to-end, and ANN latency is from the small
   corpus.** A node-replay figure measures one node in isolation. Graph latency
   excludes PDF parsing and storage I/O, which together are larger than what it
   includes. Every ANN latency number was measured on the 2,124-chunk corpus and
   has not been re-measured since the corpus grew to 5,948 chunks.

The generated number index is [BENCHMARKS.md](./BENCHMARKS.md); it is produced
by `make benchmarks` and must not be hand-edited. How the harness is run and
gated is in [EVAL_GUIDE.md](./EVAL_GUIDE.md).

## Contents

- [Retrieval baseline — 15 topics, 344 documents, RRF measured](#retrieval-baseline-15-topics) — was `scripts/eval/BASELINE_15.md`
- [Keyword query formulation](#keyword-query-formulation) — was `scripts/eval/KEYWORD_QUERY.md`
- [Retrieval baseline — 4 topics, 118 documents (SUPERSEDED)](#retrieval-baseline-superseded) — was `scripts/eval/retrieval/BASELINE.md`
- [Corpus build report](#corpus-build-report) — was `scripts/eval/BUILD_REPORT.md`
- [HNSW sweep](#hnsw-sweep) — was `scripts/eval/ANN_SWEEP.md`
- [Node replay cost](#node-replay-cost) — was `scripts/eval/NODE_COST.md`
- [Prompt caching in the reviewer panel](#prompt-caching) — was `scripts/eval/PROMPT_CACHE.md`
- [Graph latency under load](#graph-latency-under-load) — was `scripts/eval/LATENCY.md`

---

<a id="retrieval-baseline-15-topics"></a>

_Moved here unchanged from `scripts/eval/BASELINE_15.md`._

## Retrieval baseline — 15 topics, 344 documents, RRF measured

**This document supersedes [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded). Do not quote that file's
numbers.** Two things are wrong with it, and neither is fixable by editing a
sentence:

1. **Its dense row is mislabelled.** "dense (pgvector HNSW, cosine)" was measured
   against an exhaustive sequential scan. On the 2124-chunk corpus, Postgres
   declined `idx_document_chunks_embedding` above a `LIMIT` of roughly 35, and
   the harness asks for `k × chunk_oversample` = 50 chunks. The recall numbers
   were valid *retrieval quality*; the index name on them was not earned. See
   [§ HNSW sweep](#hnsw-sweep) §0 for the original finding and §2 below for the fix.
2. **Its label snapshot no longer exists.** [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded) ran under labels
   fingerprint `019bee4a06eb2d39` (118 indexed documents, 4 topics with a
   corpus, 59 scorable queries). [§ HNSW sweep](#hnsw-sweep) and [§ Keyword query formulation](#keyword-query-formulation) ran under
   `425df789a844f1f3`. **Everything in this document runs under
   `230c6ea9d9b7e8fd`** — 344 indexed documents, 15 topics, 338 scorable queries.
   The fingerprint has changed twice. A recall@10 from one snapshot and a
   recall@10 from another are not the same quantity, so **every arm here was
   re-measured rather than carried forward**, including the ones that already had
   a number.

The construction ceilings are also recomputed. [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded)'s
`0.1061 / 0.5307 / 0.7789 / 0.8798` belong to the dead snapshot and must not be
used to rescale anything below.

Reproduce:

```bash
cd scripts/eval
python3 -m retrieval.run_retrieval_eval --retriever dense   --chunk-oversample 5  --arm dense_os5
python3 -m retrieval.run_retrieval_eval --retriever dense   --chunk-oversample 12 --arm dense_os12
python3 -m retrieval.run_retrieval_eval --retriever keyword --chunk-oversample 5  --arm keyword_v1
KEYWORD_SEARCH_V2=1 python3 -m retrieval.run_retrieval_eval --retriever keyword --chunk-oversample 5 --arm keyword_v2
KEYWORD_SEARCH_V2=1 python3 -m retrieval.run_retrieval_eval --retriever hybrid  --chunk-oversample 5 --k-rrf 60 --arm rrf_k60
```

Results append to `scripts/eval/results/retrieval_eval.jsonl`. Nothing is
overwritten. Every record now carries `plan`, `recall_ceilings`,
`percent_of_attainable`, and (for fusions) per-leg row counts.

---

### 1. Scale — say n, and say what changed

| | [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded) | **this document** |
|---|---|---|
| labels fingerprint | `019bee4a06eb2d39` | **`230c6ea9d9b7e8fd`** |
| queries fingerprint | `1f6c584e8fd6c055` | `1f6c584e8fd6c055` (unchanged) |
| indexed documents / chunks | 118 / 2124 | **344 / 5948** |
| pooled label corpus | 118 docs | **345 docs** |
| topics with queries **and** labels | 4 of 15 | **15 of 15** |
| **scorable queries (n)** | **59** | **338** |
| relevant judgments | 903 | **8554** |
| references resolved | 119 | **370** |
| references excluded as corpus gaps | 65 | **211** (`no_oa_pdf` 81, `no_openalex_match` 78, `download_failed` 52) |

n = 338 is 5.7× larger, but **it is not simply a better measurement of the same
thing**. Going from 4 topics to 15 adds queries *and* adds distractors: the
9ceadCJY4B queries now compete against 226 documents that did not exist in the
index before. Absolute recall falling between the two documents is expected and
is not evidence that anything regressed. Nothing here should be compared to
[§ Retrieval baseline (superseded)](#retrieval-baseline-superseded) at all.

The 338 queries come from 15 manuscripts. That is still not a random sample of
anything, and a few points between two configurations is still noise. The
comparisons that survive that objection are flagged below; the ones that do not
are flagged too.

---

### 2. The crossover moved, and the eval's default depth is now genuinely HNSW

[§ HNSW sweep](#hnsw-sweep) predicted this and it is worth saying that it did: *"the crossover
at LIMIT ≈ 35 is a property of this row count. On 10× the corpus the sequential
scan gets 10× more expensive while the HNSW scan barely changes, so the crossover
moves far above any realistic k."*

Re-determined empirically at 5948 chunks by binary search over `EXPLAIN`, with
the RPC's own `hnsw.ef_search = 80`:

| corpus | chunks | crossover (last LIMIT planned as index scan) | growth |
|---|---|---|---|
| old ([§ HNSW sweep](#hnsw-sweep)) | 2124 | ~35 (bracketed 30 → 40) | — |
| **new (this document)** | **5948** | **103** (104 flips to seqscan) | corpus ×2.80, crossover ×2.96 |

`ef_search` moves it slightly, as before — a larger `ef_search` raises the index
scan's estimated cost:

| `hnsw.ef_search` | last LIMIT with index scan | first LIMIT with seq scan |
|---|---|---|
| 40 | 104 | 105 |
| **80 (production / the RPC)** | **103** | **104** |
| 160 | 102 | 103 |
| 320 | 100 | 101 |

Verified over 10 distinct query vectors at each depth; all 10 agree at every
point, so the boundary is a property of the cost model, not of the query.

#### The `EXPLAIN` evidence

`match_document_chunks` is plpgsql, so `EXPLAIN` of a call to it reports one
`Function Scan` and hides the real plan. What follows is the RPC's body verbatim
(same SELECT shape, same `INNER JOIN documents`, same WHERE, same ORDER BY, same
LIMIT) under `SET hnsw.ef_search = 80`. Vectors elided.

```
=== LIMIT 50  (the harness's default depth: k=10 × oversample 5) ===
  Limit  (cost=209.79..419.99 rows=50 width=80)
    ->  Nested Loop  (cost=209.79..25067.78 rows=5913 width=80)
          ->  Index Scan using idx_document_chunks_embedding on document_chunks dc
                Order By: (embedding <=> '[<1536-d vector>]'::vector)
                Filter: (project_id = 'e7a1c0b0-...-000000000001'::uuid)
          ->  Memoize  (cost=0.28..0.31 rows=1 width=16)
                ->  Index Only Scan using documents_pkey on documents d

=== LIMIT 103  (last depth the planner still takes the index) ===
  Limit  (cost=209.79..642.80 rows=103 width=80)
    ->  Nested Loop
          ->  Index Scan using idx_document_chunks_embedding on document_chunks dc
          ...

=== LIMIT 104  (one row deeper — the index is gone) ===
  Limit  (cost=638.75..639.01 rows=104 width=80)
    ->  Sort  (cost=638.75..653.53 rows=5913 width=80)
          Sort Key: ((dc.embedding <=> '[<1536-d vector>]'::vector))
          ->  Hash Join  (cost=14.99..411.09 rows=5913 width=80)
                ->  Seq Scan on document_chunks dc
                ->  Hash
                      ->  Seq Scan on documents d
```

Note the shape of the flip: the index plan's cost is dominated by *startup*
(209.79) and grows slowly with LIMIT; the seq-scan plan pays 638.75 up front and
then almost nothing per row. They cross between 103 and 104.

**Consequence: [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded)'s mislabelling has fixed itself.** At the current
corpus size the harness's default depth of 50 is comfortably below the crossover,
so the "dense" arm below really is HNSW — and the record says so because it
asked, not because someone assumed.

#### The durable fix: `plan` is recorded in every record

`retrieval/plan_probe.py` EXPLAINs the query at the depth actually being used and
stamps `plan: "index" | "seqscan" | "mixed" | "unknown"` into the results record.
`mixed` is never collapsed to a majority — "half of this arm was HNSW" is its own
finding. `unknown` is used for retrievers that have no plan (mock, keyword) and
is deliberately not `"index"`.

The two dense regimes, on the same queries and the same labels:

| arm | depth | `plan` |
|---|---|---|
| `dense_os2` | 20 chunks | `index` |
| **`dense_os5`** (harness default) | **50 chunks** | **`index`** |
| `dense_os12` | 120 chunks | `seqscan` |

---

### 3. The numbers

Relevance unit: **document** (see [EVAL_GUIDE.md § Relevance definition](./EVAL_GUIDE.md#relevance-definition)). k = 10. Binary
relevance. Chunk results are max-pooled to documents, then truncated.
**n = 338 scorable queries, 8554 relevant judgments, 345-document pooled corpus,
labels fingerprint `230c6ea9d9b7e8fd`, queries fingerprint `1f6c584e8fd6c055`.**
Every row below shares those two fingerprints; all 11 records are on disk in
`results/retrieval_eval.jsonl` with distinct config hashes.

| arm | plan | R@1 | R@5 | R@10 | R@20 | MRR | NDCG@10 | MAP |
|---|---|---|---|---|---|---|---|---|
| **dense** (os ×5, k=50) | `index` | 0.0341 | 0.1365 | **0.2195** | 0.3062 | 0.7328 | **0.5191** | 0.2319 |
| dense (os ×2, k=20) | `index` | 0.0341 | 0.1350 | 0.1874 | 0.1982 | 0.7302 | 0.4780 | 0.1624 |
| dense (os ×12, k=120) | `seqscan` | **0.0351** | **0.1369** | 0.2227 | **0.3420** | **0.7436** | 0.5221 | **0.2948** |
| keyword **v1** (`plainto_tsquery`) | — | 0.0012 | 0.0021 | 0.0022 | 0.0022 | 0.0311 | 0.0110 | 0.0021 |
| keyword **v2** (OR of lemmas) | — | 0.0240 | 0.0888 | 0.1447 | 0.2322 | 0.6675 | 0.3830 | 0.1439 |
| RRF(dense, keyword v2) k=60 | `index` | 0.0305 | 0.1198 | 0.2042 | 0.2993 | 0.7335 | 0.4989 | 0.2431 |

#### Construction ceilings, recomputed for this snapshot

Every query inherits its manuscript's **entire** resolved reference list, so a
query with 37 relevant documents cannot exceed recall@10 = 10/37. The ceiling is
the mean over scorable queries of `min(k, |rel_q|) / |rel_q|` — the same
unweighted-over-queries average ranx uses for recall, so measured/ceiling is a
ratio of like for like.

| k | **new ceiling** (`230c6ea9d9b7e8fd`) | old ceiling (`019bee4a06eb2d39`, void) |
|---|---|---|
| 1 | **0.0694** | 0.1061 |
| 5 | **0.2939** | 0.5307 |
| 10 | **0.5199** | 0.7789 |
| 20 | **0.7599** | 0.8798 |

The ceilings fell because the average query now inherits 25.3 relevant documents
(8554/338) rather than 15.3. That alone accounts for a large part of the drop in
absolute recall between the two documents, which is the whole reason
percent-of-attainable is the number to read:

| arm | R@1 | R@5 | R@10 | R@20 |
|---|---|---|---|---|
| dense (os ×5) | 49% | 46% | **42%** | 40% |
| dense (os ×2) | 49% | 46% | 36% | 26% |
| dense (os ×12) | 51% | 47% | 43% | 45% |
| keyword v1 | 2% | 1% | 0% | 0% |
| keyword v2 | 35% | 30% | 28% | 31% |
| RRF k=60 | 44% | 41% | **39%** | 39% |

MRR, NDCG@10 and MAP have no simple construction ceiling here and are recorded as
`null`, not as 1.0. "No ceiling computed" and "at its ceiling" are different
claims.

#### Failure attribution

| arm | total misses | retrieval failure (never returned) | ranking failure (returned, below k) | unresolved |
|---|---|---|---|---|
| dense (os ×5) | 6946 | 6010 | 936 | 0 |
| dense (os ×2) | 7147 | 7038 | 109 | 0 |
| dense (os ×12) | 6942 | 4695 | 2247 | 0 |
| keyword v1 | 8532 | **8532** | **0** | 0 |
| keyword v2 | 7416 | 6343 | 1073 | 0 |
| RRF k=60 | 7029 | **5144** | 1885 | 0 |

Three readings:

* **"Retrieval failure" is mostly depth, not indexing.** Every one of those
  documents is in the index. With 25 relevant documents per query on average and
  a retrieval depth of 50 chunks (which pool to far fewer than 50 documents),
  most of them were never in the requested window. Compare `dense_os2` (7038)
  with `dense_os12` (4695): the same retriever, the same index, only the depth
  changed.
* **keyword v1's zero ranking failures are the signature of a retriever that
  returns nothing.** It returned 60 rows across 338 queries and produced an empty
  result for **321 of 338** (95%). `KEYWORD_SEARCH_DEGRADED` was clear for that
  run, so this is real behaviour, not a swallowed error — exactly the finding
  [§ Keyword query formulation](#keyword-query-formulation) diagnosed, reproduced at 5.7× the scale.
* **RRF has the best coverage of any arm at this depth** (5144 retrieval
  failures vs dense's 6010) and the *worst* ranking of the three below-crossover
  arms (1885 vs 936). It finds more and orders it worse. That is the entire
  result of §5, visible in one table.

---

### 4. Keyword v2 — the OR fix holds at 5.7× the scale

| | v1 `keyword_search_chunks` | v2 `keyword_search_chunks_v2` |
|---|---|---|
| queries returning zero rows | **321 / 338** (95%) | **0 / 338** |
| total rows across the run (k=50) | 60 | 16 900 |
| recall@10 | 0.0022 | **0.1447** (66× ) |
| MRR | 0.0311 | **0.6675** |
| NDCG@10 | 0.0110 | **0.3830** |
| MAP | 0.0021 | **0.1439** |
| % of attainable recall@10 | 0% | **28%** |

`KEYWORD_SEARCH_DEGRADED` was clear for **both** runs. These are real results.

The gap is ~66× and survives the "n is small, a few points is noise" objection by
a wide margin. [§ Keyword query formulation](#keyword-query-formulation) measured 0.0026 → 0.2841 on the old snapshot;
both absolute numbers moved under the larger corpus and the direction did not.
**Quote the ratio, not either absolute.**

---

### 5. RRF — implemented, measured, and it does **not** beat dense

`HybridRetriever` is no longer a stub. `score(d) = Σᵢ 1/(k_rrf + rankᵢ(d))`, fused
by **rank**, at **document** level (a document's rank within a leg is the rank of
its best chunk; the eval's relevance unit is document, and chunk-level fusion
would give a document no agreement bonus when the two legs found different chunks
of it).

**Fusing by rank rather than by weighted score is the point.** `ts_rank(…, 1|32)`
values in this corpus sit between **0.0038 and 0.0071** while cosine similarity
sits around **0.42–0.68** (both ranges are measured, see §6). `hybrid_search`'s
`0.7 × similarity + 0.3 × keyword_score` would give the keyword leg roughly
0.3 × 0.005 / (0.7 × 0.55 + 0.3 × 0.005) ≈ **0.4%** of the combined total —
technically fused, practically ignored. RRF consumes order and is immune to this
by construction; `test_rrf_is_invariant_to_score_scale` pins it.

#### The result

| | dense (os ×5) | RRF k=60 | Δ |
|---|---|---|---|
| recall@1 | **0.0341** | 0.0305 | **−10.6%** |
| recall@5 | **0.1365** | 0.1198 | **−12.2%** |
| recall@10 | **0.2195** | 0.2042 | **−7.0%** |
| recall@20 | **0.3062** | 0.2993 | −2.3% |
| MRR | 0.7328 | **0.7335** | +0.1% |
| NDCG@10 | **0.5191** | 0.4989 | **−3.9%** |
| MAP | 0.2319 | **0.2431** | **+4.8%** |

**RRF loses to dense on every recall level and on NDCG@10, ties on MRR, and wins
only on MAP.** MAP rewards deep ordering over the whole ranked list, and the
fusion's union of two legs genuinely covers more of the corpus — the retrieval
failures drop from 6010 to 5144. But it pays for that coverage at the top of the
list, which is where NDCG@10 and recall@10 look and where a downstream RAG
consumer actually reads.

This is a **measured negative**, and it is reported as the result. It is not a
failed build: an unmeasured "we added hybrid retrieval and it helped" would have
been worse than useless.

The honest hedge in the other direction: the recall deltas are 2–12% relative on
n = 338. That is bigger than the eyeball-noise threshold this repo has been using
but it is one label snapshot on one corpus, and the sign could plausibly flip on
a corpus where the lexical leg is stronger. What can be said flatly is that
**there is no evidence RRF helps the top of the list here**, and the burden of
proof was on the fusion.

#### Why it loses — the mechanism, not a guess

The keyword leg is roughly two-thirds as good as dense (recall@10 0.1447 vs
0.2195) and its errors are **not** independent of dense's in the way fusion
needs. [§ Keyword query formulation](#keyword-query-formulation) §5 identified the failure mode and it reproduces here
at scale: on claims made of generic academic filler, an OR of
`highlight | superior | generaliz | approach | train | instanc | scale` matches
most of the corpus and ranks by whatever is longest and most vocabulary-rich.
RRF then treats that noise as a **vote**, and one vote from a leg that is wrong is
enough to push a correct dense hit out of the top 10. §6's second hand-check
shows exactly this happening.

#### k sensitivity

| k_rrf | R@1 | R@5 | R@10 | R@20 | MRR | NDCG@10 | MAP |
|---|---|---|---|---|---|---|---|
| 5 | 0.0300 | 0.1231 | 0.1981 | 0.2984 | 0.7324 | 0.4863 | 0.2393 |
| 10 | 0.0307 | 0.1243 | 0.2011 | 0.2993 | **0.7411** | 0.4955 | 0.2419 |
| 20 | **0.0308** | 0.1200 | **0.2047** | 0.2991 | 0.7363 | **0.4999** | 0.2428 |
| **60** (conventional) | 0.0305 | 0.1198 | 0.2042 | 0.2993 | 0.7335 | 0.4989 | **0.2431** |
| 120 | 0.0303 | 0.1197 | 0.2044 | 0.2993 | 0.7311 | 0.4987 | 0.2428 |
| 300 | 0.0303 | 0.1194 | 0.2044 | 0.2993 | 0.7306 | 0.4988 | 0.2428 |

**`k_rrf` barely matters, and it converges.** Across a 60× span the whole grid
moves by 0.007 on recall@10 and 0.014 on NDCG@10, and everything from 60 upward
is identical to three decimals. The only visible structure is at the small end:
`k_rrf = 5` sharpens the top ranks enough to *lose* 0.013 NDCG@10, because a
sharpened top rank means trusting the keyword leg's confident #1, and the keyword
leg's confident #1 is frequently a long survey paper.

Two things follow. First, **the conventional 60 is fine and nobody needs to tune
it** — this is a knob with no gradient. Second, and more usefully: because
`k_rrf` cannot rescue the arm, the fusion's deficit is not a tuning problem. It
is the keyword leg's error profile. Re-tuning `k_rrf` further would be measuring
noise.

#### Where RRF *would* be worth revisiting

Not as a replacement for dense at k=10, but as a **first-stage recall pool**. It
has the best coverage of any below-crossover arm (retrieval failures 5144 vs
6010) and the worst top-10 ordering. That is precisely the profile of a candidate
generator feeding a reranker. This document does not test that claim and does not
assert it.

---

### 6. Hand-checks — are the top hits actually relevant?

More rows is not better if they are noise, so every arm was eyeballed on the same
queries. Full output regenerable with `--inspect N`, or with the four-topic
comparison used below.

#### 6a. A content-bearing claim — all three arms are genuinely working

> *[ApjY32f3Xr] "First, domain decomposition is beneficial for addressing problems
> characterized by complex geometries, and PINN-NTK is a strong method for
> balancing loss weights as experiments show."* — 29 cited references in corpus

| arm | relevant in top 5 | top hit |
|---|---|---|
| dense | **5 / 5** | `shukla_2021_parallel_physics_informed_neural_networks_via_domain_decomposition` (0.676 on `hao_2022_..._survey`) |
| keyword v2 | **5 / 5** | `yao_2023_multiadam_parameter_wise_scale_invariant_optimizer` |
| RRF k=60 | **5 / 5** | `shukla_2021_parallel_pinns_via_domain_decomposition` |

Verdict: **not noise.** Dense's #2 is literally the domain-decomposition paper
the claim is about, and `wang_2021_when_and_why_pinns_fail_to_train_a_neural_
tangent_kernel_perspective` is its #3 — the claim names NTK. Keyword v2 finds a
different but also-correct five. RRF's top-5 is the union's best five and is also
all-relevant.

> *[BQvbL2sFQx] "This approach seamlessly integrates into existing CNN models, not
> only enforcing true shift equivariance but also enhancing generalization…"* —
> 12 cited references in corpus

| arm | relevant in top 5 |
|---|---|
| dense | **5 / 5** (`dieleman_2016_exploiting_cyclic_symmetry`, `marcos_2018_scale_equivariance_in_cnns_with_vector_fields`, …) |
| keyword v2 | **1 / 5** — three of its five hits are from unrelated fields (`shorten_2019_image_data_augmentation`, `zhao_2026_a_survey_of_large_language_models`, `hao_2022_physics_informed_ml`) |
| RRF k=60 | **4 / 5** |

Verdict: dense clean, keyword mostly noise, RRF recovers most of dense but drops
one relevant document to make room for keyword's `shorten_2019` survey. This is
the loss mechanism in miniature.

#### 6b. A contentless claim — every arm fails, and RRF makes it worse

> *[10eQ4Cfh8p] "We experimentally verified that our method can achieve good
> results."* — 8 cited references in corpus

| arm | relevant in top 10 | note |
|---|---|---|
| dense | 1 (**at rank 1**: `zhang_2020_learning_to_dispatch_for_job_shop_scheduling`) | the only correct hit, and it is first |
| keyword v2 | 1 (at rank 10) | `liu_2020_actor_critic_drl_for_solving_job_shop_scheduling` |
| RRF k=60 | **0** | dense's rank-1 hit is **pushed out of the top 10 entirely** |

This is the clearest single illustration of §5. Dense's confident and correct #1
got one vote; six documents that keyword ranked highly for containing the words
*experimentally*, *verified*, *method*, *results* got two weak votes each and
outranked it. A claim with no domain vocabulary gives the lexical leg nothing to
discriminate on, and RRF cannot tell an informative vote from an uninformative
one.

> *[10eQ4Cfh8p] "…we highlight the superior generalizability of our approach, as
> it maintains strong performance on large-scale instances even when trained on
> small-scale instances."* — 8 cited references in corpus

**0 / 5 relevant for all three arms.** Not one hit is even from job-shop
scheduling; the lists are full of LLM and dataset-distillation papers. The claim
contains no retrievable content. [§ Keyword query formulation](#keyword-query-formulation) flagged this same query on
the old corpus and it is unchanged at 5.7× the scale.

**Overall verdict on the hand-checks:** the arms are measuring retrieval, not
noise — on claims that carry domain vocabulary, top-5 precision is near perfect
for dense and RRF. The aggregate metrics are dragged down by a population of
contentless filler claims for which *no* retriever can succeed, because the query
carries no information. That is a **query-set property**, and it caps every
number in §3 in a way the construction ceiling does not capture. Filtering
non-content claims out of the query set would raise every arm and is the single
most likely source of a large apparent "improvement" that is not one.

The observed score ranges quoted in §5: dense cosine similarity across these
hand-checks spans 0.43–0.68; `ts_rank(…, 1|32)` spans 0.0038–0.0076. Two orders of
magnitude apart, on the same query.

---

### 7. Run integrity

`KEYWORD_SEARCH_DEGRADED` was **clear (`checked: true, degraded: false`) for all
11 runs**. All 11 are `valid: true`. Every record carries `plan`,
`recall_ceilings`, `percent_of_attainable`, and — for the fusions — per-leg row
counts:

```
fusion legs : dense 16900 rows (0 empty), keyword 16900 rows (0 empty)
```

The gate was verified to still fire on the RRF path, end to end, by pointing a
hybrid run at a project id with no data:

```
  RUN INVALID -- DO NOT QUOTE THESE NUMBERS
    - the hybrid retriever returned 0 rows for all 338 scored queries. ...
    - the dense leg of the fusion returned 0 rows across all 338 scored queries.
      Fusing with an empty leg is not a fusion; this run measures the other leg alone.
    - the keyword leg of the fusion returned 0 rows across all 338 scored queries. ...
[eval] exiting 3: this run's numbers are void.
```

The per-leg check is new and is the fusion-specific half of the gate: a hybrid
run whose keyword leg silently contributed nothing would otherwise report as a
perfectly healthy fusion while measuring dense alone. That is the exact class of
failure `rag_retrieval.keyword_search`'s swallowed exception caused in
production.

---

### 8. Caveats, in full

1. **Nothing here is comparable to [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded).** Different label
   fingerprint, 2.9× the indexed documents, 5.7× the queries, different ceilings.
2. **Nothing here is comparable to [§ Keyword query formulation](#keyword-query-formulation)'s or [§ HNSW sweep](#hnsw-sweep)'s
   absolutes either** (fingerprint `425df789a844f1f3`). The *directions* in those
   documents reproduce; the numbers do not transfer.
3. **The oversample arms are confounded with depth.** `dense_os2` returns at most
   20 chunks, which pool to fewer than 20 documents, so its recall@20 (0.1982) is
   depth-capped, not a ranking result. Only `dense_os5` vs `dense_os12` is a clean
   below-/above-crossover comparison, and even there the deeper arm has a
   mechanical advantage on recall@20 and MAP. **The plan flip is not the cause of
   `dense_os12`'s better numbers; the extra depth is.** Exact search and HNSW at
   `ef_search = 80` returned near-identical results in [§ HNSW sweep](#hnsw-sweep)
   (ANN@50 = 0.984) and there is no reason to expect otherwise here.
4. **No latency is reported.** This document measures quality only. [§ HNSW sweep](#hnsw-sweep)
   owns the latency curve, and its absolute timings are from the smaller corpus.
5. **The crossover is a property of this corpus and this machine's cost
   settings.** At 5948 chunks it is 103. It will keep rising roughly linearly with
   the row count. It is not a constant and must not be cached as one — that is
   why `plan` is measured per run rather than inferred from a remembered
   threshold.
6. **`unresolved` is 0 in every arm, and 211 references are excluded upstream as
   corpus gaps.** Those 211 are references the retriever could never have
   surfaced, and they are out of the recall denominator. The resolution *rate* is
   still **unknown**: 11 of 26 corpora have no `references.json` sidecar, so the
   attempted-reference denominator is not recoverable from disk. It is reported
   as unknown rather than substituted.
7. **The query set contains a substantial population of contentless claims** (§6).
   Every aggregate in §3 is an average over them. This is the largest single
   uncontrolled factor in the absolute numbers.
8. **RRF was measured with the keyword leg at `KEYWORD_SEARCH_V2=1`, which is OFF
   by default in production.** The fusion measured here is not the fusion
   production would run today; production's keyword leg is the v1 function that
   returns nothing for 95% of queries, and fusing with it would be dense scaled
   by a constant.
9. **Embedding spend was near zero.** 338 query embeddings, cached to
   `cache/retrieval_query_embeddings/text-embedding-3-large.json` and shared by
   all six dense-bearing arms, so every arm saw byte-identical vectors. That is a
   correctness property as much as a cost one: the API is not bit-stable across
   calls, and un-cached re-embedding would have introduced a difference between
   arms that has nothing to do with the retriever.

---

<a id="keyword-query-formulation"></a>

_Moved here unchanged from `scripts/eval/KEYWORD_QUERY.md`._

## Keyword query formulation — why lexical retrieval measured 0.004, and what fixed it

Companion to [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded), which recorded the finding. This document
records the diagnosis, the options measured against each other, the choice, and
the honest limits of the result.

Nothing here changes `keyword_search_chunks`. Migration 038 adds a **second**
function, `keyword_search_chunks_v2`, and `app/services/rag_retrieval.py`
selects between them with the `KEYWORD_SEARCH_V2` env flag, **default off**.

---

### 1. The finding

The first baseline measured keyword search at **recall@10 = 0.0040** against
dense at **0.4221**. That reads like a broken retriever. It is not.

`keyword_search_chunks` builds its query with `plainto_tsquery`, which **ANDs
every lemma**:

```
plainto_tsquery('english', 'job shop scheduling')  ->  'job' & 'shop' & 'schedul'
```

The queries this system issues are manuscript claims averaging ~20 words, so a
chunk must contain **all ~20 lemmas** to match at all. Reproduced directly
against the local eval database (118 docs / 2124 chunks, port 5433):

```
keyword_search_chunks(<proj>, 'job shop scheduling', 50)                     -> 38 rows
keyword_search_chunks(<proj>, 'we highlight the superior generalizability of
   our approach trained on small-scale instances', 50)                       ->  0 rows
```

**55 of the 59 scorable eval queries returned zero rows.** 6 rows total across
the entire run. This is a query-formulation mismatch, not a statement about
lexical retrieval, and it matters because a hybrid retriever fusing this leg
would be fusing dense with almost nothing.

---

### 2. Options considered

All measured on the **same 59 queries**, same database, same labels, in one
process. k = 10, chunk oversample ×5 (each query asks for 50 chunks, max-pooled
to documents), relevance unit = document — the configuration [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded)
defines.

| strategy | recall@10 | NDCG@10 | MAP | zero-row queries | ms/query |
|---|---|---|---|---|---|
| `plainto_tsquery` (current, ANDs) | 0.0026 | 0.0098 | 0.0026 | **55 / 59** | 4 |
| `websearch_to_tsquery` | 0.0077 | 0.0305 | 0.0082 | 53 / 59 | 8 |
| OR of lemmas, `ts_rank(…, 32)` | 0.2643 | 0.4578 | 0.2253 | 0 / 59 | 29 |
| OR of lemmas, `ts_rank_cd(…, 32)` | 0.2174 | 0.3916 | 0.1921 | 0 / 59 | 45 |
| OR, coverage-weighted `ts_rank` | 0.2509 | 0.4457 | 0.2229 | 0 / 59 | 159 |
| OR + ≥30 % term-coverage floor | 0.2643 | 0.4578 | 0.2253 | 0 / 59 | 217 |
| IDF-coverage score, all terms | 0.2633 | 0.4676 | 0.2465 | 0 / 59 | 118 |
| IDF-coverage, drop terms with df > 25 % | 0.2481 | 0.4604 | 0.2445 | 0 / 59 | 61 |
| IDF-coverage blended with `ts_rank` | 0.2669 | 0.4680 | 0.2461 | 0 / 59 | 104 |
| **OR of lemmas, `ts_rank(…, 1\|32)` — CHOSEN** | **0.2841** | **0.4960** | **0.2669** | **0 / 59** | 27 |

#### `websearch_to_tsquery` — rejected

Better ergonomics (free-form text, quoted phrases, `-exclusion`) but it **still
ANDs bare terms**, which is the actual problem. It lifted recall@10 from 0.0026
to 0.0077 and still returned nothing for 53 of 59 queries. It fixes the input
syntax, not the semantics. (The migration keeps the historical filename
`038_keyword_search_websearch.sql`; the measurement moved on from that idea.)

#### OR of the query's lemmas — chosen

There is no "`plainto_tsquery` but with OR" in Postgres, so the function extracts
the lemmas the index was built from (`tsvector_to_array(to_tsvector('english',
q))` — already stopword-stripped and stemmed) and rebuilds the query with `|`.

This is the permissive option, and permissiveness is the whole risk: for the
20-word claim above it matches **1648 of 2124 chunks (78 % of the corpus)**. All
of the discrimination therefore comes from the ranking, which is why §3 is not a
footnote.

#### The coverage floor — rejected *by measurement*

Requiring ≥30 % of the query's lemmas to be present looked like the obvious way
to cut the 78 %. Measured, it produced **recall@10 = 0.2643, NDCG@10 = 0.4578,
MAP = 0.2253 — identical to four decimals** to no floor at all, at **8×** the
latency (217 ms vs 27 ms; the per-row lexeme `INTERSECT` cannot use the GIN
index). `ts_rank` already down-weights chunks matching few query terms, so the
floor was redundant with the ranking rather than additive to it. Not shipped.

#### IDF term selection — rejected *for now*

The most principled option: score by the summed IDF of the query terms present
in the chunk, optionally dropping lemmas that appear in more than 25 % of chunks
(in an ML corpus, `train`/`approach`/`scale` are near-stopwords — measured
document frequencies for one claim were `small-scal` 11, `generaliz` 46,
`superior` 64, `highlight` 170, `instanc` 312, `small` 487, `approach` 670,
`scale` 782, `train` 1076 out of 2124). It is also cheap to compute: 9 GIN
probes, ~11 ms.

It did not win. Best IDF variant: recall@10 0.2669, NDCG@10 0.4680 — **below**
the chosen option on both, at 4× the latency and several times the complexity.
On 59 queries a few points is noise, so the honest reading is "no better", and
"no better" does not earn the machinery. Worth revisiting when the corpus is
large enough that ubiquitous domain terms genuinely dominate.

---

### 3. Ranking: `ts_rank(…, 1|32)`

Ranking mattered as much as matching. Normalisation flags, all with the same OR
query, same 59 queries:

| flags | meaning | recall@1 | recall@10 | recall@20 | MRR | NDCG@10 |
|---|---|---|---|---|---|---|
| `0` | raw `ts_rank` (unbounded) | 0.0339 | 0.2643 | 0.3536 | 0.6683 | 0.4578 |
| `32` | `rank/(rank+1)` | 0.0339 | 0.2643 | 0.3536 | 0.6683 | 0.4578 |
| `2` | ÷ length | 0.0339 | 0.2879 | **0.4405** | 0.6401 | 0.4582 |
| `2\|32` | ÷ length, bounded | 0.0339 | 0.2879 | **0.4405** | 0.6401 | 0.4582 |
| `4\|32` | ÷ mean harmonic distance, bounded | 0.0339 | 0.2643 | 0.3536 | 0.6683 | 0.4578 |
| **`1\|32`** | **÷ (1+log length), bounded** | **0.0472** | **0.2841** | 0.3939 | **0.7460** | **0.4960** |

- **Flag 32** bounds the score into (0, 1). It does not change the order within a
  query — it is monotonic, and flags `0` and `32` give bit-identical metrics —
  it makes scores comparable *across* queries, which matters because
  `hybrid_search` adds `0.3 × keyword_rank` to a cosine similarity already in
  [0, 1].
- **Flag 1** divides by `1 + log(length)`, so long chunks stop ranking high
  merely for containing more words. It is the only change that improved recall@1
  (0.0339 → 0.0472) and MRR (0.668 → 0.746).
- **`ts_rank_cd` was worse on every metric** (recall@10 0.2174, NDCG@10 0.3916).
  Cover density rewards query terms appearing *close together* — the right
  instinct for a phrase query, the wrong one for a 20-lemma OR where no chunk
  contains most of the terms.

`2|32` beats `1|32` on recall@20 (0.4405 vs 0.3939) and loses on everything
else. `1|32` was chosen because MRR and NDCG@10 describe the top of the list,
which is what a fusion consumes.

#### Escaping, not string-concatenation

The tsquery is assembled with `array_to_tsvector(ARRAY[lexeme])::text`, not
`quote_literal`. `quote_literal` renders a lexeme containing a backslash as
`E'c\\d'`, and the tsquery parser reads the `E` as part of the lexeme:

```
quote_literal      ->  'a''b' | 'E''c\\d''' | 'e f' | 'g|h'     (wrong)
array_to_tsvector  ->  'a''b' | 'c\\d'      | 'e f' | 'g|h'     (right)
```

An empty, whitespace-only, punctuation-only or stopword-only query produces no
lemmas, and the function returns **zero rows** rather than an error or an
unbounded OR. That distinction is load-bearing: `KEYWORD_SEARCH_DEGRADED` must
stay clear for "matched nothing" and fire only for "the RPC failed".

---

### 4. Before / after, on the same 59 queries

Both numbers come from the deployed RPCs in one process, against the same
database and the same label set (labels fingerprint `425df789a844f1f3`, 4
topics with both queries and an ingested corpus, 86 label docs, 118 indexed
docs). Reproduce with `scripts/eval/db.py` + `retrieval.run_retrieval_eval`'s
`run_eval`; nothing was written to `results/retrieval_eval.jsonl`.

| | `keyword_search_chunks` | `keyword_search_chunks_v2` |
|---|---|---|
| queries returning **zero rows** | **55 / 59** | **0 / 59** |
| median rows returned (k = 50) | **0** | **50** |
| total rows across the run | 6 | 2950 |
| recall@10 | 0.0026 | **0.2841** |
| precision@10 | 0.0051 | **0.4339** |
| hit-rate@10 (≥1 relevant doc in top 10) | 0.0339 | **0.9322** |
| MRR | 0.0339 | **0.7460** |
| NDCG@10 | 0.0098 | **0.4960** |
| MAP | 0.0026 | **0.2669** |
| latency | ~4 ms | ~22–42 ms |
| misses: *retrieval failure* (never returned) | 996 | 593 |
| misses: *ranking failure* (returned, below k) | 0 | 150 |

`KEYWORD_SEARCH_DEGRADED` was clear for both runs — these are real results, not
swallowed errors.

The failure-attribution shift is the shape of a working retriever: the old
function had **zero** ranking failures because it retrieved essentially nothing,
so every miss was a retrieval failure. 150 of the new misses are documents the
retriever *found* and ranked below 10 — a ranking problem, which is tractable.

**Two caveats on comparing these to [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded).** (1) That document reports
0.0040 for the old function; this run measures 0.0026 for the same function.
The difference is the label snapshot: more corpora have been built since, and
this run restricts the label set to the 4 scorable topics. The old-vs-new
comparison above is within one run and is the one to quote. (2) **Dense was not
re-measured under this label snapshot** — re-running it costs OpenAI query
embeddings. [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded)'s dense recall@10 = 0.4221 is from the earlier
snapshot and is therefore *approximately*, not exactly, comparable.

---

### 5. Hand inspection — are the new rows relevant, or merely numerous?

More rows is not better if they are noise, and an OR query matches almost
everything, so this section is not optional. Two aggregate checks and then the
eyeballing.

**Aggregate 1 — precision against the random baseline.** With 15.3 relevant docs
per query on average out of 118 indexed, a retriever returning random documents
would score precision@10 ≈ 0.14. Per topic:

| topic | queries | relevant docs | P@10 | random P@10 | lift | R@10 |
|---|---|---|---|---|---|---|
| 10eQ4Cfh8p (job-shop scheduling) | 24 | 8 | 0.275 | 0.068 | **4.1×** | 0.344 |
| 9ceadCJY4B (LLM evaluation) | 8 | 37 | 0.825 | 0.314 | **2.6×** | 0.223 |
| ApjY32f3Xr (physics-informed NNs) | 11 | 29 | 0.673 | 0.246 | **2.7×** | 0.232 |
| BQvbL2sFQx (shift invariance) | 16 | 12 | 0.225 | 0.102 | **2.2×** | 0.188 |
| all | 59 | — | 0.410 | 0.143 | **2.9×** | — |

(0.410 rather than §4's 0.4339 because this table counts unlabelled distractor
documents in the top 10 against precision, where ranx drops them. The stricter
denominator is the honest one for a noise check.)

Every topic clears its own base rate by 2.2–4.1×. This matters because
`9ceadCJY4B`'s raw P@10 of 0.825 would be misleading on its own: 37 of 118
documents are relevant to those queries, so a coin flip scores 0.31 there.

**Aggregate 2 — hit-rate@10 = 0.9322.** 55 of 59 queries surface at least one
cited reference in the top 10, against 2 of 59 before.

**The eyeballing.** Top-5 documents, `REL` = cited by that manuscript:

A content-bearing claim — every hit relevant and on-topic:

```
"Solving FJSP is equivalent to selecting a disjunction arc and fixing its
 direction for each operation node."
  REL  0.00711  zhang_2020_learning_to_dispatch_for_job_shop_scheduling
  REL  0.00698  hurink_1994_tabu_search_for_the_job_shop_scheduling_problem
  REL  0.00653  zhang_2020_learning_to_dispatch_for_job_shop_scheduling
  REL  0.00645  hurink_1994_tabu_search_for_the_job_shop_scheduling_problem
  REL  0.00583  han_2021_a_deep_reinforcement_learning_based_solution_for_fjsp
```

```
"This shows that directly optimizing an average of the PDE losses and
 initial/boundary condition losses leads to critical issues..."
  REL  0.00536  krishnapriyan_2021_characterizing_possible_failure_modes
  REL  0.00536  hao_2022_physics_informed_machine_learning_a_survey
  REL  0.00527  krishnapriyan_2021_characterizing_possible_failure_modes
  ...
```

A contentless claim — pure noise, and from the wrong field entirely:

```
"we highlight the superior generalizability of our approach, as it maintains
 strong performance on large-scale instances even when trained on small-scale..."
  (job-shop scheduling manuscript; not one hit is from its field)
       0.00557  <an unlabelled distractor document>
       0.00545  brown_2020_language_models_are_few_shot_learners
       0.00543  huang_2023_revisiting_the_reliability_of_psychological_scales
       0.00539  bommasani_2021_on_the_opportunities_and_risks_of_foundation_models
       0.00497  bommasani_2021_on_the_opportunities_and_risks_of_foundation_models
```

**Read:** the improvement is real but **conditional on the claim carrying
domain vocabulary**. Claims made of generic academic filler ("we highlight the
superior generalizability of our approach", "we experimentally verified that our
method achieves good results") have no discriminating lexemes, and an OR query
over `highlight | superior | generaliz | approach | train | instanc | scale`
retrieves whatever is longest and most vocabulary-rich. Note that
`bommasani_2021` (a 200-page survey) appears as a false hit repeatedly: document
scores are max-pooled over chunks, so a document with many chunks gets many
lottery tickets. Chunk-level length normalisation (flag 1) does not correct a
document-level chunk-count bias.

That is a real limitation of the *lexical leg specifically*, and it is exactly
the case dense retrieval handles better — which is the argument for fusing them
rather than picking one.

---

### 6. Is hybrid + RRF unblocked?

**Yes — with one concrete warning about *how* to fuse.**

Before: the keyword leg returned nothing for 93 % of queries. Any fusion would
have been dense scaled by 0.7, and the exercise could not have shown a benefit
because there was nothing to fuse. After: the leg returns rows for 100 % of
queries at recall@10 = 0.2841, precision@10 = 0.4339, MRR = 0.746 — roughly
two-thirds of dense's recall@10 (0.4221, earlier snapshot), with a plausibly
different error profile (it wins on claims with distinctive terminology, loses
on generic ones). That is a leg worth fusing.

**Use RRF, not `hybrid_search`'s weighted sum.** `ts_rank(…, 1|32)` is bounded
into (0, 1) but the values live in a narrow band near zero — every score in the
hand-inspection above is between **0.0038 and 0.0071**. Fed into
`0.7 × similarity + 0.3 × rank`, the keyword leg would contribute well under 1 %
of the combined score: technically fused, practically ignored. Reciprocal rank
fusion consumes *order*, not magnitude, and is immune to this. If a weighted sum
is wanted instead, the keyword score has to be rank-normalised per query first —
and that is a decision for the fusion lane, made explicitly, not inherited by
accident from `ts_rank`'s output scale.

**What is still not known.** n = 59, from 4 manuscripts, is small; the
[§ Retrieval baseline (superseded)](#retrieval-baseline-superseded) caveat that "a difference of a few points between two configurations
is noise" applies to every comparison in §2 and §3. The old-vs-new gap is ~100×
and survives that objection; the choice *among* the OR variants does not, and was
made on simplicity and latency as much as on the numbers. Nothing here has been
measured on production data, and the flag is off by default for that reason.

---

### 7. Reproducing

```bash
# 1. Apply the migration to the local eval database
docker exec -i noesis-pgvector psql -U noesis_local -d noesis_eval \
    < services/backend/migrations/038_keyword_search_websearch.sql

# 2. The two-row reproduction of the finding
docker exec -i noesis-pgvector psql -U noesis_local -d noesis_eval -c "
  SELECT 'old' , count(*) FROM keyword_search_chunks(
    'e7a1c0b0-0000-4000-8000-000000000001',
    'we highlight the superior generalizability of our approach trained on small-scale instances', 50)
  UNION ALL SELECT 'new', count(*) FROM keyword_search_chunks_v2(
    'e7a1c0b0-0000-4000-8000-000000000001',
    'we highlight the superior generalizability of our approach trained on small-scale instances', 50);"
# old -> 0     new -> 50

# 3. Turn the new path on in the application
export KEYWORD_SEARCH_V2=1        # default is off

# 4. Unit tests (no database, Supabase mocked)
cd services/backend && python3 -m pytest tests/test_keyword_query_formulation.py -v
```

The original `keyword_search_chunks` is untouched: its `pg_get_functiondef`
hash is `dc382fec1d5f5cfdf0815074c03af9eb` both before and after 038 is applied.

---

<a id="retrieval-baseline-superseded"></a>

_Moved here unchanged from `scripts/eval/retrieval/BASELINE.md`._

> **SUPERSEDED by [§ Retrieval baseline (15 topics)](#retrieval-baseline-15-topics). Do not quote the numbers below.**
> Two reasons: (1) the "dense (pgvector HNSW, cosine)" row was measured against an
> exhaustive sequential scan, not the HNSW index — Postgres declined the index
> above LIMIT ≈ 35 on the 2124-chunk corpus and the harness asks for 50; (2) the
> label snapshot this document ran under (fingerprint `019bee4a06eb2d39`, 118
> documents, 4 topics, 59 queries) no longer exists — the corpus is now 344
> documents / 5948 chunks across all 15 topics. Every arm has been re-measured
> under the current snapshot, and the construction ceilings recomputed. This file
> is kept as history, not as a reference.

## Retrieval baseline — first measured numbers, 2026-07-30

Before this run, `grep -rE "ndcg|MRR|recall@"` over this repository returned
nothing. There was no retrieval measurement of any kind. These are the first.

Read [EVAL_GUIDE.md § Relevance definition](./EVAL_GUIDE.md#relevance-definition) first — it defines the relevance unit, and every number below
is meaningless without it. Read §"What these numbers are not" here before
quoting anything.

Reproduce:

```
cd scripts/eval
python3 -m retrieval.run_retrieval_eval --retriever dense   --inspect 2
python3 -m retrieval.run_retrieval_eval --retriever keyword --inspect 2
```

Results append to `scripts/eval/results/retrieval_eval.jsonl`, one JSON record
per run, keyed by relevance unit + retriever + k + config hash. Nothing is ever
overwritten.

---

### 1. The numbers

Relevance unit: **document**. k = 10. Chunk oversample ×5 (each query asks the
index for 50 chunks, which are max-pooled to documents and then truncated to k).
Corpus: 118 documents / 2124 chunks in local pgvector. Binary relevance.

| metric | **dense** (pgvector HNSW, cosine) | **keyword** (Postgres FTS) |
|---|---|---|
| recall@1 | **0.0896** | 0.0034 |
| recall@5 | **0.3051** | 0.0040 |
| recall@10 | **0.4221** | 0.0040 |
| recall@20 | **0.5299** | 0.0040 |
| MRR | **0.8836** | 0.0339 |
| NDCG@10 | **0.6526** | 0.0112 |
| MAP | **0.4391** | 0.0040 |

Both runs are byte-identical on re-execution (config hashes `7330ae9c1e22ce33`
and `cf6b3f1b3fc00644`; two runs of each are on disk with identical metrics).

Hybrid fusion was **not** implemented or run. `HybridRetriever` remains a
deliberate stub. Fusion built before a baseline exists cannot be shown to have
helped, and there is now a baseline for it to beat.

#### Failure attribution

| | dense | keyword |
|---|---|---|
| total misses | 600 | 900 |
| ranking failure (retrieved, ranked below k) | 137 | 0 |
| retrieval failure (in corpus, not in the 50 chunks requested) | 463 | 900 |
| unresolved (no corpus doc id) | 0 | 0 |
| **excluded upstream as corpus gaps** | **65** | **65** |

"Retrieval failure" is named optimistically. It means *not in the 50 chunks the
retriever was asked for* — which for a topic with 37 relevant documents is
mostly the oversample depth, not an indexing bug. Do not read 463 as "463
documents are missing from the index"; every one of them is in the index.

Per topic (dense):

| topic | queries | relevant docs | ranking failures | retrieval failures |
|---|---|---|---|---|
| 10eQ4Cfh8p | 24 | 8 | 22 | 89 |
| 9ceadCJY4B | 8 | 37 | 59 | 164 |
| ApjY32f3Xr | 11 | 29 | 45 | 183 |
| BQvbL2sFQx | 16 | 6 | 11 | 27 |

#### recall@k is capped well below 1.0 by construction

Every query inherits its whole manuscript's reference list. A query with 37
relevant documents cannot exceed recall@10 = 10/37. The achievable ceiling,
weighted by query count:

| k | ceiling | dense achieved | fraction of achievable |
|---|---|---|---|
| 1 | 0.1061 | 0.0896 | 84% |
| 5 | 0.5307 | 0.3051 | 58% |
| 10 | 0.7789 | 0.4221 | 54% |
| 20 | 0.8798 | 0.5299 | 60% |

So dense recall@10 of 0.42 is 54% of the maximum this label design permits, not
42% of a reachable 100%. Anyone comparing 0.4221 against a published recall@10
from a benchmark with one relevant document per query is comparing two different
quantities.

#### The keyword leg is not degraded — it is doing exactly what it was told

`KEYWORD_SEARCH_DEGRADED` was **clear** for both runs: the RPC raised nothing,
so migration 037's fix holds against the local schema. The keyword numbers are
real, not a swallowed error. They are near zero because
`keyword_search_chunks` uses `plainto_tsquery`, which **AND**s every lemma in
the query. Our queries are natural-language claims averaging ~20 words, so a
chunk must contain all ~20 lemmas to match. It returned **0 rows for 55 of 59
queries** (29 rows total across the whole run).

Verified directly against the same database:

```
'job shop scheduling'                                        -> 20 rows
'reinforcement learning'                                     -> 20 rows
'we highlight the superior generalizability of our approach' ->  1 row
```

This is a finding about the query formulation, not about lexical retrieval.
Keyword search over long natural-language queries needs `websearch_to_tsquery`
with OR semantics, or query-term extraction upstream. Until one of those exists,
a hybrid retriever fusing this leg would be fusing dense with almost nothing.
That is worth knowing *before* building the fusion.

---

### 2. Scale — say how small

- **59 queries.** Not 338: 338 claim-queries were built from cached exports, but
  only 4 of the 15 manuscripts have a corpus, so 279 queries have no labels and
  are dropped rather than scored as zeros.
- **903 relevant judgments** (each query inherits its manuscript's full resolved
  reference list; 24×8 + 8×37 + 11×29 + 16×6 = 903).
- **119 resolved references** across 12 topics; **80** of them from the 4 topics
  that carry an authoritative sidecar.
- **65 references excluded as corpus gaps** — see §3.
- **118 documents / 2124 chunks** in the index. 118 is the pooled corpus: the 80
  new OpenReview reference PDFs plus 38 surviving `draft1`–`draft10` documents,
  which serve as distractors.
- **4 of 15 topics are built.** OpenAlex is now a metered paid API; the
  remaining 11 manuscripts have cached claims but no corpus, so they contribute
  queries that cannot be scored and no labels at all.

**n = 59 is small.** Confidence intervals on 59 queries across 4 manuscripts are
wide, and the 4 manuscripts are not a random sample of anything. A difference of
a few points between two configurations is noise. The dense-vs-keyword gap here
is roughly 60× and survives that objection; nothing smaller would.

---

### 3. Corpus gaps: 65 references excluded from the denominator

A reference that never became a downloadable PDF is not a retrieval miss — no
retriever could have surfaced it. All 65 are excluded from the recall
denominator and reported separately, with the reason `build_corpus.py` recorded:

| recorded status | count |
|---|---|
| `no_oa_pdf` | 27 |
| `pending` | 19 |
| `no_openalex_match` | 10 |
| `download_failed` | 9 |
| **total** | **65** |

Sidecar totals: **145 references attempted, 80 resolved (55.2%)** across the 4
OpenReview topics.

#### The matcher fix that produced that 65

Before this lane, `labels.py` counted **44** unresolved references where the
sidecars record **65** non-resolved entries. It had no access to per-reference
outcomes, so it guessed resolution from title-token overlap against downloaded
filenames — and that guess credited **21** references as resolved that
`build_corpus.py` records as never having downloaded. Each one inflated recall
by handing the retriever credit for a document that does not exist.

`references.json` now carries an authoritative per-reference `status`, so the
matcher defers to it:

- `status == "resolved"` **and** a `filename` → maps to that document, full stop.
- any other status → excluded from the denominator, counted by reason.
- `status == "resolved"` but the file is absent → also a gap
  (`resolved_but_file_missing`), because there is still nothing to retrieve.

The lenient title-token fallback survives **only** for a corpus whose sidecar has
no `status` field, and both `labels.py` and the eval CLI print a loud warning
naming every topic where it fired and stating that those topics' recall is
inflated. Today no topic uses it: the 4 OpenReview corpora use the sidecar
matcher and the 11 `draft*` corpora have no sidecar at all (their references
were never persisted, so their denominator remains unrecoverable and their
resolution rate is reported as UNKNOWN rather than as 100%).

Before → after: **44 → 65** unresolved. Per-topic resolution rates are unchanged
(24.2% / 75.5% / 76.3% / 24.0%), because on these four corpora the sidecar's
resolved set happens to match the directory listing exactly; what changed is
that 21 references stopped being silently credited.

---

### 4. What these numbers are not

1. **This measures "would we have found what the author cited", not "what is
   relevant."** The labels are the manuscripts' own reference lists. Authors
   cite for reasons other than relevance — collaborators, reviewer demands,
   venue convention, self-citation, what was available when they wrote. Every
   one of those is a false positive in the label set and none is detectable.

2. **It cannot reward finding relevant work the author missed** — the larger
   error, and the inverse one. A retriever that surfaces a highly relevant paper
   the author never cited is scored as a false positive: punished for doing
   exactly what the product exists to do. **Measured precision is therefore a
   lower bound**, the gap is unquantified, and MAP/NDCG inherit that bias.
   **Recall is the sounder number here.** Do not quote MAP = 0.4391 as though it
   were precision.

3. **The extractor was PyMuPDF, not production's Docling → GROBID → PyMuPDF
   chain.** With no GROBID sections, chunking fell back to *basic* adaptive
   chunking. This describes the **basic-chunking arm** only. The section-aware
   arm is unmeasured. Every manifest row records `extractor="pymupdf"` and
   `chunking_method="basic"` so no number here can later be attributed to the
   other arm.

4. **Open-access survivorship bias.** Only OA PDFs entered the corpus. 27 of 65
   gaps are `no_oa_pdf`. The corpus is not a random sample of a reference list;
   it is the OA-available subset, skewed recent and preprint-heavy.

5. **Distractors are other manuscripts' references, not a realistic corpus.**
   Negatives for topic A are the references of topics B..O. With 118 documents
   across topically distant areas (job-shop scheduling, LLM alignment,
   physics-informed neural nets, shift-invariance), retrieval is easier here than
   against a real literature index, and every metric is optimistic.

6. **`--max-papers 20` truncated long reference lists** in the older corpora, and
   only the first N in GROBID's emission order were attempted — not a random
   subset with respect to section or importance.

7. **No human made a relevance judgment for this harness.** The labels are
   *reused* human judgments (citation decisions) made for another purpose. That
   beats LLM-generated labels and loses to purpose-built ones.

8. **One document was ingested through a patched tokenizer.**
   `corpora/9ceadCJY4B/greshake_2023_not_what_youve_signed_up_for_*.pdf` contains
   the literal string `<|endoftext|>` three times, which makes `tiktoken` raise
   under its default `disallowed_special="all"`. Production has the identical
   bug (`app/services/rag_ingest.py:121`, `app/services/rag_chunking.py:380`), so
   that paper would fail production ingestion too. It was ingested here with
   special-token checking disabled; the only effect is that three short strings
   are counted as several tokens rather than one. Worth fixing upstream.

---

### 5. Ingest, for the record

| | |
|---|---|
| dry-run estimate (whole corpus) | 118 unique docs, 2124 chunks, 3,760,495 tokens, $0.4889 |
| actual this run | 80 ingested, 38 skipped (already present), 1426 chunks, 2,623,076 tokens, **$0.3410** |
| embedding | `text-embedding-3-large` @ dim=1536 (the same call `ingest.py` used, so the query and the index share a model) |
| extractor | PyMuPDF |
| chunking | basic adaptive, `CHUNKING_SPLITTER=pysbd` |
| wall clock | 128s |
| NUL chars stripped | 194 across 31 documents (bad embedded font encodings) |
| query embeddings | 59 per run, cached within a run |

---

### 6. Run integrity

Every record carries `valid`, `invalidated_by`, `degradation`, and
`retrieval_health`. A run is marked **invalid** and the CLI exits `3` when:

- `app.services.rag_retrieval.KEYWORD_SEARCH_DEGRADED` is set — the keyword RPC
  failed and the error was swallowed, so any number is an artefact of that
  failure rather than a measurement;
- the retriever returned 0 rows for every scored query — a broken connection or
  RPC, not a recall of 0.0;
- rows came back but **none** joined to a corpus document id — an id-space
  mismatch, not a retrieval result.

That last check is not hypothetical. `labels.py` identifies a document by
`sha256(pdf_bytes)[:16]`; `ingest.py` writes `uuid5(namespace, <full sha256>)`.
Those spaces never overlap, so an unmapped run reports a flat 0.0 on every metric
while looking perfectly healthy. `run_retrieval_eval.db_doc_id_map` translates
between them and the gate fails the run if the translation maps nothing.

When the backend is not importable the degradation state is recorded as
`degraded: null, checked: false` — never as `false`. "We did not check" and "we
checked and it is fine" are different claims.

---

<a id="corpus-build-report"></a>

_Moved here unchanged from `scripts/eval/BUILD_REPORT.md`._

## Corpus build report — 15-topic OpenReview retrieval corpus

Built `2026-07-30` with `scripts/eval/build_corpus.py --openreview-all --max-papers 0`
against an authenticated OpenAlex key. Exit code 0. No ingestion was run and no
database was written.

### Budget

| | Before | After |
|---|---|---|
| Auth state | authenticated | authenticated |
| Daily allowance remaining | **$0.9999** of $1.00 | **$0.6479** of $1.00 |
| Prepaid balance | $0.0000 | $0.0000 |
| Spendable | $0.9999 (~999 title searches) | $0.6479 (~647 title searches) |

**Actual spend: $0.3520.** That is the measured difference in the daily
allowance, not an estimate. [EVAL_GUIDE.md § OpenAlex](./EVAL_GUIDE.md#openalex) predicted ~$0.38 (worst case ~$0.43);
the run came in ~8% under the prediction.

**Requests: ~464 estimated, actual count not instrumented.** The script prints a
per-paper estimate before each corpus (summing to 464 requests / $0.382) but does
not report a realised request count, so the honest figure here is the estimate
plus the measured dollar spend. Five requests returned 5xx (`OpenAlex 504` once,
`OpenAlex 500` four times, all on `qBL04XXex6`); the script backed off
exponentially and all five recovered. Retried requests are additional to the 464.

Budget was never exhausted. **Zero references are in `pending` state anywhere in
the corpus** — every reference reached a terminal status.

### Per-paper results

`attempted` is `references_attempted` from each `references.json`; it equals both
the number of entries in that sidecar and the parsed reference count from the
source PDF. `pdfs` is the count of `.pdf` files actually on disk in the corpus
directory.

| Topic | Attempted | Resolved | PDFs on disk | `no_openalex_match` | `no_oa_pdf` | `download_failed` | `pending` | Rate |
|---|---|---|---|---|---|---|---|---|
| 10eQ4Cfh8p | 33 | 8 | 8 | 0 | 22 | 3 | 0 | 24.2% |
| 9ceadCJY4B | 49 | 37 | 37 | 8 | 2 | 2 | 0 | 75.5% |
| ApjY32f3Xr | 38 | 29 | 29 | 2 | 3 | 4 | 0 | 76.3% |
| BQvbL2sFQx | 25 | 12 | 12 | 4 | 7 | 2 | 0 | 48.0% |
| H9DYMIpz9c | 62 | 41 | 41 | 7 | 8 | 6 | 0 | 66.1% |
| cXs5md5wAq | 27 | 9 | 9 | 3 | 2 | 13 | 0 | 33.3% |
| eR4W9tnJoZ | 12 | 2 | 2 | 3 | 2 | 5 | 0 | 16.7% |
| eUgS9Ig8JG | 20 | 13 | 13 | 4 | 3 | 0 | 0 | 65.0% |
| gYcft1HIaU | 29 | 16 | 16 | 8 | 1 | 4 | 0 | 55.2% |
| jx6njBKH8E | 55 | 37 | 37 | 10 | 7 | 1 | 0 | 67.3% |
| kKRbAY4CXv | 22 | 8 | 8 | 6 | 4 | 4 | 0 | 36.4% |
| miGpIhquyB | 59 | 43 | 43 | 12 | 3 | 1 | 0 | 72.9% |
| qBL04XXex6 | 32 | 25 | 25 | 3 | 3 | 1 | 0 | 78.1% |
| rhgIgTSSxW | 52 | 36 | 36 | 3 | 9 | 4 | 0 | 69.2% |
| rp5vfyp5Np | 29 | 17 | 17 | 5 | 5 | 2 | 0 | 58.6% |
| **Total** | **544** | **333** | **333** | **78** | **81** | **52** | **0** | **61.2%** |

#### What the non-resolved statuses mean

- **`no_openalex_match` (78, 14.3%)** — OpenAlex was asked and returned nothing
  usable for that reference string. Concentrated in references that are not
  indexed works: arXiv-only preprints cited informally, non-English entries, blog
  posts and URLs, workshop papers. Terminal.
- **`no_oa_pdf` (81, 14.9%)** — the work was matched in OpenAlex but has no open
  access location, so there is no PDF to fetch. Terminal, and not a failure of
  the pipeline: it is a property of the literature. `10eQ4Cfh8p` is the outlier
  here (22 of its 33 refs), which is why its rate is the corpus low.
- **`download_failed` (52, 9.6%)** — OpenAlex reported an `oa_url` but the fetch
  from that publisher or repository did not yield a usable PDF (403 bot walls,
  landing pages instead of files, dead repository handles, ACM/Elsevier
  gateways). These are the recoverable ones: a re-run with different fetch
  handling could convert some. `cXs5md5wAq` lost 13 refs this way alone.

### Corpus-wide resolution rate

**333 / 544 = 61.2%.**

The denominator is 544, the sum of `references_attempted` across all 15 sidecars.
This is verifiable and not `resolved/resolved`: every reference OpenAlex was asked
about is present in a `references.json` with its own terminal status, the entry
count of each sidecar equals its `references_attempted`, and the four status
buckets sum exactly to 544 (333 + 78 + 81 + 52 = 544). The number of `.pdf` files
on disk equals `resolved` in every one of the 15 directories.

### 15 topics versus the previous 4

| | 4-topic corpus (before) | Same 4 topics (now) | 15-topic corpus (now) |
|---|---|---|---|
| Resolved / attempted | 80 / 145 | 86 / 145 | 333 / 544 |
| Rate | 55.2% | 59.3% | **61.2%** |

The 4 pre-existing topics went from 80 to 86 resolved with no change in
denominator. All six came from retrying `BQvbL2sFQx`'s 19 `pending` references,
which took that topic from 6/25 to **12/25**. The other three were already
complete and cost nothing to re-check.

The 11 new topics contributed 247 / 399 = 61.9%, marginally better than the
existing four, which is why the corpus-wide rate rises rather than falls. The
retrieval baseline now covers **15 of 15 topics** and is 3.75x larger in
resolved documents (333 vs 89 — 89 being the 4-topic set as it now stands after
the pending retry, including the 3 unchanged topics).

### Caveat: the denominator is references *as segmented by the parser*

`544` counts reference entries as `build_corpus.py` extracted them, not
reference entries as the papers actually list them. The extractor under-segments:
scanning the `raw` field of every sidecar entry, **60 of 544 entries (11%) are
long blocks containing two or more distinct works** — e.g. one `BQvbL2sFQx` entry
whose `raw` runs "Ian Goodfellow, Yoshua Bengio, Aaron Courville … Deep learning,
volume 1. MIT press Cambridge, 2016. Suriya Gunasekar. Generalization to
translation shifts …", two separate references merged into one. Only the second
was resolved and recorded; the first was never looked up.

So the true bibliography across the 15 papers is **larger than 544**, and 61.2%
is a rate over what the parser produced, not over what the papers cite. The rate
is internally consistent and comparable across the 15 topics — every topic was
parsed and resolved the same way — but it should not be quoted as "we resolve
61% of the references in these papers."

**No paper failed to parse outright.** All 15 produced references. One paper is
badly enough under-parsed to name explicitly:

- **`eR4W9tnJoZ`** — 12 references parsed, of which 7 (58%) are suspected merged
  blocks, the worst ratio in the corpus. Its reference section in the source PDF
  visibly contains well over twice that many entries. Its `2/12 = 16.7%` is
  reported above for completeness but is the least trustworthy per-topic number
  here, on both numerator and denominator, and it is the smallest corpus by a
  wide margin. Treat it as provisional.

Fixing this needs a change to the reference segmenter in `build_corpus.py`, which
was out of scope for this build. Doing so would raise the denominator, change
every sidecar, and require a re-run.

### Verification performed

1. `--check-budget` before and after — figures in the table above.
2. Every corpus directory has a `references.json`; its entry count equals
   `references_attempted`, and its `resolved` count equals the number of PDFs on
   disk. Checked for all 15.
3. Zero references in `pending` state.
4. Re-ran `--openreview-all --max-papers 0` after completion: **4.15s wall clock,
   every topic reported "all N refs already recorded — nothing to do"**, and the
   budget was **still $0.6479** afterwards, confirming zero network calls. Build
   is idempotent.
5. No ingestion. `scripts/eval/results/*.jsonl` line counts are unchanged from
   before the build: `node_eval_spans.jsonl` 11, `openreview_history.jsonl` 10,
   `node_eval.jsonl` 14, `retrieval_eval.jsonl` 4.

---

<a id="hnsw-sweep"></a>

_Moved here unchanged from `scripts/eval/ANN_SWEEP.md`._

## HNSW sweep — the recall-vs-latency curve for the vector index

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

### 0. The headline, before the tables

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
[§ Retrieval baseline (superseded)](#retrieval-baseline-superseded)'s "dense (pgvector HNSW, cosine)" numbers were in fact
measured against an exhaustive scan. That is a labelling error in the baseline,
not a wrong number: exact search is a legitimate retriever, it just is not HNSW.

---

### 1. Does the planner use the index? (`record_type: planner_choice`)

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

### 2. Exact sequential scan — the recall = 1.0 ceiling

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

### 3. `ef_search` sweep

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
  [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded) §"recall@k is capped well below 1.0").

#### 3A. k = 50 — planner free (what the eval harness executes)

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

#### 3B. k = 50 — index forced (`enable_seqscan = off`, other indexes dropped inside a rolled-back transaction)

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

#### 3C. k = 10 — production's real depth, planner free

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

### 4. `m` × `ef_construction` sweep

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

### 5. Index-set restoration — before and after

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

### 6. Recommended operating point

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
[§ Retrieval baseline (superseded)](#retrieval-baseline-superseded)'s dense row is an exact-scan result wearing an index's
name.

---

### 7. Does any of this generalise? Mostly no.

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

### 8. Measurement method, in full

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
* **Label-set drift:** [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded) reports dense recall@10 = 0.4221
  with labels fingerprint `019bee4a06eb2d39`. This sweep measures 0.3488 with
  fingerprint `425df789a844f1f3`. The difference is the label set, not the
  retriever — another lane added PDFs under `corpora/` between the two runs.
  Comparisons **within** this document are all against the same fingerprint and
  are valid; comparisons against [§ Retrieval baseline (superseded)](#retrieval-baseline-superseded)'s absolute numbers are not.

---

<a id="node-replay-cost"></a>

_Moved here unchanged from `scripts/eval/NODE_COST.md`._

## Node replay cost — the first complete measurement

Measured 2026-07-31. Tool: `scripts/eval/node_eval.py`. Results appended to
`scripts/eval/results/node_eval.jsonl` (run ids `f0af0ecb5365`, `9c11daa01698`,
`82092c60b36c`, `dc045ccaaadb`).

### Every cost figure produced before this run was a lower bound

Not "approximately right" — **low by a margin that cannot be recovered**.

`scripts/eval/match.py` computes the severity-weighted-recall metric and makes
two kinds of network call: an embedding batch and one or more GPT confirmation
calls. Until 2026-07-30 it called the OpenAI client directly. Those calls were:

* not recorded by `llm_budget`, so they appeared in no total this harness printed;
* not bounded by `NOESIS_LLM_KILL_SWITCH`, `EVAL_REPLAY_ONLY`,
  `NOESIS_LLM_MAX_CALLS` or `NOESIS_LLM_MAX_SPEND_USD`.

The margin is unrecoverable rather than merely unknown. The matcher's disk
caches (`cache/match/embed`, `cache/match/confirm`) store an embedding vector
and a `{confirmed, reason}` verdict respectively — no prompt text, no usage
block, no model. There is nothing on disk from which the missing token counts
could be reconstructed. The most-quoted prior figure, **$0.21999** for a
three-invocation node-replay exercise, made **6 uncounted matcher calls** (3
embed + 3 confirm, visible only as counters in `match_stats`) and reported
$0.00 for all of them.

The matcher is now guarded and recorded (`match._match_label` composes
`match:` with the ambient node label). This run is therefore the first complete
figure the harness has produced.

`node_eval.replay_once` now slices `llm_budget` twice per replay: `usage` is
what the node spent inside its span, `match_usage` is what scoring its output
spent afterwards. Both are in the run total. `run_summary.spend_by_label`
carries per-label dollars so the total is reconcilable against its own
breakdown — the property that was silently false before, since node-only totals
could never have summed to the money actually being spent.

#### Still outside the accounting

`scripts/eval/atomize_reviews.py` (gold-side atomization) also calls OpenAI
directly and is still neither guarded nor recorded. It contributed **$0.00 to
this run**: `score_replay` now returns `atomize_stats`, and every replay
reported `{"cache_hits": 4, "llm_calls": 0}` — the atomize cache was fully warm
for all three papers. That is luck, not a guarantee. It is the one remaining
bypass and it should be wired up the same way `match.py` was.

### Total

| | node | matcher | total |
|---|---|---|---|
| recorded spend | $0.16761 | $0.03255 | **$0.20016** |
| share | 83.7% | **16.3%** | 100% |

**Matcher spend is 16.3% of the complete figure** — that is exactly the margin
older numbers were missing, and it is not uniform. It scales with how many
items a node emits, not with what the node cost:

| node | node $ | matcher $ | matcher share |
|---|---|---|---|
| `run_quality_diagnostics` | $0.00000 | $0.00277 | **100%** |
| `editor_pass_node` | $0.00339 | $0.00297 | **46.7%** |
| `reviewer_panel_node[methodology]` | $0.12098 | $0.02682 | 18.1% |

A node the old accounting reported as **free** costs $0.00277 to measure. The
cheaper the node, the worse the old figure was in relative terms.

Against the prior exercise: the old $0.21999 was node spend only. On these
replays the matcher runs about **$0.005 per scored `reviewer_panel_node`
replay**, so the prior metric-enabled run (`4ce7276cc133`, 3 replays, reported
$0.06256) was short by roughly **$0.015, about 19% of its true cost**.

### Per-node

Same shape as the prior table. All figures from run ids above; `wall` is summed
node span time (matcher time is outside the span, as before).

| node | n | wall | LLM calls | input (cached) | node $ | matcher $ | matcher calls | total $ |
|---|---|---|---|---|---|---|---|---|
| `reviewer_panel_node[methodology]` | 5 | 96.43s | 5 | 46,120 (36,352) | $0.12098 | $0.02682 | 10 | **$0.14779** |
| `reviewer_panel_node[literature_positioning]` | 1 | 19.52s | 1 | 8,697 (8,064) | $0.02251 | — | 0 | $0.02251 |
| `reviewer_panel_node[clarity]` | 1 | 16.64s | 1 | 8,657 (8,064) | $0.02073 | — | 0 | $0.02073 |
| `editor_pass_node` | 3 | 23.35s | 3 | 2,682 (0) | $0.00339 | $0.00297 | 2 | **$0.00636** |
| `run_quality_diagnostics` | 3 | 0.18s | 0 | 0 | $0.00000 | $0.00277 | 3 | **$0.00277** |

Model: `gpt-5.2-chat-latest` for nodes, `gpt-5.2` + `text-embedding-3-small`
for the matcher. Embedding spend is negligible ($0.000029 across the whole
run); essentially all matcher cost is the confirmation call.

The two single-persona panel rows ran `--no-metric` (they exist to measure
prefix caching, not quality), hence no matcher spend.

#### Comparability with the prior table

* `editor_pass_node` and `run_quality_diagnostics` are the identical selection
  (same 2 nodes × same 3 papers). `editor_pass_node` consumed **exactly 2,682
  prompt tokens both times** — the fixtures are deterministic inputs, so the
  only movement is on the output side ($0.00399 → $0.00339, 1,360 completion
  tokens this time).
* The panel row is **not** the same composition. The prior `n=5` mixed two
  papers (`10eQ4Cfh8p` and the much larger `9ceadCJY4B`, which alone accounted
  for 53,535 of the prior 90,215 input tokens). This run is 5 × `10eQ4Cfh8p`,
  deliberately, so latency variance is measured on one fixture instead of being
  confounded by fixture size. Compare per-call, not row totals.

#### Does the corpus change affect comparability?

No, for this selection. The database went from 118 documents / 4 topics to
5,948 chunks / 344 documents / 15 topics. That is irrelevant here because:

* node fixtures are JSON on disk and already contain whatever evidence the node
  saw upstream — a replayed `reviewer_panel_node` does not re-query the corpus;
* the matcher embeds critique text and gold review units, not corpus chunks,
  and its embedding cache is keyed on text, not on database state.

It **would** matter for `search_literature`, `detect_gaps` or
`discover_external_sources`, which query live. None of those are in this
selection, and a future cost comparison that includes them is not comparable
across the corpus change.

### What the prefix-caching reorder actually bought

The panel prompt was reordered so the shared preamble and manuscript come first
and the persona block last, giving a byte-identical prefix across all three
personas. The 58.8% hit-rate figure came from a purpose-built A/B. Here is what
it does on the normal replay path.

Replaying one persona at a time, on paper `10eQ4Cfh8p`:

| call | prompt | cached | hit rate | $ |
|---|---|---|---|---|
| methodology #1 (nothing warm) | 9,224 | 0 | 0.0% | $0.035224 |
| methodology #2–#5 (same persona again) | 9,224 | 9,088 | 98.5% | $0.02071 / $0.02027 / $0.02395 / $0.02083 |
| clarity (persona never sent before) | 8,657 | 8,064 | **93.2%** | $0.020733 |
| literature_positioning (ditto) | 8,697 | 8,064 | **92.7%** | $0.022511 |

The load-bearing rows are the last two. Those personas' prompts had **never**
been sent, yet 8,064 tokens came back cached — that is the shared prefix, and
nothing but the reorder puts it there. 8,064 tokens is 87.4% of the
methodology prompt, against the 85% the A/B claimed (8,064 = 63 × 128, i.e. it
is quantised to OpenAI's cache block size).

Rolled up to a cold three-persona panel: 16,128 cached of 26,578 prompt tokens
= **60.7% hit rate**, versus the A/B's 58.8%. Costing the cached tokens at the
full input rate instead of the cached rate ($1.75 vs $0.175 per 1M) gives a
counterfactual uncached panel of $0.10387 against the measured $0.07847, i.e.
**24.5% cheaper per cold panel**, versus the A/B's 23.8%.

Both A/B numbers reproduce on the real replay path, within ~2 points.

One caveat that matters for reading the table: in a `--repeat` run the
*repeats* also hit the cache (98.5%, larger than the cross-persona prefix
because the whole prompt including the persona block is warm). So a repeat-N
panel measurement understates cost per genuinely cold panel. Only the first
call of a cold run is priced like production. That is why the aggregate row
above shows `cached_prompt_fraction = 0.788` — it is 1 cold call and 4 warm
ones, not a production figure.

`DRAFT_REVIEWER_COMPACT_MANUSCRIPT` remains OFF and was OFF for this run.

### Variance

#### Latency — measurable, n=5

`reviewer_panel_node[methodology]` @ `10eQ4Cfh8p`, 5 replays of one fixture:

```
17.10  18.26  19.69  24.13  17.25   (seconds)
mean 19.286   sd 2.897   CV 15.0%   min 17.10   max 24.13
```

95% CI on the mean (t, 4 df): **19.29 ± 3.60 s → [15.69, 22.89]**.

The prior claim of CV ~7% came from n=3 and does not survive n=5 — the spread
roughly doubled once a fifth sample was drawn. What is defensible: a latency
difference smaller than about **±19% of the mean (~±3.6 s)** is not resolvable
with n=5 on this node. Anything claimed inside that band needs more samples,
not more confidence. Note the 24.13 s outlier is a single sample and there is
no basis in n=5 for excluding it.

The three cheap nodes are not interestingly variable: `run_quality_diagnostics`
runs in 0.02–0.12 s and makes no LLM call at all.

#### Quality — still unresolvable, no delta reported

Severity-weighted recall across the same 5 replays, 79 gold units:

```
0.0463  0.0232  0.0000  0.0116  0.0116
mean 0.0185   sd 0.0176   CV 95%
```

In matched units: **4, 2, 0, 1, 1** out of 79. The metric is quantised at
~0.0116 per matched unit, so sd ≈ 1.5 quanta and the observed range spans the
entire signal. Five draws from the same fixture, same prompt, same model
produced anything from zero matches to four.

**No quality delta is reported from this run, and none should be inferred from
it.** The cause is unchanged: `retry_utils` strips `temperature` for every
`gpt-5.2*` model and no seed is set anywhere, so replays are genuinely
non-deterministic. At n=5 the CV improved from the prior ~172% only because the
mean happened to land away from zero, not because the measurement got tighter.
Any quality claim on this node needs either a seed, a much larger n, or a
metric that is not quantised at 1/79 of its own range.

### Spend against estimate

| run | selection | estimated node calls | actual | recorded $ |
|---|---|---|---|---|
| `f0af0ecb5365` | diagnostics + editor × 3 papers, metric ON | 3–3 | 3 | $0.009126 |
| `9c11daa01698` | panel[methodology] × 5, metric ON | 5–10 | 5 | $0.147794 |
| `82092c60b36c` | panel[clarity] × 1, `--no-metric` | 1–2 | 1 | $0.020733 |
| `dc045ccaaadb` | panel[literature_positioning] × 1, `--no-metric` | 1–2 | 1 | $0.022511 |
| | | **10–17** | **10** | **$0.200164** |

Every invocation set both `NOESIS_LLM_MAX_CALLS` and
`NOESIS_LLM_MAX_SPEND_USD`; no ceiling tripped and no run halted. Actual node
calls landed on the low end of every band — the conditional domain-audit call
that widens the panel estimate to 2 never fired.

**Plus about $0.02 that is not in that table.** A first attempt at the
`literature_positioning` replay was killed by an operator-side shell timeout
(a buffering pipeline, not the node — the retry completed in 19.5 s). The node
had almost certainly already made its call. `NOESIS_LLM_USAGE_LOG` was not set
for that attempt, so the process died with its usage only in memory and the
spend is gone. True spend for this exercise is therefore **~$0.22**, against
the prior exercise's $0.21999 — same order, as intended.

That is a small, on-theme lesson: **set `NOESIS_LLM_USAGE_LOG` on every paid
run.** It is an append-only sink written per call, so a killed process still
leaves its spend on disk. The retry did set it and the record survived.

### Reproducing this

From the repo root, with `OPENAI_API_KEY` exported (`node_eval` is run as a
module so that `score_replay`'s `scripts.eval.*` imports resolve):

```bash
set -a; . services/backend/.env; set +a

# 1. Always dry-run first. Resolves the selection, prints the estimate band,
#    imports no node and makes no call.
python3 -m scripts.eval.node_eval \
  --node run_quality_diagnostics --node editor_pass_node \
  --paper 10eQ4Cfh8p --paper 9ceadCJY4B --paper ApjY32f3Xr --dry-run

# 2. Cheap nodes, metric ON — this is what surfaces matcher spend.
NOESIS_LLM_MAX_CALLS=20 NOESIS_LLM_MAX_SPEND_USD=0.06 \
NOESIS_LLM_USAGE_LOG=/tmp/usage.jsonl \
python3 -m scripts.eval.node_eval \
  --node run_quality_diagnostics --node editor_pass_node \
  --paper 10eQ4Cfh8p --paper 9ceadCJY4B --paper ApjY32f3Xr

# 3. Latency + quality variance on one fixture.
NOESIS_LLM_MAX_CALLS=30 NOESIS_LLM_MAX_SPEND_USD=0.20 \
NOESIS_LLM_USAGE_LOG=/tmp/usage.jsonl \
python3 -m scripts.eval.node_eval \
  --node reviewer_panel_node --paper 10eQ4Cfh8p \
  --reviewer-type methodology --repeat 5 --yes

# 4. Prefix caching. Must run within the cache TTL (~5-10 min) of step 3, and
#    with --no-metric: these measure cache hits, not quality.
for rt in clarity literature_positioning; do
  NOESIS_LLM_MAX_CALLS=6 NOESIS_LLM_MAX_SPEND_USD=0.05 \
  NOESIS_LLM_USAGE_LOG=/tmp/usage.jsonl \
  python3 -m scripts.eval.node_eval \
    --node reviewer_panel_node --paper 10eQ4Cfh8p \
    --reviewer-type "$rt" --repeat 1 --no-metric
done
```

Notes for whoever repeats this:

* Order matters in step 4. It only measures the cross-persona prefix if a
  sibling persona was sent recently. Run it cold and you measure nothing.
* `--repeat` inflates the cache hit rate. Do not quote a repeat-N
  `cached_prompt_fraction` as a production number.
* The matcher call count is *not* in the `--dry-run` estimate band — it depends
  on how many items the node emits and how much of the pair cache hits. Leave
  headroom in the ceilings or pass `--no-metric`.
* Results are append-only. Nothing here ever opens
  `results/node_eval.jsonl` in anything but `"a"` mode; this repo has lost its
  eval history to an in-place rewrite once already.

---

<a id="prompt-caching"></a>

_Moved here unchanged from `scripts/eval/PROMPT_CACHE.md`._

## Prompt caching in the reviewer panel

Measured 2026-07-30. Model `gpt-5.2-chat-latest`, priced from
`app/core/llm_budget.py` (input $1.75 / cached input $0.175 / output $14.00 per
1M tokens, retrieved 2026-07-30).

### What was already true

OpenAI's automatic prefix cache was already working with no `cache_control`
anywhere in this repo. Replaying the *same* prompt twice within the cache TTL
already returned ~99% `cached_tokens`. Nothing here turns caching on.

What did **not** work was cache reuse *across the three panel personas*, which
is where the volume is: one draft produces three reviewer calls whose prompts are
~88% identical text.

### The ordering problem

The prompt cache keys on an exact token prefix. The old assembly put the variable
part first:

```
system : REVIEWER_PROMPTS[reviewer_type]   <- persona text, differs at token ~5
user   : "Review this paper:\n\n" + metadata + profile + FULL MANUSCRIPT
         + persona-specific context slice
```

Because the persona sits at the head of the system message, the three calls
diverge on their first few tokens and share **no** cacheable prefix — the
manuscript (the expensive part) was paid for at full input rate three times.

### The new ordering

```
system : SHARED_REVIEWER_PREAMBLE          <- byte-identical for all 3 personas
                                              (generic framing + RATING_CALIBRATION)
user   : "Review this paper:\n\n"
         + DRAFT METADATA                  <- shared
         + MANUSCRIPT PROFILE / route      <- shared
         + FULL MANUSCRIPT TEXT            <- shared, the expensive block
         + persona context slice           <- variable
         + "YOUR REVIEWER ASSIGNMENT:" + persona block   <- variable, LAST
```

`build_shared_reviewer_prefix()` produces the invariant head;
`build_reviewer_messages()` assembles the pair. `REVIEWER_PROMPTS` is retained
(persona + calibration, as before) because `reviewer_judge._retry_reviewer`
consumes it as a standalone system prompt.

Prefix-breakers checked and confirmed absent from the shared head: no timestamp,
no uuid, no `draft_id`/`project_id`/`user_id`, no reviewer type. Every list
rendered into the profile block (`domain_tags`, `secondary_domains`,
`FORBIDDEN_REVIEW_STANDARDS`, `DOMAIN_PROMPT_PACKS`) comes from an ordered
list/tuple, not a set, so the block is byte-stable across runs.
`tests/test_prompt_cache_structure.py` pins all of this without touching the
network.

### Measured: cold panel of 3 personas, one draft

Paper `eR4W9tnJoZ` (~9.1k prompt tokens/call), no prior warm cache for this
paper, arms run AFTER-then-BEFORE so the old layout had every chance to warm:

| | prompt tokens | cached tokens | hit rate | $/panel | $/replay |
|---|---|---|---|---|---|
| BEFORE (persona first) | 27,265 | 0 | **0.0%** | $0.1103 | $0.0368 |
| AFTER (shared prefix first) | 27,428 | 16,128 | **58.8%** | $0.0841 | $0.0280 |

Per-call: calls 2 and 3 of the panel go from 0 cached tokens to 8,064 cached
(87–93% of their prompt). Call 1 is always cold — it is what populates the cache.
Ceiling for a 3-call panel is therefore ~2/3 × (shared fraction) ≈ 59%, which is
what was measured. Cost reduction on a cold panel: **23.8%**.

Prompt tokens rise 0.6% (+~55 tokens/call) because the shared preamble adds a
short framing sentence. That is paid once at full rate and returned tenfold.

Confirmation on a second paper (`10eQ4Cfh8p`, 2 rounds × 3 personas):

* round 1 (cold): BEFORE 34.4% (contaminated — one persona was already warm from
  concurrent work), AFTER 60.7%
* round 2 (exact repeat): BEFORE 98.9%, AFTER 98.7% — as expected, exact repeats
  already cached fine under either layout. The reordering does not help repeats;
  it helps the *first* pass, which is the only pass a real user run has.

### Manuscript compaction — `DRAFT_REVIEWER_COMPACT_MANUSCRIPT`

Default **OFF**. When set (`1/true/yes/on`), `_reviewer_manuscript_text()` routes
the draft through `_section_excerpts()` (1400 chars/section, max 7 sections,
`[:5000]` fallback when no headings are detected) and caps the result at
`DRAFT_REVIEWER_MANUSCRIPT_MAX_CHARS` (24000).

`node_eval.py --node reviewer_panel_node --paper 10eQ4Cfh8p --reviewer-type
methodology --repeat 5`:

| | prompt tokens/replay | $/replay | recall mean (n) | recall stdev |
|---|---|---|---|---|
| OFF | 9,224 | $0.0216 (4 replays, ~98% warm) | 0.0087 (n=4) | 0.0058 |
| ON | 3,622 | $0.0204 (5 replays, ~87% warm) | 0.0100 (n=5) | 0.0101 |

**Token reduction: 60.7%.** The $/replay difference is only ~5% and is *not* the
real cost picture — both arms ran against a warm cache, where input is already
billed at the 10× discount. On a cold call the saving is the full 60.7% of input:
9,224 → 3,622 tokens ≈ $0.0161 → $0.0063.

**Quality effect: not resolvable.** The severity-weighted-recall metric is
quantized here in steps of 0.0116 (one matched review unit), both arms sit within
one step of zero, and the spread swamps the difference (Welch t ≈ 0.24). This is
the known variance floor: `temperature` is stripped for `gpt-5.2*` models and no
seed is available, so identical inputs give different outputs. With n=4/5 the
compaction quality delta **could not be distinguished from run-to-run noise** —
do not read the +0.0013 as an improvement.

There is also a first-principles cost that the metric cannot see: the
`GROUNDING RULE` in `RATING_CALIBRATION` instructs reviewers to search the entire
manuscript before claiming something is absent. Compaction removes ~60% of that
text, so false "not reported" critiques should become *more* likely. Keep the
flag OFF until an eval with enough repetitions to resolve it exists.

### Not changed

`audit_domain_triggers()` still sends the full uncompacted manuscript, and its
checklist sits before the manuscript in the user message. It is the second-call
path that makes a triggered replay ~6× the single-call cost. It cannot share the
panel's cached prefix (different system prompt, different task), and compacting
it would manufacture false "absent" verdicts — the audit exists precisely to
check for presence. Left alone deliberately.

---

<a id="graph-latency-under-load"></a>

_Moved here unchanged from `scripts/eval/LATENCY.md`._

## Graph latency under load — the first measurement of a whole run

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

### Read this before quoting any number below

**1. Every figure here is GRAPH-LEVEL latency.** It is the wall time of
`run_draft_analysis_workflow` from entry to return. Excluded, in full:

| excluded | why it matters |
|---|---|
| upload + Supabase Storage download | network, user-visible, unmeasured |
| **PDF parsing (Docling / GROBID)** | **not measured here, and not small: `CREATEX_PRESENTATION.md` (untracked local file, no longer in the repo) puts the user-visible path at ~3.5 min against the 65 s of graph time measured below, so the excluded remainder is larger than what is included** |
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

### The real-LLM calibration run

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

#### Per-node wall time, in-graph, real LLM (n=3 runs)

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

### Stub fidelity

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

### Time compression

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

### Open loop — Poisson arrivals at rate λ

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

#### The λ where throughput still rises and goodput collapses

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

### Closed loop — fixed concurrency

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

### The open-vs-closed p99 gap — coordinated omission, measured

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

### The reviewer fan-out — what it actually buys

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

#### Cross-checked against the real-LLM run

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

### Adjudicating "53s → 18s (~66%) via parallel reviewer fan-out"

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
the direction of the ~3.5 min in `CREATEX_PRESENTATION.md` (untracked local file, no longer in the repo). The 18 s figure is
closest in magnitude to a *single reviewer node* (17.05 s measured here), which
is likely where it came from.

**4. Was a "before" constructible?** Yes — but it is a counterfactual built
today, not a recovered historical baseline. There is no commit in this repo that
runs the reviewers sequentially, no recorded timing from one, and no artefact
anywhere claiming to be the 53 s baseline. `fanout.py` serializes today's code;
it does not reconstruct whatever was measured, if anything ever was.

#### What the owner may and may not now claim

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

### Caveats, in descending order of how much they could change a number

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

### Zero Supabase writes — how that was verified

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

#### One write path does NOT sit behind `stage_only`

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

### What is in the harness

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
