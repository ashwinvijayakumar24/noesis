# Eval guide

How the eval harness is run, gated, and interpreted. Each section below is a
former standalone document, moved here verbatim.

One document did **not** fold in: the degraded-output labelling rubric, which
stays a separate file at [gate_rubric.md](./gate_rubric.md). It is not prose.
`gate_calibration/llm_labeller.py` reads it verbatim and embeds it in the
labelling prompt, and it is the same text a human labeller reads — the two
raters must answer the same question or the kappa measures the paraphrase.
Folding it into this document would change the instrument.

Measured results live in [MEASUREMENTS.md](./MEASUREMENTS.md).

## Contents

- [Relevance definition for retrieval eval](#relevance-definition) — was `scripts/eval/retrieval/RELEVANCE.md`
- [CI and the eval gate](#ci-and-the-eval-gate) — was `scripts/eval/CI.md`
- [OpenAlex: keys, budget, and finishing the corpus](#openalex) — was `scripts/eval/OPENALEX.md`
- [LLM labelling and human–model agreement](#llm-labelling-and-agreement) — was `scripts/eval/gate_calibration/AGREEMENT.md`

---

<a id="relevance-definition"></a>

_Moved here unchanged from `scripts/eval/retrieval/RELEVANCE.md`._

## Relevance definition for retrieval eval

This document is written first and deliberately. The single most consequential
decision in a retrieval harness is **what counts as a relevant unit**. It moves
NDCG far more than any embedding-model swap, and a harness that leaves it
implicit produces numbers nobody can interpret six months later.

Every number this harness emits is stamped with the relevance unit that produced
it (`relevance_unit` field + config hash). Results computed under different units
are never comparable and the harness refuses to pretend otherwise.

---

### 1. The three candidate units

| Unit | "A retrieval is correct when…" | Pros | Cons |
|---|---|---|---|
| **chunk** | the exact chunk containing the supporting passage is returned | matches what the LLM actually consumes; sensitive to chunking strategy | requires passage-level ground truth we do not have; label cost is enormous; chunk ids are unstable across re-ingestion |
| **section** | any chunk from the correct section of the correct document is returned | tolerant to chunk-boundary churn | requires section-aligned labels; section segmentation is itself a GROBID output with its own error rate, so it injects a second unmeasured system into the ruler |
| **document** | any chunk of the correct *paper* is returned | ground truth already exists (the author's own reference list); stable ids; chunker-independent | blind to *where* in the paper the support was; a 40-page paper retrieved for the wrong reason still scores as a hit |

### 2. Decision: **document-level relevance is primary**

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

### 3. Computing the other two units from the same run

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

### 4. How an OpenAlex reference resolves to a corpus doc id

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

#### The five ways a reference fails to resolve

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

#### Known gap: the denominator is not recoverable today

`build_corpus.py` **does not persist the reference list it started from**. It
prints counts and exits. Therefore, from disk alone, we know how many references
resolved (= file count) but **not how many were attempted**. The true resolution
rate is unknown-by-construction, not merely unmeasured.

`labels.py` handles this with three matchers, in descending order of trust:

1. **Sidecar with per-reference `status`** (`MATCHER_SIDECAR`) — the authority.
   `build_corpus.py` now writes `corpora/<stem>/references.json` recording every
   attempted reference, its outcome (`resolved` / `no_oa_pdf` /
   `no_openalex_match` / `download_failed` / `pending` / `skipped_max_papers`)
   and, when resolved, the filename it wrote. A reference maps to a document if
   and only if its status is `resolved` and that file is on disk. Everything else
   is excluded from the denominator and counted **by reason**. Resolution rate is
   exact.
2. **Sidecar without statuses** (`MATCHER_TITLE_TOKEN`) — the legacy lenient
   fallback: guess resolution from title-token overlap against filenames. It was
   measurably wrong. Against the four corpora that now carry statuses it credited
   **21** never-downloaded references as resolved (44 unresolved counted vs. 65
   actual), inflating recall by handing the retriever credit for documents that
   do not exist. It survives only for statusless sidecars, and `labels.py` and
   the eval CLI both print a loud warning naming every topic where it fired.
3. **No sidecar** (`MATCHER_NONE`) — `references_total` is `null`,
   `resolution_rate` is `null`, `denominator_recoverable` is `false`. The
   harness **never substitutes the resolved count for the denominator**, because
   doing so reports a 100% resolution rate, which is the exact
   silent-denominator-shrink failure this lane exists to prevent.

`LABELS_SCHEMA_VERSION` is part of the label cache key, so a cache written under
the old lenient matcher can never be silently served for a run under the new one.

### 5. Graded vs. binary relevance

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

### 6. Methodological limitations — read before quoting any number

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

### 7. Actual state of the ground truth on disk

**Current — 2026-07-30, after the OpenReview corpora landed. Measured, not
assumed. Headline numbers live in [MEASUREMENTS.md § Retrieval baseline (superseded)](./MEASUREMENTS.md#retrieval-baseline-superseded).**

- **118 unique corpus PDFs** across 15 topic directories; all 118 are ingested
  into local pgvector as 2124 chunks.
- **4 topics carry an authoritative sidecar** (`10eQ4Cfh8p`, `9ceadCJY4B`,
  `ApjY32f3Xr`, `BQvbL2sFQx`): **145 references attempted, 80 resolved (55.2%)**,
  65 excluded as corpus gaps (`no_oa_pdf` 27, `pending` 19, `no_openalex_match`
  10, `download_failed` 9).
- **The 11 `draft*` topics still have no sidecar**, so their denominator remains
  unrecoverable and their resolution rate is reported as UNKNOWN. Their 39
  documents serve as distractors.
- **The join is non-empty**: 59 of 338 built queries have labels, carrying 903
  relevant judgments across those 4 topics. The other 279 queries belong to the
  11 OpenReview manuscripts with cached claims but no corpus (OpenAlex is now a
  metered paid API), and are dropped rather than scored as zeros.
- The database document id is `uuid5(ns, sha256_hex)` (`ingest.py`) while the
  label doc id is `sha256_hex[:16]`. `run_retrieval_eval.db_doc_id_map`
  translates; without it every DB-backed run scores a flat 0.0 while looking
  healthy, so the CLI fails any run whose rows join to nothing.

#### Historical — the state that motivated this document (before the OpenReview corpora)

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

The join was therefore **empty**: the manuscripts with labels had no queries, and
the manuscripts with queries have no labels. This is a real finding about the
repo's eval assets, not a limitation of the harness. The harness is built,
tested, and runnable end-to-end against `MockRetriever` today; feeding it real
data requires **one** of:

- build a corpus for any OpenReview paper that already has cached claims
  (`build_corpus.py --draft openreview/.../<id>.pdf`), which yields both halves
  for the same paper; or
- restore a `draft1`–`draft10` PDF and extract its claims.

Either unblocks real numbers. The first path is the one that was taken.

---

<a id="ci-and-the-eval-gate"></a>

_Moved here unchanged from `scripts/eval/CI.md`._

## CI and the eval gate

### The problem this exists to fix

`.github/workflows/ci.yml` contained zero references to `scripts/eval`. No
workflow ran `run_eval.py`, `check_heldout.py`, `benchmarks.py --check`, or any
`make eval-*` target. Meanwhile the regression gate inside `run_eval.py` had been
failing since 2026-06-20 — `scoreboard.json` reported `mean_overall 6.97` against
`min_overall: 8.5` in `config.yaml` — and nobody noticed, because nothing ran it.

A quality gate that nothing runs is not a gate. This file describes what now
runs, what deliberately does not, and why.

### The split: free vs. paid

Every real measurement in this project either costs OpenAI money or needs a
pgvector database holding an ingested corpus. A GitHub PR runner has neither.
So the work is split in two, and the split is the whole design:

| | Runs on a PR | Costs money | Needs a DB |
|---|---|---|---|
| `scripts/eval/ci_gate.py` | yes, blocking | no | no |
| `benchmarks.py --check` (full) | no — skips, sinks are gitignored | no | no |
| `run_eval.py` / `run_harness.py` | **never** | yes | yes |
| `retrieval/run_retrieval_eval.py` | **never** | yes | yes |
| `node_eval.py` replay | **never** | yes | no (needs gitignored fixtures) |

Nothing in the right-hand column may ever be added to the PR workflow. If you
want it in CI, it goes in `eval-nightly.yml`.

### Workflow layout

```
.github/workflows/
  ci.yml               push + pull_request. Now contains an `eval-gate` job.
  eval-nightly.yml     schedule + workflow_dispatch ONLY. Never blocks a merge.
```

#### `ci.yml` → job `eval-gate`

Blocking. Two steps:

1. `pytest scripts/eval/tests/test_ci_gate.py -q` — the gate's own tests.
2. `python scripts/eval/ci_gate.py --base <PR base sha>` — the gate.

It checks out with `fetch-depth: 0` because the append-only check diffs against
the PR base commit; a shallow clone cannot resolve that ref and the check would
SKIP silently, which is worse than failing.

Nothing else in `ci.yml` was made stricter. `security` is still `|| true` and the
frontend steps still `|| echo` to success — those were already non-gating and
tightening them was not this change's job. The known backend baseline is
**984 passed, 2 failed** (`test_reviewer_context_caps_long_draft_at_24000`,
`test_reviewer_panel_failure_returns_empty_list`); both are pre-existing and
deliberately deferred, and `eval-gate` neither blocks on them nor hides them.

The `deploy` job SSHes into an EC2 box and runs `git reset --hard origin/master`.
**The product is frozen and that box is torn down** (see `VITE_FREEZE_MODE`), so
that job cannot succeed. It was left exactly as it was — fixing or removing it is
out of scope here and would be an unrelated change.

#### `eval-nightly.yml`

`schedule` (07:00 UTC) and `workflow_dispatch` only. It has no `needs:`
relationship with any PR job and must **not** be added to branch protection.

| Job | What it does |
|---|---|
| `integrity-strict` | the same gate as the PR, with `--strict` (warnings fail) |
| `preflight` | resolves credential presence into job outputs |
| `node-replay` | paid node replay, with `NOESIS_LLM_MAX_SPEND_USD` set |
| `retrieval-eval` | paid + DB retrieval eval |
| `notify` | opens a GitHub issue when a scheduled run fails |

A missing credential produces a **skipped** job and a `::warning::`, never a
green tick. `skipped` means "not measured", not "passed" — the notification body
says so explicitly, because the failure mode this repo actually hit was a silent
absence of measurement, not a loud failure.

Cron on GitHub is best-effort and can be dropped entirely on a quiet repo. Treat
a missing nightly run as *unknown*, not as *passed*.

### What the owner must configure

No secret values appear anywhere in this repo, and none should be committed.
Set these as **repository secrets** (Settings → Secrets and variables → Actions):

| Secret | Needed by | Effect if unset |
|---|---|---|
| `OPENAI_API_KEY` | `node-replay`, `retrieval-eval` | both jobs skip with a warning |
| `EVAL_DB_HOST` | `retrieval-eval` | job skips with a warning |
| `EVAL_DB_PORT`, `EVAL_DB_NAME`, `EVAL_DB_USER`, `EVAL_DB_PASSWORD` | `retrieval-eval` | falls back to `db.py` local defaults, which will not resolve on a runner |

Also required for the nightly to do anything real, and **not** solvable with
secrets:

- **Replay fixtures.** `scripts/eval/cache/` is gitignored, so a clean
  GitHub-hosted checkout has no state fixtures and `node_eval.py` has nothing to
  replay. The workflow detects this and skips loudly. To make it real, either
  run the nightly on a runner that holds the eval cache, or restore
  `scripts/eval/cache/state/` from an artifact before the replay step.
- **An ingested corpus.** `retrieval-eval` needs a pgvector database that already
  holds the eval corpus. Against an empty database the harness records the run
  `valid: false` — which the integrity gate then refuses to let anyone quote.

Branch protection: mark `eval-gate` as required. Do not mark any nightly job as
required.

### `ci_gate.py`

```
python3 scripts/eval/ci_gate.py                     # working tree vs HEAD
python3 scripts/eval/ci_gate.py --base origin/master
python3 scripts/eval/ci_gate.py --strict            # warnings become failures
python3 scripts/eval/ci_gate.py --json              # machine-readable
```

Stdlib only. No network, no database, no credentials — `pyyaml` is deliberately
not imported, which is why the threshold parser is a twelve-line regex reader.

#### Exit codes

| Code | Meaning |
|---|---|
| 0 | all blocking checks passed (warnings may have been printed) |
| 1 | at least one blocking check FAILED |
| 2 | warnings present and `--strict` was given |
| 3 | the gate itself could not run (not a git repo, git unavailable, bad args) |

Every failure prints the exact command to reproduce it locally.

#### The checks

Each encodes a failure mode this project actually hit.

**`board-tracked-sources`** — blocking, runs everywhere.
`benchmarks.json` records a line count for each sink it was built from. If a sink
that is *tracked in git* has a different line count than the board recorded, the
board is stale. A drifted board is a lying board. Fix: `make benchmarks`, commit
both [BENCHMARKS.md](./BENCHMARKS.md) and `benchmarks.json`.

**`board-regenerates`** — blocking where runnable, otherwise SKIP.
The full `benchmarks.py --check`. Four of its eight sinks are gitignored
(`retrieval_eval.jsonl`, `node_eval_spans.jsonl`, `ingest_manifest.jsonl`,
`ann_sweep.jsonl`), so on a clean checkout the board **cannot** be regenerated
and this check SKIPs rather than failing on absent data. That is the honest
answer, not a hole: `board-tracked-sources` still covers the tracked sinks in CI,
and this check does the complete job on any machine that has the sinks. Run it
locally with `make benchmarks-check`.

**`append-only`** — blocking, runs everywhere.
`results/history.jsonl`, `results/openreview_history.jsonl` and
`results/node_eval.jsonl` are append-only: they are the only durable record this
repo has of its own eval scores. The check requires the base ref's content to be
a line-wise prefix of the current content, so a shrink or an in-place line
rewrite fails. This repo already destroyed its eval history once by overwriting
`scoreboard.json` in place; that is why the check exists and why it blocks.
Recovery is printed in the failure message:
`git show <base>:<path> > <path>`, then append the new records.

**`invalid-run-quoted`** — blocking, runs everywhere.
`run_retrieval_eval.py` marks a run `valid: false` when its verdict finds a join
bug or an empty fusion leg, and prints `RUN INVALID -- DO NOT QUOTE THESE
NUMBERS`. This check builds the registry of invalidated `run_id`s from the
tracked board (`retrieval.invalidated[*].run_id`) plus any jsonl sink present in
the checkout, then scans tracked measurement markdown for those ids. A mention
alongside a number, with no invalidation marker within three lines, fails.
`gold/*.md` are excluded — they are reference critiques, not measurement reports.
In CI the registry comes from the board alone, since the sinks are gitignored;
locally it is a superset.

**`metric-without-n`** — warning.
A headline metric (`recall@k`, `NDCG@k`, `MRR`, `precision@k`, `mean overall`)
stated with a number and no sample size within two lines. It is a warning and not
a gate on purpose: a markdown table can legitimately carry its `n` in a column
header or a caption the heuristic cannot see, and against the current docs it
reports **38** hits, most of them table rows whose `n` lives in the surrounding
prose. A noisy blocking check gets disabled, and a disabled check is worth less
than an honest warning. `--strict` promotes it, and the nightly runs `--strict`.

**`threshold-note`** — warning.
If the `thresholds:` block in `config.yaml` moves relative to the base ref and
the new value is not mentioned in the threshold change log below, warn. Moving
`min_overall` is how a failing gate becomes a passing one without any code
improving, so it should be visible in review — but it is legitimate often enough
that blocking would be wrong.

### Threshold change log

Add a line here whenever `scripts/eval/config.yaml` thresholds move. Name the
key, the old and new value, and why.

- (no changes recorded yet — `min_overall: 8.5`, `min_dim_score: 7.5`,
  `max_mean_drop: 0.5` as of this file's creation)

> Standing note, not a change: `min_overall: 8.5` has been violated by the
> measured `mean_overall 6.97` since 2026-06-20. The gate is correct and the
> product is below it. Lowering the threshold to make it green would be exactly
> the move this log exists to make visible.

### Known open findings

**The `eval-gate` job will be red on its first run, and it is right to be.**
Against a clean clone (what CI sees), the gate reports:

- **FAIL `board-tracked-sources`** — the committed `benchmarks.json` records 31
  lines for `results/node_eval.jsonl`, but the committed `node_eval.jsonl` holds
  14. The board was regenerated locally against 31 records and committed, while
  the 17 newer records were never committed. The tracked board therefore
  describes data that does not exist at `HEAD` — precisely the "generated
  artefact drifted from its source" failure this check is for.
  Fix: commit the appended `scripts/eval/results/node_eval.jsonl` records (they
  are already un-gitignored for exactly this reason), then `make benchmarks` and
  commit both board outputs.

Running `python3 scripts/eval/ci_gate.py` on a full local checkout (where the
gitignored sinks exist) additionally reports:

- **FAIL `board-regenerates`** — the tracked [BENCHMARKS.md](./BENCHMARKS.md) and
  `benchmarks.json` are stale. The board records 8 records for
  `results/retrieval_eval.jsonl`; the file holds 15. Fix with `make benchmarks`
  and commit both outputs. This does not fire in CI, where the sink is absent.
- **WARN `metric-without-n`** — 38 hits across [MEASUREMENTS.md § HNSW sweep](./MEASUREMENTS.md#hnsw-sweep), [MEASUREMENTS.md § Retrieval baseline (15 topics)](./MEASUREMENTS.md#retrieval-baseline-15-topics),
  [MEASUREMENTS.md § Keyword query formulation](./MEASUREMENTS.md#keyword-query-formulation), [BENCHMARKS.md](./BENCHMARKS.md) and [MEASUREMENTS.md § Retrieval baseline (superseded)](./MEASUREMENTS.md#retrieval-baseline-superseded).
- **Not a gate finding, but adjacent:** `results/history.jsonl` does not exist
  and `results/openreview_history.jsonl` is untracked, even though `.gitignore`
  negates both specifically so they would survive a clone. Until they are
  committed, the append-only check has only `node_eval.jsonl` to protect.

---

<a id="openalex"></a>

_Moved here unchanged from `scripts/eval/OPENALEX.md`._

## OpenAlex: keys, budget, and finishing the corpus

`build_corpus.py` resolves each manuscript's reference list against OpenAlex to
find open-access PDFs. OpenAlex became a metered, paid API in February 2026, and
that is why the retrieval eval currently covers **4 of 15 topics**.

**Read this first, because it probably saves you the money:** the single biggest
lever is not paying, it is getting a **free API key**. An unauthenticated caller
gets **$0.10/day**. A free key — no credit card — gets **$1.00/day**, ten times
as much, and the entire remaining build is estimated at **~$0.38**. On the
measured numbers below, a free key finishes the job in one run for $0.

Add prepaid credit only if you want headroom against the estimate being wrong.

---

### 1. Sign up and (optionally) add funds

| Step | URL |
|------|-----|
| Create an account (free, ~30 seconds) | <https://openalex.org> |
| Get your API key | <https://openalex.org/settings/api> |
| Buy prepaid usage, if you want it | <https://openalex.org/pricing> |
| Watch spend | <https://openalex.org/settings/usage> |

**What I verified and what I did not.** The URLs above are the ones OpenAlex's
own documentation and launch blog post give. I could **not** load
`openalex.org/pricing` or `openalex.org/settings/api` to check the on-page flow —
both return **HTTP 403** to non-browser clients (bot protection). So I cannot
confirm, from my own observation, what the checkout looks like, which payment
methods are accepted, or whether prepaid credit is bought per-key or per-account.
OpenAlex's blog states you can "buy prepaid usage in 1min with your credit card,
whenever you want, however much you want," but **I am relaying that, not
confirming it.** Open the page in a browser and trust what you see there over
this file.

What I *did* confirm live is that prepaid balance is a real, separate pool: the
API returns an `X-RateLimit-Prepaid-Remaining-USD` header alongside the daily
allowance, and `--check-budget` reports both.

### 2. Where the key goes

OpenAlex authenticates with an **`api_key` query parameter** — not a bearer
token, not a custom header.

Confirmed two ways:

- <https://developers.openalex.org/api-reference/authentication> — *"add
  `api_key=YOUR_KEY` to your API calls"*, example
  `curl "https://api.openalex.org/works?api_key=YOUR_KEY"`.
- Live, on 2026-07-30: a bogus key on `?api_key=` returns
  `401 {"error":"Invalid or missing API key"}` — so the parameter is genuinely
  read and validated, not ignored.

Set it as an environment variable:

```bash
export OPENALEX_API_KEY=<your key>
```

or add a line to `services/backend/.env`:

```
OPENALEX_API_KEY=<your key>
```

**Never commit the key.** It is a credential that spends money. Note that
because OpenAlex puts it in the *URL* rather than a header, it is unusually easy
to leak — it would otherwise show up in any logged request URL. `build_corpus.py`
routes every printed message, raised exception and written file through a
redaction step, and there are tests asserting the key appears in none of them. If
you add code here, keep it that way.

`mailto` is unrelated and unchanged: it is the old *polite pool* convention, not
authentication. The script still sends it either way.

### 3. Verify the key worked

```bash
python3 scripts/eval/build_corpus.py --check-budget
```

One cheap request, then it exits. Funded and working looks like:

```
[build-corpus] OpenAlex: authenticated
[build-corpus]   daily allowance remaining: $1.0000 of $1.00
[build-corpus]   prepaid balance: $1.0000
[build-corpus]   spendable now: $2.0000 (~2000 title searches)
```

The state you are in *right now*, with no key, is this real output:

```
[build-corpus] OpenAlex: unauthenticated (free tier)
[build-corpus]   daily allowance remaining: $0.0000 of $0.10
[build-corpus]   prepaid balance: $0.0000
[build-corpus]   spendable now: $0.0000 (~0 title searches)
[build-corpus]   daily allowance resets in 2.9h (midnight UTC)
[build-corpus] Budget is spent. Add prepaid credit at https://openalex.org/pricing
               or wait for the midnight-UTC reset.
```

Exit codes: `0` fine, `1` key rejected or OpenAlex unreachable, `2` budget spent.
A mistyped key reports `API key rejected (401)` rather than silently falling back
to the unauthenticated tier.

### 4. Finish the remaining 11 papers

```bash
export OPENALEX_API_KEY=<your key>
python3 scripts/eval/build_corpus.py --check-budget     # confirm first
python3 scripts/eval/build_corpus.py --openreview-all --max-papers 0
```

`--openreview-all` walks every OpenReview topic that has cached claims and skips
the four already done, so this one command is the whole job.

**Measured, not guessed.** Parsing the 11 outstanding manuscripts offline gives:

| | |
|---|---|
| References still to resolve | **418** (+19 `pending` in `BQvbL2sFQx`) |
| Of those, carrying a DOI | 90 |
| Estimated OpenAlex requests | **~463** |
| Estimated cost | **~$0.38**, worst case ~$0.43 |
| Wall clock | **~30–40 min**, set by the 0.12s throttle and PDF downloads, not by budget |

Two things make this cheaper than a flat "one call per reference" estimate:

- A single-entity lookup (`/works/<doi>`) costs **$0.0001**; a title search
  (`/works?search=`) costs **$0.001** — 10x more. Only 90 of 418 references have
  a DOI, which is why the cost is dominated by searches.
- Downloading the OA PDFs is **free**. Those fetch from the publisher or
  repository at `oa_url`, not from OpenAlex, so they never touch the budget.

Prices confirmed live from `X-RateLimit-Cost-Required-USD` on 2026-07-30.

One caveat I could not settle: OpenAlex's launch blog says single-record lookups
by ID or DOI are *free and unmetered*. The live headers disagree — a DOI lookup
reported a required cost of `$0.0001`. The estimate above assumes the **headers**
are right, i.e. the pessimistic reading. If the blog is right, the run is cheaper
still.

The script now prints the request count, the estimated cost and your remaining
budget **before** it starts each corpus, and warns outright if the budget cannot
cover the estimate — so an under-funded run announces itself in the first second
rather than 429ing twenty minutes in.

### 5. The free route: no money at all

The build is **fully resumable**, so you can simply run it once a day and let the
midnight-UTC reset pay for it.

```bash
python3 scripts/eval/build_corpus.py --openreview-all --max-papers 0
```

Re-run after each reset. It picks up exactly where it stopped.

- With **no key** ($0.10/day) that is roughly **4 days**; with a **free key**
  ($1.00/day) it should finish in **one run**.
- Re-running finished work is free: I measured re-checking the three completed
  corpora at **0.4s and zero network calls**. Already-resolved references are
  served from the `references.json` sidecar and never looked up again.
- It is safe to run unsupervised. When the budget runs out mid-run, unlooked-up
  references are recorded as `pending`, **not** as `no_openalex_match`. That
  distinction matters: `no_openalex_match` is a terminal state the resume index
  would skip forever, so mislabelling it would silently and permanently shorten
  the corpus while still counting toward the denominator. `pending` stays in the
  denominator and is retried on the next run.

Given the free key gets $1/day, **section 5 and section 4 are likely the same
run.** The money is optional.

### 6. What was not built: a Crossref + Unpaywall fallback

There is an obvious free alternative — resolve references through Crossref
(metadata, no key, no charge) and Unpaywall (OA locations, free with a `mailto`)
and skip OpenAlex entirely. It was considered and deliberately not built. The
reasons are about correctness of the eval, not effort:

1. **Different id space.** The `references.json` sidecar is specified around
   `openalex_id` — that field is the join key, and `retrieval/labels.py` reads
   the sidecar as the retrieval label set. Crossref returns DOIs and Unpaywall
   returns OA locations; neither yields an OpenAlex work id. Supporting both
   means either a nullable id column, which weakens the schema for every
   consumer, or a translation step that needs OpenAlex anyway.
2. **Different match semantics.** OpenAlex title search and Crossref
   bibliographic search do not agree on what counts as a match, and they fail
   differently on preprints, workshop papers and arXiv duplicates. A corpus built
   half one way and half the other has a *resolution rate that no longer means
   one thing* — and the whole point of the sidecar is that the denominator is
   trustworthy. Mixing resolvers across the 15 topics would quietly make the
   retrieval numbers incomparable between topics, which is worse than having 4
   topics that are comparable.
3. **The cost being avoided is ~$0.38**, or $0 with a free key. Building a
   second resolver to dodge that, at the price of a fuzzier eval, is a bad trade.

If OpenAlex ever becomes genuinely unaffordable, the honest version of this is a
full migration — one resolver, rebuild all 15 corpora, bump
`EXTRACTOR_VERSION` so every sidecar regenerates — not a fallback that mixes the
two.

---

### Quick reference

```bash
# Do I have budget?
python3 scripts/eval/build_corpus.py --check-budget

# Finish everything (skips completed topics automatically)
python3 scripts/eval/build_corpus.py --openreview-all --max-papers 0

# One topic
python3 scripts/eval/build_corpus.py --openreview rhgIgTSSxW --max-papers 0
```

| Env var | Effect |
|---------|--------|
| `OPENALEX_API_KEY` | Sent as `?api_key=`. Absent → unauthenticated, $0.10/day. |
| `OPENALEX_EMAIL` / `UNPAYWALL_EMAIL` | Polite-pool `mailto`. Not authentication. Default `contact@noesis.is`. |

Remaining topics: `H9DYMIpz9c`, `cXs5md5wAq`, `eR4W9tnJoZ`, `eUgS9Ig8JG`,
`gYcft1HIaU`, `jx6njBKH8E`, `kKRbAY4CXv`, `miGpIhquyB`, `qBL04XXex6`,
`rhgIgTSSxW`, `rp5vfyp5Np` — plus 19 `pending` references in `BQvbL2sFQx`.

---

<a id="llm-labelling-and-agreement"></a>

_Moved here unchanged from `scripts/eval/gate_calibration/AGREEMENT.md`._

## LLM Labelling and Human–Model Agreement

**Status:** methodology note for `llm_labeller.py`. Read [gate_rubric.md](./gate_rubric.md) first — it is
the labelling standard, and the model is given it verbatim.

---

### 0. What this is, in one sentence

The publish gate has three hand-set thresholds and no labelled data to justify
them; labelling all 77 analysis-run exports by hand is a multi-day job, so the
owner labels a subsample and a **Claude** model labels the rest, with Cohen's κ
reported between the two on the overlap.

**Every number derived from these labels must be reported as
_LLM-labelled, κ = X against human on a subsample of n_ — never as human labels.**
That is not a formality. The κ is the entire warrant for using the model labels
at all; a figure quoted without it is an unsupported claim.

---

### 1. Why the judge must be a different model family

The critiques being judged were generated by **GPT-5.2**. An OpenAI model
judging GPT-5.2's own output is the **self-preference problem**: LLM judges
systematically prefer text from their own family. Two mechanisms, both bad here:

1. **Stylistic affinity.** A judge rates text that matches its own generation
   distribution as more fluent, better-structured, and more competent. On a
   rubric where D2 (non-specificity) turns on whether a critique reads as
   substantive, that bias points straight at the axis being measured.
2. **Shared blind spots.** A judge cannot flag a failure mode it also has. If
   GPT-5.2 produces plausible-sounding but ungrounded criticism, a GPT judge is
   the least likely reader to notice, because the same prior produced both.

The judge is therefore `claude-sonnet-4-5-20250929` — a different family,
different training data, different failure modes. Cross-family judging does not
eliminate bias; it makes the judge's bias **independent of the generator's**,
which is what lets a disagreement carry information.

This does not make the model labels correct. It makes them a defensible second
rater. κ is what says how defensible.

---

### 2. Why this is not the `judge_openreview` circularity

`judge_openreview` had a structural defect: an LLM verdict could **promote** an
item into the "correct" set. The thing being measured and the thing doing the
measuring were the same object, so precision was incapable of failing — it
could only report how often the judge agreed with itself.

The shape here is different:

| | `judge_openreview` (broken) | This labeller |
|---|---|---|
| What the LLM produces | a verdict that changes the score | the **label** (the ground-truth axis) |
| What is scored | the LLM's own output, partly | a deterministic, hand-set threshold |
| Can the thing under test move the ground truth? | **yes** | **no** |
| Can the metric fail? | no | yes |

The gate's thresholds were fixed before any labelling and are pure arithmetic on
three numbers. The labeller never sees those numbers (§3). The gate therefore
cannot influence its own label, and `sweep.py` can — and does — report that the
gate as shipped catches nothing.

This is ordinary **LLM-as-judge**: an LLM stands in for a human annotator on the
ground-truth axis, and its stand-in quality is quantified by agreement with the
human it replaces. It is a well-worn method with well-known limits (§5), not the
same error.

---

### 3. Blinding

The model sees exactly what the human labeller sees: the output of
`label_cli.render_run` — title, structure, every durable revision task, reviewer
feedback, meta-review. It does **not** see `gate_status`, `publishable`,
`parser_quality_score`, `page_anchor_coverage`, or `verbatim_anchor_coverage`.
A label that has seen the gate's opinion is correlated with the gate by
construction and measures nothing ([gate_rubric.md](./gate_rubric.md) §0).

This is **asserted on the constructed prompt string**, not assumed:
`assert_blind()` runs before every call and before every dry-run count, and
raises rather than proceeding. It checks two channels:

- **Field names** — the snake_case telemetry identifiers, which never occur in
  critique prose.
- **Exact float values** of the hidden scores, but only for reprs with ≥4
  decimal digits. A repr like `0.6923076923076923` cannot occur by coincidence
  and its presence proves a leak. `1.0` and `0.75` occur constantly in ordinary
  run text, so matching on them produces false alarms and nothing else — a check
  that fires on every prompt gets switched off, which is worse than no check.
  For low-entropy values the defence is the field-name channel plus the
  structural fact that `render_run` never reads `rec["_hidden"]` at all.

[gate_rubric.md](./gate_rubric.md) §0 *names* the forbidden fields, as an instruction not to look at
them. That constant text is subtracted before scanning; a test asserts the check
would fire if it were not, so the exemption cannot quietly widen.

#### The model's one disadvantage

The human can open the PDF; the model cannot. Rubric tie-break **T6** ("cannot
verify without opening the PDF ⇒ do not guess, label `unsure`") therefore binds
the model much more often, and the prompt says so explicitly. Expect the model
to use `unsure` more than the human on D1 (fabrication) calls, which are exactly
the calls that need the manuscript. **A low κ driven by `unsure` asymmetry is a
statement about access, not about judgement** — the confusion matrix separates
the two, which is why it is printed even when κ is refused.

---

### 4. How κ is computed

`metrics.cohens_kappa` (already unit-tested in `test_metrics.py`) — not
reimplemented. `(p_o − p_e) / (1 − p_e)`: observed agreement corrected for the
agreement two raters would reach by chance given their marginal rates. Raw
percent agreement is not enough on this data, because ~85% of runs are `ok` —
two raters who both guessed `ok` every time would score ~0.85 percent agreement
and κ = 0.

**`unsure` is excluded from the headline κ.** It is not treated as a third class.
The justification is that `sweep.py` already drops `unsure` from every metric,
so the labels that actually drive the calibration are the degraded/ok ones — and
κ should measure agreement on exactly the labels being used. Folding in a class
that never reaches a metric would move κ for reasons the calibration never
feels. A three-class κ is printed alongside as a **diagnostic**, because it
answers a different and genuinely interesting question — does the model abstain
where the human abstains? — but it is never the headline, and the per-rater
`unsure` counts are printed so the asymmetry from §3 is visible rather than
buried in a single number.

**κ is refused below n = 15 jointly-labelled scoreable runs**, printing
`n/a (n=X < 15)` rather than a number. This matches the discipline throughout
`scripts/eval/` (`sweep.py` withholds AUC-PR below 10 labels and warns below
30). Below that floor κ is dominated by which particular handful of runs
happened to be double-labelled — a value that will swing by 0.3 when two more
labels arrive is not a measurement, and printing it invites someone to quote it.
The confusion matrix and per-class counts are still printed: those counts are
facts about the labels even when κ is not yet meaningful.

#### Reading the number

Landis–Koch (κ > 0.6 "substantial", > 0.8 "almost perfect") is the usual
shorthand and is worth stating so nobody invents their own bar. Three caveats
that matter more than the label:

- **κ is depressed by class imbalance.** With a ~15% positive rate, the chance
  correction `p_e` is large, so a couple of disagreements on the rare class cost
  a lot of κ. A "moderate" κ here is not comparable to a "moderate" κ on a
  balanced task.
- **κ measures agreement, not correctness.** Two raters can agree perfectly and
  both be wrong. If the rubric is mis-specified, high κ certifies that both
  raters applied the same wrong standard consistently.
- **κ is estimated on the overlap only.** It is a claim about the subsample,
  generalised to the rest by assumption. Draw the overlap as a **random** sample
  of the 77 runs, not the first 15 in filename order and not the ones that
  looked interesting — otherwise the assumption is false and the κ transfers
  nowhere.

---

### 5. The standing power problem — a good κ does not fix it

**Say this plainly, because it is the binding constraint on the whole
exercise.** At the observed base rate, roughly **12 degraded runs out of 77**.
That is the sample the entire calibration rests on, and it is **underpowered for
a rare-class estimate however the labels are produced.**

- A 95% confidence interval on recall estimated from ~12 positives is roughly
  ±0.25. That interval is wider than the difference between a threshold that
  works and one that does not.
- Precision at any operating point is estimated from however many runs fire —
  frequently fewer than 12. `sweep.py` already refuses AUC-PR below 10 labels
  for this reason.
- Moving a threshold reclassifies one or two runs. One run is ~8% of the
  positive class. The metric moves; that movement is noise.

**Labelling faster does not add positives.** The LLM labeller removes a *labour*
bottleneck, not a *statistical* one. Even at κ = 0.9 on a large overlap, the
downstream estimate is still built on ~12 positives and is still too noisy to
justify changing a production threshold. What a good κ buys is the right to use
model labels *in place of* human ones — nothing more.

The only real fixes are more degraded runs (adversarial/degraded-input
generation, or more corpus papers) or a metric that does not need many
positives. Neither is in scope here, and neither is what this labeller does.

---

### 6. Honest limitations

- **Single judge, single sample.** One model, one prompt, temperature not
  pinned. No self-consistency across repeated samples, so run-to-run variance in
  the model's own labels is unmeasured. The prompt is cached by content hash, so
  a re-run reproduces the *stored* answer, not a fresh draw — reproducibility of
  the artifact, not of the judgement.
- **Position and length effects.** LLM judges are known to be sensitive to
  ordering and to output length. Runs with more tasks give the model more text;
  whether that biases toward `ok` is not tested here.
- **The model cannot open the PDF** (§3). D1 is systematically harder for it.
- **Prompt version is a confound.** `PROMPT_VERSION` is recorded on every label
  and is part of the cache key precisely so labels from different prompts are
  never silently pooled. If the prompt changes, do not compute κ across the
  boundary.
- **`sweep.py` does not distinguish rater type.** It joins on `run_id` and reads
  `label`, so model labels flow into the calibration as ground truth. Every
  record carries `labeller_type: "llm"`, `labeller: "llm:<model>"`, `model`, and
  `prompt_sha256`, so the provenance is on disk and recoverable — but sweep's
  own header still says "vs human label". Fixing that wording, and having sweep
  report the human/LLM split, is an open follow-up.

---

### 7. Procedure

1. Owner labels ~20 runs with `label_cli.py`, drawn at random (§4).
2. `python3 llm_labeller.py --dry-run` — confirm call count and cost estimate.
3. `python3 llm_labeller.py` — labels every unlabelled run. Live calls are
   guarded by `check_llm_allowed()` and bounded by `--max-calls`; every call is
   recorded via `record_usage()` under the label `gate_label`, so its spend is
   separable from every other lane. Results are content-hash cached, so a re-run
   is free and idempotent.
4. Owner **relabels a random ~15–20 of the model-labelled runs** with
   `label_cli.py --relabel` to build the overlap. Do this without reading the
   model's note first; a note seen before judging is the same contamination the
   blinding exists to prevent.
5. `python3 llm_labeller.py --agreement` — κ, confusion matrix, per-class
   agreement.
6. Report downstream numbers as *LLM-labelled, κ = X on n = Y*, with §5's power
   caveat attached. Not one without the other.
