# The 50-chunk cost ceiling overshoots its own limit

`MAX_CHUNKS_PER_DOCUMENT = 50` (`services/backend/app/services/rag_chunking.py`)
is a **cost** ceiling, not a retrieval strategy — the module says so itself. This
document does not argue with that tradeoff. It reports a narrower fact: **the
ceiling does not hold.** When it fires, the geometry it picks produces *more*
than 50 chunks, on every document it has ever fired on.

Everything below carries its `n`. The two retrieval arms are measured **within
one label snapshot**, and nothing here is differenced against any other snapshot.

---

## 1. Characterization

**Corpus:** every PDF under `scripts/eval/corpora/**`, deduplicated by content
hash exactly as `scripts/eval/ingest.py::plan_corpus` does it.
**n = 344 unique documents** (345 found, 1 unreadable:
`friedman_2017_community_structure…pdf`, `FileDataError` — it has never been
ingestible and is unrelated to this work).

Inputs are the **raw document token counts** (PyMuPDF text → `cl100k_base`),
which is what `get_chunking_strategy` is actually called with.

> **Trap, and it cost a first pass of this analysis.** The `token_count` field in
> `scripts/eval/cache/ingest_manifest.jsonl` is *not* this number. It is the sum
> of tokens over the emitted chunks, so it counts every overlap region twice —
> for Bommasani 2021 it reads 243,358 against a true 207,394, **17% high**.
> Characterizing off the manifest inflates the population of documents that trip
> the ceiling from 6 to 16. The numbers below are recomputed from the PDFs.

### How often the ceiling fires

| | n | share |
|---|---|---|
| documents in corpus | 344 | — |
| ceiling fires (`was_adjusted`) | **6** | **1.7%** |
| documents reaching ≥ 50 chunks at all | 8 | 2.3% |

The ceiling is a rare event. It bites only the six longest documents in the
corpus — and those are exactly the documents where chunk granularity matters
most, which is the tradeoff the module docstring already concedes.

### How badly it overshoots

**Legacy geometry (shipped, and still the default): 6 of 6 firings exceed the
limit. n = 6.**

| overshoot | documents |
|---|---|
| +2 chunks (52) | 1 |
| +3 chunks (53) | 1 |
| +4 chunks (54) | 1 |
| +5 chunks (55) | 3 |

Max **+5, i.e. 55 against a limit of 50 — 10% over.** Median +5.
There is no firing that lands *at* 50, and none that lands under it.

Per document (`n = 6`, all of them):

| document | pages | tokens | legacy size/overlap → est. | exact size/overlap → est. |
|---|---|---|---|---|
| `bommasani_2021_on_the_opportunities_and_risks…` | 214 | 207,394 | 4441 / 666 → **55** | 4863 / 729 → **50** |
| `w_2018_relational_inductive_biases…` | 40 | 176,514 | 3824 / 573 → **55** | 4139 / 620 → **50** |
| `liang_2022_holistic_evaluation_of_language_models` | 162 | 175,382 | 3801 / 570 → **55** | 4113 / 616 → **50** |
| `ref_2021_proceedings_of_the_2021_conference…` | 166 | 154,001 | 3374 / 506 → **54** | 3611 / 541 → **50** |
| `guha_2023_legalbench…` | 143 | 127,831 | 2850 / 427 → **53** | 2998 / 449 → **50** |
| `klambauer_2017_self_normalizing_neural_networks` | 102 | 111,617 | 2526 / 378 → **52** | 2618 / 392 → **50** |

### Under-utilisation: **did not reproduce**

The prompt for this work suspected the ceiling might also land *well under* 50 on
some documents, wasting retrievable material. **It does not.** Across `n = 6`
firings the legacy arm's estimates are 52, 53, 54, 55, 55, 55 — the minimum is
52, above the limit, not below it. The error is one-sided.

Reported as a null result rather than dressed up: the overshoot is real, the
undershoot is not, and no undershoot was manufactured to fill the section.

### Reproduction

`services/backend/tests/test_rag_chunking_ceiling.py` reproduces the overshoot on
Bommasani 2021 (214 pages, 207,394 tokens), the worst real document in the
corpus. Before the fix the exact-arm tests failed **11 of 20**; after, **20 of
20** pass. The legacy overshoot itself is asserted, not merely tolerated, so the
comparison arm cannot drift.

