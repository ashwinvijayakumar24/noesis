# The PDF parsed twice — fixed behind a flag, and measured

Measured 2026-08-01. The defect is the one `scripts/eval/E2E_LATENCY.md`
reported and did not fix: `POST /drafts/upload` parses the whole PDF inside
`validate_file_format`, uses the result for one length check, throws it away,
and `ingest_draft` then re-downloads the file and parses it again.

Tool: `scripts/eval/e2e_latency.py`, unmodified. Tests:
`services/backend/tests/test_double_parse.py` (28).

---

## Read this before quoting any number below

**1. `n = 4` per arm, 8 measured runs total.** No p90/p95/p99 appears here and
the harness refuses to compute one at this `n` — `trace_report.metrics` is the
same code the graph-level harness uses. Every `p50` below is that module's
nearest-rank p50, the same convention `E2E_LATENCY.md` used.

**2. The user-visible total moved by less than the noise, and the two summary
statistics disagree in sign.** p50 −6.49 s, mean +1.10 s. **The headline effect
of this change is not resolvable at n=4 on this host, and this document does not
claim one.** What *is* resolvable, by a factor of ~17 in standard deviations, is
the stage the parse lived in: `upload_request` 4.33 s → 0.05 s p50.

**3. The environment on 2026-08-01 is not the environment the n=7 baseline was
taken in, and the difference is enormous.** Under the identical config hash
`670fccc87731`, same fixture, same parser, same flags:

| | baseline, 2026-07-31/08-01 (n=7) | here, 2026-08-01 06:14–06:33 UTC (arm A, n=4) |
|---|---|---|
| user-visible p50 | 212.82 s | **117.87 s** |
| both parses, per run, p50 | 68.66 s | **8.36 s** |
| parse #1 p50 | 52.38 s | **4.28 s** |
| graph p50 | 112.51 s | 94.75 s |
| parsing as a share of the mean path | 39.2% | **7.4%** |

Nothing in this repository changed to cause that. Docling was resident during
part of the baseline sessions and GROBID was being OOM-killed and timing out
(baseline §Variables 4); today GROBID is the only parser running and it is warm.
**Parsing on this host is bimodal by an order of magnitude, and the size of this
fix is exactly the cost of one parse.** In the environment the double-parse
finding was discovered in, one parse was 52 s. Today it is 4 s.

**4. Local Supabase only.** Production was never contacted; `assert_local_only`
has no override.

---

## The approach, and what was given up

Two candidates were on the table. **(b) was chosen: validation stops doing a
full parse.**

| | (a) cache and reuse | **(b) cheap validation — chosen** |
|---|---|---|
| what it removes | parse #2, in `ingest` | parse #1, in `upload_request` |
| baseline estimate | 179.81 s p50 | 160.41 s p50 |
| touches `ingest_draft` | yes | **no** |
| can the two arms produce different analysis? | yes, in principle | **no, structurally** |

### Why (b), against the brief's framing

The brief called (a) safer and (b) riskier. On this codebase that is backwards
for the correctness question and right for the gate question, and the two should
be separated.

**(a) cannot be done in-process at all.** `validate_file_format` runs in the
FastAPI web process; `ingest_draft` runs in the Celery worker
(`analyze_draft_task.delay`, `routes/drafts.py`). A returned artifact or an
in-memory LRU cache does not cross that boundary. Making (a) real means putting
a ~33 k-character parse artifact into Redis or Storage keyed by content hash,
which is new cross-process state, a new serialization surface, a new eviction
policy, and a new failure mode. Worse, **it would have measured as a win in this
harness and not in production**, because the harness calls the task body inline
— an in-process cache would have shown a 4 s saving that no user would ever get.

**(b) leaves `ingest_draft` byte-for-byte unmodified.** The parse whose output
reaches structure, anchors, the graph and the user is the *same call in both
arms*. Equivalence is therefore structural, not a property that has to be
re-proved after every future edit.

### What was given up

**Validation no longer answers "will GROBID parse this document". It answers
"is this an openable PDF with at least 50 characters of extractable text".**
Those are not the same question, and the cheap gate is strictly the weaker of
the two. The rest of this section is the evidence for how much weaker.

