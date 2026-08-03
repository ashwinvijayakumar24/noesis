# Cost/quality cascade: where the cliff actually is

Nine of the ten LLM call sites in the draft-analysis pipeline run
`gpt-5.2-chat-latest`. Only `editor_pass` runs `gpt-5-mini`, and it does so
because someone decided it should, not because anything measured it.

**The answer has a shape: cheap for synthesis, expensive for generation.**
`meta_reviewer` — which *synthesises* three reviews into one verdict — runs on
`gpt-5-mini` at 5.4× lower cost with no detectable quality loss at n=9.
`reviewer_panel` — which *generates* the product's actual output — does not: it
fails 5 of 9 calls even after the blocking constraint is removed.

Run with `scripts/eval/cascade_arms.py`; append-only results in
`results/cascade_arms.jsonl`, keyed by a config hash that includes the per-node
model assignment and the reasoning effort.

---

## 1. Recommendation

| site | share of pipeline spend | verdict |
|---|---:|---|
| `meta_reviewer` | 10.0% | **MOVE to `gpt-5-mini` @ `reasoning_effort=low`** — 9/9 clean, 5.4× cheaper, no detectable quality loss at n=9 |
| `reviewer_panel` | 51.9% | **STAYS on 5.2** — 5/9 calls fail even at `reasoning_effort=low` |
| `extract_claims` | 23.1% | **STAYS on 5.2** — mini is clean and 60% cheaper, but its quality is **unmeasurable** by this instrument |
| `structural_checks` | 12.0% | **STAYS on 5.2** — untested at `reasoning_effort=low`; failed 3/3 without it |
| `reviewer_judge`, `editor_pass` | 3.1% | not swept — too small to fund |

**Combined saving from the one recommended move: ~8.2% of pipeline cost**
(`$0.01834` → `~$0.00338` per run, against a `$0.1832` pipeline). That is the
whole prize on the table today. It is real, and it is *not* the ~51% that moving
the panel would have bought.

**Moving `meta_reviewer` requires two changes, not one:** the model *and*
`reasoning_effort=low`. The model alone fails 1/3 of calls. Shipping the first
without the second reproduces the bug this document is about.

### What remains untested

* `structural_checks` (12.0%) at `reasoning_effort=low` — the obvious next spend
  and the only remaining candidate. Its 1,500-token cap is the tightest in the
  pipeline, so it is also the least likely to pass.
* `extract_claims` (23.1%) quality, at any tier. Needs a claim-extraction metric
  that does not exist; the review-unit gold cannot score it.
* `gpt-5.1` as a middle tier at any node. It accepts `temperature=0` and is ~29%
  cheaper than 5.2, but was skipped as low information per dollar.

---

## 2. Cost profile — which nodes were worth sweeping

Sweeping a node that costs nothing buys nothing. From
`results/checkpoint_bench_nodes.jsonl` — a full pipeline, **n=8 runs**,
`$1.4658` total, `$0.1832`/run:

| node | $/run | share | tok/run |
|---|---:|---:|---:|
| `reviewer_panel_node` | 0.09504 | **51.9%** | 47,757 |
| `extract_claims` | 0.04227 | **23.1%** | 14,291 |
| `structural_checks` | 0.02194 | **12.0%** | 6,919 |
| `meta_reviewer_node` | 0.01834 | **10.0%** | 5,614 |
| `reviewer_judge_node` | 0.00438 | 2.4% | 1,808 |
| `editor_pass_node` (already mini) | 0.00125 | 0.7% | 1,458 |
| 12 other nodes | 0.00000 | 0.0% | 0 |

**Four nodes are 97.0% of spend.** Those four were swept; the rest were not.

Two corrections to the original framing fall out of this table:

* There is an **eleventh** call site, and it is the 12% node: `structural_checks`
  reaches its model through `app/services/structural_review.py:95`, outside
  `nodes/`.
* Three of the named sites — `citation_mapping`, `citation_judge`,
  `analysis_quality_judge` — **made no LLM calls at all** in eight full runs.
  Their paths are data-dependent and did not trigger. Their cost is not "small",
  it is unobserved.

---

## 3. What this instrument can and cannot resolve

It detects **cliffs, not margins**:

* quality CV ~95% at n=5 — `temperature` is stripped for `gpt-5.2*` and rejected
  outright by the cheap tiers; there is no seed;
* the confirmation judge disagrees with **itself** at κ 0.75–0.85, so every unit
  count carries a **±10% band**, printed `N ± b`, never bare;
