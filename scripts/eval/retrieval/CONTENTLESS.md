# Contentless claims in the retrieval query set

**Label snapshot `230c6ea9d9b7e8fd`. Queries fingerprint `1f6c584e8fd6c055`. n = 338 scorable
queries, 8,554 relevant judgments, 344 indexed documents / 5,948 chunks, 15 of 15 topics.**

`docs/history/WAVE_LOG.md` carries a standing caveat on the retrieval baseline:

> "The query set also contains a large population of contentless claims that no retriever can
> serve; filtering them would raise every arm and improve nothing."

That sentence asserts a size ("large") and an effect ("would raise every arm") and measures
neither. This document replaces both with numbers that carry their `n` and their ceiling.

> **Corpus identity: `5948c/344d`, `index_digest 8d3edbe3f3b28cdb`**, verified before *and* after
> every retrieval pass reported here. An earlier version of this document was measured against a
> different corpus and every absolute number in it was wrong; §3f names the discarded runs and how
> the contamination was established. Nothing was silently replaced.

**The headline, in one line:** the population is **71 of 338 = 21.0%** by the classifier and
**31 of 120 = 25.8%** by hand — real, but the second half of the caveat is **wrong**. Contentless
claims are *not* unservable. Hand-judged contentless queries score recall@10 **0.1388** against
their own recomputed ceiling of **0.4549** — **31% of attainable**, n = 31. Filtering them moves
dense recall@10 from **0.2200** (n = 338, ceiling 0.5199, 42% attainable) to **0.2273** (n = 267,
ceiling 0.5231, 43% attainable). That is **+3.3% relative and +1 point of attainable fraction** —
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

The eval database is shared with other agents on this branch, and the first version of this
document was silently measured against someone else's experimental corpus (§3e, §3g). Every pass
reported here therefore fingerprints the index **before and after** the whole run and refuses to
report if the digest moved: `5948c/344d`, `8d3edbe3f3b28cdb`, verified at both ends. **A row count
is not a corpus identity** — that is the check that failed the first time.

All tables below are **run 3**, the first pass whose corpus identity was verified unchanged at both
ends (`5948c/344d`, `8d3edbe3f3b28cdb`).

### 3a. Unfiltered — n = 338, 8,554 judgments

| arm | R@10 | ceiling | % attainable | NDCG@10 | MRR |
|---|---|---|---|---|---|
| **dense** (oversample ×5, plan `index`) | **0.2200** | **0.5199** | **42%** | 0.5196 | 0.7336 |
| dense (×12) | 0.2227 | 0.5199 | 43% | 0.5221 | 0.7436 |
| keyword **v1** (`plainto_tsquery`) | 0.0022 | 0.5199 | 0% | 0.0110 | 0.0311 |
| keyword **v2** (OR of lemmas) | 0.1447 | 0.5199 | 28% | 0.3830 | 0.6675 |
| RRF(dense, keyword v2), k=60 | 0.2046 | 0.5199 | 39% | 0.4985 | 0.7330 |

Dense ×5 reads **0.2200**, matching the lead's independent control on this corpus
(`7c5439423119`, 0.22000627228526437, reproduced twice) to every printed digit.

### 3b. Classifier-filtered — n = 267 (71 dropped, 21.0%), 6,753 judgments

| arm | R@10 | ceiling | % attainable | NDCG@10 | MRR | Δ R@10 vs 3a |
|---|---|---|---|---|---|---|
| **dense** (×5) | **0.2273** | **0.5231** | **43%** | 0.5277 | 0.7441 | **+3.3%** |
| dense (×12) | 0.2315 | 0.5231 | 44% | 0.5319 | 0.7562 | +4.0% |
| keyword v1 | 0.0007 | 0.5231 | 0% | 0.0030 | 0.0112 | **−68%** |
| keyword v2 | 0.1550 | 0.5231 | 30% | 0.4003 | 0.6934 | +7.1% |
| RRF k=60 | 0.2182 | 0.5231 | 42% | 0.5167 | 0.7455 | +6.6% |

### 3c. The dropped queries, scored on their own — n = 71, 1,801 judgments

| arm | R@10 | ceiling | % attainable | NDCG@10 | MRR |
|---|---|---|---|---|---|
| dense (×5) | 0.1925 | 0.5077 | 38% | 0.4892 | 0.6942 |
| dense (×12) | 0.1896 | 0.5077 | 37% | 0.4855 | 0.6960 |
| keyword v1 | 0.0078 | 0.5077 | 2% | 0.0411 | 0.1056 |
| keyword v2 | 0.1058 | 0.5077 | 21% | 0.3178 | 0.5703 |
| RRF k=60 | 0.1533 | 0.5077 | 30% | 0.4298 | 0.6857 |

