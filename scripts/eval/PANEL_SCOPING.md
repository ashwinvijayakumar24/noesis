# Per-reviewer section scoping — `DRAFT_REVIEWER_SCOPED_PANEL`

Measured 2026-08-01. Tool: `scripts/eval/panel_arms.py`. Results append to
`scripts/eval/results/panel_arms.jsonl`, keyed by a config hash that includes
the flag. Branch `dev/harness-and-retrieval`; the flag itself is S1's commit
`aa5c6b4`.

---

## Read this before quoting any number below

**1. The build scope's premise was false, and it was false for free.**

The scope doc (`private/BUILD_SCOPED_PANEL.md` §1) asserts:

> ~27% of the manuscript is discarded before any reviewer sees it, and it is
> always the tail.

It is not. `_reviewer_manuscript_text()` reads:

```python
if not reviewer_compaction_enabled():
    return draft_content or ""
return _section_excerpts(draft_content or "")[:REVIEWER_MANUSCRIPT_MAX_CHARS]
```

`DRAFT_REVIEWER_COMPACT_MANUSCRIPT` is **off by default** and is set nowhere in
this repo — not in `infra/`, not in `.env`, not in CI, and `docs/MEASUREMENTS.md:1847`
records it as off for the last measured run. The 24,000-char cap lives *inside*
the compaction branch and **never fires in production**. Measured against the
committed fixtures, at $0:

| paper | manuscript | reviewer receives | discarded | tail delivered |
|---|---|---|---|---|
| `10eQ4Cfh8p` | 31,363 chars | 31,363 | **0 (0.0%)** | yes |
| `kKRbAY4CXv` | 49,589 chars | 49,589 | **0 (0.0%)** | yes |
| `cXs5md5wAq` | 57,801 chars | 57,801 | **0 (0.0%)** | yes |

Two further corrections while we are here. The scope doc says manuscripts run
"~33,000 chars"; on this corpus they run 31k–58k. And even with compaction *on*,
`_section_excerpts()` is not a head-first truncation — it selects up to 7 named
sections and explicitly wants `discussion`, `conclusions` and `limitations`. So
"always the tail" is wrong twice: the tail is not cut on the shipped path, and
it would not be the thing cut on the compaction path either.

**Consequence: the control arm is "three reviewers × the full manuscript", not
"three × a head-truncated one."** Every number below is measured against that
control. `panel_arms.py` refuses to run if compaction is on, because then the
control would be a path nobody takes and the delta against it would mean nothing.

**2. The hypothesis that survives is a different one.** Not "scoping restores
text that truncation removed" — nothing was removed. The live question is the
one the companion agent harness actually tested: **does per-reviewer context
isolation beat three passes over identical full text?**

**3. This is node replay, not a full pipeline run.** `panel_arms.py` replays
`reviewer_panel_node` from the committed state fixtures, so every upstream node
is byte-identical between arms — which is what "the arms differ only by the
flag" requires. A full-pipeline arm would let upstream nondeterminism leak into
the delta and would cost roughly an order of magnitude more than the $5 budget.
The cost of the choice: this measures the *panel's* prompt-cache behaviour, not
the whole graph's, and a scoping change that shifted downstream node cost would
not be visible here.

---

## The trade, before any money was spent

Prompt assembly is pure string manipulation, so the cost side of this experiment
is fully determined and does not need to be bought. Measured over the three
labelled manuscripts, all three personas, both flag states:

| | assembled input | cacheable shared prefix |
|---|---|---|
| flag **off** | 457,089 chars | 144,279 chars |
| flag **on** | **229,035 chars (−49.9%)** | **6,200 chars (4.3% surviving)** |

This is the whole tension in two rows. The manuscript *was* the shared prefix,
so making it vary per persona necessarily forfeits ~96% of the prefix that calls
2 and 3 were billing at the cached rate — while also sending roughly half as
much text overall.

Neither number alone is the result. Quoting only −49.9% makes scoping look free;
quoting only "4.3% of the prefix survives" makes it look purely costly. **Which
one wins is a dollar question, and dollars are what the arms below measure.**

(S1 reports −55% / 9.3% prefix survival across all 15 fixtures. This table is
the 3 labelled papers only — the ones the 212-unit gold covers — so the two are
consistent, not conflicting.)

### Where the −49.9% comes from, and why it is not free

The build's own acceptance criterion (§6) is:

> Union of scoped sections covers the manuscript; asserted by test.

Measured, at $0, on the real fixtures — what fraction of each manuscript reaches
**at least one** of the three personas:

| paper | manuscript | scoped union coverage |
|---|---|---|
| `10eQ4Cfh8p` | 31,363 chars | **99.7%** |
| `kKRbAY4CXv` | 49,589 chars | **71.1%** |
| `cXs5md5wAq` | 57,801 chars | **63.6%** |

Re-measured at half the window width (40 chars) the figures are 99.9% / 73.8% /
64.8%, so this is not an artefact of windows straddling section boundaries — it
is real text loss.

**The per-persona budget still totals the same 24,000 chars, and it binds on any
manuscript larger than that.** On a 31k paper the lanes fit and coverage is
complete. On a 50–58k paper, a third of the manuscript reaches no reviewer at
all. The off arm sends 100% by construction.

