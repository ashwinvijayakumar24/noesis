# How much of the 94% miss is actually missable

Both the Noesis DAG and the reviewer agent score around 10% of 212 review units.
The owner wants 50–75%. Before anyone spends a quarter trying to close that gap,
this file separates the miss into the part worth engineering against and the
part that is not.

## The verdict, first

**Of 212 units, 76 are defect-addressable (n=212, every unit hand-labelled).
Pooled over every recorded run, the two systems together find 35 of those 76 at
a calibrated threshold — 19 at the deployed one. The realistic ceiling for an
automated reviewer on this corpus is 35.8% of all units; 45.8% if the system is
given literature retrieval. Current true recall against the addressable subset
is 46.1% for the two systems pooled and 35.5% for the DAG alone (n=76).**

So:

- **50–75% of all 212 units is arithmetically impossible.** The addressable
  population is 35.8%. Even crediting surface copyedits *and* literature
  retrieval, the absolute upper bound is 120/212 = 56.6%, and that requires a
  system that reports missing commas and reads the cited literature. The target
  has to be restated against the addressable subset.
- **Restated against the addressable subset, 50–75% is reachable, and the DAG
  is already at 35.5% of it.** The gap from 35.5% to 50% is smaller than the
  gap the matcher alone accounts for.
- **The single largest lever is not the pipeline. It is the matcher.** At the
  deployed `COS_THRESHOLD = 0.55` the prefilter's estimated recall is **0.20**
  (n=146 hand-labelled pairs). Four in five true matches never reach the
  confirmation judge. Moving to a calibrated 0.45 takes the DAG from 31 matched
  units to 56 with **no change to the pipeline at all**.

---

## 1. What was measured

| | |
|---|---|
| Label units | **212**, rebuilt from Noesis's OpenReview gold + warm `cache/atomize`. 79 / 72 / 61, total severity weight **85.4** — identical to `HEADTOHEAD.md` §1 |
| Hand taxonomy labels | **212 of 212**, `hand_labels.json`. Not a sample |
| Hand pair labels | **146**, `pair_labels.json`, stratified over 8 cosine bins, seed `20260801` |
| Finding corpus | **201** (153 DAG, 48 agent), `corpus.py` |
| Matcher | Noesis's own `scripts/eval/match.py`, unmodified, `match_v1`, `text-embedding-3-small` + `gpt-5.2` confirmation |
| Sinks | `ceiling.jsonl` (append-only, config-hash keyed), `sweep.json`, `pair_labels.json`, `hand_labels.json` |
| Supabase | not contacted. Nothing here needs a database |
| Spend | **$1.41** against a $6.00 ceiling (§7) |

### The finding corpus is re-derived, and that is itself a finding

`eval/results/headtohead.jsonl` records metrics, cost, and config hashes. It
does **not** record the finding texts, and the optional `--detail-path` dump was
not written on the recorded run. Probing every candidate text against
`match._embedding_cache_key` and the head-to-head embedding cache recovers
**0 of the agent's 56** and **2 of the DAG's 99** findings.

The matcher decisions behind the published 0.0815 and 0.0098 therefore cannot be
audited from what is committed. This study rebuilds a corpus of the same two
systems' output on the same three manuscripts — the DAG's canonical revision
tasks and coverage gaps from Noesis's own eval exports, and the agent's findings
from `eval/results/matched.trace.jsonl`. It pools **every** recorded run, which
makes the "found" set a best case: the union over replicates, not one run. For a
ceiling question that is the right direction to err.

**Recommendation (not made, as instructed):** `run_headtohead.py` should write
its `--detail-path` dump unconditionally. A metrics-only sink cannot be
re-scored, and this study had to reconstruct 201 findings to ask a question the
sink should have already answered.

---

## 2. The taxonomy

Eight categories, one per unit, assigned under a fixed precedence with
`defect_addressable` as the **residual** — a unit lands there only if nothing
else claims it, so the ceiling is a lower bound. Full definitions and the
precedence rationale are in `taxonomy.py`.

Two departures from the brief's starting point, both because the descriptive
version would have produced a misleading number:

