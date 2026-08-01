# The half of the embedding we throw away — measured

`app/services/rag_ingest.py:316` asks OpenAI for `dimensions=1536` and explains
itself in a comment: *"Fixed at 1536 for pgvector index compatibility."*
`text-embedding-3-large` is natively **3072**. Every vector this system has ever
stored is a Matryoshka truncation that discards half of what the model produced.

The comment is **half true**. Verified on the local database, pgvector 0.8.6:

| DDL | result |
|---|---|
| `HNSW on vector(3072)` | **FAILS** — `column cannot have more than 2000 dimensions` |
| `HNSW on halfvec(3072)` | OK |
| `HNSW on halfvec(4000)` | OK |

True for `vector`, false for `halfvec`. So the constraint that justified throwing
away 1,536 dimensions has not been binding since pgvector 0.7.0 shipped
`halfvec`, and the question of whether those dimensions carry retrievable signal
was answerable for about two dollars.

**They do not.** That is the finding, and this document is why it is trustworthy.

---

## The result

Both arms, same session, same 5,948 chunk ids, same 338 queries, same labels
(`230c6ea9d9b7e8fd`), same `k = 10`, same `chunk_oversample = 5`, same
`hnsw.ef_search = 80`, same cosine distance, same max-pool to document. **Only
the embedding width and the vector column type change.**

### As shipped — HNSW, ef_search 80, 50-chunk pool, n = 338

| metric | ceiling | control `vector(1536)` | arm `halfvec(3072)` | Δ |
|---|---|---|---|---|
| recall@1 | 0.0694 | 0.0341 | 0.0344 | **+0.0003** |
| recall@5 | 0.2939 | 0.1366 | 0.1383 | **+0.0017** |
| **recall@10** | **0.5199** | **0.2199** | **0.2229** | **+0.0030** |
| recall@20 | 0.7599 | 0.3067 | 0.3020 | **−0.0047** |
| MRR | — | 0.7335 | 0.7372 | +0.0037 |
| NDCG@10 | — | 0.5196 | 0.5307 | +0.0111 |
| MAP | — | 0.2320 | 0.2337 | +0.0017 |
| pool oracle@10 | — | 0.2982 | 0.2969 | −0.0013 |
| mean pool documents | — | 19.77 | 19.41 | −0.36 |
| plan (observed) | — | `index` | `index` | — |

### Exact — whole corpus, no HNSW graph in the comparison, n = 338

Two HNSW graphs built over different vectors are not the same graph. §2.1 of
`FIRSTSTAGE.md` measured the size of that confound directly: the shipped ef-80
index reads 0.2199 where the identical 50-chunk pool scored *exactly* reads
0.2210, so **0.001–0.003 of any difference between two indexes is graph luck**
— which is the same size as the effect being measured. So both arms were also
scored exactly, in memory, against all 344 documents.

| metric | ceiling | control `1536` | arm `3072` | Δ |
|---|---|---|---|---|
| recall@1 | 0.0694 | 0.0351 | 0.0345 | **−0.0006** |
| recall@5 | 0.2939 | 0.1369 | 0.1398 | **+0.0029** |
| **recall@10** | **0.5199** | **0.2227** | **0.2247** | **+0.0020** |
| recall@20 | 0.7599 | 0.3420 | 0.3404 | **−0.0016** |
| MRR | — | 0.7438 | 0.7399 | −0.0039 |
| NDCG@10 | — | 0.5221 | 0.5313 | +0.0092 |
| MAP | — | 0.3862 | 0.3913 | +0.0051 |

(MAP and recall@20 read much higher here than in the ANN table because the exact
run ranks all 344 documents rather than the ~20 a 50-chunk pool surfaces. The
two tables are internally comparable and must not be compared *across*.)

**The signs do not agree.** recall@10 up, recall@1 and recall@20 down, NDCG up,
MRR down. Doubling the embedding width moved recall@10 by **+0.0020 against
0.2972 of headroom — 0.7% of the gap**, and moved three of the seven metrics the
wrong way. That is not a small win. It is noise with a direction chosen by
whichever metric you read first.

For scale, the same benchmark's other measured levers: pool depth **0.0000**,
chunk granularity at 3× **+0.0013**, a cross-encoder reranker **+0.0070**.
Full-width embedding lands **between chunk granularity and depth** — the two
levers already declared dead.

---

## The mechanism, which is the number that actually settles it

Recall can move for reasons that have nothing to do with the encoder — a
different pool composition, a different graph, a tie broken differently. The
encoder's *discriminative power* cannot. It is the mean max-pooled cosine
between a query and its cited documents versus everything else, and if a wider
embedding is genuinely seeing more, this is where it has to show.

**A separation figure is meaningless without its population**, so both are given.
`FIRSTSTAGE.md` published the pooled one.

