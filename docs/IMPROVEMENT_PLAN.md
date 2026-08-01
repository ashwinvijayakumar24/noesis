# IMPROVEMENT_PLAN.md

**Goal as stated:** catch 50–75% of reviewer comments, get the DAG working close
to expectation, and fix latency, repeated uploads, leaks and accuracy — for a
product real researchers would use.

**Status:** Phase 0 is running. Everything downstream of it is provisional until
it reports, and this document says which numbers are load-bearing.

---

## 0. The reframe — "we miss 94%" is three different problems

Both systems match ~10% of 212 label units. That single number hides three
populations with completely different fixes, and nobody has separated them:

| population | fix | evidence it is large |
|---|---|---|
| **A. Genuinely missed** — a real flaw the system could have found | pipeline work | unknown |
| **B. Found but not credited** — the matcher didn't recognise it | **calibrate the matcher** | relaxing `COS_THRESHOLD` 0.55 → 0.45 moved recall **0.0815 → 0.2807**, same pipeline, same findings |
| **C. Unaddressable** — needs domain expertise, literature knowledge, proof verification; or is a question, not a defect | nothing — it is the ceiling | see below |

**Population B may be the largest single term, and it is a measurement bug, not
a product bug.** `match.py:34-36` contains a comment specifying the calibration
study — *"30 labeled pairs with agreement >=0.85; update this comment with
precision/recall"* — **that was never run.** The 0.55 threshold is a typed guess.

**Population C is real and probably big.** Actual label units, verbatim:

```
[question] Does the method only work on semi-linear PDEs?
[question] Can you add results of how shifting affects accuracy?
[weakness] However, some PINN methods can solve KS Equations such as Causal PINNs [1].
[weakness] In their proof in Appendix B.1, they show that E[Rep(F,D_F)] < B_1 ...
[weakness] Orientation equivariance is subject to the problems noted above ...
[question] I am still wondering about your method for the Machine Process Queue Embedding:
```

Those require: knowing Causal PINNs exist, verifying a Rademacher-complexity
proof, resolving a reference to *another reviewer's comment*, and a fragment the
atomizer cut mid-sentence. Roughly half the corpus is **questions** — requests
for information, not defects.

> ⚠️ **On the 50–75% target.** If population C is ~half the corpus, then 50–75%
> **of all units is arithmetically unreachable** and chasing it would burn months
> against a ceiling. The right target is a percentage **of the addressable
> subset**, and Phase 0 is measuring exactly that. The goal is not being lowered
> — it is being made falsifiable.

---

## Phase 0 — Fix the ruler *(running now, ~$6, blocking)*

Nothing downstream is worth doing until the measurement is trustworthy. Three
deliverables:

1. **A taxonomy of the 212 units**, hand-labelled, ≥120 units, stratified, fixed
   seed. Human judgment is the deliverable; any classifier is a labelling aid
   whose agreement is measured and reported.
2. **The matcher calibration that `match.py` specifies and never got** — 100–200
   hand-labelled candidate pairs, `COS_THRESHOLD` swept, precision/recall
   plotted, an operating point chosen against a stated cost asymmetry, Cohen's κ
   reported.
3. **The ceiling sentence:** *"Of 212 units, X are defect-addressable. Both
   systems find Y of those. The realistic ceiling is Z%, current true recall
   against it is W%."*

**Exit criterion:** both systems' recall re-expressed against the *addressable*
subset. That is the number the rest of this plan targets.

---

## Phase 1 — Accuracy *(after Phase 0 sets the target)*

Ordered by expected value, and every item is measurable against the Phase-0
baseline.

### 1.1 Adopt the calibrated matcher and re-baseline everything
Mechanical once Phase 0 lands. Every historical recall figure moves; they are
append-only and keyed by config hash, so old rows stay and are not differenced
against new ones. **Expected to be the single largest recall change in this
plan, and it is not a product improvement — it is the removal of a measurement
error.**

### 1.2 Calibrate the judge *(N8, ~8 h)*
Today: `gpt-5.2` judging `gpt-5.2` output against **`gpt-5.2`-written gold**
(`judge.py:211-238` bootstraps gold and prints *"Edit it, then rename to
`.gold.md` to approve"*; `draft3`–`draft10` are byte-identical to the bootstrap,
i.e. never edited). No temperature, no seed.
- swap in a different model family as judge
- pairwise with position swap
- measure drift across reruns
- fix the held-out contamination (`heldout/manifest.json` lists 4 papers whose
  PDFs come from corpora already used by Track A)

### 1.3 Specialise the reviewer panel
`reviewer_panel.py:350-351` hands **all three reviewers the entire manuscript**,
so it is three prompts over ~95% identical context. The harness measured the
alternative: scoped workers reach **0.0362 recall vs 0.0063** for an unscoped
single actor, and **fund fewer workers adequately rather than all partially**
(producers 0.82 vs 0.42, n=60, p=0.0033; 0.76 vs 0.28, n=71, p=0.000076).
**Port that scheduling result into the DAG's panel.**