Beyond the single fixture, a sweep over all three tiers × 76 token counts ×
`max_chunks ∈ {1, 2, 10, 50, 200}` asserts the exact arm never exceeds its limit,
and records that the legacy arm violates the same property on **> 50%** of the
sweep.

---

## 2. The fix

Two independent defects, both pushing the count up:

1. **Floor division.** `(total + (m-1)*o) // m` rounds the chunk size *down*,
   below the size the constraint requires. One token short is one whole extra
   chunk.
2. **The overlap it solves against is not the overlap it uses.** The function
   preserves the overlap *ratio*, so a larger chunk size means a larger overlap —
   but the size is solved using the *original* overlap. More overlap means less
   new material per chunk, means more chunks. This defect dominates and grows
   with document length.

`calculate_estimated_chunks` fits within `m` iff

```
total_tokens <= m * c - (m - 1) * o
```

The exact arm substitutes the overlap it will really use, `o = c * ratio`, and
solves for `c`:

```
c >= total_tokens / (m - (m - 1) * ratio)
```

with ceiling division. The denominator exceeds 1 for any `ratio < 1`, which every
tier and every adjusted pair satisfies, so it cannot degenerate. Using the
unfloored `o` makes the bound conservative, never short.

Change is ~15 lines inside `apply_cost_ceiling`. Nothing else moved.

### The old path is an arm, not a deleted bug

```bash
CHUNK_CEILING_GEOMETRY=legacy   # DEFAULT — the shipped, overshooting geometry
CHUNK_CEILING_GEOMETRY=exact    # holds the limit
```

Default stays `legacy` deliberately. Every retrieval number in
`docs/BENCHMARKS.md` and every one of the 5,948 chunks in the eval database were
produced under it; a silent swap would change the corpus underneath measurements
already taken and make them unreproducible. An unrecognised value falls back to
`legacy` with a warning.

`scripts/eval/ingest.py` needed **no change** — it imports the production
`get_chunking_strategy`, which reads the environment at call time.

---

## 3. Retrieval effect — both arms, one snapshot

### The snapshot did not change, and that is a finding

The brief for this work assumed re-ingesting would produce a new label snapshot
with its own ceiling. **It does not.** `LabelSet.fingerprint()`
(`scripts/eval/retrieval/labels.py:229`) hashes the schema version, the graded
flag, the document id set and the per-topic relevant-id sets. Chunk geometry
appears nowhere in it, and document ids are `uuid5` of the file content, which
re-chunking does not touch.

So both arms sit in **snapshot `230c6ea9d9b7e8fd` / queries `1f6c584e8fd6c055`**,
with **the same ceiling, 0.5199**, and the same `n = 338` scorable queries over
8,554 relevant judgments. That makes this the cleanest possible comparison — same
labels, same queries, same ceiling, one variable — rather than a cross-snapshot
one. **No number here is differenced against anything outside this snapshot.**

### Both arms

`n = 338` scorable queries · 8,554 relevant judgments · 344 indexed documents ·
344-document pooled corpus (345 pooled, 1 unreadable) · dense retriever,
oversample ×5, k=10, relevance unit = document, query plan `index` on both runs ·
config hash `5d1408923f74702d` on both.

| | **legacy** (run `63d8281c6eeb`) | **exact** (run `e05d808dffc9`) | ceiling |
|---|---|---|---|
| chunks in index | **5,948** | **5,924** (−24) | — |
| `recall@10` | **0.2195** (42% of attainable) | **0.2186** (42%) | **0.5199** |
| `recall@20` | 0.3062 (40%) | 0.3052 (40%) | 0.7599 |
| `recall@5` | 0.1365 (46%) | 0.1363 (46%) | 0.2939 |
| `recall@1` | 0.0341 (49%) | 0.0343 (49%) | 0.0694 |
| `ndcg@10` | 0.5191 | 0.5145 | — |
| `mrr` | 0.7328 | 0.7312 | — |
| `map` | 0.2319 | 0.2310 | — |
| total misses | 6,946 | 6,964 | — |
| — retrieval failures | 6,010 | 6,028 | — |
| — ranking failures | 936 | 936 | — |

### Reading it