**`surface_copyedit` split out of `defect_addressable` (n=23).** "page 4:
'avenger' → 'average'", "Comma missing after Equation 7", "Larger title lave on
Figure 6". These *are* findable by reading, so calling them unaddressable would
understate the ceiling — but a pre-submission reviewer whose recall is carried
by missing commas is not the product. They get their own line and the ceiling is
reported both ways.

**`generic_non_defect` added (n=3).** "This complexity might make it challenging
for practitioners who are not well-versed in all of these areas." Names no flaw,
asks for nothing. Not a request, not a defect, not context-dependent. Small
enough that it barely moves the arithmetic, large enough that folding it into
either neighbour would be a lie about what it is.

### Counts

| category | n | share | severity weight | share of 85.4 |
|---|---:|---:|---:|---:|
| **defect_addressable** | **76** | **35.8%** | **31.32** | **36.7%** |
| request_not_defect | 34 | 16.0% | 11.71 | 13.7% |
| needs_expertise | 27 | 12.7% | 10.24 | 12.0% |
| context_dependent | 27 | 12.7% | 12.09 | 14.2% |
| surface_copyedit | 23 | 10.8% | 9.96 | 11.7% |
| needs_literature | 21 | 9.9% | 9.36 | 11.0% |
| generic_non_defect | 3 | 1.4% | 0.48 | 0.6% |
| meta_venue | 1 | 0.5% | 0.24 | 0.3% |
| **total** | **212** | | **85.4** | |

Orthogonal flag: **7 units** (3.3%) depend on a figure, a rendered table, or page
layout — content GROBID text extraction does not carry. Both systems read GROBID
output, so those are out of reach on modality grounds whatever their category.

### The segmentation manufactures 27 of the misses

`atomize_reviews_v1` is asked to split reviewer prose into "atomic,
independently-verifiable concerns". It splits mid-argument. **27 units (12.7% of
the corpus, 14.2% of the severity weight) are fragments that cannot be
understood standing alone**, and nothing a reviewer system emits can or should
match them:

> `cXs5md5wAq::anon2::06` — "This will add more strength to the paper."
> `cXs5md5wAq::anon2::15` — "The authors should square these two facts."
> `10eQ4Cfh8p::anon4::17` — "There should be more that you need to find out for fixing."
> `10eQ4Cfh8p::anon3::08` — "This paper has significant defects with clarity."

The sharpest case is `cXs5md5wAq::anon2::23`, which is a **verbatim quote of the
manuscript** with no critique attached; the reviewer's actual concern lives in
the two units after it. A finding that correctly rebuts that concern (agent-032,
"MLPs can be made permutation-invariant with appropriate design") sits at cosine
0.682 against the quote and is scored as no-match, correctly, because the quote
asserts nothing. The segmentation destroyed a genuine hit.

This is a **denominator defect**. Every recall figure in `HEADTOHEAD.md` is
divided by 212 when 27 of those are unmatchable by construction.

---

## 3. The matcher calibration `match.py:65-66` specified and never got

The comment on `COS_THRESHOLD`:

> `# Initial value chosen before hand-label calibration. Phase-2 calibration target: 30 labeled pairs with agreement >=0.85; update this comment with precision/recall.`

Run here at n=146 rather than 30, stratified across 8 cosine bins over the full
14,488-pair within-manuscript matrix, seed `20260801`, reproducible at $0 for the
sweep itself.

### Precision / recall against the hand labels

Estimates are population-weighted: each labelled pair stands for
`bin_population / bin_drawn` pairs of the matrix, because the top bin is
oversampled by three orders of magnitude.

| threshold | precision | recall | F1 | est. candidate pairs |
|---:|---:|---:|---:|---:|
| 0.30 | 0.045 | 1.000 | 0.085 | 6728 |
| 0.35 | 0.071 | 1.000 | 0.133 | 4199 |
| 0.40 | 0.141 | 1.000 | 0.247 | 2129 |
| 0.42 | 0.176 | 1.000 | 0.299 | 1703 |
| **0.44** | **0.221** | **0.822** | **0.348** | **1117** |
| 0.45 | 0.232 | 0.822 | 0.361 | 1064 |
| 0.48 | 0.253 | 0.534 | 0.343 | 632 |
| 0.50 | 0.210 | 0.342 | 0.260 | 488 |
| **0.55 (deployed)** | **0.291** | **0.200** | **0.237** | **206** |
| 0.60 | 0.441 | 0.115 | 0.182 | 78 |
| 0.65 | 0.410 | 0.043 | 0.077 | 31 |
| 0.70 | 0.333 | 0.007 | 0.013 | 6 |

