# Degraded-Output Labelling Rubric

**Status:** written BEFORE any labelling, deliberately. A rubric authored after
looking at score distributions gets fitted to the data and then "validates" the
thresholds it was derived from. If you find yourself wanting to edit this file
mid-labelling, stop, finish the batch under the current rubric, and version-bump
the rubric instead of editing it in place.

---

## 0. The one rule that makes this measurement valid

**Do not look at the gate's verdict, `parser_quality_score`,
`page_anchor_coverage`, or `verbatim_anchor_coverage` while labelling.**

`label_cli.py` hides all four. Do not open the raw export JSON alongside the CLI
to "check". The entire point of the exercise is to produce a human label that is
statistically independent of the gate, so the gate can be scored against it. A
label contaminated by the gate's own opinion measures nothing except your ability
to agree with a number you already saw.

You are labelling **the critique a user would receive**, not the run's telemetry.

---

## 1. Definition of `degraded`

> A run is **degraded** if a competent researcher who wrote this manuscript,
> reading only the critique, would conclude the system did not actually read
> their paper — or would be actively misled by it.

The operational test is **user-visible harm**, not internal metrics. A run can
have terrible internal grounding and still be `ok` if the critique it produced is
accurate and useful. A run can have perfect grounding and be `degraded` if the
critique is empty, generic, or wrong.

Three failure families count as degraded. Any one is sufficient:

**D1 — Fabrication / misattribution.** The critique asserts something about the
manuscript that is not true: criticises a section that does not exist, quotes an
anchor that does not appear in the paper, claims a method is missing when it is
described, or attributes a claim to the wrong part of the paper. Includes anchor
quotes that are visibly garbled parser output (`"Bacterial genomes Bacterial
genomes are generated to"` repeated, ligature soup, mid-word truncation) such
that the author cannot find the passage being discussed.

**D2 — Non-specificity.** The critique would apply unchanged to any paper in the
field. "Add more baselines", "the writing could be clearer", "discuss limitations"
with no manuscript-specific referent. The test: **swap in a different paper's
title. Does the critique still read as valid?** If yes for the majority of items,
degraded.

**D3 — Emptiness / collapse.** Effectively no actionable output: zero durable
revision tasks, or so few and so thin that a user paying for pre-submission review
received nothing. A run with 0 tasks and 1 boilerplate reviewer comment is
degraded regardless of how clean the parse was.

Everything else is `ok`. **`ok` does not mean good.** A mediocre-but-honest
critique that identifies real, findable issues is `ok`. We are calibrating a
safety gate, not a quality score — the gate's job is to withhold *harmful* output,
not *unimpressive* output.

---

## 2. Worked examples from real exports

These are drawn from `scripts/eval/results/*.json` as they existed at rubric time.

### Negative examples (label `ok`)

**N1 — `qBL04XXex6__no-corpus__2026-06-21T20-29-03.json`, task 1.**
> problem: "Key hyperparameters ('small max depth value' and score thresholds
> [0.3, 0.8]) are described qualitatively or partially, without a consolidated
> table of final numeric values."
> anchor: "we use a small max depth value in BoT and label a node as a leaf when
> its V i-1,i and V i values are outside the specified range [0.3, 0.8]."

Quotes a real, locatable sentence; the criticism is specific to *this* paper's
actual hyperparameter reporting. Passes the swap test — this critique is
meaningless applied to another paper. `ok`.

**N2 — same file, task 2 (missing `M`).** Names a specific symbol from the
manuscript's own notation and explains the reproducibility consequence. `ok`.

**N3 — `cXs5md5wAq...T04-31-42.json`, task 1 (simulation bijectivity).**
> "In simulation, genomes are constructed to encode growth parameters via an
> approximately bijective mapping. This makes the prediction task structurally
> well-posed and may overestimate the ability of GNNs..."

A substantive methodological objection that required understanding the paper's
simulation design. `ok` — note this run's page-anchor coverage was 0.692, i.e.
**below** the gate's 0.75 threshold. That mismatch is exactly what we are
measuring; it does not change the label.