So roughly half of the "−49.9% input" is not a redundancy saving; on the two
larger papers it is text nobody reads. This has a direct consequence for how the
quality arms below must be read: **a yield drop on `kKRbAY4CXv` or `cXs5md5wAq`
is confounded between context isolation and plain text loss, and the two cannot
be separated at this budget.** `10eQ4Cfh8p` is the only paper in this corpus
where the on arm is a clean test of isolation.

The irony is worth stating plainly: the build set out to fix a head-truncation
that does not exist, and in doing so introduces one that does.

---

## Method

- **Arms.** `off` = flag unset (shipped default). `on` = `DRAFT_REVIEWER_SCOPED_PANEL=1`.
  One process, same manuscripts, same order.
- **n.** A *run* is one full panel over one manuscript — all three personas.
  3 papers × 2 replicates = **n = 6 runs per arm**, 18 LLM calls per arm.
- **Scoring.** The ceiling study's label set and taxonomy verbatim
  (`ceiling/hand_labels.json`, 212 units, 76 `defect_addressable`) and the real
  matcher at its calibrated `COS_THRESHOLD = 0.44`. Findings are pooled across
  an arm's replicates before matching, exactly as `score_ceiling.run` pools
  across recorded runs, so "units matched" is each arm's best case.
- **Bands.** Every unit count carries `±ceil(10%)`, as `RECAL` used. The
  confirmation judge disagrees with itself at κ 0.75–0.85; a bare integer would
  imply a precision the instrument does not have.
- **Identity.** Config hash includes `flag_name` *and* `flag_value`, and
  `assert_arms_separate()` refuses to run if the two arms collide. Strip the
  flag from the config and the two arms hash identically — there is a test that
  asserts exactly that, because this project has had seven incidents of two
  different things sharing one identity.
- **Fabrication.** Unverified-quote rate uses the production oracle
  (`draft_evidence_gate._is_verbatim`), not a private reimplementation.

### The mechanism check

A headline delta means nothing without knowing *where* it landed. Two readings
have to be ruled out:

- **A uniform rise across all three personas is not context isolation.**
  Isolation acts on personas differently by construction. A flat rise points at
  run-to-run variance or at something else in the prompt.
- **A up, D down is the section map, not the hypothesis.** Reviewer D's declared
  duties — terminology consistency *throughout*, argument structure, reporting
  completeness — are properties of the whole document. Only `abstract` and
  `limitations` are sectional for D, so under any sectional map D is carried
  almost entirely by the unclaimed-goes-to-everyone rule and would lose context
  whether or not isolation helps anybody.

### One risk worth naming

The system preamble's GROUNDING RULE asserts *"The FULL manuscript text is
provided below"*. Under scoping that sentence is **false** — and S1 could not
change it without breaking the byte-identical shared prefix that the off arm
depends on. The scoped manuscript block carries its own header telling the
reviewer that other sections belong to other reviewers, but a reviewer told the
full text is present while holding a subset is precisely the setup that produces
confident claims about material it cannot see. The unverified-quote rate is the
instrument for this and is reported for both arms.

---

## Results

`n = 6` runs per arm (3 papers × 2 replicates), 18 LLM calls per arm, 0 errors.
Config hashes `off = 155353393c1d`, `on = f71c721014e7` — **distinct**, asserted
before the run. Total spend **$1.6376**.

### Quality — flat

| metric (`n=6`/arm) | off | on | delta |
|---|---|---|---|
| distinct units matched, of **76 addressable** | **22 ± 3** | **24 ± 3** | +2 |
| distinct units matched, of **all 212** | **54 ± 6** | **50 ± 5** | −4 |
| severity-weighted recall vs 76 | 0.2733 | 0.2791 | +0.0058 |
| severity-weighted recall vs 212 | 0.2547 | 0.2210 | −0.0337 |
| unverified-quote rate | **0/62 = 0.0** | **0/67 = 0.0** | 0 |

Both unit deltas sit **inside their own ±10% bands**, and they point in opposite
directions depending on the denominator. There is no quality effect here that
this instrument can resolve.

The fabrication risk did not materialise: despite the GROUNDING RULE telling the
scoped reviewer that "the FULL manuscript text is provided below" when it is
not, every anchored quote in both arms was verbatim. Zero events in either arm,
so Fisher is degenerate — nothing to test, and no evidence of harm.

### The mechanism check — the hypothesis fails here

| persona | findings off → on | addressable units off → on |
|---|---|---|
| **A** `literature_positioning` (sectional lane) | 23 → 24 (+1) | **8 → 5 (−3)** |
| **B** `methodology` | 20 → 24 (+4) | **4 → 11 (+7)** |
| **D** `clarity` (cross-cutting lane) | 19 → 19 (0) | **16 → 13 (−3)** |

**The gain is entirely Reviewer B's, and Reviewer A — the persona whose lane is
most cleanly sectional — lost ground.**

