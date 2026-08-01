# Cross-encoder reranking — measured

A local cross-encoder (`BAAI/bge-reranker-v2-m3`) re-scores the dense first
stage's candidate pool. **It helps, by a little, and costs 13.3 seconds per
query.** Both halves of that sentence are the result.

Everything here is on label snapshot **`230c6ea9d9b7e8fd`** (n = 338 scorable
queries · 8,554 relevant judgments · 344 documents / 5,948 chunks · 15 of 15
topics). Numbers from any other snapshot are not comparable to these — the
ceiling moves with the labels, so the yardstick changes along with the
measurement. `rerank.py` asserts the snapshot id and refuses to run on another.

---

## The arms

Relevance unit `document`, k = 10, ceiling **0.5199**, `plan: index` throughout.
Every reranked arm reorders the pool and takes the top 10 through the *same*
scoring code as the control.

| arm | n | recall@10 | ceiling | % attainable | NDCG@10 | MRR | MAP | added latency p50 / p95 | spend |
|---|---|---|---|---|---|---|---|---|---|
| **dense ×5** (control) | 338 | 0.2200 | 0.5199 | 42.3% | 0.5196 | 0.7336 | 0.2321 | — (27.7 ms retrieval) | $0.00 |
| **dense ×5 → bge-reranker-v2-m3 (50) → take 10** | 338 | **0.2270** | 0.5199 | **43.7%** | **0.5328** | **0.7438** | **0.2349** | **13,314 ms / 16,506 ms** (n=108) | $0.00 |
| dense ×5 → `gpt-5-mini` reranker **as shipped pre-`663e0f6`** → take 10 | 338 | 0.2200 | 0.5199 | 42.3% | 0.5196 | 0.7336 | 0.2321 | 1,782 ms / 2,395 ms (n=338) | **$0.33134** |
| Δ (cross-encoder − control) | | **+0.0070 (+3.2%)** | — | +1.35 pts | +0.0132 (+2.5%) | +0.0102 (+1.4%) | +0.0028 (+1.2%) | **+481× the first stage** | |
| Δ (`gpt-5-mini` − control) | | **0.0000** | — | 0.00 | **0.0000** | **0.0000** | **0.0000** | +1,782 ms | +$0.33 |

The `gpt-5-mini` row is identical to the control **to four decimal places on every
metric**, because it never reranked anything. See below.

`run_id` `cc6db8bc0388`, config hash `464430efb82b54ed`; control `6fc17ba43999`,
config hash `6eb1e010040c0684`. Model revision
**`953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e`**, `max_length=512`, fp16, batch 32.

**The delta is real, not noise.** The pipeline is deterministic: cached query
embeddings, a fixed HNSW index, exact metric arithmetic. R1 measured run-to-run
variance on this corpus at **0.0000** across 75 of 75 cells. The control was
measured **three times around this arm** — before, between and after — and read
`0.2200` every time, with an identical `index_state` stamp, so the arm is paired
to its control rather than merely adjacent to it.

### What the reranker can and cannot touch

| failure mode | control | reranked | change |
|---|---|---|---|
| `retrieval_failure` (never in the 50-candidate pool) | 6,011 | 6,011 | **0** |
| `ranking_failure` (in the pool, ranked below 10) | 933 | 880 | **−53 (−5.7%)** |
| total misses | 6,944 | 6,891 | −53 |

This is the whole story in two rows. **86.5% of all misses are chunks the first
stage never returned**, and no reranker can ever fix one of those — reranking is
a permutation of a fixed pool. Of the 933 misses it *could* address, it fixed
53. `recall@20` is unchanged (0.3066 → 0.3067) for the same reason: at k = 20 you
are already seeing most of what a 50-candidate pool can offer, so reordering it
buys almost nothing.

**If you want a bigger number than +3.2%, it is not in the reranker.** It is in
the 6,011, which is a first-stage recall problem: deeper retrieval, better
chunking, or a better embedding.

