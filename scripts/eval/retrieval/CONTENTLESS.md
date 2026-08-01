# Contentless claims in the retrieval query set

**Label snapshot `230c6ea9d9b7e8fd`. Queries fingerprint `1f6c584e8fd6c055`. n = 338 scorable
queries, 8,554 relevant judgments, 344 indexed documents / 5,948 chunks, 15 of 15 topics.**

`docs/history/WAVE_LOG.md` carries a standing caveat on the retrieval baseline:

> "The query set also contains a large population of contentless claims that no retriever can
> serve; filtering them would raise every arm and improve nothing."

That sentence asserts a size ("large") and an effect ("would raise every arm") and measures
neither. This document replaces both with numbers that carry their `n` and their ceiling.

**The headline, in one line:** the population is **71 of 338 = 21.0%** by the classifier and
**31 of 120 = 25.8%** by hand — real, but the second half of the caveat is **wrong**. Contentless
claims are *not* unservable. Hand-judged contentless queries score recall@10 **0.1377** against
their own recomputed ceiling of **0.4549** — **30% of attainable**, n = 31. Filtering them moves
dense recall@10 from **0.2186** (n = 338, ceiling 0.5199, 42% attainable) to **0.2260** (n = 267,
ceiling 0.5231, 43% attainable). That is **+3.4% relative and +1 point of attainable fraction** —
not the large lift the caveat implies.

**Filtering improves no user's experience.** Nobody's retrieval gets better. The 71 queries do not
stop being asked; they stop being counted. What changes is what is being measured. The only honest
reading of the filtered column is: *"about a fifth of this benchmark is composed of claims that
name nothing outside their own manuscript, and the retriever scores 0.14 on them instead of 0.27."*

---

## 1. The definition

A query is **contentless** when, after stripping

1. first-person and contribution framing — *"we show"*, *"our method"*, *"this paper"*;
2. evaluative and comparative rhetoric — *"significantly outperforms"*, *"state-of-the-art"*;
3. the manuscript's own protagonist artifact names — *TabR*, *BATTLE*, *SaNN*, *MedDisK*;
4. intra-document deixis — *"Fig. 3"*, *"these results"*, *"the tradeoffs identified in §4.1"*;
5. generic academic prose — *"performance"*, *"extensive"*, *"comprehensive"*,

nothing is left but the manuscript's own topic label and ordinary academic English: **no named
external entity and no specific domain phenomenon**.

The operative test is **discrimination within the manuscript's own topic**, not technicality in the
abstract. Every query inherits its manuscript's entire resolved reference list as its relevant set,
so a term shared by all of those references cannot point at any one of them. *"TabR substantially
outperforms the existing retrieval-based DL models while being significantly more efficient"* reads
technical and is contentless: `TabR` is the paper's own system and `retrieval-based`, `tabular`,
`DL` are shared by all 40-odd candidate references. *"SaNN implicitly, is strictly more powerful
than GAMLPs, SPIN, or SIGN"* is servable: three externally-owned model names survive the strip.

This is why the classifier uses **per-topic document frequency** rather than a fixed keyword list.
"LLM" is a referent in a paper about tabular data and noise in a paper about LLMs. A hardcoded list
of protagonist names would need hand-maintenance per manuscript and would rot silently the first
time one was added.

### Edge cases, and where the line was drawn

| case | call | why |
|---|---|---|
| **Priority claims** — *"our work is the first to …"* | depends | Contentless only when the thing claimed first is described in the paper's own vocabulary. *"our method is the first to conduct a behavior-oriented adversarial attack against DRL agents through PbRL"* names PbRL and DRL → servable. *"Our work is the first to highlight the importance of error analysis in enhancing the prompt"* → contentless. |
| **Empty predicate, named subject** — *"the future of retrieval-based tabular DL looks positive"* | servable | The claim says nothing, but *"retrieval-based tabular DL"* is a searchable subfield and a retriever can return the cited retrieval-for-tabular papers from it. Calling this contentless would be scoring the sentence's intellectual content — a different and far more subjective question. **A stricter "no propositional content" reading would call it contentless and would raise the population.** |
| **Scoreboard reports naming an external baseline** — *"MASS-enabled architectures consistently outperforms … baseline and APS"* | servable | APS is somebody else's method and is in the reference list. |
| **Inline citation marker** — *"(Grinsztajn et al., 2022)"* | servable | Short-circuited before any lexical analysis. The author has pointed at the literature inside the sentence. 18 of 338 queries qualify. |
| **Anaphora with no antecedent** — *"These observations demonstrate that …"* | contentless unless something survives | The antecedent lives in a part of the manuscript the query does not carry. |
| **Own coined metric names** — *"a quadratic dependence of conformity and diversity"* | contentless | `conformity`, `diversity`, `faithfulness` are that paper's own metrics; every one of its references is about text generation. |

