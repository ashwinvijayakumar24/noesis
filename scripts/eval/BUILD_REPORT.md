# Corpus build report — 15-topic OpenReview retrieval corpus

Built `2026-07-30` with `scripts/eval/build_corpus.py --openreview-all --max-papers 0`
against an authenticated OpenAlex key. Exit code 0. No ingestion was run and no
database was written.

## Budget

| | Before | After |
|---|---|---|
| Auth state | authenticated | authenticated |
| Daily allowance remaining | **$0.9999** of $1.00 | **$0.6479** of $1.00 |
| Prepaid balance | $0.0000 | $0.0000 |
| Spendable | $0.9999 (~999 title searches) | $0.6479 (~647 title searches) |

**Actual spend: $0.3520.** That is the measured difference in the daily
allowance, not an estimate. `OPENALEX.md` predicted ~$0.38 (worst case ~$0.43);
the run came in ~8% under the prediction.

**Requests: ~464 estimated, actual count not instrumented.** The script prints a
per-paper estimate before each corpus (summing to 464 requests / $0.382) but does
not report a realised request count, so the honest figure here is the estimate
plus the measured dollar spend. Five requests returned 5xx (`OpenAlex 504` once,
`OpenAlex 500` four times, all on `qBL04XXex6`); the script backed off
exponentially and all five recovered. Retried requests are additional to the 464.

Budget was never exhausted. **Zero references are in `pending` state anywhere in
the corpus** — every reference reached a terminal status.

## Per-paper results

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

### What the non-resolved statuses mean

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

## Corpus-wide resolution rate

**333 / 544 = 61.2%.**

The denominator is 544, the sum of `references_attempted` across all 15 sidecars.
This is verifiable and not `resolved/resolved`: every reference OpenAlex was asked
about is present in a `references.json` with its own terminal status, the entry
count of each sidecar equals its `references_attempted`, and the four status
buckets sum exactly to 544 (333 + 78 + 81 + 52 = 544). The number of `.pdf` files
on disk equals `resolved` in every one of the 15 directories.

## 15 topics versus the previous 4

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

## Caveat: the denominator is references *as segmented by the parser*

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

## Verification performed

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