**This table is the finding.** The queries the classifier calls unservable score dense recall@10
**0.1925 at 38% of their own ceiling** — 90% of the unfiltered arm's 42%. "No retriever can serve
them" does not survive contact with the measurement. Note also that keyword v1 scores *higher* on
the contentless subset (0.0078) than on the servable one (0.0007): `plainto_tsquery` ANDs every
lemma, so short generic sentences are the only ones it can match at all.

### 3d. Classifier-free: hand labels only

The classifier is weak (§2), so the same comparison is repeated over the 120 hand-labelled queries,
with nothing between the human judgment and the metric. Smaller `n`, no classifier error.

**Hand-servable — n = 89, 2,086 judgments**

| arm | R@10 | ceiling | % attainable | NDCG@10 | MRR |
|---|---|---|---|---|---|
| **dense** (×5) | **0.2733** | **0.5604** | **49%** | 0.5989 | 0.8261 |
| dense (×12) | 0.2761 | 0.5604 | 49% | 0.6025 | 0.8378 |
| keyword v1 | 0.0009 | 0.5604 | 0% | 0.0025 | 0.0112 |
| keyword v2 | 0.1763 | 0.5604 | 31% | 0.4045 | 0.6991 |
| RRF k=60 | 0.2552 | 0.5604 | 46% | 0.5580 | 0.8212 |

**Hand-contentless — n = 31, 873 judgments**

| arm | R@10 | ceiling | % attainable | NDCG@10 | MRR |
|---|---|---|---|---|---|
| **dense** (×5) | **0.1388** | **0.4549** | **31%** | 0.3917 | 0.5699 |
| dense (×12) | 0.1387 | 0.4549 | 30% | 0.3912 | 0.5710 |
| keyword v1 | 0.0008 | 0.4549 | 0% | 0.0071 | 0.0323 |
| keyword v2 | 0.0969 | 0.4549 | 21% | 0.3028 | 0.5673 |
| RRF k=60 | 0.1254 | 0.4549 | 28% | 0.3843 | 0.6032 |

**The human separates the two populations far more sharply than the classifier does** — 49% of
attainable vs 31%, against the classifier's 43% vs 38%. That difference *is* the classifier's error
rate made visible: a filter at P = 0.57 mixes the populations back together. The contentless
queries still reach **31% of their own ceiling**, so even under human labels they are not
unservable — they are *harder*, by roughly 18 points of attainable fraction, n = 89 and n = 31.
This is the finding that survived the corpus contamination unchanged: the absolute recalls all
moved, the 18-point structural gap did not.

**The ceilings move, and by a lot: 0.5199 → 0.5231 → 0.5604 → 0.4549.** The hand-contentless subset
has a *lower* ceiling than the full set (its queries come from manuscripts with longer reference
lists), so its raw recall understates how it is doing relative to what is attainable. Reusing
0.5199 for it would have reported 27% of attainable instead of 31%.

### 3e. RETRACTED: the RRF non-determinism finding

**An earlier version of this document reported that only dense ×5 reproduced across runs, and that
RRF(dense, keyword v2) moved 0.0019 in R@10 between two identical invocations — 26% of the entire
filtering effect. That finding is withdrawn. The cause was a corpus swap under the runs, not
non-determinism.**

It is recorded here rather than deleted, because how it was caught matters more than the claim did.

The timeline, established from `document_chunks.created_at` and the process wall-clock:

| when (UTC) | when (local, CDT) | event |
|---|---|---|
| 23:34–23:46 | 18:34–18:46 | **run 1** — entirely before the swap |
| 23:50 | 18:50 | **run 2** starts |
| **23:57:36–23:59:47** | **18:57:36–18:59:47** | **agent R2 re-ingests 324 chunks across 6 documents** |
| ~00:15 | ~19:15 | run 2 ends |

Run 1 sat wholly on R2's experimental corpus. **Run 2 straddled the swap.** My driver measures the
arms in a fixed order — dense ×5, dense ×12, keyword v1, keyword v2, RRF — at roughly 5 minutes per
arm, so run 2's dense arms were measured *before* 18:57 and its keyword and RRF arms *after* 19:00.
The arms in a single run 2 record therefore describe **two different corpora**.

That is exactly what the numbers show, and it is what gave the game away:

| arm | run 1 (experimental) | run 2 (split) | run 3 (restored, verified) |
|---|---|---|---|
| dense ×5 | 0.2186 | 0.2186 | **0.2200** |
| dense ×12 | 0.2217 | 0.2228 | 0.2227 |
| keyword v1 | 0.0024 | **0.0022** | **0.0022** |
| keyword v2 | 0.1441 | **0.1447** | **0.1447** |
| RRF k=60 | 0.2027 | **0.2046** | **0.2046** |