The definition is the result. The code is bookkeeping, and it is only as good as its agreement with
a human, measured below.

---

## 2. The classifier and how well it works

`contentless.py`. Deterministic, stdlib-only, **zero LLM calls**
(`test_contentless.py::test_classifier_makes_zero_llm_calls` asserts
`llm_budget.events() == []`, `total_spend_usd() == 0.0`, `unpriced_calls() == 0` after classifying
all 338). Three tests in order, first match wins:

1. inline citation marker → servable;
2. a named-entity anchor (embedded capital run, interior camel case, or embedded digit) that is
   *not* in the topic's own vocabulary → servable;
3. otherwise, count distinct surviving referent tokens against `MIN_REFERENTS = 4`.

`TOPIC_VOCAB_FRACTION = 0.20` and `MIN_REFERENTS = 4` were tuned on the development labels and then
**frozen before the held-out set was labelled**.

### Hand labels

120 queries labelled by one person (agent R1) reading them. Two disjoint seeded samples of 60 from
the 338, drawn with `random.Random(seed).sample`. File:
`contentless_hand_labels.json`.

| split | seed | n | hand-judged contentless | prevalence |
|---|---|---|---|---|
| development (labelled **before** any code existed) | 20260731 | 60 | 13 | 21.7% |
| held out (labelled **after** the thresholds were frozen) | 20260801 | 60 | 18 | 30.0% |
| **all** | — | **120** | **31** | **25.8%** |

**One labeller. There is no second annotator, so no inter-annotator agreement exists and none is
claimed.** The gap between 21.7% and 30.0% across two random samples of the same population is
itself a warning about how sharp this category is: at n = 60 the binomial standard error is ~6
points, so the two splits are about 1σ apart, but the category is fuzzy enough that labeller drift
between the two sittings cannot be ruled out either.

### Agreement, classifier vs. hand

| split | n | agreement | precision | recall | F1 | hand prevalence |
|---|---|---|---|---|---|---|
| development *(in sample — thresholds tuned on it)* | 60 | 0.850 | 0.700 | 0.538 | 0.609 | 0.217 |
| **held out** *(out of sample — the quotable figure)* | **60** | **0.733** | **0.571** | **0.444** | **0.500** | **0.300** |
| all | 120 | 0.792 | 0.625 | 0.484 | 0.545 | 0.258 |

**The held-out figure is the classifier's accuracy: 73.3% agreement, precision 0.571, recall 0.444,
n = 60.** The development figure is not, and the 0.850 → 0.733 drop is the size of the tuning. Both
are published because reporting only the first would be exactly the error this repo keeps finding
in its own history.

At P = 0.57 / R = 0.44 this classifier is **weak**. Roughly two in five of the queries it drops are
ones a human called servable, and it misses more than half of what a human called contentless. That
is why §4 reports the classifier-free measurement over the hand labels as well, and why the two
should be read together rather than either alone.

### Known false positives and negatives (named, from the held-out split)

- **`Wikipedia`, `Meta-world`** — plain capitalised proper nouns are not matched by the anchor
  regex, which requires an embedded capital run, interior camel case, or a digit. Both were called
  contentless; both name an external dataset. Left unfixed rather than patched after seeing the
  held-out errors, because patching against the held-out set would destroy the only out-of-sample
  number in this document.
- **`GBDT` in topic `rhgIgTSSxW`** — appears in ≥ 20% of that manuscript's queries, so per-topic
  document frequency classes it as the paper's own vocabulary. It is not; it is the external
  baseline the paper is arguing against. The frequency heuristic cannot tell "the system we built"
  from "the system we are beating" when a paper is defined by the comparison.
