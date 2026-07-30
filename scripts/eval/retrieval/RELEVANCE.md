# Relevance definition for retrieval eval

This document is written first and deliberately. The single most consequential
decision in a retrieval harness is **what counts as a relevant unit**. It moves
NDCG far more than any embedding-model swap, and a harness that leaves it
implicit produces numbers nobody can interpret six months later.

Every number this harness emits is stamped with the relevance unit that produced
it (`relevance_unit` field + config hash). Results computed under different units
are never comparable and the harness refuses to pretend otherwise.

---

## 1. The three candidate units

| Unit | "A retrieval is correct when…" | Pros | Cons |
|---|---|---|---|
| **chunk** | the exact chunk containing the supporting passage is returned | matches what the LLM actually consumes; sensitive to chunking strategy | requires passage-level ground truth we do not have; label cost is enormous; chunk ids are unstable across re-ingestion |
| **section** | any chunk from the correct section of the correct document is returned | tolerant to chunk-boundary churn | requires section-aligned labels; section segmentation is itself a GROBID output with its own error rate, so it injects a second unmeasured system into the ruler |
| **document** | any chunk of the correct *paper* is returned | ground truth already exists (the author's own reference list); stable ids; chunker-independent | blind to *where* in the paper the support was; a 40-page paper retrieved for the wrong reason still scores as a hit |

## 2. Decision: **document-level relevance is primary**

Reasons, in order of weight:

1. **It is the only unit for which we have non-LLM ground truth.** A manuscript's
   own reference list is human-authored, externally verifiable, and free. Chunk-
   and section-level labels would have to be manufactured — most likely by an LLM
   — which would make the ruler a product of the same class of system it is
   meant to measure. A ruler built from the thing it measures is not a ruler.
2. **Chunk ids are not stable.** Chunk ids are generated at ingestion. Re-ingest
   the same PDF with a different chunk size and every chunk-level label is void.
   Document identity survives re-chunking, so document-level labels are a durable
   asset; chunk labels would have to be rebuilt on every chunking change — i.e.
   exactly the change we most want to measure.
3. **It isolates the variable under test.** Chunk-level scoring entangles the
   retriever with the chunker. Document-level scoring lets a chunking change be
   measured against a *fixed* ruler, which is the whole point of building one.

The cost is stated plainly: **document-level relevance cannot distinguish
"retrieved the right paper for the right reason" from "retrieved the right paper
by coincidence."** Precision of grounding is not measured here. It needs a
separate, smaller, human-labelled passage set. Do not claim this harness measures
it.

## 3. Computing the other two units from the same run

The harness stores the full `RetrievedDoc` list (doc id, chunk id, score, rank),
so all three units are derivable from a single retrieval pass. Only the
*aggregation* differs:

- **document (primary)** — max-pool chunk scores per document, then re-rank
  documents by pooled score. Max-pool rather than sum: summing rewards a document
  merely for being long enough to occupy many chunk slots, which is a length bias,
  not a relevance signal. Dense-rank after pooling so the document run has no gaps.
- **section** — pool by `(doc_id, section_id)` using the same max-pool rule.
  Available only when the retriever populates `section_id`; the harness reports
  `section_id_coverage` and refuses to emit section metrics below full coverage
  rather than silently scoring a partial run.
- **chunk** — no pooling; the raw run is the run. Requires chunk-level qrels,
  which do not exist today. `metrics.py` accepts them if supplied; nothing in this
  repo supplies them yet.

`k` is applied **after** pooling for document/section units. Applying it before
would mean a document occupying 5 of the top 10 chunk slots crowds out 4 other
documents and depresses recall@10 for reasons that have nothing to do with
ranking quality. `metrics.py` therefore requests `k * chunk_oversample` chunks
from the retriever (default 5x) and pools down to `k` documents. This oversample
factor is part of the config hash.

## 4. How an OpenAlex reference resolves to a corpus doc id

`scripts/eval/build_corpus.py` is the resolution path we inherit. For each
manuscript it: extracts references via GROBID → resolves each against OpenAlex by
DOI, falling back to fuzzy title match (≥0.6 word-overlap on words longer than 3
chars) → takes `open_access.oa_url` or `primary_location.pdf_url` → downloads to
`scripts/eval/corpora/<manuscript_stem>/<firstauthor>_<year>_<title>.pdf`.

The consequence, and it is the load-bearing fact of this whole lane:

> **Presence of a PDF in `corpora/<stem>/` *is* the resolved reference label.**
> A file exists there if and only if a reference of `<stem>` survived GROBID
> extraction, OpenAlex resolution, open-access availability, and download.

So the corpus doc id is derived from the file, not from OpenAlex:

- `doc_id` = `sha256(pdf_bytes)[:16]`, content-addressed. Two corpora that both
  downloaded the same paper collapse to one doc id, which is correct — it is one
  document — and is what makes a **pooled** corpus possible.
- `doc_key` = `<corpus_name>/<filename stem>` is retained for human readability
  and for joining to Lane A's ingested documents by filename.

### The five ways a reference fails to resolve

1. **GROBID drop** — reference never extracted from the PDF's bibliography.
2. **OpenAlex miss** — no DOI and title search returns nothing above threshold.
3. **Not open access** — resolved, but no downloadable PDF URL.
4. **Download failure** — non-200, wrong content-type, or <5 KB response.
5. **Truncation** — `build_corpus.py --max-papers` (default 20) caps how many
   references are even attempted, regardless of how many the paper cites.

All five produce the same observable on disk: *absence*. **They are not
distinguishable post-hoc**, and none of them is a retrieval failure. Every one is
excluded from the recall denominator and reported in a separate `unresolved`
bucket. A reference the harness could never have surfaced must not be scored as
a retriever miss — that is a measurement bug, not conservatism.

### Known gap: the denominator is not recoverable today

`build_corpus.py` **does not persist the reference list it started from**. It
prints counts and exits. Therefore, from disk alone, we know how many references
resolved (= file count) but **not how many were attempted**. The true resolution
rate is unknown-by-construction, not merely unmeasured.

`labels.py` handles this honestly:

- It looks for an optional sidecar `corpora/<stem>/references.json` — a list of
  `{title, doi, authors, year}` from the GROBID extraction.
- **Present** → resolution rate is computed exactly, and each unresolved
  reference is listed individually in the `unresolved` bucket.
- **Absent** → `references_total` is `null`, `resolution_rate` is `null`, and
  `denominator_recoverable` is `false`. The harness prints a loud warning and
  **never substitutes the resolved count for the denominator**, because doing so
  reports a 100% resolution rate, which is the exact silent-denominator-shrink
  failure this lane exists to prevent.

Writing that sidecar requires a one-line change in `build_corpus.py`, which this
lane does not own. It is the single highest-value follow-up.

## 5. Graded vs. binary relevance

**Binary (relevance = 1), by decision.** Graded relevance is only defensible when
the grades come from something real. The two gradings that were considered:

- *Citation frequency* (a reference cited 5 times is more relevant than one cited
  once) — requires in-text citation counts per reference. GROBID emits these, but
  `build_corpus.py` discards them and nothing on disk retains them. Unavailable.
- *Section of first citation* (related-work citations are more retrieval-relevant
  than a passing methods citation) — same problem, plus it encodes a contestable
  assumption about what retrieval is for.

Fabricating grades from what we do have (e.g. OpenAlex citation count) would
grade *paper prominence*, not *relevance to this manuscript*, and would inflate
NDCG for retrievers biased toward famous papers. That is worse than binary.

So: binary now, with the grading hook preserved. `labels.py` emits qrels as
`{query_id: {doc_id: int}}` and `metrics.py` passes grades through to ranx
untouched, so the day the reference sidecar carries citation counts, grading is a
label-side change with no metric-side work. The `graded` flag is part of the
config hash, so today's binary numbers can never be silently compared against
tomorrow's graded ones.

## 6. Methodological limitations — read before quoting any number

1. **This measures "would we have found what the author cited", not "would we
   have found what is relevant."** These are correlated but not the same. Authors
   cite for reasons other than relevance: prior work by collaborators, reviewer-
   demanded citations, venue convention, self-citation, availability of the paper
   at writing time. Every one of those is a false positive in our label set, and
   we cannot detect them.
2. **It cannot reward finding relevant work the author missed.** This is the
   inverse and larger error. A retriever that surfaces a highly relevant paper the
   author never cited is scored as a *false positive* — it is punished for doing
   precisely the thing the product exists to do. Measured precision is therefore a
   **lower bound** on true precision, and the gap is unquantified. Never report
   precision from this harness as though it were true precision. Recall is the
   sounder number here; treat precision as directional only.
3. **Open-access survivorship bias.** Only OA PDFs make it into the corpus. Paywalled
   references — disproportionately older, journal-published, and in some fields the
   majority — are silently absent. The corpus is not a random sample of the
   reference list; it is the OA-available subset, which skews recent and
   preprint-heavy.
4. **The `--max-papers 20` cap truncates long reference lists.** A paper citing 80
   works contributes at most 20 labels, and specifically the *first* 20 in GROBID's
   emission order, which is not random with respect to section or importance.
5. **Distractors are other manuscripts' references, not a realistic corpus.** In the
   pooled setup, negatives for manuscript A are the references of manuscripts B..K.
   If those manuscripts are topically distant, retrieval is easier than reality and
   every metric is optimistic. `labels.py` reports pooled corpus size and per-topic
   distractor count so this is visible rather than assumed. **With the current
   corpus this bias is severe — see §7.**
6. **Small-N.** Confidence intervals on a corpus of tens of documents are wide.
   Differences of a few points are noise. The harness reports `n_queries` and
   `n_relevant_total` alongside every metric so nobody quotes a delta that a
   single document could flip.
7. **No relevance judgments were made by a human for this harness.** The labels are
   *reused* human judgments (citation decisions) made for a different purpose. That
   is a strength versus LLM-generated labels and a weakness versus purpose-built
   ones.

## 7. Actual state of the ground truth on disk (2026-07-30)

Measured, not assumed:

- **39 corpus PDFs total** across 11 corpus directories, of which `corpus_a`,
  `draft5`, and `draft7` are **empty**. Largest is `draft9` at 10.
- **Reference denominators are unrecoverable** (no sidecar, per §4). With
  `--max-papers 20` and 11 corpora, at most ~200 references were attempted;
  39 landed. End-to-end yield is therefore **≤19.5%**, an upper bound, not a
  measurement.
- **The manuscript PDFs for `draft1`–`draft10` are no longer on disk**
  (`scripts/eval/pdfs/` is empty). Their corpora survived; their texts did not.
- **Cached claims exist for 15 OpenReview papers** (759 claims across 75 export
  files in `cache/exports/`), every one recorded with `corpus: "no-corpus"`.

The join is therefore **empty**: the manuscripts with labels have no queries, and
the manuscripts with queries have no labels. This is a real finding about the
repo's eval assets, not a limitation of the harness. The harness is built,
tested, and runnable end-to-end against `MockRetriever` today; feeding it real
data requires **one** of:

- build a corpus for any OpenReview paper that already has cached claims
  (`build_corpus.py --draft openreview/.../<id>.pdf`), which yields both halves
  for the same paper; or
- restore a `draft1`–`draft10` PDF and extract its claims.

Either unblocks real numbers. Neither is in this lane's file scope.