Run 2's keyword and RRF rows are **bit-identical to run 3's**, measured 25 minutes apart on the
restored corpus, while its dense rows are bit-identical to run 1's on the experimental one. The
"non-determinism" I reported was the boundary between those two groups. dense ×12, whose window
contains 18:57 itself, is the only arm that matches neither — a straddle inside a single arm.

**The retracted claim was: "only dense ×5 reproduces; RRF moves 0.0019."** The evidence now says
every arm that was measured twice on the same corpus reproduced exactly — §3f measures the
run-to-run spread at **0.0000 across all 75 metric cells, n = 2 runs**. I had inverted the finding:
the retriever is perfectly reproducible and the *corpus* was the volatile input.

**A limit of the `index_digest` fix this exposes.** `index_fingerprint()` as wired into
`run_retrieval_eval.py` is sampled **once per run**, so a run that straddles a swap stamps whichever
state it happened to read and looks clean — run 2 would have carried a single valid-looking digest
for a record spanning two corpora. This driver therefore fingerprints **before and after** the whole
pass and raises `CorpusChangedUnderRun` if they differ
(`test_arms_driver_refuses_a_run_that_straddles_a_corpus_change`). Recommend the same for
`run_retrieval_eval.py`: one sample cannot detect a change, only two can.

### 3f. Run-to-run variance on a verified-stable corpus

Runs 3 and 4: the same command, back to back, each fingerprint-verified `8d3edbe3f3b28cdb` at both
ends. **Every metric cell is bit-identical — 5 arms × 5 subsets × 3 metrics = 75 cells, zero
differences**, checked by mechanical diff rather than by eye.

| | |
|---|---|
| runs compared | **n = 2** |
| metric cells per run | 75 (5 arms × 5 subsets × {R@10, NDCG@10, MRR}) |
| cells differing | **0** |
| observed run-to-run spread | **0.0000 on every arm, including keyword v1/v2 and RRF** |

**Measured run-to-run variance on this benchmark is zero, n = 2 runs.** Not "small" — zero, at four
decimal places, on every arm including the two I had accused of drifting. The keyword leg's
`ts_rank` ties do not reorder in practice, and the earlier "0.0019 RRF movement" was entirely the
corpus swap.

Read this narrowly. It says the pipeline is deterministic *given a fixed corpus and fixed cached
query embeddings*; it says nothing about stability across re-ingestion, and §3g shows re-ingesting
6 of 344 documents moved the headline arm 0.2195 → 0.2200. **The volatile input is the corpus, not
the retriever.** n = 2 is also the minimum useful number of runs; it can establish that variance
exists but bounds its absence only weakly.

This is, as far as I can find, the only run-to-run variance figure measured anywhere in this
project on a corpus of recorded identity.

### 3g. Discarded runs

Neither discarded run was ever appended to `results/retrieval_eval.jsonl` — this driver does not
write to the append-only sink — so they carry no `run_id`. They are identified by their content and
by the corpus they hit:

| run | wall-clock (local) | corpus | identifying value | disposition |
|---|---|---|---|---|
| run 1 | 18:34–18:46 | R2 experimental (5,924c) | dense ×5 R@10 = `0.2186276861114972` | **discarded** — wrong corpus |
| run 2 | 18:50–~19:15 | **split** (experimental → restored) | dense ×5 `0.2186276861114972`, RRF `0.2046` | **discarded** — straddles the swap; describes no single corpus |

The identification is conclusive rather than circumstantial: my dense ×5 value
`0.2186276861114972` is **identical to 16 significant figures** to the lead's record
`e05d808dffc9` (`chunk_ceiling_exact`), R2's experimental-corpus arm. The real control on the
original corpus was `63d8281c6eeb` at `0.21946256307598289`, and on the current restored corpus is
`693079081219` / `7c5439423119` at `0.22000627228526437` — which run 3 reproduces.

**The published control is 0.22001, not 0.2195.** 0.2195 belongs to a corpus that no longer exists:
R2 restored by re-ingesting 6 documents, so the corpus is content-equivalent but carries 324 new
chunk ids and freshly generated embeddings. My earlier note calling the 0.2186-vs-0.2195 gap "an
open, unisolated discrepancy" is also withdrawn — it is fully explained, and the explanation was
contamination, not a bug in anyone's scoring path.