| arm | population | relevant (n) | irrelevant (n) | gap | pooled sd | gap in σ |
|---|---|---|---|---|---|---|
| control 1536 | pool, depth 1000 | **0.4415** (7,346) | **0.3821** (55,562) | **0.0594** | 0.0683 | **0.87** |
| **arm 3072** | pool, depth 1000 | 0.4159 (7,350) | 0.3558 (55,315) | **0.0601** | 0.0683 | **0.88** |
| control 1536 | whole corpus | 0.4253 (8,534) | 0.3367 (107,738) | 0.0886 | 0.0804 | 1.10 |
| **arm 3072** | whole corpus | 0.4003 (8,534) | 0.3122 (107,738) | 0.0881 | 0.0789 | 1.12 |

> **The control reproduces `FIRSTSTAGE.md`'s published 0.4415 / 0.3821 / 0.0593
> to four decimals and to the exact population sizes — 7,346 and 55,562 —
> through different code, in a different module, on a different day.** That is
> what makes the arm's number believable rather than merely self-consistent, and
> it is pinned by `test_control_separation_reproduces_the_published_0593`.

**Separation moves by +0.0007 on the published population and −0.0005 on the
whole corpus.** In σ: 0.87 → 0.88. The wider vector shifts both means down by a
similar amount — everything is slightly less similar to everything in 3072-space
— and the *gap between them does not change*.

This is decisive in a way the recall table is not. Recall@10 moved +0.0020 while
the quantity any real embedding improvement must move stayed flat. Per the rule
this arm was commissioned under: **when recall moves without separation moving,
distrust the recall.**

---

## Index size and latency — the old N9 question, answered for free

`halfvec` is fp16, so it halves per-component storage. At double the width that
should be roughly a wash; it is better than a wash.

| | control `vector(1536)` | arm `halfvec(3072)` | ratio |
|---|---|---|---|
| HNSW index | 52,256,768 B (**49.84 MB**) | 48,734,208 B (**46.48 MB**) | **0.93×** |
| table incl. TOAST | 200,974,336 B (**191.7 MB**) | 98,959,360 B (**94.38 MB**) | **0.49×** |
| p50 query latency | **~2.8 ms** | **~3.9 ms** | ~1.4× |
| p90 query latency | ~6.3 ms | ~7.9 ms | ~1.25× |
| plan observed | `index` | `index` | — |

**Twice the dimensions, 7% less index and half the heap.** The heap halving is
fp16 doing exactly what it says. The index shrinking despite double the width is
the same effect beating the dimension count, because HNSW stores the vectors in
its own pages.

Latency is the one place the wider vector costs something real: **p50 rises from
~2.8 ms to ~3.9 ms**, roughly 1.4×, consistent across five passes (control
2.38–3.29 ms, arm 3.44–4.59 ms). Reported as a range rather than a point, because
that is what five passes support.

**The plan is `index` on both arms.** A plan flip is not an embedding result, and
this is the only way to say so.

The narrower reading of the same rows: **`halfvec` is a free storage win
independent of width.** Storing the *existing* 1536-dim vectors as
`halfvec(1536)` was never tested here, but the fp16 heap halving above is
attributable to the type, not the width, and it is the cheapest thing on this
page.

---

## What was not touched

`document_chunks` is shared with another agent running full-pipeline arms
against this same database, concurrently. This project has already lost a
published result to exactly that situation — two agents, one mutable corpus,
identical config hashes describing different data
(`docs/ENGINEERING_LOG.md`, "The concurrency incident").

- **Nothing was written to `document_chunks`.** No re-ingest, no `REINDEX`, no
  index drop. Its vectors are read, once, for the control's exact pass.
- The 3072 arm lives in `public.document_chunks_3072`, created by
  `scripts/eval/schema/100_local_embedding_arm_3072.sql`. **Local only.**
- **`index_digest` on `document_chunks` was `8d3edbe3f3b28cdb` before the run
  and `8d3edbe3f3b28cdb` after it**, sampled at both ends of every pass. One
  sample cannot detect a mid-run swap; two can.
- `rag_ingest.py` is unchanged. If the arm had won, changing production would
  have been a separate decision with its own review.
- The 1536 query-embedding cache is untouched; the 3072 vectors live in
  `scripts/eval/cache/retrieval_3072/`.

## Corpus identity

**The 3072 arm is a new corpus identity.** New vectors, new index, new
`config_hash` — `f20b55d4c555fd6c` for the control and `4b4dfe37bbfbb592` for
the arm, and the run asserts they differ before recording anything. The hash
includes `embed_dimensions` and `vector_column_type` precisely because without
them the two arms are identical in every other recorded field and the sink would
read the second as run-to-run variance on the first. Run-to-run variance on a
fixed corpus is **0.0000**, so that misreading would have looked like a real
effect appearing from nowhere.

**Every delta on this page is against the control measured in the same session.**
None of them is against the historical 0.2195 / 0.2200 lineage, which describes
corpora that no longer exist.

## Reproducibility

Both arms were scored twice, and both records are in the sink. Every measured
cell is bit-identical across the two passes — all seven metrics on both the ANN
and exact tables, both separation populations, all three delta blocks, both
config hashes, both index sizes, both plans.