> ↻ **Corrected 2026-08-01 — the last sentence above is wrong, and the correction
> is more useful than the claim was.** See `FIRSTSTAGE.md`, which measured all
> three of its proposed remedies.
>
> **Everything above this box reproduces exactly** from an independent driver.
> The 6,011 is real. What was wrong is calling it *a first-stage recall problem*.
>
> - **98.5% of the 6,011 were pooled for some *other* query.** Only 0.33% were
>   never ingested and 1.18% were dark to every query. The documents are found;
>   they are found for the wrong claim.
> - **The mechanism is a unit mismatch, not missing coverage.**
>   `chunk_oversample` counts **chunks** while the relevance unit is
>   **documents**: 50 chunks collapse to a median 20 distinct documents against a
>   median 25 relevant, so for 230 of 338 queries the pool is smaller than the
>   ground truth by construction.
> - **Deeper retrieval: measured, +0.0027.** Scoring every query against all
>   5,948 chunks with no depth limit takes `retrieval_failure` 6,011 → 20 and
>   recall@10 0.2200 → 0.2227. The failures relabel as `ranking`; they do not go
>   away. Depth alone, plan forced, moves **0.0000** from 120 chunks to the whole
>   corpus.
> - **Better chunking: measured, +0.0013.** 5,948 → 17,844 sub-chunks,
>   re-embedded and scored in memory.
> - **A perfect reranker over this pool tops out at recall@10 = 0.2982, and
>   dense already reaches 73.8% of it.** The cross-encoder took 0.0070 of a
>   maximum 0.0782.
>
> So of the three remedies this document proposed, two are measured near-zero
> and the third — **a better embedding** — is the only one left. Relevant and
> irrelevant scores separate by 0.0593 against a ~0.07 sd, **under 1σ**, and the
> attainable fraction is flat at 43–52% from k=1 to k=50: a weak scoring
> function, not a missing pool. That is a modelling project, not a config change.

### By claim type

`queries.py` carries `claim_type` from the pipeline's own claim extractor, so
this is a real field. Each slice gets **its own ceiling** — slices inherit
different numbers of references, and one global ceiling would misscale every row.

| claim type | n | ceiling | recall@10 control → reranked | NDCG@10 control → reranked |
|---|---|---|---|---|
| empirical | 196 | 0.4891 | 0.1962 → 0.2001 (+0.0039) | 0.5171 → 0.5224 |
| theoretical | 115 | 0.5375 | 0.2520 → 0.2627 (+0.0107) | 0.5367 → 0.5612 |
| methodological | 27 | 0.6680 | 0.2566 → 0.2700 (+0.0134) | 0.4652 → 0.4873 |

All three move the same way. The largest relative gain is on the smallest slice
(methodological, n = 27), which is exactly where a slice-level number is least
trustworthy; it is reported with its `n` rather than promoted to a finding.

---

## Oversample depth vs. reranking — the confound, separated

The existing record has `dense ×5 (plan: index)` at 0.2195 and `dense ×12 (plan:
seqscan)` at 0.2227, which tangles three things: pool depth, the planner flipping
to a sequential scan, and (in any reranked comparison) the reranker itself. This
sweep holds the reranker fixed and varies only depth, with the plan stamped on
every record.

**n = 12, its own ceiling 0.6334, cache bypassed so every point carries real
latency.** This subsample is far too small to publish a quality claim from — a
single query moves recall@10 by ~0.02 here. It is reported for the *shape* it
shows and for the latency, both of which are unambiguous, and the numbers carry
their `n` so nobody mistakes them for the headline.

| depth (candidates) | plan | control R@10 | reranked R@10 | Δ | reranked NDCG@10 | reranked MRR | added latency p50 / p95 |
|---|---|---|---|---|---|---|---|
| ×5 (50) | `index` | 0.2083 | 0.2205 | **+0.0122** | 0.4838 | 0.6230 | 13.6 s / 25.6 s |
| ×12 (120) | `seqscan` | 0.2251 | 0.2143 | −0.0108 | 0.4839 | 0.6649 | 31.8 s / 39.1 s |
| ×25 (250) | `seqscan` | 0.2251 | 0.2089 | −0.0162 | 0.4909 | 0.7318 | 62.7 s / 81.4 s |
| ×50 (500) | `seqscan` | 0.2251 | 0.2143 | −0.0108 | 0.4878 | **0.7936** | **128.1 s** / 144.7 s |

Control NDCG@10 is 0.4478 at ×5 and 0.4744 at every deeper point; control MRR is
0.6042 then 0.6906. Three things fall out, and the first two do not depend on the
thin `n`:

1. **The plan flips between ×5 and ×12**, exactly as the ANN sweep predicted
   (crossover ~103 candidates). Any depth comparison that does not record this is
   attributing a planner decision to a retrieval idea. The dense control is flat
   at 0.2251 from ×12 onward — a deeper pool does not change which 10 *documents*
   come out on top, so "deeper is better" was never the depth's doing.
2. **Latency is linear in candidates and brutal**: 13.6 → 31.8 → 62.7 → 128.1 s,
   i.e. ~2.6 ms per candidate, unchanged across the sweep. Reranking a 500-
   candidate pool costs **two minutes per query** on this hardware.