- **Own coined metrics** (`conformity`, `diversity`, `faithfulness` in `miGpIhquyB`, a 55-query
  topic) fall *below* the 20% threshold and survive as referents, so those result reports are
  called servable. Both this and the `GBDT` case are the same knob failing in opposite directions.
- **Small topics degenerate.** With fewer than `1 / 0.20 = 5` queries in a topic, a document
  frequency of one clears the threshold and the whole topic is stripped to nothing. The smallest
  real topic has 8 queries so this does not bite here;
  `test_topic_vocabulary_degenerates_on_tiny_topics` pins the behaviour so a future 3-query topic
  is not silently reported as 100% contentless.

### Where the population sits

71 of 338 (21.0%): 155 servable on referent count, 94 on a named-entity anchor, 18 on an inline
citation.

| topic | contentless / total | | topic | contentless / total |
|---|---|---|---|---|
| `10eQ4Cfh8p` | 6 / 24 (25%) | | `kKRbAY4CXv` | 0 / 11 (0%) |
| `9ceadCJY4B` | 3 / 8 (38%) | | `miGpIhquyB` | 8 / 55 (15%) |
| `ApjY32f3Xr` | 0 / 11 (0%) | | `qBL04XXex6` | 7 / 34 (21%) |
| `BQvbL2sFQx` | 0 / 16 (0%) | | `rhgIgTSSxW` | 18 / 51 (35%) |
| `H9DYMIpz9c` | 2 / 24 (8%) | | `rp5vfyp5Np` | 10 / 39 (26%) |
| `cXs5md5wAq` | 5 / 20 (25%) | | `eR4W9tnJoZ` | 2 / 12 (17%) |
| `eUgS9Ig8JG` | 4 / 14 (29%) | | `gYcft1HIaU` | 4 / 10 (40%) |
| `jx6njBKH8E` | 2 / 9 (22%) | | | |

The spread — 0% on four topics, 35–40% on three — is not noise about a mean. It is a property of
how the manuscripts write. The papers with a strongly branded protagonist system (`TabR`,
`BATTLE`) generate the most self-referential scoreboard sentences.

---

## 3. Every arm, both ways

Retrieval was run **once per arm over all 338 queries**, and the subsets were cut from the same raw
results. The filtered and unfiltered columns therefore cannot differ because of retrieval
nondeterminism — only because of which queries are in the denominator, which is the whole
comparison.

**Every ceiling below is recomputed for its own subset.** Recall@10 is capped at
`mean(min(10, |rel_q|) / |rel_q|)` over the queries actually scored, so dropping queries changes it.
Carrying 0.5199 across to the filtered set would silently rescale every arm — the error
`docs/BENCHMARKS.md` forbids by name.

Zero LLM calls: all 338 query embeddings were already in
`cache/retrieval_query_embeddings/text-embedding-3-large.json`, and the run was made under
`NOESIS_LLM_KILL_SWITCH=1`, so a cache miss would have raised rather than quietly bought a vector.

The eval database was shared with a concurrent agent on this branch during measurement, so the
corpus was checked directly against the index rather than assumed: `document_chunks` held
**5,948 chunks across 344 documents under project `e7a1c0b0-…-000000000001`, and no other
project**, matching `BASELINE_15.md` exactly. A corpus that had grown or shrunk mid-run would have
made every row below incomparable to the published baseline, and nothing in the harness would have
said so.

> **Run 1 of 2.** Only the dense ×5 rows below are reproducible; the keyword and RRF rows moved on
> a second identical invocation. §3e prints both runs and the deltas. Read those rows as one draw.

### 3a. Unfiltered — n = 338, 8,554 judgments

| arm | R@10 | ceiling | % attainable | NDCG@10 | MRR |
|---|---|---|---|---|---|
| **dense** (oversample ×5, plan `index`) | **0.2186** | **0.5199** | **42%** | 0.5145 | 0.7312 |
| dense (×12) | 0.2217 | 0.5199 | 43% | 0.5180 | 0.7435 |
| keyword **v1** (`plainto_tsquery`) | 0.0024 | 0.5199 | 0% | 0.0134 | 0.0459 |
| keyword **v2** (OR of lemmas) | 0.1441 | 0.5199 | 28% | 0.3803 | 0.6605 |
| RRF(dense, keyword v2), k=60 | 0.2027 | 0.5199 | 39% | 0.4913 | 0.7219 |

### 3b. Classifier-filtered — n = 267 (71 dropped, 21.0%), 6,753 judgments