**The fix is retrieval-neutral at this corpus.** `recall@10` moves
0.2195 → 0.2186: **−0.0009 absolute, −0.4% relative**, on `n = 338`. Eighteen
additional retrieval failures out of 8,554 judgments. Ranking failures are
identical at 936, which is what you would expect — the geometry changed for 6 of
344 documents and nothing about ranking changed.

**This is not a regression and must not be quoted as one.** The change is
one-sided in the direction of *fewer, larger chunks* on six long documents
(−24 chunks total), and fewer chunks means marginally fewer retrieval targets.
That is the ceiling's own documented tradeoff being applied *correctly* instead
of being exceeded by 10%. Nothing here says a 50-chunk ceiling is right; it says
that whatever the ceiling is, it is now the number it claims to be.

**Both directions are within the resolving power of this measurement, and the
measurement has no error bar.** The retrieval eval is deterministic — no
sampling, no temperature — so 0.2195 and 0.2186 are exact and reproducible, but
"deterministic" is not "meaningful." Six documents out of 344 is a 1.7%
perturbation of the corpus, and no variance estimate exists for the retrieval
harness under corpus perturbation. **Do not claim the exact arm is worse.** The
honest statement is: *correcting the ceiling changed recall@10 by −0.4% relative
on n=338 within snapshot `230c6ea9d9b7e8fd`, which is too small to attribute.*

### What was not measured

- Whether **50** is the right ceiling. Every number here holds it fixed. The
  interesting sweep — ceiling as a retrieval parameter rather than a cost one —
  is untouched.
- The **section-aware** path (`get_section_aware_chunking_strategy`). It calls
  the same fixed `apply_cost_ceiling` and so inherits the fix, but eval ingestion
  uses `chunking_method: basic`, so the section-aware arm is unmeasured here as
  it is everywhere else in this repo.
- Any **production** effect. This is the local eval corpus on local pgvector.

---

## 4. Spend

Ceiling set to `NOESIS_LLM_MAX_SPEND_USD=6`. Embeddings only, no completions.

| step | calls | tokens | cost |
|---|---|---|---|
| re-ingest 6 documents, legacy → exact | 6 | 1,116,741 | **$0.1452** |
| retrieval eval, legacy arm | 0 | 0 | $0.0000 (query embeddings cached) |
| retrieval eval, exact arm | 0 | 0 | $0.0000 (cached) |
| re-ingest 6 documents, exact → legacy (restore) | 6 | 1,118,724 | **$0.1454** |
| **total** | **12** | **2,235,465** | **$0.2906** |

The restore embeds 1,983 more tokens than the forward pass over the same six
documents: legacy produces 55 chunks where exact produced 50, and each extra
chunk boundary duplicates an overlap region. The token asymmetry between the two
rows *is* the overshoot, in dollars.

0 unpriced calls. `text-embedding-3-large` at $0.13/1M input.

**4.8% of the $6 ceiling.** Only 6 of 344 documents needed re-embedding, because
`ingest.py` is fingerprint-incremental and the geometry changed for nobody else.
A full forced re-ingest of all 344 documents would have been ~$1.36 — also inside
the ceiling, and unnecessary.

Per the standing house rule, this figure is a **lower bound** like every cost
figure in this project.

### The database was restored

The eval database is shared with other agents on this branch. It was returned to
the legacy 5,948-chunk state after the exact-arm run, which is why the restore
line above exists and why the total is double the necessary spend. That was
worth $0.1452.

> ⚠️ **One run was contaminated before the restore.** Retrieval record
> `3a5e8995583e` (`arm: dense_x5_control`, config hash `93fd20285ed9088b`,
> 2026-07-31T23:48:47Z) was written by another agent while the exact-arm corpus
> was live in the database. It reads `recall@10 = 0.2186` — byte-identical to the
> exact arm, not to the 0.2195 legacy corpus its owner would have assumed. **That
> record was measured against a 5,924-chunk index and should be re-run.** The
> underlying hazard is structural and outlives this task: the retrieval eval
> records a labels fingerprint and a config hash but **nothing identifying the
> state of the index it queried**, so two runs with identical hashes can silently
> be measuring different corpora. Flagged for the lead; not fixed here, because
> `run_retrieval_eval.py` is not this agent's file.