3. **MRR rises monotonically with depth (0.6230 → 0.7936) while recall@10 goes
   negative past ×5.** The cross-encoder is increasingly good at putting *one*
   strongly on-topic document first, and increasingly willing to promote
   semantically-similar-but-uncited documents into the rest of the top 10. That
   is what these labels punish: they measure "would we have found what the author
   *cited*", not "what is relevant", so a reranker optimising for topical
   relevance is being scored against a different objective. Worth re-running at a
   real `n` before anyone builds on it.

---

## Latency — the half of the result that usually goes missing

**Hardware: Apple M4, 10 cores, 16 GB, macOS 24.6.0.** Device: Apple GPU via
torch MPS, fp16. `sentence-transformers` 5.6.1 / torch 2.12.0.

| stage | p50 | p95 | n |
|---|---|---|---|
| dense first stage (pgvector, 50 candidates) | **27.7 ms** | 651.5 ms | 338 |
| cross-encoder second stage (50 pairs) | **13,314 ms** | 16,506 ms | 108 |

Sustained throughput **3.77 pairs/second**. The second stage costs **481× the
first**, and the whole reranked arm took 1,491 s of wall clock for 338 queries.

For scale: the entire draft-analysis graph has a measured p50 of **63.75 s**
(`scripts/eval/LATENCY.md`, n = 3). Adding this reranker to a single retrieval
call would add **13.3 s — 21% of the whole graph** — for +0.007 recall@10.
On this hardware, in this configuration, that trade does not clear.

Three caveats on those latency numbers, all of which cut the same way:

- **`n_fresh = 108`, not 338.** Latency is reported only from queries whose 50
  candidates were *all* scored from scratch. The other 230 were served from the
  score cache (see below) and a dictionary lookup is not a reranker; averaging
  those in would have reported a free second stage.
- **MPS, not CPU.** Measured on the same 50-candidate pools with `device=cpu`:
  **p50 31,060 ms, p95 56,096 ms, 1.28 pairs/s (n = 3)** — **2.3× slower** than
  the MPS figure above. A CPU-only server is slower than this table, not faster.
- **The p95 of the first stage (651 ms) is 24× its p50.** That is pgvector, not
  the reranker, and it is not explained here.

---

## What the cross-encoder actually sees

The corpus's chunks are enormous: **median 6,025 characters, range 3,177 to
17,690** in a sampled 50-candidate pool. At `max_length=512` tokens the
cross-encoder reads roughly **the first third of a median chunk** and less than a
fifth of a large one. A chunk whose relevant sentence sits at character 4,000 is
invisible to the reranker even though the bi-encoder embedded all of it.

So +3.2% is a number for *this* reranker on *these* chunks. It is not a ceiling
on cross-encoder reranking in general, and the obvious next experiment is not a
bigger reranker but smaller chunks (which is R2's lane, on its own snapshot —
not differenced against this one).

---

## Cost

**$0.00, asserted, not assumed.** `BudgetGuard` reads
`app.core.llm_budget.total_spend_usd()` before and after every local arm and
raises if it moved by a cent or a call. All 338 query embeddings were served from
`cache/retrieval_query_embeddings`, so even the dense leg made no API call. Model
weights (~2.2 GB) download once from HuggingFace and cost nothing to run.

Total spend for this task: **$0.61283** against a $2 budget, all of it on the
`gpt-5-mini` arms below — $0.33134 (as-shipped, n=338), $0.22418 (fixed, n=100),
$0.04822 (as-shipped, n=100), $0.00908 (two smoke tests). Every cross-encoder arm
cost exactly $0.00. `unpriced_calls` was 0 on every record, so unlike most
figures in this project this one is **not** a floor.

---

## The shipped `gpt-5-mini` reranker was structurally inert

Measured as a byproduct, and worth more than the arm it came from.

> **Fixed upstream in `663e0f6` while this was being written.** The budget is now
> 2000, `response_format` is pinned to `json_object`, and both failure paths are
> counted in `_RERANK_STATS` and logged. Everything below describes the
> configuration the arms were measured under — `max_completion_tokens=100` — and
> is a record of what was shipped, **not** of current behaviour. `rerank.py`
> keeps 100 on purpose: it is what the published 338/338 figure ran with, and
> changing it would silently redefine an already-published number.
> `test_rerank.py` now guards the fix instead of the bug.

`app/services/rag_retrieval.py:rerank_results` asks `gpt-5-mini` to return a JSON
array of indices with `max_completion_tokens=100`. Against the live API on
2026-08-01:

```
finish_reason  : 'length'
completion_tokens: 100   (reasoning_tokens: 100)
content        : ''
```