* only **76 of 212** hand-labelled units are `defect_addressable`, so **both
  denominators are always reported**.

Nothing here claims "no quality loss". It claims **"no detectable loss at n=N"**.
**A node where the cheap model is 10% worse would not show up at all.**

### The instrument's own drift, measured

The `reviewer_panel` control was run twice, in two sessions, identical config:

| session | units of 76 | units of 212 |
|---|---|---|
| A | 20 ± 2 | 48 ± 5 |
| B | 15 ± 2 | 40 ± 4 |

**The control moved 25% between sessions, outside its own band.** That is why
every comparison here is same-session, and why cross-session unit counts in this
document are not comparable to each other. It also bounds what any single arm
can prove.

### The diversity confound — read before any unit count

The metric counts **distinct units matched across pooled replays**, which
rewards an arm that repeats itself less, independently of whether any individual
finding is better. **This design cannot separate diversity from quality.** It is
reported alongside every score (`raw_findings`, `unique_texts`,
`repetition_rate`) rather than acknowledged afterwards.

The confound is **strongest for `reviewer_panel`**, where three personas generate
independently and are more diverse than one synthesiser by construction.

`extract_claims` is not scored at all: it emits *claims*, not critiques.

---

## 4. The mechanism: reasoning tokens eat the completion budget

Before quality could be asked, two failures had to be cleared.

### 4.1 The cheap tiers reject `temperature=0`

Verified live, 2026-08-01: `gpt-5-nano` and `gpt-5-mini` both return
`400 Unsupported value: 'temperature' does not support 0`; `gpt-5.1` accepts it.
`_sanitize_structured_completion_kwargs` stripped that parameter only for
`gpt-5.2*`. `reviewer_panel` and `meta_reviewer` both pass it, so **both would
have failed 100% of calls on every cheap arm** — reading as "the cheap model is
broken" rather than "the helper knew one model family". Fixed in `retry_utils`
as a prefix allow-list of models *observed* to reject it, so no call that works
today changes behaviour. Latent, not live: `editor_pass`, already on
`gpt-5-mini`, passes no temperature.

### 4.2 The real cliff

The cheap tiers are **reasoning models**. They spend `max_completion_tokens` on
reasoning before emitting anything:

```
Could not parse response content as the length limit was reached -
CompletionUsage(completion_tokens=8000, prompt_tokens=13055,
  completion_tokens_details=CompletionTokensDetails(reasoning_tokens=8000, ...))
```

`reasoning_tokens == completion_tokens == the cap`. **The entire budget went to
reasoning; zero output tokens were produced.** With no `reasoning_effort` set,
survival tracked the cap:

| node | `max_completion_tokens` | `gpt-5-mini` | `gpt-5-nano` |
|---|---:|---|---|
| `structural_checks` | 1,500 | 3/3 failed | 3/3 failed |
| `meta_reviewer_node` | 2,000 | 1/3 failed | 3/3 failed |
| `reviewer_panel_node` | 2,500 | 9/9 failed | 9/9 failed |
| `extract_claims` | 8,000 | 0/3 failed | 2/3 failed |

Nine of twelve cheap-tier arms produced **no data**. That is a blocked
experiment, not a negative result — so the constraint was removed.

### 4.3 The lever: `reasoning_effort`, not a bigger cap

Two levers existed and they are not equivalent. Raising
`max_completion_tokens` papers over the mechanism with headroom **and changes
the arm's cost basis**, so a cost delta against a control at the old cap is no
longer like-for-like. Setting `reasoning_effort` targets the mechanism and
leaves the cap identical on both sides.

**`reasoning_effort` was used. `max_completion_tokens` is unchanged everywhere.**
Control and arm run the same cap, prompt and node; the only difference is that
the arm is told not to spend that shared budget on reasoning. No confound to
declare.

Verified before committing to it, on the 1,500-token cap that failed 3/3:

| model | effort | reasoning/total | parsed |
|---|---|---:|---|
| `gpt-5-mini` | *(none)* | 448/708 | ✓ |
| `gpt-5-mini` | `low` | **64**/258 | ✓ |
| `gpt-5-nano` | *(none)* | 896/1086 | ✓ |
| `gpt-5-nano` | `low` | **128**/278 | ✓ |
| `gpt-5.2-chat-latest` | `low` | **400 — unsupported** | — |