Estimated true matches in the whole matrix: **~300 of 14,488**. Zero of the 40
labelled pairs below cosine 0.40 were matches, which is what makes the
recall = 1.00 rows credible.

### The operating point, and the asymmetry that picks it

**Chosen: 0.44–0.45.** The rule is in `choose_operating_point`: the *lowest*
threshold whose estimated candidate volume stays inside a confirmation budget of
6 candidates per finding, not the highest F1.

The asymmetry: **this is a prefilter for a downstream judge, not a decision.** A
false negative here is unrecoverable — the pair is never shown to the confirmer
and the unit is scored as missed forever, and it silently deflates the one metric
the whole comparison turns on. A false positive costs one extra line in a batched
20-pair confirmation call, about $0.0002. Recall is worth roughly three orders of
magnitude more than precision, so maximising F1 — which would pick 0.45 anyway,
and 0.60 if you squint at precision — is the wrong objective for the wrong
reason. 0.55 is not defensible on any reading of the curve: it is worse than
0.60 on precision *and* worse than 0.45 on recall.

**Caveat with its `n`.** The `[0.40, 0.45)` bin holds 1065 pairs and contributed
**1** positive out of 20 labelled. That single label carries an estimated weight
of 53 positives, ~18% of all estimated true matches, and it is the entire reason
recall falls from 1.00 to 0.82 across 0.42→0.44. The shape of the curve is solid;
the exact recall figure in that band is not. Anyone re-running this should label
that bin more densely first.

### Cohen's κ against the `gpt-5.2` confirmation judge

| | value | n |
|---|---:|---:|
| κ, all labelled pairs | **0.673** | 146 |
| κ, pairs above 0.55 only | **0.618** | 46 |
| judge precision vs hand labels | 0.679 | 28 judge-positives |
| judge recall vs hand labels | 0.792 | 24 hand-positives |

Substantial agreement. Two things follow. First, the hand labels are not
idiosyncratic — an independent judge applying the same written contract lands in
the same place two times in three above chance. Second, and more useful: **the
confirmation judge is not the bottleneck.** It recovers 79% of true matches it is
shown. The losses are upstream, in a prefilter that shows it 20% of them.

One caveat on reproducibility: re-running the 0.45 scoring after clearing 20
confirmation cache entries produced **56 → 57** matched DAG units. Same config
hash, `temperature=0`, different answer. Both rows are in `ceiling.jsonl`. Unit
counts from this pipeline carry ±1.

---

## 4. How many "misses" are matcher artefacts

Running the real matcher over the full corpus at both thresholds
(`ceiling.jsonl`):

| | 0.55 (deployed) | 0.45 (calibrated) | recovered |
|---|---:|---:|---:|
| DAG units matched | 31 / 212 | 56 / 212 | **+25** |
| agent units matched | 12 / 212 | 23 / 212 | **+11** |
| union | 41 / 212 | 72 / 212 | **+31** |
| union, severity-weighted | 0.207 | 0.362 | |

**Of the DAG's 181 "missed" units at the deployed threshold, 25 (13.8%) are pure
matcher false negatives** — the DAG said it, the prefilter never showed it to the
judge. For the union: 31 of 171 missed units, 18.1%. And the calibration says
even 0.45 still loses ~18% of true matches, so these are lower bounds.