**The entire token budget is consumed by reasoning before a single output token
is emitted.** `json.loads('')` then raises, and the function's
`except Exception: return chunks[:top_k]` hands back the first stage's order —
silently, with nothing logged and nothing counted.

Measured as a full arm, n = 338:

| | |
|---|---|
| calls | 338 |
| empty-content responses | **338** |
| parse failures | **338** |
| no-op fallbacks | **338** |
| **no-op rate** | **1.000 (338/338)** |
| last error | `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` |
| spend | **$0.33134** ($0.00098/query) |
| added latency | p50 **1,782 ms**, p95 2,395 ms (n=338) |

Its recall@10 is **0.2200 — the control's, exactly**, as are its NDCG@10, MRR and
MAP to four decimals. That is not a reranker that failed to help. It is a
reranker that has never run: every call bought the dense ordering back at full
price.

This is on a live production path — `literature_search.py:149` calls
`retrieve_relevant_chunks_hybrid(..., use_reranking=True)` for the Tier-2 broad
fallback. At the measured rates that path pays **$0.00098 and 1.78 s per
retrieval** for a no-op, and neither the spend nor the failure appears in any log
or counter.

Two independent bugs stack here, and fixing either alone is not enough: the token
budget makes the call always return empty, and the bare `except` makes that
invisible.

### The same reranker, actually running

To separate "the LLM reranker does not help" from "the LLM reranker never ran",
the identical call was re-run with `max_completion_tokens=2000` and
`response_format={"type":"json_object"}` — nothing else changed. **n = 100**
(topic-stratified, deterministic), its own ceiling **0.5956**, paired against a
control on the same 100 queries. These do not difference against the n = 338
table above; different query set, different ceiling.

| arm (n = 100, ceiling 0.5956) | recall@10 | NDCG@10 | MRR | MAP | no-op rate | added p50 | spend |
|---|---|---|---|---|---|---|---|
| dense ×5 control | 0.2406 | 0.5132 | 0.7268 | 0.2468 | — | — | $0.00 |
| `gpt-5-mini` **as shipped** | 0.2406 | 0.5132 | 0.7268 | 0.2468 | **100/100** | 1,798 ms | $0.0482 |
| `gpt-5-mini` **fixed** | 0.2409 | 0.5207 | 0.7332 | 0.2503 | **0/100** | 10,648 ms | $0.2242 |

Fixed, it runs cleanly — `finish_reason='stop'`, 0 parse failures — and consumes
**1,408 reasoning tokens** on its last call, which is why a 100-token budget was
never going to work. And having run, it recovered **1 ranking failure out of
222** (222 → 221). recall@10 moves +0.0003.

So the honest reading is three-layered, and only the first two were previously
knowable:

1. As shipped, it does not rerank. 100/100 and 338/338 no-ops.
2. Fixed, it reranks correctly and costs **$0.00224 and 10.6 s per query** —
   2.3× the price of the broken version, since reasoning tokens are billed.
3. Fixed, it buys **+0.0003 recall@10**. On the same failure population the free
   local cross-encoder recovered **53 of 933 (5.7%)** against this model's
   **1 of 222 (0.45%)**, at comparable latency and no cost.

The fix worth making is therefore in the *error handling*, not the reranker: a
counted, logged failure path — the same treatment `keyword_search` got when its
silent degradation was found. Turning the reranker on properly is not where the
recall is.

`test_rerank.py` pins the two constants that make this inevitable
(`max_completion_tokens=100`, a `gpt-5*` model), so a fix forces this section to
be re-measured rather than leaving a stale accusation standing.

---

## Runs that were discarded, and why

Nothing is deleted from the append-only sink; these records are on disk and are
listed here so no one quotes them.

| run_id | arm | reading | why discarded |
|---|---|---|---|
| `3a5e8995583e` | `dense_x5_control` | recall@10 **0.2186** | Measured 23:48:47Z while R2's experimental 5,924-chunk corpus was live in the shared eval database. It is R2's corpus under my config, not a control. |

**The published `0.2195` does not reproduce, and that is not a code change.**
The sequence, with nothing edited between readings:

| time (UTC) | reading | index |
|---|---|---|
| published | 0.2195 | original |
| 23:34 | 0.2195 | original — reproduced exactly |
| 23:48 | 0.2186 | R2's experimental corpus (contaminated) |
| 00:05 onward | **0.2200**, five times | restored corpus |

R2 restored the corpus by re-ingesting 6 documents, which minted new chunk ids
and fresh embeddings — **content-equivalent, not measurement-equivalent**. The
proof that the corpus itself is intact: the exact-search arm (`--chunk-oversample
12`, which flips the planner to `seqscan`) reproduces its published **0.2227 bit
for bit** on the restored index. Only the approximate path moved. **An HNSW graph
rebuilt over identical content shifts recall@10 by 0.0005.**