| arm | R@10 | ceiling | % attainable | NDCG@10 | MRR | Δ R@10 vs 3a |
|---|---|---|---|---|---|---|
| **dense** (×5) | **0.2260** | **0.5231** | **43%** | 0.5217 | 0.7379 | **+3.4%** |
| dense (×12) | 0.2306 | 0.5231 | 44% | 0.5270 | 0.7530 | +4.0% |
| keyword v1 | 0.0010 | 0.5231 | 0% | 0.0063 | 0.0262 | **−58%** |
| keyword v2 | 0.1544 | 0.5231 | 30% | 0.3978 | 0.6866 | +7.1% |
| RRF k=60 | 0.2158 | 0.5231 | 41% | 0.5078 | 0.7275 | +6.5% |

### 3c. The dropped queries, scored on their own — n = 71, 1,801 judgments

| arm | R@10 | ceiling | % attainable | NDCG@10 | MRR |
|---|---|---|---|---|---|
| dense (×5) | 0.1911 | 0.5077 | 38% | 0.4877 | 0.7060 |
| dense (×12) | 0.1882 | 0.5077 | 37% | 0.4839 | 0.7077 |
| keyword v1 | 0.0075 | 0.5077 | 1% | 0.0402 | 0.1197 |
| keyword v2 | 0.1053 | 0.5077 | 21% | 0.3146 | 0.5623 |
| RRF k=60 | 0.1538 | 0.5077 | 30% | 0.4295 | 0.7008 |

**This table is the finding.** The queries the classifier calls unservable score dense recall@10
**0.1911 at 38% of their own ceiling** — 87% of the unfiltered arm's 42%. "No retriever can serve
them" does not survive contact with the measurement. Note also that keyword v1 scores *higher* on
the contentless subset (0.0075) than on the servable one (0.0010): `plainto_tsquery` ANDs every
lemma, so short generic sentences are the only ones it can match at all.

### 3d. Classifier-free: hand labels only

The classifier is weak (§2), so the same comparison is repeated over the 120 hand-labelled queries,
with nothing between the human judgment and the metric. Smaller `n`, no classifier error.

**Hand-servable — n = 89, 2,086 judgments**

| arm | R@10 | ceiling | % attainable | NDCG@10 | MRR |
|---|---|---|---|---|---|
| **dense** (×5) | **0.2718** | **0.5604** | **48%** | 0.5927 | 0.8257 |
| dense (×12) | 0.2761 | 0.5604 | 49% | 0.5977 | 0.8374 |
| keyword v1 | 0.0009 | 0.5604 | 0% | 0.0025 | 0.0112 |
| keyword v2 | 0.1768 | 0.5604 | 32% | 0.4049 | 0.6973 |
| RRF k=60 | 0.2518 | 0.5604 | 45% | 0.5490 | 0.8114 |

**Hand-contentless — n = 31, 873 judgments**

| arm | R@10 | ceiling | % attainable | NDCG@10 | MRR |
|---|---|---|---|---|---|
| **dense** (×5) | **0.1377** | **0.4549** | **30%** | 0.3758 | 0.5183 |
| dense (×12) | 0.1375 | 0.4549 | 30% | 0.3757 | 0.5196 |
| keyword v1 | 0.0024 | 0.4549 | 1% | 0.0213 | 0.0968 |
| keyword v2 | 0.0960 | 0.4549 | 21% | 0.2878 | 0.4957 |
| RRF k=60 | 0.1213 | 0.4549 | 27% | 0.3710 | 0.5948 |

**The human separates the two populations far more sharply than the classifier does** — 48% of
attainable vs 30%, against the classifier's 43% vs 38%. That difference *is* the classifier's error
rate made visible: a filter at P = 0.57 mixes the populations back together. The contentless
queries still reach **30% of their own ceiling**, so even under human labels they are not
unservable — they are *harder*, by roughly 18 points of attainable fraction, n = 89 and n = 31.

**The ceilings move, and by a lot: 0.5199 → 0.5231 → 0.5604 → 0.4549.** The hand-contentless subset
has a *lower* ceiling than the full set (its queries come from manuscripts with longer reference
lists), so its raw recall understates how it is doing relative to what is attainable. Reusing
0.5199 for it would have reported 26% of attainable instead of 30%.