**Why my own contamination check failed.** I verified the corpus mid-work by counting rows:
5,948 chunks / 344 documents, matching `BASELINE_15.md`, and concluded the corpus was intact. It
was not. **Chunk count is not corpus identity.** R2's restore returned the count to 5,948 while
replacing 324 chunk ids, so the count check would have passed at every moment before, during and
after the incident. Only `index_digest` distinguishes them.

---

## 4. What this does and does not license

**Claimable.**

- *"21.0% of the 338-query retrieval benchmark (71 queries) is classified as contentless — claims
  that name nothing outside their own manuscript — against a hand-judged prevalence of 25.8%
  (31 of 120)."*
- *"Filtering them raises dense recall@10 from 0.2200 (n=338, ceiling 0.5199) to 0.2273 (n=267,
  ceiling 0.5231): +3.3% relative, +1 point of attainable fraction. Corpus `8d3edbe3f3b28cdb`."*
- *"Under human labels the gap is larger — 0.2733 at 49% of a 0.5604 ceiling (n=89) versus 0.1388
  at 31% of a 0.4549 ceiling (n=31) — but contentless claims are still served at 31% of
  attainable, so 'no retriever can serve them' is false."*
- *"The lexical classifier agrees with a single human labeller 73.3% of the time out of sample
  (precision 0.571, recall 0.444, n=60)."*
- Any statement about run-to-run non-determinism: see §3e, retracted, and §3f for what replaced it.

**Not claimable.**

- Any filtered number without its `n` and its own recomputed ceiling.
- Any number here alongside a number from a different corpus. `0.2195` (original corpus) and
  `0.2200` (restored corpus) are not comparable and must not be differenced, exactly as two label
  snapshots are not. The corpus is now part of the config hash (`index_digest`), so the existing
  house rule about trends within a hash covers this automatically.
- Any comparison against snapshots `019bee4a06eb2d39` or `425df789a844f1f3`. Three snapshots exist;
  only `230c6ea9d9b7e8fd` is current, and they are not comparable at all.
- That filtering makes retrieval better for anyone. It does not. It changes the denominator.
- The word "large" in the standing caveat, unqualified. One fifth is real; it is not the dominant
  share the caveat suggests, and 90% of the unfiltered attainable fraction survives on exactly the
  population it says is unservable.
- Inter-annotator agreement. One labeller, no second pass.

### Recommended correction to `WAVE_LOG.md`

> ~~The query set also contains a large population of contentless claims that no retriever can
> serve; filtering them would raise every arm and improve nothing.~~
>
> **21.0% of the query set (71 of 338) is classified as contentless — self-referential or purely
> evaluative claims naming nothing outside their own manuscript; hand-judged prevalence 25.8%
> (31 of 120, one labeller). They are harder, not unservable: dense recall@10 0.1388 at 31% of
> their own 0.4549 ceiling (n=31, hand-labelled) against 0.2733 at 49% of 0.5604 for the servable
> half (n=89). Filtering moves the headline arm 0.2200 → 0.2273 (+3.3%) and improves no user's
> experience — it changes what is being measured. Corpus `8d3edbe3f3b28cdb`.** See
> `scripts/eval/retrieval/CONTENTLESS.md`.

---

## 5. Caveats that travel with every number here

- **Everything inherits the standing label caveat.** These labels measure *"would we have found
  what the author cited"*, not *"what is relevant"*. Every precision-like metric is a lower bound;
  recall is the sounder number. Filtering does not touch this.
- **This is why contentless queries still score.** A query inherits its manuscript's *whole*
  reference list. A sentence naming nothing still embeds near its manuscript's topic, and
  everything in that manuscript's reference list is labelled relevant — so the retriever gets
  credit for topical proximity without ever resolving the claim. The label design, not the
  retriever, is what makes 0.1388 possible on queries a human says name nothing. **Any label design
  that scored per-claim rather than per-manuscript would report a much larger gap.**
- **Every absolute recall here is a property of corpus `8d3edbe3f3b28cdb` and of nothing else.**
  The same measurement on the pre-restore corpus reads 0.2195 on the headline arm and on R2's
  experimental corpus 0.2186. The *relative* structure — a fifth of the set contentless, an
  18-point attainable-fraction gap between the hand-labelled halves, a filtering effect near
  +3% — held across all three, which is why the finding survived and the numbers did not.
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

`--arms` fingerprints the index before and after the whole pass and raises `CorpusChangedUnderRun`
if the digest moved, so a contaminated run fails instead of publishing. It prints all five subsets.
It is a measurement driver, not a harness: it appends nothing to `results/retrieval_eval.jsonl`. Once `partition()` is wired into `run_retrieval_eval.py` (see the
handover note in the commit body), the filtered arms become ordinary append-only records with their
own config hash.
