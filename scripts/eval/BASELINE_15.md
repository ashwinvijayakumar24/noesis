# Retrieval baseline — 15 topics, 344 documents, RRF measured

**This document supersedes `retrieval/BASELINE.md`. Do not quote that file's
numbers.** Two things are wrong with it, and neither is fixable by editing a
sentence:

1. **Its dense row is mislabelled.** "dense (pgvector HNSW, cosine)" was measured
   against an exhaustive sequential scan. On the 2124-chunk corpus, Postgres
   declined `idx_document_chunks_embedding` above a `LIMIT` of roughly 35, and
   the harness asks for `k × chunk_oversample` = 50 chunks. The recall numbers
   were valid *retrieval quality*; the index name on them was not earned. See
   `ANN_SWEEP.md` §0 for the original finding and §2 below for the fix.
2. **Its label snapshot no longer exists.** BASELINE.md ran under labels
   fingerprint `019bee4a06eb2d39` (118 indexed documents, 4 topics with a
   corpus, 59 scorable queries). `ANN_SWEEP.md` and `KEYWORD_QUERY.md` ran under
   `425df789a844f1f3`. **Everything in this document runs under
   `230c6ea9d9b7e8fd`** — 344 indexed documents, 15 topics, 338 scorable queries.
   The fingerprint has changed twice. A recall@10 from one snapshot and a
   recall@10 from another are not the same quantity, so **every arm here was
   re-measured rather than carried forward**, including the ones that already had
   a number.

The construction ceilings are also recomputed. BASELINE.md's
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

## 1. Scale — say n, and say what changed

| | BASELINE.md | **this document** |
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
BASELINE.md at all.

The 338 queries come from 15 manuscripts. That is still not a random sample of
anything, and a few points between two configurations is still noise. The
comparisons that survive that objection are flagged below; the ones that do not
are flagged too.

---

## 2. The crossover moved, and the eval's default depth is now genuinely HNSW

`ANN_SWEEP.md` predicted this and it is worth saying that it did: *"the crossover
at LIMIT ≈ 35 is a property of this row count. On 10× the corpus the sequential
scan gets 10× more expensive while the HNSW scan barely changes, so the crossover
moves far above any realistic k."*

Re-determined empirically at 5948 chunks by binary search over `EXPLAIN`, with
the RPC's own `hnsw.ef_search = 80`:

| corpus | chunks | crossover (last LIMIT planned as index scan) | growth |
|---|---|---|---|
| old (`ANN_SWEEP.md`) | 2124 | ~35 (bracketed 30 → 40) | — |
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

### The `EXPLAIN` evidence

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

**Consequence: BASELINE.md's mislabelling has fixed itself.** At the current
corpus size the harness's default depth of 50 is comfortably below the crossover,
so the "dense" arm below really is HNSW — and the record says so because it
asked, not because someone assumed.

### The durable fix: `plan` is recorded in every record

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

## 3. The numbers

Relevance unit: **document** (see `retrieval/RELEVANCE.md`). k = 10. Binary
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

### Construction ceilings, recomputed for this snapshot

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

### Failure attribution

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
  `KEYWORD_QUERY.md` diagnosed, reproduced at 5.7× the scale.
* **RRF has the best coverage of any arm at this depth** (5144 retrieval
  failures vs dense's 6010) and the *worst* ranking of the three below-crossover
  arms (1885 vs 936). It finds more and orders it worse. That is the entire
  result of §5, visible in one table.

---

## 4. Keyword v2 — the OR fix holds at 5.7× the scale

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
a wide margin. `KEYWORD_QUERY.md` measured 0.0026 → 0.2841 on the old snapshot;
both absolute numbers moved under the larger corpus and the direction did not.
**Quote the ratio, not either absolute.**

---

## 5. RRF — implemented, measured, and it does **not** beat dense

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

### The result

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

### Why it loses — the mechanism, not a guess

The keyword leg is roughly two-thirds as good as dense (recall@10 0.1447 vs
0.2195) and its errors are **not** independent of dense's in the way fusion
needs. `KEYWORD_QUERY.md` §5 identified the failure mode and it reproduces here
at scale: on claims made of generic academic filler, an OR of
`highlight | superior | generaliz | approach | train | instanc | scale` matches
most of the corpus and ranks by whatever is longest and most vocabulary-rich.
RRF then treats that noise as a **vote**, and one vote from a leg that is wrong is
enough to push a correct dense hit out of the top 10. §6's second hand-check
shows exactly this happening.

### k sensitivity

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

### Where RRF *would* be worth revisiting

Not as a replacement for dense at k=10, but as a **first-stage recall pool**. It
has the best coverage of any below-crossover arm (retrieval failures 5144 vs
6010) and the worst top-10 ordering. That is precisely the profile of a candidate
generator feeding a reranker. This document does not test that claim and does not
assert it.

---

## 6. Hand-checks — are the top hits actually relevant?

More rows is not better if they are noise, so every arm was eyeballed on the same
queries. Full output regenerable with `--inspect N`, or with the four-topic
comparison used below.

### 6a. A content-bearing claim — all three arms are genuinely working

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

### 6b. A contentless claim — every arm fails, and RRF makes it worse

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
contains no retrievable content. `KEYWORD_QUERY.md` flagged this same query on
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

## 7. Run integrity

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

## 8. Caveats, in full

1. **Nothing here is comparable to `retrieval/BASELINE.md`.** Different label
   fingerprint, 2.9× the indexed documents, 5.7× the queries, different ceilings.
2. **Nothing here is comparable to `KEYWORD_QUERY.md`'s or `ANN_SWEEP.md`'s
   absolutes either** (fingerprint `425df789a844f1f3`). The *directions* in those
   documents reproduce; the numbers do not transfer.
3. **The oversample arms are confounded with depth.** `dense_os2` returns at most
   20 chunks, which pool to fewer than 20 documents, so its recall@20 (0.1982) is
   depth-capped, not a ranking result. Only `dense_os5` vs `dense_os12` is a clean
   below-/above-crossover comparison, and even there the deeper arm has a
   mechanical advantage on recall@20 and MAP. **The plan flip is not the cause of
   `dense_os12`'s better numbers; the extra depth is.** Exact search and HNSW at
   `ef_search = 80` returned near-identical results in `ANN_SWEEP.md`
   (ANN@50 = 0.984) and there is no reason to expect otherwise here.
4. **No latency is reported.** This document measures quality only. `ANN_SWEEP.md`
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