### 3e. Reproducibility — measured, and only one arm passes

Both runs below are the same command on the same corpus (verified at 5,948 chunks / 344 docs
between them), the same cached query embeddings, and the same query set. Unfiltered subset:

| arm | run 1 R@10 | run 2 R@10 | Δ | `BASELINE_15.md` |
|---|---|---|---|---|
| **dense ×5** | **0.2186** | **0.2186** | **0.0000** | 0.2195 |
| dense ×12 | 0.2217 | 0.2228 | +0.0011 | 0.2227 |
| keyword v1 | 0.0024 | 0.0022 | −0.0002 | 0.0022 |
| keyword v2 | 0.1441 | 0.1447 | +0.0006 | 0.1447 |
| RRF k=60 | 0.2027 | 0.2046 | +0.0019 | 0.2042 |

**Only the headline arm reproduces.** dense ×5 is identical to four decimal places across both runs
on **all five subsets and all three metrics** — 0.2186 / 0.2260 / 0.1911 / 0.2718 / 0.1377, NDCG and
MRR included. Every other arm moves between runs, and RRF moves by **0.0019, which is 26% of the
entire +0.0074 filtering effect this document reports.**

Two consequences, both of which constrain what may be quoted:

- **The filtering comparison is safe**, because it rests on dense ×5 and the +0.0074 effect is 4×
  the largest drift observed anywhere. The servable-vs-contentless gap it rests on (0.1341) is 70×
  that drift.
- **The keyword and RRF rows in §3a–3d must be read as one draw, not as a measurement.** They come
  from run 1. Run 2's keyword and dense ×12 figures land on `BASELINE_15.md`'s published values
  almost exactly (0.0022, 0.1447, 0.2228 vs 0.2227) while run 1's do not, which is consistent with
  run 1 having been perturbed by a concurrent agent's load on the shared eval database — but that
  is a hypothesis, not a measurement, and **picking whichever run agrees with the baseline would be
  exactly the selection this document exists to avoid.** Both are printed above; neither is
  preferred.

Why dense is stable and the rest are not is not established here. The plausible mechanism is tie
handling: `ts_rank(..., 1|32)` values in this corpus sit in a band of 0.0038–0.0071, so the keyword
leg produces many ties whose row order Postgres need not preserve, and RRF consumes that order
directly. Cosine similarity ties far less often. **That is a hypothesis, not a finding**, and it is
worth a dedicated experiment — a nondeterministic keyword leg silently invalidates every hybrid
number this repo has published or will publish.

---

## 4. What this does and does not license

**Claimable.**

- *"21.0% of the 338-query retrieval benchmark (71 queries) is classified as contentless — claims
  that name nothing outside their own manuscript — against a hand-judged prevalence of 25.8%
  (31 of 120)."*
- *"Filtering them raises dense recall@10 from 0.2186 (n=338, ceiling 0.5199) to 0.2260 (n=267,
  ceiling 0.5231): +3.4% relative, +1 point of attainable fraction."*
- *"Under human labels the gap is larger — 0.2718 at 48% of a 0.5604 ceiling (n=89) versus 0.1377
  at 30% of a 0.4549 ceiling (n=31) — but contentless claims are still served at 30% of
  attainable, so 'no retriever can serve them' is false."*
- *"The lexical classifier agrees with a single human labeller 73.3% of the time out of sample
  (precision 0.571, recall 0.444, n=60)."*
- *"Dense (oversample ×5) is bit-stable across repeated runs — identical R@10, NDCG@10 and MRR on
  all five subsets, n=2 runs — while RRF(dense, keyword v2) moves 0.0019 in R@10 between two
  identical invocations."*

**Not claimable.**

- Any filtered number without its `n` and its own recomputed ceiling.
- Any keyword or hybrid figure above to four decimal places. They are single draws from a
  distribution whose spread (up to 0.0019 for RRF) has been measured but not characterised; n = 2
  runs.
- Any comparison against snapshots `019bee4a06eb2d39` or `425df789a844f1f3`. Three snapshots exist;
  only `230c6ea9d9b7e8fd` is current, and they are not comparable at all.
- That filtering makes retrieval better for anyone. It does not. It changes the denominator.
- The word "large" in the standing caveat, unqualified. One fifth is real; it is not the dominant
  share the caveat suggests, and 87% of the unfiltered attainable fraction survives on exactly the
  population it says is unservable.
