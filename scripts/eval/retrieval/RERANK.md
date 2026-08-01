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
| Δ | | **+0.0070 (+3.2%)** | — | +1.35 pts | +0.0132 (+2.5%) | +0.0102 (+1.4%) | +0.0028 (+1.2%) | **+481× the first stage** | |

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
- **MPS, not CPU.** On CPU the same model measured **4.4 pairs/s on synthetic
  text and ~2 pairs/s on real chunks**, i.e. roughly half. A CPU-only server
  would be slower than the table above, not faster.
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

Total spend for this task: **$0.0020**, all of it from a two-query smoke test of
the `gpt-5-mini` arm below. Budget was $2.

---

## The shipped `gpt-5-mini` reranker is structurally inert

Measured as a byproduct, and worth more than the arm it came from.

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
silently, with nothing logged and nothing counted. Observed no-op rate on a
smoke test: **2 of 2 calls (n=2)**.

This is on a live production path: `literature_search.py:149` calls
`retrieve_relevant_chunks_hybrid(..., use_reranking=True)` for the Tier-2 broad
fallback. So production pays for a reranker on every such call and receives the
unranked list. A full n = 338 arm is queued to put a real denominator under that
rate; the mechanism above does not depend on it.

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