The prediction was that scoping concentrates each reviewer on its own lane and
that the sectional personas benefit. What actually happened is redistribution:
B's lane (methods, results) is the largest and densest region of these
manuscripts, so a per-lane budget hands B more of what it needs and takes from
everyone else. A fell 3, D fell 3, B rose 7.

D falling is the artefact the section map predicts — its duties are
cross-cutting, so any sectional map starves it. **But A falling is not
predicted by anything in the hypothesis.** If context isolation were the
mechanism, A is the persona that should have moved first and up. It moved down.

So the +2 on the addressable denominator, already inside its band, is not
evidence for scoping. It is one persona's lane getting a bigger share of a fixed
budget.

### Cost — the trade, and it does not net out the way the input number suggests

| | off | on | delta |
|---|---|---|---|
| input tokens / run | 39,816 | **22,016** | **−44.7%** |
| prompt-cache hit rate (measured) | 95.1% | 85.7% | −9.4 pts |
| $ / run (measured) | $0.07253 | $0.06841 | **−5.7%** |
| $ / verified finding (absolute) | **$0.01978** | **$0.01710** | −13.6% |

Cache hit rate came from the API's own `usage.cached_tokens` via `llm_budget`,
reported for every call; `cache_reported` is `true` for both arms.

**Read the −5.7% carefully — it is an artefact of the measurement design.** Two
replicates per paper means the second replicate of *both* arms is an exact
prompt repeat and bills almost entirely at the cached rate. That inflates both
hit rates (95.1% and 85.7%) far above what a real panel sees, and it compresses
the gap between them. A production run analyses one draft once, cold.

Modelling a cold single panel from the same token counts, at the published rates
($1.75 / $0.175 / $14.00 per 1M), using the measured cross-persona hit rates for
that case — 60.7% for the off arm (`docs/MEASUREMENTS.md`) and 4.3% for the on
arm (the surviving prefix measured above):

| cold single panel | input/run | cached | modelled $/run |
|---|---|---|---|
| off | 39,816 | 60.7% | **$0.09410** |
| on | 22,016 | 4.3% | **$0.09662** |

**Cold, scoping costs 2.7% *more* — while sending 44.7% fewer input tokens.**
The forfeited shared prefix more than consumes the entire input saving. This is
modelled, not measured, and is labelled as such; the measured warm numbers are
in the table above it.

That is the actual finding of this build: **the manuscript was the cache, and
you cannot both scope it and keep it.**

### Off-arm reproduction

The off arm reproduces the recorded behaviour of `reviewer_panel_node` on these
manuscripts:

| | recorded (`checkpoint_bench_nodes.jsonl`, same 3 papers, n=6) | off arm now (n=18 calls) |
|---|---|---|
| prompt tokens / call | 12,701 mean (range 8,657–16,725) | 13,272 mean |
| $ / call | $0.0297 | $0.0242 |

+4.5% on prompt tokens, comfortably inside the recorded range. The lower $/call
is the replicate-2 cache effect described above, not a behaviour change. **The
comparison is valid.**

---

## Verdict

**Do not ship. Keep `DRAFT_REVIEWER_SCOPED_PANEL` default off.**

1. **Quality is flat.** Both unit deltas are inside their ±10% bands and change
   sign with the denominator.
2. **The mechanism check fails.** The gain is one persona's (B, +7), while the
   persona the hypothesis names (A) *lost* 3. That is budget redistribution, not
   context isolation.
3. **The cost saving is smaller than it looks and probably negative in
   production.** −44.7% input yields −5.7% warm and a modelled **+2.7% cold**.
4. **It introduces a real coverage regression.** On manuscripts above ~31k
   chars, 26–36% of the text reaches no reviewer at all — against the build's own
   acceptance criterion, and it is the very failure the build was meant to fix.

The honest bullet is the third one from the scope doc's §8, with a correction:

> Tested whether per-reviewer section scoping would raise reviewer-panel yield.
> It did not — yield was flat within ±10% bands and the only per-persona gain
> was one reviewer's lane taking budget from the other two. Establishing this
> also corrected the premise: the shipped panel does not truncate the manuscript
> at all, so the 24k head-truncation the work was scoped against did not exist.
> Measured the cost trade the change would have forced — 45% less input against
> 96% of the cross-persona cache prefix, netting **+2.7% more expensive** on a
> cold panel. Shipped behind a flag, default off.

### What would change the answer

The per-persona budget is the confound. It is fixed at the same 24,000 chars in
total, which binds on any manuscript larger than that and makes the on arm lossy
on 2 of these 3 papers. A scoped arm with a *per-persona* budget large enough to
cover each lane in full would separate isolation from text loss — and would also
raise the on arm's input, shrinking the only column where scoping currently wins.
That is the experiment worth running before this idea is revisited.

---

## Reproducing

```bash
cd scripts/eval

# The $0 audit: control-arm characterisation + the assembly trade. No LLM calls.
python3 panel_arms.py --audit-only

# Both arms, n=6 each. Real spend.
NOESIS_LLM_MAX_SPEND_USD=4.50 python3 panel_arms.py --replicates 2 --yes
```

`--audit-only` is worth running on its own: it settles the premise and measures
the entire cost side without spending anything.