- Inter-annotator agreement. One labeller, no second pass.

### Recommended correction to `WAVE_LOG.md`

> ~~The query set also contains a large population of contentless claims that no retriever can
> serve; filtering them would raise every arm and improve nothing.~~
>
> **21.0% of the query set (71 of 338) is classified as contentless — self-referential or purely
> evaluative claims naming nothing outside their own manuscript; hand-judged prevalence 25.8%
> (31 of 120, one labeller). They are harder, not unservable: dense recall@10 0.1377 at 30% of
> their own 0.4549 ceiling (n=31, hand-labelled) against 0.2718 at 48% of 0.5604 for the servable
> half (n=89). Filtering moves the headline arm 0.2186 → 0.2260 (+3.4%) and improves no user's
> experience — it changes what is being measured.** See `scripts/eval/retrieval/CONTENTLESS.md`.

---

## 5. Caveats that travel with every number here

- **Everything inherits the standing label caveat.** These labels measure *"would we have found
  what the author cited"*, not *"what is relevant"*. Every precision-like metric is a lower bound;
  recall is the sounder number. Filtering does not touch this.
- **This is why contentless queries still score.** A query inherits its manuscript's *whole*
  reference list. A sentence naming nothing still embeds near its manuscript's topic, and
  everything in that manuscript's reference list is labelled relevant — so the retriever gets
  credit for topical proximity without ever resolving the claim. The label design, not the
  retriever, is what makes 0.1377 possible on queries a human says name nothing. **Any label design
  that scored per-claim rather than per-manuscript would report a much larger gap.**
- **Dense ×5 does not match `BASELINE_15.md` and the cause is not isolated.** It reads 0.2186 here
  in **both** runs (NDCG@10 0.5145, MRR 0.7312) against that document's 0.2195 / 0.5191 / 0.7328,
  on the same label snapshot, the same 338 queries, the same 8,554 judgments and the same ceiling
  to four places (0.5199). A 0.0009 gap on an arm that is otherwise bit-stable is not ANN
  nondeterminism, so something differs between this driver and `run_retrieval_eval.py`'s path that
  I did not find. It is 0.4% relative and does not move any conclusion here, but it is **an open
  discrepancy, not a rounding difference**, and the lead should reconcile it before the filtered
  arms are written into `results/retrieval_eval.jsonl`.
- **Only dense ×5 reproduces across runs; the keyword and hybrid arms do not** (§3e). RRF moves
  0.0019 between two identical invocations. Every hybrid number in this repo inherits that.
- **The classifier partition is fully deterministic** and asserted as such
  (`test_classification_is_deterministic_across_calls`, `test_published_population_reproduces`), so
  every subset boundary above reproduces exactly. Where a number moves, it is the retriever moving,
  never the filter.
- **One labeller, 120 of 338 labelled.** The classifier-free tables in §3d rest on n = 89 and
  n = 31 and are the least statistically comfortable numbers in this document.
- **The classifier's largest error source is a hand-curated lexicon.** With 15 topics and 338
  queries there is not enough data to learn generic academic English by inverse document frequency
  (cross-topic spread thresholds 4–8 yield between 10 and 101 tokens, none of which is a usable
  stoplist). `GENERIC_ACADEMIC` is ~700 hand-chosen words and is the most inspectable and most
  fragile component.
- **Local pgvector, PyMuPDF extraction, basic chunking.** Not production's Docling → GROBID
  section-aware chain, and none of this is a production retrieval number.

---

## 6. Reproducing

```bash
# classifier population + agreement with the hand labels (no DB, no network)
python3 -m scripts.eval.retrieval.contentless --validate

# every arm on every subset (needs the local pgvector container; zero LLM calls)
NOESIS_LLM_KILL_SWITCH=1 python3 -m scripts.eval.retrieval.contentless --validate --arms

# tests, including the zero-spend assertion and the pinned published numbers
python3 -m pytest scripts/eval/retrieval/tests/ -q
```

`--arms` prints all five subsets. It is a measurement driver, not a harness: it appends nothing to
`results/retrieval_eval.jsonl`. Once `partition()` is wired into `run_retrieval_eval.py` (see the
handover note in the commit body), the filtered arms become ordinary append-only records with their
own config hash.