Also given up: nothing was done about parse #2. (a) and (b) are not exclusive —
a future change could still eliminate the remaining parse — but stacking them
was out of scope and would have confounded this measurement.

---

## Does the cheap gate reject everything the full gate rejected? Almost.

24 inputs: **18 real manuscripts** (`scripts/eval/openreview/`) and **6
adversarial synthetics**. Each run through `validate_file_format` twice, flag
off and flag on, against a live GROBID.

| | cases | agreements | disagreements |
|---|---|---|---|
| real manuscripts | 18 | 18 | 0 |
| adversarial synthetics | 6 | 5 | **1** |
| **total** | **24** | **23** | **1** |

The five synthetics both gates reject identically: not-a-PDF-at-all, a truncated
PDF header, a blank one-page PDF, a blank three-page PDF, and a PDF containing 3
characters.

### The one disagreement, and it is the one the code predicts

`pdf_with_200_chars` — a synthetic page containing `"A" * 200` and nothing else.

```
GROBID full_text            -> ''            (GROBID succeeds, returns nothing)
PyMuPDF via probe_pdf_text  -> 72 chars
full gate  -> valid=False, error_type='file_empty'
cheap gate -> valid=True
```

The cause is in `extract_text_from_pdf`: when GROBID **succeeds** and returns
empty text it raises `FileEmptyError` directly and **does not** fall through to
the PyMuPDF fallback. So any document PyMuPDF can read but GROBID renders empty
is rejected at upload by the full gate and accepted at upload by the cheap one.

**This is a real weakening, and it is bounded.** Such a file is not then
analysed anyway: `ingest_draft` calls the same `extract_text` and raises the same
`FileEmptyError`, so the draft fails there instead. What moves is *where the user
learns*: a 400 at upload time becomes a failed draft a few seconds later. No such
file exists among the 18 real manuscripts. The divergence is pinned by
`test_known_divergence_grobid_empty_but_pymupdf_has_text` so that it cannot
change silently in either direction.

Gate cost on that same corpus, standalone and uncontended — **not comparable to
the harness stage numbers above, and reported only as a ratio**:

| gate | n | p50 | mean | min | max |
|---|---|---|---|---|---|
| full parse | 18 | 6.23 s | 6.65 s | 3.15 s | 11.66 s |
| cheap probe | 18 | **0.010 s** | 0.012 s | 0.005 s | 0.034 s |

---

## The flag

`DRAFT_VALIDATION_CHEAP_PARSE`, **default off**, read per call in
`draft_processing.cheap_validation_enabled()` — the same shape as
`KEYWORD_SEARCH_V2` and `CHUNK_CEILING_GEOMETRY`. Off is the behaviour
`E2E_LATENCY.md` measured, so the default arm remains the arm with a published
number behind it. It affects **PDFs only**; DOCX and TXT extraction is already
local and was never the cost, and is untouched.

One production call site exists (`routes/drafts.py:546`) and it did not need to
change: the flag is read inside `validate_file_format`. **`routes/drafts.py` was
not modified at all.**

---

## Both arms, measured

Interleaved in blocks of two — `E2E_LATENCY.md` §Variables 2 records two sessions
90 minutes apart at an identical config hash giving p50 141.03 s and 219.59 s, so
running one arm entirely before the other would let that drift masquerade as the
effect. Order: A, B, A, B. Config hash `670fccc87731` on all four blocks; one
warmup discarded per arm; `PDF_PARSER=grobid`; residual accounting gap 0.0 on
every run.

| stage | arm | n | p50 | mean | sd | CV | min | max |
|---|---|---|---|---|---|---|---|---|
| `upload_request` | **A** | 4 | **4.33** | 4.46 | 0.25 | 5.5% | 4.19 | 4.74 |
| `upload_request` | **B** | 4 | **0.05** | 0.05 | 0.01 | 28.3% | 0.03 | 0.07 |
| `ingest` | A | 4 | 18.37 | 19.64 | 1.61 | 8.2% | 18.13 | 21.14 |
| `ingest` | B | 4 | 17.53 | 17.77 | 1.67 | 9.4% | 15.62 | 19.63 |
| `graph` | A | 4 | 94.75 | 98.57 | 7.34 | 7.4% | 91.39 | 108.26 |
| `graph` | B | 4 | 93.02 | 105.94 | 27.33 | 25.8% | 81.76 | 144.50 |
| `task_tail` | A / B | 4 | 0.01 / 0.01 | | | | | |
| `first_read` | A / B | 4 | 0.01 / 0.01 | | | | | |
| **user-visible** | **A** | 4 | **117.87** | 122.68 | 8.64 | 7.0% | 113.86 | 133.39 |
| **user-visible** | **B** | 4 | **111.38** | 123.78 | 27.79 | 22.4% | 97.43 | 162.09 |