`low` was chosen over `minimal` so a failure could not be blamed on crippling
the model. **The control rejects the parameter**, which settles "same basis": it
cannot be applied symmetrically, so it is applied to neither the cap nor the
control — only to how the arm spends its own budget.

Injected at the SDK boundary by the harness, scoped by model name, **zero
production edits**. `reasoning_effort` is an experimental lever, not a routing
decision; wiring it through five call sites for an experiment would leave a
half-configured parameter in production if the answer were "don't ship". That it
reaches the SDK is pinned by a test — the nesting is subtle enough that a first
hand-written probe got it wrong, and a silently-unapplied parameter would have
turned §5.2 into a false negative.

---

## 5. Results

### 5.1 `meta_reviewer_node` — synthesis. Passes.

n=9 replays/arm (3 papers × 3 repeats), same cap (2,000) both sides, same session:

| | control (5.2) | `gpt-5-mini@low` |
|---|---|---|
| replays OK | 9/9 | **9/9** |
| structurally broken | no | **no** |
| findings/run | 15.78 | 16.44 |
| units of **76** | **24 ± 3** | **35 ± 4** |
| units of **212** | **61 ± 7** | **70 ± 7** |
| raw / unique texts | 142 / 132 (93% unique) | 148 / **147 (99% unique)** |
| $/run | 0.01520 | **0.00280** (5.4× cheaper) |

**Structurally fixed:** mini went from 1/3 calls failing to **0/9**, cap
untouched. That confirms §4.2 — the failure was reasoning eating the budget, not
inability to do the task.

**Do not read 24 → 35 as "the cheap model is better."** The arm produced 147
unique texts from 148 findings (99%) against the control's 132 from 142 (93%) —
30% more candidate pairs. Part of the gap is diversity, and this design cannot
separate it from quality. Normalising by unique text, all-212 is near flat
(0.462 vs 0.476) while addressable-76 still favours the arm (0.182 vs 0.238) — a
sanity check, not a validated metric.

**Supportable:** no detectable quality loss at n=9 on either denominator, 5.4×
cheaper, zero structural failures. **Not supportable:** that it is better.

### 5.2 `reviewer_panel_node` — generation. Fails.

n=9 replays/arm (3 papers × 3 personas), same cap (2,500) both sides, same
session:

| | control (5.2) | `gpt-5-mini@low` |
|---|---|---|
| calls failed | **0/9** | **5/9** |
| structurally broken | no | **YES** |
| findings/run | 11.00 | 4.89 |
| raw / unique texts | 99 / 70 | 44 / 34 |
| units of **76** | 15 ± 2 | 10 ± 1 |
| units of **212** | 40 ± 4 | 22 ± 3 |
| $/run | 0.02398 | 0.00246 |

Every failure carries the same signature at the same cap:
`reasoning_tokens = 2500 = completion_tokens`, on prompts of **14,325–16,725
tokens**.

**`reasoning_effort=low` helped and was not enough.** Failures fell from 9/9 to
5/9 — the lever demonstrably applies, verified at the SDK boundary — but a 56%
failure rate is not a candidate for anything.

**The quality row is void and should not be quoted.** With 5 of 9 calls
returning nothing, the arm produced 44 raw findings against the control's 99.
`10 ± 1` versus `15 ± 2` measures how often the model answered, not how well.

**Per-persona — they do not move together:**

| persona | control | `gpt-5-mini@low` |
|---|---|---|
| clarity | 12 ± 2 | 7 ± 1 |
| methodology | 3 ± 1 | 4 ± 1 |
| literature_positioning | 2 ± 1 | **0 ± 1** |

`literature_positioning` collapses to zero while `methodology` is flat within
band. A single pooled number would have hidden that entirely.

### 5.3 Why generation fails where synthesis passes

The two nodes differ on both axes that matter:

| | `meta_reviewer` | `reviewer_panel` |
|---|---|---|
| task | synthesise 3 reviews | generate review from manuscript |
| prompt size | ~4,000 tokens | **14,325–16,725 tokens** |
| cap | 2,000 | 2,500 |
| outcome at `low` | 0/9 fail | **5/9 fail** |

Synthesis over pre-digested summaries fits the budget; generation over a full
manuscript does not. **The cap is not the whole story — the panel's cap is
*larger* and it still fails.** The task genuinely needs more reasoning than
`low` produces at that input size.

This is also the node where a degradation would matter most: it is where the
product's actual output comes from. A 56% failure rate there is not a marginal
result to be traded off, and the cap was **not** escalated to make something
pass — that would convert a clean negative into an unfalsifiable one. The clean
negative is the more useful result, because it gives the cascade its shape.

