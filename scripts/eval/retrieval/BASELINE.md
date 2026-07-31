> **SUPERSEDED by `scripts/eval/BASELINE_15.md`. Do not quote the numbers below.**
> Two reasons: (1) the "dense (pgvector HNSW, cosine)" row was measured against an
> exhaustive sequential scan, not the HNSW index — Postgres declined the index
> above LIMIT ≈ 35 on the 2124-chunk corpus and the harness asks for 50; (2) the
> label snapshot this document ran under (fingerprint `019bee4a06eb2d39`, 118
> documents, 4 topics, 59 queries) no longer exists — the corpus is now 344
> documents / 5948 chunks across all 15 topics. Every arm has been re-measured
> under the current snapshot, and the construction ceilings recomputed. This file
> is kept as history, not as a reference.

# Retrieval baseline — first measured numbers, 2026-07-30

Before this run, `grep -rE "ndcg|MRR|recall@"` over this repository returned
nothing. There was no retrieval measurement of any kind. These are the first.

Read RELEVANCE.md first — it defines the relevance unit, and every number below
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

## 1. The numbers

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

### Failure attribution

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

### recall@k is capped well below 1.0 by construction

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

### The keyword leg is not degraded — it is doing exactly what it was told

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

## 2. Scale — say how small

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

## 3. Corpus gaps: 65 references excluded from the denominator

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

### The matcher fix that produced that 65

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

## 4. What these numbers are not

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

## 5. Ingest, for the record

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

## 6. Run integrity

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