PDF parsing, the thing that actually changed:

| | arm | n | p50 | mean | sd |
|---|---|---|---|---|---|
| parse calls per run | A | 4 | **2** (every run) | | |
| parse calls per run | B | 4 | **1** (every run) | | |
| parse #1, in `upload_request` | A | 4 | 4.28 | 4.40 | |
| parse #2, in `ingest` | A | 4 | 4.08 | 4.74 | |
| the only parse, in `ingest` | B | 4 | 4.25 | 4.49 | 0.57 |
| all parsing per run | A | 4 | **8.36** | 9.13 | 1.17 |
| all parsing per run | B | 4 | **4.25** | 4.49 | 0.57 |

Per-run user-visible seconds, in the order they ran:

- A: 113.86, 117.87, 125.59, 133.39
- B: 124.21, 162.09, 111.38, 97.43

### The delta, and why only one row of it is real

| | A | B | delta |
|---|---|---|---|
| `upload_request` p50 | 4.33 s | 0.05 s | **−4.28 s, −98.8%** |
| parse seconds per run, p50 | 8.36 s | 4.25 s | **−4.11 s, −49.2%** |
| user-visible p50 | 117.87 s | 111.38 s | −6.49 s, −5.5% |
| user-visible mean | 122.68 s | 123.78 s | **+1.10 s, +0.9%** |

The first two rows are the change, measured directly, at a spread of 0.25 s and
0.01 s. They are not in dispute.

The last two are not resolvable and disagree in sign. The reason is in the table
above: **the `graph` stage, which this change does not touch at all, differs by
+7.37 s in mean between the two arms** (98.57 → 105.94) and its sd in arm B is
27.33 s. A stage nobody edited moved by more than the entire effect. At n=4 with
that noise floor, a 4.3 s saving cannot be read out of a 120 s total, and no
amount of presentation makes it readable. It is recovered arithmetically —
117.87 − 4.28 = 113.59 against a measured 111.38 — and that is consistent, not a
confirmation.

### How the estimates held up

`E2E_LATENCY.md` offered two counterfactuals, both explicitly labelled estimates:
**179.81 s** (cache and reuse) and **160.41 s** (stop parsing in validation, i.e.
arm B).

**The 160.41 s estimate could not be tested, because its premise did not hold on
the day the test was run.** It is `212.82 − 52.41`, and the 52.41 s came from a
parse #1 that cost 52.38 s p50. Today parse #1 cost **4.28 s p50**. The estimate
is not refuted — it is inapplicable; today's baseline was 117.87 s, not 212.82 s.

The estimate's own three stated assumptions can each be graded:

1. *removing a parse removes exactly its measured wall time* — **held.**
   `upload_request` fell from 4.33 s to 0.05 s, which is parse #1 (4.28 s) plus
   the ~0.05 s of validation and route work that was always there.
2. *the surviving parse costs what it cost when it ran second* — **held.** Arm
   A's parse #2 p50 4.08 s, arm B's only parse p50 4.25 s, within a 0.57 s sd.
3. *nothing downstream depends on the parse happening twice* — **held, and now
   tested rather than assumed.** See the equivalence section.

The honest restatement is a rule, not a number: **this change removes exactly one
PDF parse from the user-visible path. Its value equals the cost of one parse on
the host, which on this machine has been measured at both 4.3 s and 52.4 s under
the same config hash.** On the baseline day it would have been worth ~25% of the
path. Today it is worth ~3.6%.

---

## Equivalence: what the two arms produced

**"Equivalent" here means: the parse artifact persisted for the draft is
identical under a byte-level hash.** Specifically, for each of the 8 drafts the
measured runs created, read back from the local database:

