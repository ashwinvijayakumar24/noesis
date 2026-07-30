# Keyword query formulation — why lexical retrieval measured 0.004, and what fixed it

Companion to `retrieval/BASELINE.md`, which recorded the finding. This document
records the diagnosis, the options measured against each other, the choice, and
the honest limits of the result.

Nothing here changes `keyword_search_chunks`. Migration 038 adds a **second**
function, `keyword_search_chunks_v2`, and `app/services/rag_retrieval.py`
selects between them with the `KEYWORD_SEARCH_V2` env flag, **default off**.

---

## 1. The finding

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

## 2. Options considered

All measured on the **same 59 queries**, same database, same labels, in one
process. k = 10, chunk oversample ×5 (each query asks for 50 chunks, max-pooled
to documents), relevance unit = document — the configuration `BASELINE.md`
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

### `websearch_to_tsquery` — rejected

Better ergonomics (free-form text, quoted phrases, `-exclusion`) but it **still
ANDs bare terms**, which is the actual problem. It lifted recall@10 from 0.0026
to 0.0077 and still returned nothing for 53 of 59 queries. It fixes the input
syntax, not the semantics. (The migration keeps the historical filename
`038_keyword_search_websearch.sql`; the measurement moved on from that idea.)

### OR of the query's lemmas — chosen

There is no "`plainto_tsquery` but with OR" in Postgres, so the function extracts
the lemmas the index was built from (`tsvector_to_array(to_tsvector('english',
q))` — already stopword-stripped and stemmed) and rebuilds the query with `|`.

This is the permissive option, and permissiveness is the whole risk: for the
20-word claim above it matches **1648 of 2124 chunks (78 % of the corpus)**. All
of the discrimination therefore comes from the ranking, which is why §3 is not a
footnote.

### The coverage floor — rejected *by measurement*

Requiring ≥30 % of the query's lemmas to be present looked like the obvious way
to cut the 78 %. Measured, it produced **recall@10 = 0.2643, NDCG@10 = 0.4578,
MAP = 0.2253 — identical to four decimals** to no floor at all, at **8×** the
latency (217 ms vs 27 ms; the per-row lexeme `INTERSECT` cannot use the GIN
index). `ts_rank` already down-weights chunks matching few query terms, so the
floor was redundant with the ranking rather than additive to it. Not shipped.

### IDF term selection — rejected *for now*

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

## 3. Ranking: `ts_rank(…, 1|32)`

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

### Escaping, not string-concatenation

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

## 4. Before / after, on the same 59 queries

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

**Two caveats on comparing these to `BASELINE.md`.** (1) That document reports
0.0040 for the old function; this run measures 0.0026 for the same function.
The difference is the label snapshot: more corpora have been built since, and
this run restricts the label set to the 4 scorable topics. The old-vs-new
comparison above is within one run and is the one to quote. (2) **Dense was not
re-measured under this label snapshot** — re-running it costs OpenAI query
embeddings. `BASELINE.md`'s dense recall@10 = 0.4221 is from the earlier
snapshot and is therefore *approximately*, not exactly, comparable.

---

## 5. Hand inspection — are the new rows relevant, or merely numerous?

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

## 6. Is hybrid + RRF unblocked?

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
BASELINE.md caveat that "a difference of a few points between two configurations
is noise" applies to every comparison in §2 and §3. The old-vs-new gap is ~100×
and survives that objection; the choice *among* the OR variants does not, and was
made on simplicity and latency as much as on the numbers. Nothing here has been
measured on production data, and the flag is off by default for that reason.

---

## 7. Reproducing

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