Two things vary and neither is a measurement. Latency, reported as a range for
that reason. And `pg_total_relation_size('document_chunks')` grew by 80 KB
between passes while its **chunk-id digest stayed `8d3edbe3f3b28cdb`** — no rows
changed; that is a read-heavy pass dirtying pages and updating the visibility
and free-space maps. It is recorded here rather than smoothed away, because on
this branch an unexplained change to the shared table is the one thing that must
never be waved through.

Two independent instrument checks, both pinned as tests:

1. the control's exact whole-corpus recall@10 reads **0.2227**, reproducing
   `FIRSTSTAGE.md` §2.1's sequential-scan figure from in-memory numpy;
2. the control's separation reads **0.4415 / 0.3821 / 0.0594 over n = 7,346 and
   55,562**, reproducing §2.5 exactly.

The ANN control reads **0.2199** against the published **0.2200**. That 0.0001 is
the HNSW approximation, is documented in `test_firststage.py` as the reason its
own tolerance is ±0.0002, and is a fifth of the smallest delta reported here.

## Cost

| | |
|---|---|
| chunks embedded at 3072 | 5,948 |
| queries embedded at 3072 | 338 |
| tokens, `cl100k_base` | 10,464,364 + 9,585 |
| **actual spend** | **$1.3616** |
| ledger figure (`record_usage`) | $1.1581 |
| budget | $3.00 |
| completions | none — this arm needs no LLM calls at all |

**The ledger under-records by 17.6% on this corpus.** `record_usage` is called
with `len(text) // 4`, the standard chars-per-token rule of thumb, and dense
scientific prose tokenizes at ~3.4 chars/token. Every embedding-cost figure this
repo has recorded is therefore a **floor**, not a total. That is a finding about
the budget guard, not about this arm, and it belongs to whoever owns
`app/core/llm_budget.py`.

Re-running is free: chunk vectors are cached in
`scripts/eval/cache/retrieval_3072/chunks.npz` (float32, keyed by chunk id) and
queries in `queries.json`.

---

## The verdict

> **The 1,536 dimensions Matryoshka discards carry no retrievable signal on this
> corpus.** Storing `text-embedding-3-large` at its native 3072 as
> `halfvec(3072)` under an HNSW cosine index moves recall@10 by **+0.0020**
> exact / **+0.0030** ANN (n = 338, ceiling 0.5199, 0.7% of the 0.2972 gap),
> moves three of seven metrics the wrong way, and leaves the relevant/irrelevant
> separation **unchanged at 0.87σ → 0.88σ**. The truncation was never costing
> anything measurable.

This closes the cheapest arm in the embedding lane. It does **not** close the
lane: the separation is still under 1σ and that is still where the headroom is
if there is any. What it establishes is that the headroom is not sitting inside
the model we already use, waiting to be un-truncated. A different encoder
(`Arm 3`) or an objective trained on these judgments (`Arm 4`) has to do real
work; there is no free version.

**Do not change `rag_ingest.py`.** Not because 3072 is worse — it is a wash on
recall and cheaper on disk — but because a wash is not a reason to re-embed a
production corpus, re-write a migration, and take a 1.4× latency regression on
every query. If `halfvec` is adopted, adopt it at **1536** for the heap halving,
which is the only unambiguous win on this page and costs no re-embedding at all.

---

## Not claimable

- Any number here without its `n` and its **recomputed** ceiling.
- Any of these figures beside `0.2195` or `0.2186`. Different corpora.
- "3072 is worse." recall@10 rose. Three other metrics fell. **Neither
  direction is supported** — that is what a null looks like, and reporting it as
  a small win would be the same error in the opposite direction.
- "`halfvec` costs 1.4× latency." It costs that **at double the width**. The
  type and the width are confounded in this arm and separating them needs a
  `halfvec(1536)` arm that was not run.
- That any of this is a production retrieval number. Local pgvector, PyMuPDF
  extraction, basic chunking — not production's Docling → GROBID chain.
- "Matryoshka truncation is harmless in general." Measured on **one** corpus of
  344 documents under labels that mean *"would we have found what the author
  cited"*. A corpus with finer-grained distinctions could plausibly need the
  width.

---

## Reproducing

```bash
# what it would cost, before spending anything
python3 -m scripts.eval.retrieval.embed_arms --mode cost

# embed 5,948 chunks + 338 queries at 3072. COSTS ~$1.36. Cached after the
# first run; writes nothing to document_chunks.
NOESIS_LLM_MAX_SPEND_USD=3.00 \
  python3 -m scripts.eval.retrieval.embed_arms --mode embed --allow-spend

# create document_chunks_3072, fill it, build the HNSW index  (~20 s)
python3 -m scripts.eval.retrieval.embed_arms --mode load

# both arms, both separation populations, exact + ANN, $0.00  (~90 s)
python3 -m scripts.eval.retrieval.embed_arms --mode run

python3 -m pytest scripts/eval/retrieval/tests/test_embed_arms.py -q   # 20 tests
```

Records append to `scripts/eval/results/embedding_arms.jsonl`, keyed by
`config_hash`, never rewritten.