---

## 6. Accounting: the ledger under-reports, and the gap is a signal

Two defects, one previously known (`record_usage` estimating tokens at `len//4`
against a corpus that tokenizes at ~3.4 chars/token) and one found here:

**A call that fails on the length limit records no usage at all.**
`record_response_usage` is only reached on success; the failure path raises
first. So a broken arm is billed for a full completion budget and **the ledger
reports `$0.0000`**. The direction is the problem: it is exactly the cheap,
failing arms that are under-reported, so a naive reading says "nano is nearly
free" when nano is burning full budgets and returning nothing.

**The gap between ledgered and true spend is a direct proxy for how broken an
arm is:**

| run | ledgered | unrecorded | true | failure rate |
|---|---:|---:|---:|---|
| original 12-arm sweep | ~$1.55 | +$0.1300 | ~$1.68 | 9/12 arms broken |
| `meta_reviewer` @ low | $1.8883 | **+$0.0000** | $1.8883 | **0/9 calls** |
| `reviewer_panel` @ low | $0.7175 | +$0.0446 | $0.7621 | 5/9 calls |

A clean arm and an honest ledger are the same event.

**This round's spend: `$0.7175` ledgered, `$0.7621` true**, of a `$3.00` budget —
stopped early because the result was a clean negative, not because the money ran
out. Cumulative across the whole cascade investigation: ~`$4.34` true.

One number worth keeping: **the confirmation judge costs more than the nodes it
scores** — `$0.4795` against `$0.2379` of node spend in the panel run, and 85% of
spend in the `meta_reviewer` run. Scoring, not sweeping, is the expensive half of
this harness, and it is why each round bought one node at a real `n` rather than
three at n=2.

---

## 7. What was changed, and what was not

**Production defaults are unchanged.** Every call site keeps the model it had;
`model_for(site, default)` is the identity function on that default with no
override set. `reasoning_effort` exists only in the harness.

| file | change |
|---|---|
| `app/workflows/draft_analysis/model_routing.py` | new — the override seam |
| `nodes/reviewer_panel.py` | 2 hardcoded strings → `model_for(...)`, same default |
| `nodes/claim_extraction.py` | 1 hardcoded string → `model_for(...)`, same default |
| `nodes/meta_reviewer.py` | 1 hardcoded string → `model_for(...)`, same default |
| `services/structural_review.py` | 1 hardcoded string → `model_for(...)`, same default |
| `services/retry_utils.py` | `temperature=0` strip extended to the tiers that reject it |
| `core/llm_budget.py` | price entries for `gpt-5-nano` and `gpt-5.1` |

The price entries are not cosmetic: an unpriced model contributes **$0** to
`_total_usd`, so `NOESIS_LLM_MAX_SPEND_USD` cannot see it and every cost figure
quoting it is silently zero rather than visibly unknown. Both rates were
cross-checked against two official OpenAI pages, per the protocol already
documented in that file.

### A scoring crash used to discard paid measurements

`match.py` raised `RuntimeError: Missing confirmation for pair index 101` while
scoring an arm, *after* all nine replays had been billed. Records existed only
in memory, so the crash threw away the measurement and kept the charge. Replays
are now appended **before** scoring, and a scoring failure is recorded as
`score_error` rather than ending the batch. This paid for itself immediately: a
later run exhausted its budget during the control's scoring, and the fix
preserved 9 paid replays that would otherwise have been lost. `match.py` itself
was not modified.

### Harness version 2

The first pass read `meta_review` keys (`priorities`, `key_concerns`) the node
never writes — `MetaReviewOutput` defines `must_address`, `nice_to_address`,
`consensus_weaknesses` — and read `extracted_claims` where the state key is
`claims`. Both reported **zero findings for every arm**, which reads as "all arms
identical" rather than "the measurement is broken". `HARNESS_VERSION` is part of
the config hash, so v1 rows remain in the append-only sink and remain
distinguishable. **v1 rows for `meta_reviewer_node` and `extract_claims` should
be ignored.**

### A note on the sink

Hash `839c47b55c04` appears twice: the first attempt spent its budget on the
control's scoring and was blocked before scoring the arm (`score_error` set,
`score` null); the second re-measured the same config and scored it. Same
config, two measurements, distinguishable by `score_error` — the append-only
sink behaving correctly, not a collision.