- `sha256` of the canonical JSON of `section_map`
- the section titles, in order
- `grobid_references_count`
- the number of anchors in `anchor_map`
- `sha256` of the anchor id list, in order

Result, all 8 drafts (4 arm A, 4 arm B):

| | value |
|---|---|
| distinct fingerprints in arm A | **1** |
| distinct fingerprints in arm B | **1** |
| arm A set == arm B set | **True** |
| sections in `section_map` | 14 (the 13 GROBID body sections + the abstract) |
| references | 33 |
| anchors | 49 |
| `section_map` sha256 | `529123b64b98…` |
| anchor-id sha256 | `9de979b94e58…` |
| parser recorded | `grobid` |

The harness's own per-parse record agrees independently: the ingest-side parse
returned **32,999 chars / 13 body sections / 33 references in all 8 runs across
both arms**, and all 8 runs reached `status='analyzed'`.

This is a strong result but it is one fixture. The structural argument is what
carries it: `ingest_draft` is not modified by either arm, so there is no path by
which the flag can change what is parsed, ingested or anchored. The unit test
`test_ingest_parse_is_untouched_by_the_flag` asserts the same fingerprint
definition under both parser regimes the baseline observed (GROBID up, GROBID
down → PyMuPDF), with GROBID stubbed deterministic so the assertion is about the
flag rather than GROBID's variance.

---

## Cost

| | |
|---|---|
| arm A | $1.0199, 65 LLM calls |
| arm B | $0.9754, 65 LLM calls |
| **total actual spend** | **$1.9953** of a **$3.00** ceiling |
| unpriced calls | 0 |
| per-invocation ceilings | `NOESIS_LLM_MAX_SPEND_USD` 0.80 / 0.80 / 0.55 / 0.55 — none tripped |
| corpus gate comparison | $0.0000 — no LLM calls |

LLM calls were identical between arms (65 = 5 runs × 13), which is itself a check:
this change is upstream of every model call and must not alter their number.

Standing project caveat applies unchanged: **every cost figure in this project is
a lower bound**, because `match.py` bypassed the spend guardrails.

---

## What is still unmeasured, and what contradicts the brief

- **Whether the fix is worth 25% or 3.6%.** Both are measured facts about this
  host on different days. Which one production resembles is unknown; every parse
  number in this repo is emulated x86 under QEMU.
- **A resolvable user-visible delta.** It needs either a host where one parse
  costs what it cost on 2026-07-31, or an `n` large enough to see 4 s through a
  27 s graph sd. Neither was in budget.
- **Parse #2.** Still there, still ~4 s, still re-downloading the file from
  Storage first. Option (a) would remove it, at the cost of cross-process state.
- **DOCX and TXT.** Deliberately untouched; their extraction is local. Not
  measured here either.
- **The config hash does not cover this flag.** `e2e_latency.py::config_hash`
  covers the fixture, parser, LLM mode and skip flags — all four blocks hashed to
  `670fccc87731` regardless of arm. That is why the arms were written to separate
  result files rather than into `results/e2e_latency.jsonl`, where they would
  have been indistinguishable from the baseline's seven runs and from each other.
  The harness was not modified to fix this.
- **Contradicting the brief:** the brief's premise that "(a) is safer, (b) is
  riskier" does not survive contact with the process boundary. (a) is the one
  that threads state across processes and the one whose correctness would need
  re-proving; (b)'s risk is confined to gate strength, which is a testable
  property and was tested. The brief also anticipated needing to edit
  `routes/drafts.py:546` — it did not.

---

## Reproducing

```bash
cd services/backend && python3 -m pytest tests/test_double_parse.py -q   # 28

cd scripts/eval
python3 e2e_latency.py --dry-run
python3 e2e_latency.py --bootstrap

# arm A -- current behaviour, the PDF parsed twice
python3 e2e_latency.py --n 2 --warmup 1 --parser grobid --yes \
    --max-spend 0.80 --max-calls 60 --results /tmp/dp_arm_A.jsonl

# arm B -- one parse
DRAFT_VALIDATION_CHEAP_PARSE=1 python3 e2e_latency.py --n 2 --warmup 1 \
    --parser grobid --yes --max-spend 0.80 --max-calls 60 \
    --results /tmp/dp_arm_B.jsonl

# alternate the two, do not run one arm then the other
```