**N4 — a run whose anchor quote is slightly ragged at the edges** (starts
mid-clause, trailing whitespace) but is still unambiguously findable in the PDF.
Cosmetic parser roughness is not D1. `ok`.

### Positive examples (label `degraded`)

**P1 — `cXs5md5wAq__no-corpus__2026-06-21T03-59-08.json`.** `durable_revision_tasks`
is empty; 7 claims extracted; 2 reviewer_feedback items; readiness_score 99 with
zero critical/major tasks. The user paid for a review and got one generic
structural note. Textbook **D3**.

**P2 — repeated-phrase anchors.** An anchor like `"Bacterial genomes Bacterial
genomes are generated to encode the simulated growt"` — the duplication is a
GROBID nested-div artifact. If the surrounding task text also misreads the
duplicated fragment as the paper's actual prose, that is **D1**. If the task is
otherwise correct and the duplication is only in the quote, see tie-break T2.

**P3 — a critique whose every task is "add more detail to Methods", "clarify
notation", "discuss limitations"** with no quoted passage and no manuscript
specifics. **D2**, even if there are 12 of them. Volume is not specificity.

**P4 — a critique that demands the authors add an experiment the paper already
reports**, or criticises the absence of a section that exists in `analysis.structure.sections`.
**D1** — this is the most damaging failure mode, because the author loses trust
in the whole product from a single instance.

---

## 3. Tie-break rules

Apply **in order**; stop at the first that resolves.

- **T1 — Any single D1 in a high-severity task ⇒ `degraded`.** One confident
  fabrication in a `critical` or `major` task poisons the run. Do not average it
  away against nine good tasks. Rationale: users do not sample uniformly; they
  read the top-severity items first.
- **T2 — A D1 confined to `minor` tasks ⇒ count them.** If ≥ 1/3 of minor tasks
  are fabricated or unlocatable, `degraded`; otherwise `ok`. Isolated noise in the
  long tail is tolerable.
- **T3 — Mixed specificity ⇒ majority rules on the top-severity tier only.**
  Judge the `critical` tasks; if none, the `major` tasks; if none, the `minor`
  tasks. If more than half of that tier fails the swap test, `degraded`.
- **T4 — Zero durable revision tasks ⇒ `degraded`,** regardless of how good the
  reviewer_feedback or meta_review prose is. The tasks are the product.
- **T5 — Truncated or error-terminated run ⇒ `degraded`,** even if what shipped
  before the truncation was fine. The user received an incomplete artifact.
- **T6 — Cannot verify a claim against the manuscript without opening the PDF ⇒
  do NOT guess.** Either open the PDF and verify, or label `unsure`. Assuming a
  suspicious-looking quote is fabricated is itself a source of bias.

## 4. `unsure` — use it, it is not a failure

An explicit `unsure` is strictly better than a coin flip. A coin flip injects
label noise that is indistinguishable from real signal and will silently widen
every confidence interval downstream. `unsure` is excluded from the metrics
cleanly and honestly.

Label `unsure` when:
- The manuscript is outside your competence to judge on substance (you cannot
  tell whether the methodological objection is correct).
- The critique is borderline on D2 and the tie-breaks do not separate it.
- Verifying would require reading the full PDF and you are not going to.
- You have been labelling for more than ~45 minutes and know you are fatigued.

**Target: `unsure` under ~15% of labels.** Consistently above that means the
rubric is underspecified for this corpus and needs a versioned revision — not
that you should force yourself into binary calls.

Use the `--note` field whenever you label `unsure`, and whenever a `degraded`
call rests on a single tie-break. Future-you doing inter-rater agreement will
need it.

---

## 5. Procedure

1. Read the manuscript title, section list, and word count shown by the CLI.
2. Read every durable revision task. For each, ask: *is this true of this paper,
   and could the author find the passage?*
3. Apply the swap test to the top-severity tier.
4. Apply tie-breaks T1–T6 in order.
5. Label. Add a note if the call was close.
6. Label in batches of ~20 with breaks. Fatigue produces drift, and drift in
   labels looks exactly like miscalibration in the gate.