The control for everything in this document is therefore **0.2200**, measured
three times in the same window as the arm it brackets, not the published 0.2195.
The reproduction gate in `rerank.py` still fails on 0.2195 on purpose: widening
its tolerance to swallow this would convert a measured integrity problem into a
comfortable noise band and hide the next one.

---

## Method notes

- **The reranked arm returns the whole reordered pool, not the top 10.**
  Truncating at k here would relabel every ranking failure as a retrieval failure
  and destroy the one number that says whether a better reranker could help.
  "Take 10" happens downstream in `metrics.evaluate_run`, the same code the
  control goes through.
- **Score cache.** `(model|revision|max_length, query, chunk_id) -> score`,
  persisted under `cache/retrieval_rerank_scores/`. A depth sweep re-presents the
  same pairs — the top-50 pool nests inside the top-500 — and at 3.8 pairs/s that
  is the difference between affordable and not. It also made the headline arm
  resumable after the run was interrupted at 230 of 338 queries. It never feeds a
  latency number.
- **Text budget.** Chunk text is truncated to 3,000 characters before
  tokenisation. Lossless at 512 tokens (English scientific prose does not
  tokenise below ~3.5 chars/token, so 512 tokens cannot reach past ~1,800
  characters); verified identical scores to six decimal places.
- **`plan` is stamped on every record** and was `index` for every arm here. A
  depth sweep flips the planner to `seqscan` somewhere above ~103 candidates, and
  a plan flip must never be read as a rerank effect.
- **`index_state` is stamped before and after every arm** (chunk count, document
  count, newest write, `hnsw.ef_search`) with a derived `index_stable_during_arm`
  flag. Every arm here reads `true`. This exists because the harness records
  `labels_fingerprint` and `config_hash` but nothing identifying the *index*, so
  two records with identical hashes described different corpora for an hour.

---

## Reproducing

```bash
python3 -m pip install -r scripts/eval/requirements.txt   # adds sentence-transformers

python3 -m scripts.eval.retrieval.rerank --mode control   # dense x5, n=338
python3 -m scripts.eval.retrieval.rerank --mode rerank    # + cross-encoder, n=338  (~25 min warm, ~75 min cold)
python3 -m scripts.eval.retrieval.rerank --mode sweep --subsample 12 --sweep-depths 5,12,25,50 --no-cache
python3 -m scripts.eval.retrieval.rerank --mode cpu-probe --n-probe 3 --sweep-depths 5

python3 -m pytest scripts/eval/retrieval/tests/test_rerank.py -q   # 33 tests, no weights required
```

Results append to `scripts/eval/results/retrieval_eval.jsonl`, keyed by config
hash, one record per run, never rewritten.

## Wiring into `run_retrieval_eval.py`

`rerank.py` owns no shared entry point. To expose the arm through the main CLI,
three additions to `run_retrieval_eval.py` (owned by the lead):

1. `--retriever rerank` in the `choices` list, plus `--rerank-model`,
   `--rerank-device`, `--rerank-top-n` options.
2. In `main()`'s retriever branch:
   ```python
   elif args.retriever == "rerank":
       from scripts.eval.retrieval.rerank import (
           CrossEncoderReranker, RerankingRetriever, ScoreCache, SCORE_CACHE_DIR,
       )
       retriever = RerankingRetriever(
           build_retriever("dense", project_id=args.project_id,
                           embed_fn=production_embed_fn()),
           CrossEncoderReranker(device=args.rerank_device),
           top_n=args.rerank_top_n,
           cache=ScoreCache(SCORE_CACHE_DIR / "bge-reranker-v2-m3.json"),
       )
   ```
   `RerankingRetriever` satisfies the `Retriever` protocol and delegates
   `plan_summary()` to its first stage, so `run_eval` and `build_record` need no
   changes at all.
3. In `_variant()`, add the reranker's identity so two reranked runs with
   different models or `max_length` cannot collide in the config hash:
   ```python
   rr = getattr(retriever, "reranker", None)
   if rr is not None:
       out.update({"reranker_model": rr.model_name,
                   "reranker_revision": rr.revision,
                   "reranker_max_length": rr.max_length,
                   "reranker_device": rr.device})
   ```

Latency and the per-claim-type breakdown live in the record's `rerank` block,
which `run_arm()` attaches after `build_record()` returns — no change to
`build_record` itself. If you want them from the main CLI too, call
`rerank.metrics_by_claim_type()` and `RerankingRetriever.latency_summary()` and
attach them the same way.