### 1.4 The embedding — the only remaining retrieval lever
`FIRSTSTAGE.md` closed the others: depth **0.0000**, chunk granularity
**+0.0013**, removing the pool limit entirely **+0.0027**. Relevant/irrelevant
score separation is **under 1σ**, and a *perfect* reranker over the current pool
tops out at 0.2982 with dense already at 73.8% of it. This is a modelling
project — domain-adapted or fine-tuned embeddings — not a parameter sweep. **Do
not start it before Phase 0**, because retrieval feeds evidence, and if the gap
is mostly population B this is not where the loss is.

### 1.5 Cover the concerns that are raised and then dropped
The orchestrated agent triages 8 concerns and **dispatches only 2–4**. Straight
coverage loss, already instrumented as `uncovered_concerns`.

---

## Phase 2 — Latency *(independent of Phase 0, can start immediately)*

Measured user-visible p50: **212.82 s** (n=7, Docling contending) and **117.87 s**
(n=4, GROBID alone). Parsing on this host is **bimodal by an order of magnitude**.

| item | status | effect |
|---|---|---|
| **PDF parsed twice per upload** | **fixed, behind `DRAFT_VALIDATION_CHEAP_PARSE`, default off** | `upload_request` p50 **4.33 s → 0.05 s (−98.8%)**; removes one parse, worth 4.3 s or 52.4 s depending on parser contention |
| **Docling/GROBID memory contention** | diagnosed, unfixed | the difference between a 118 s and a 213 s baseline. Docker has ~8.2 GB; the two parsers cannot co-reside |
| Graph stage | 112.51 s p50, **99.5% LLM wait** | not fixable by code; only by fewer/cheaper calls or more parallelism |

**Actions:** enable the cheap-parse flag in production after a staged
validation; decide whether Docling is worth its memory footprint (it was
measured, it **failed**, and GROBID ran alone); then re-measure end to end.

**Target:** user-visible p50 **under 90 s** with one parse and no parser
contention. Stated as a target, not a prediction.

---

## Phase 3 — Trust *(highest priority for a real product)*

Unpublished research is the most sensitive thing a researcher owns. For a
product, this phase outranks accuracy.

### 3.1 🔴 IDOR — live, unfixed
`drafts.py:2304-2310`: the WebSocket validates the token and **never checks the
draft belongs to the caller**. Any authenticated user can stream any draft's
analysis by knowing its id.
**The fix already exists, built and adversarially tested**, in
`reviewer-agent/harness/policy.py`: ownership looked up, never taken from the
request; denial reasons that never name the owner; non-retryable on denial. Port
it.

### 3.2 Manuscript persistence
The checkpointer fan-out was writing the **full manuscript to disk three times
per run** — fixed, and caught only by a raw-BYTEA assertion. **Add that assertion
class to CI**, because inspection did not catch it and would not catch the next
one.

### 3.3 Known and unfixed
- `chrome-extension://.*` CORS wildcard (`security_middleware.py:333`)
- `embedding_cache.py:70` uses **pickle** — a deserialization surface
- injection: 7 sites interpolate untrusted text with no delimiter or hierarchy.
  61 attack cases measured; **no defense reduced ASR**. What bounds the blast
  radius today is that nothing can act — which stops being true the moment
  anything gets a write tool.

---

## Phase 4 — Repeated uploads and cost

**There is no content-hash dedup on upload.** Zero references to `sha256` /
`content_hash` / `file_hash` in `drafts.py`. Re-uploading the same PDF re-parses,
re-embeds and re-analyses at full cost and full latency.

- **Content-addressed uploads:** hash the bytes, reuse the parse artifact and
  chunks when the hash matches. The parse is 4–52 s and the embed spend is real.
- **Reuse the analysis** when the manuscript *and* pipeline version match — the
  pipeline version primitive already exists (`pipeline_cache.py:26-66`).
- **Resume now works** (SIGKILL 27/27, **87.6% of a run's cost recovered** when
  resuming after the reviewer panel, n=160). Make sure the product actually uses
  it on retry rather than restarting.

---

## Sequencing and honest targets

```
Phase 0  ── measure the ceiling ─────────────► sets every target below
   │
   ├─ Phase 2 latency ──────────┐  (independent, start now)
   ├─ Phase 3 trust ────────────┤  (independent, start now — IDOR is live)
   └─ Phase 4 dedup ────────────┘  (independent, start now)
   │
   └─ Phase 1 accuracy ─────────►  1.1 → 1.2 → 1.3 → 1.5 → 1.4
```

| target | commitment |
|---|---|
| Recall vs **all 212 units** | **No number promised.** Bounded by population C |
| Recall vs the **addressable subset** | Target set once Phase 0 reports. This is the honest goal |
| User-visible p50 | **< 90 s**, from 213 s / 118 s |
| Duplicate upload cost | **→ ~0** via content addressing |
| IDOR | **closed**, with the adversarial test ported from the harness |
| Matcher | **calibrated**, with a published precision/recall curve and κ |

**The rule that got us here and should stay:** every number carries its `n`,
results are append-only and keyed by config hash, a capability not observed
firing is not a capability, and negative results ship. Six times in one night a
measurement described a mechanism that was not running. That is what happens
without those rules, and it is why Phase 0 blocks everything.