This independently reproduces the direction of `HEADTOHEAD.md` §5 (DAG 21→60,
agent 2→11 on the head-to-head's own corpus) on a corpus built from different
artefacts, which is worth something given that §5's numbers cannot be re-derived
from anything committed.

---

## 5. The ceiling, and both systems against it

At the calibrated 0.45, pooled over every recorded run:

| denominator | n | DAG | agent | union |
|---|---:|---:|---:|---:|
| all units (the number quoted today) | 212 | 0.264 | 0.109 | 0.340 |
| all units, severity-weighted | 212 | 0.285 | 0.105 | 0.362 |
| **defect_addressable** | **76** | **0.355** | **0.158** | **0.461** |
| defect_addressable, severity-weighted | 76 | 0.382 | 0.146 | 0.484 |
| + needs_literature | 97 | 0.381 | 0.134 | 0.464 |
| + surface_copyedit | 99 | 0.273 | 0.172 | 0.404 |

At the deployed 0.55, for comparison: DAG 0.184 and union 0.250 against the
76-unit denominator.

Where the matched units actually land (union, 0.45, n=72 matched):

| category | matched | of | rate |
|---|---:|---:|---:|
| defect_addressable | 35 | 76 | 0.461 |
| needs_literature | 10 | 21 | 0.476 |
| needs_expertise | 9 | 27 | 0.333 |
| context_dependent | 7 | 27 | 0.259 |
| request_not_defect | 6 | 34 | 0.176 |
| surface_copyedit | 5 | 23 | 0.217 |
| generic_non_defect / meta_venue | 0 | 4 | 0.000 |

Two readings worth having. The DAG matches **zero** surface copyedits at either
threshold while the agent matches 5 — the agent quotes short verbatim spans and
the DAG emits 643-character prose, and typo-level units only match short text.
And 7 of the union's 72 credits are against `context_dependent` fragments, i.e.
**~10% of the credited matches are the matcher rewarding topical proximity to
text that asserts nothing.** The real recall is slightly lower than the table
says, in the same direction the denominator defect inflates it.

### The deliverable sentence

> Of 212 units, **76** are defect-addressable (n=212, fully hand-labelled). Both
> systems pooled currently find **35** of those (n=76) at a calibrated
> threshold, 19 at the deployed one. The realistic ceiling for an automated
> reviewer on this corpus is **35.8%** of all units — 45.8% with literature
> retrieval, 56.6% as an absolute upper bound if surface copyedits are also
> counted — and the current true recall against the addressable subset is
> **46.1%** pooled, **35.5%** for the DAG alone.

> ↻ **Updated 2026-08-01 — the operating point adopted was 0.44, not this file's
> 0.45, and the sentence moves with it.** Nothing above is retracted; 0.45 was
> re-measured at n=266 and survived (`CALIBRATION.md`). At 0.44, on this same
> corpus and these same labels (`ceiling.jsonl` config hash `06723c2f759c246a`,
> fully cache-reproduced):
>
> > Of 212 units, **76** are addressable. At a calibrated threshold the DAG
> > matches **29 ± 3** and the agent **12 ± 2**, i.e. **38%** and **16%** of the
> > addressable subset — up from **18%** and **8%** under an uncalibrated
> > threshold that was never validated. **The pipeline did not change.**
>
> Against all 212: DAG **61 ± 7 (28.8%)**, agent **24 ± 3 (11.3%)**, union
> **77 ± 8 (36.3%)**; the union reaches **37 ± 4 (48.7%)** of the 76. The bands
> are `ceil(10%)` of the count and come from judge run-to-run variance, not
> sampling error — §3's ±1 caveat was an underestimate, and `CALIBRATION.md` §6
> replaces it with κ(judge, judge) = 0.75–0.85.
>
> The union at 48.7% of the addressable subset puts §6's "realistic target,
> 50–60% of the 76-unit subset" within about two units of already being met by
> the two systems pooled — which says more about how weak that target was than
> about the systems. The DAG alone, at 38.2%, is the number that matters.

---

## 6. Is 50–75% reachable? Directly.

**Against all 212 units: no. It is arithmetically impossible.** 35.8% of the
corpus is defect-addressable. 12.7% is unmatchable fragments the labeller
manufactured, 12.7% needs domain expertise the manuscript does not contain, 16.0%
are requests with no flaw attached, and 9.9% needs literature the system never
reads. A target of 50% of all units requires crediting the system for "This will
add more strength to the paper." Any roadmap written against that number cannot
succeed, and would spend a quarter proving it.

**Against the addressable subset: yes, and the first 15 points are cheap.** The
DAG is at 35.5% of it today. What would have to be true:

1. **Recalibrate `COS_THRESHOLD` to 0.44–0.45.** Worth +25 DAG units on this
   corpus, zero pipeline change, one line. This is the whole difference between
   the DAG being reported at 8% and at 28% of all units. The number was never
   calibrated and the comment in the source says so.
2. **Fix the denominator.** Either drop `context_dependent` units from the score
   or re-run atomisation with a segmentation contract that forbids emitting
   fragments whose referent is another unit. 27 of 212 units currently guarantee
   a miss. This changes no system's behaviour and moves every published recall
   number, which is exactly why it should be done before any of them are quoted
   again.
3. **Give the reviewer literature retrieval.** `needs_literature` is 21 units and
   the union already reaches 10 of them accidentally, by criticising positioning
   from the manuscript's own related-work section. It is the one non-addressable
   bucket with a plausible architecture behind it.
4. **Accept `needs_expertise` (27) and `request_not_defect` (34) as out of
   scope,** or stop counting them. Together they are 28.8% of the corpus and no
   prompt change reaches them.

Realistic target to write down: **50–60% of the 76-unit addressable subset**,
which is 38–46 units, which is 18–22% of all 212. If a roadmap needs a number
against all 212, that is the number — and it should be published next to the
denominator it uses, because "22%" and "60%" here describe the same system.

---

## 7. Spend

| item | |
|---|---|
| Embeddings | 181 new texts (232 recovered from existing caches), `text-embedding-3-small` |
| Confirmations | 1124 pairs, `gpt-5.2`, `max_completion_tokens=2000` |
| Measured rate | $0.0251 for a 20-pair re-measurement, instrumented via `llm_budget.total_spend_usd()` |
| **Total** | **≈ $1.41** against the **$6.00** ceiling |

The total is reconstructed rather than directly measured: `llm_budget`
accounting is process-local and the earliest runs in this study exited before a
spend line was added. Every entry point in this directory now prints
`[spend] $X.XXXX` on exit via `atexit`, so any future run reports its own.

---

## 8. Reproducing this

```bash
# free, deterministic: the label set, the cosine matrix, the sweep, kappa arithmetic
python3 -m pytest scripts/eval/tests/test_ceiling.py -q

# free: re-derive the sample and the threshold sweep from the hand labels
python3 -m scripts.eval.ceiling.calibrate_matcher --emit-sample
python3 -m scripts.eval.ceiling.calibrate_matcher

# paid: the gpt-5.2 confirmation judge, for kappa and for scoring
NOESIS_LLM_MAX_SPEND_USD=6.00 python3 -m scripts.eval.ceiling.calibrate_matcher --confirm
NOESIS_LLM_MAX_SPEND_USD=6.00 python3 -m scripts.eval.ceiling.score_ceiling --threshold 0.55 --threshold 0.45
```

## 9. What this does not say

- It does not say the DAG is good. 35.5% of the addressable subset on three
  rejected ICLR papers is not a product claim.
- It does not say the 76 are *easy*. "Defect-addressable" means findable by
  reading the manuscript, not findable by the current prompt.
- The taxonomy is one labeller's judgement, recorded per unit with a reason so
  any individual call can be disputed. κ = 0.673 against an independent judge on
  the pair labels is the only external check; there is no second human labeller.
- Three manuscripts. The category proportions would move on a different corpus,
  and `kKRbAY4CXv::anon1` alone contributes 10 of the 34 `request_not_defect`
  units and all 3 `generic_non_defect` ones. One unusual reviewer is a
  meaningful fraction of a 212-unit corpus.
- ~~`COS_THRESHOLD` was **not** changed. `match.py` is untouched.~~ ↻ **Changed
  2026-08-01, to 0.44 rather than this file's 0.45** — the tie was broken by
  `CALIBRATION.md`, which re-ran the sweep at n=266 and confirmed §3's curve
  (0.45 recall moved 0.822 → 0.819). `match.py` now exposes
  `CALIBRATED_COS_THRESHOLD = 0.44`, `LEGACY_COS_THRESHOLD = 0.55`, and a
  `NOESIS_MATCH_COS_THRESHOLD` override.
