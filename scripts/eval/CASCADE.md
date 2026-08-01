# Cost/quality cascade: where the cliff actually is

Nine of the ten LLM call sites in the draft-analysis pipeline run
`gpt-5.2-chat-latest`. Only `editor_pass` runs `gpt-5-mini`, and it does so
because someone decided it should, not because anything measured it. This is the
measurement.

The result is not the one the question expects. **The cliff is not a quality
cliff, and it is not where the model tiers are.** It is a
`max_completion_tokens` cliff, and it is at the node's own configuration.

Run with `scripts/eval/cascade_arms.py`; append-only results in
`results/cascade_arms.jsonl`, keyed by a config hash that includes the per-node
model assignment.

---

## 1. Cost profile first

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

**Four nodes are 97.0% of spend.** Those four were swept; the other six were not,
because a 3% ceiling on the achievable saving does not justify the budget.

Two corrections to the brief's framing fall out of this table:

* The brief lists ten call sites in `nodes/*.py`. There is an **eleventh**, and
  it is the 12% node: `structural_checks` reaches its model through
  `app/services/structural_review.py:95`, outside the `nodes/` directory.
* Three of the listed sites — `citation_mapping`, `citation_judge`,
  `analysis_quality_judge` — **made no LLM calls at all** in eight full pipeline
  runs. Their paths are data-dependent and did not trigger. They cannot be
  swept, and their cost is not "small", it is unobserved.

---

## 2. What this instrument can and cannot resolve

It detects **cliffs, not margins**:

* quality CV ~95% at n=5 — `temperature` is stripped for `gpt-5.2*` and
  rejected outright by the cheap tiers; there is no seed;
* the confirmation judge disagrees with **itself** at κ 0.75–0.85, so every unit
  count carries a **±10% band** and is printed `N ± b`, never bare;
* only **76 of 212** hand-labelled units are `defect_addressable`, so **both
  denominators are always reported**.

So nothing below claims "no quality loss". It claims **"no detectable loss at
n=3"**, which is much weaker. **A node where the cheap model is 10% worse would
not show up in this measurement at all.**

`extract_claims` is not scored against the units at all: it emits *claims*, not
critiques, and matching claims against reviewer complaints measures nothing. It
is swept for cost and structural integrity only, and its quality is
**unmeasured** — not "unchanged".

---

## 3. Two failures found before any quality question could be asked

### 3.1 The cheap tiers reject `temperature=0`

Verified live, 2026-08-01:

```
gpt-5-nano  temperature=0 -> 400 Unsupported value: 'temperature' does not support 0
gpt-5-mini  temperature=0 -> 400 (identical)
gpt-5.1     temperature=0 -> OK
```

`_sanitize_structured_completion_kwargs` stripped that parameter only for
models matching `gpt-5.2`. `reviewer_panel` and `meta_reviewer` both pass
`temperature=0`, so **both would have failed 100% of calls on every cheap arm** —
which reads as "the cheap model is broken" rather than "the helper knew about
one model family". Fixed in `retry_utils` as a prefix allow-list of models
*observed* to reject the parameter, so no call that works today changes
behaviour. This was a latent trap, not a live bug: `editor_pass`, the one node
already on `gpt-5-mini`, passes no temperature at all.

### 3.2 The real cliff: reasoning tokens eat the completion budget

This is the finding. The cheap tiers are **reasoning models**. They spend
`max_completion_tokens` on reasoning before emitting any output, and the call
fails with nothing returned:

```
Could not parse response content as the length limit was reached -
CompletionUsage(completion_tokens=8000, prompt_tokens=13055,
  completion_tokens_details=CompletionTokensDetails(reasoning_tokens=8000, ...))
```

`reasoning_tokens == completion_tokens == the cap`. **The entire budget went to
reasoning and zero output tokens were produced.** Survival tracks the node's cap
almost perfectly:

| node | `max_completion_tokens` | `gpt-5-mini` | `gpt-5-nano` |
|---|---:|---|---|
| `structural_checks` | 1,500 | **3/3 failed** | **3/3 failed** |
| `meta_reviewer_node` | 2,000 | 1/3 failed | **3/3 failed** |
| `reviewer_panel_node` | 2,500 | see §4 | see §4 |
| `extract_claims` | 8,000 | 0/3 failed | 2/3 failed |

The node with the most generous budget is the only one where `gpt-5-mini` never
failed. This is not a statement about which node is "harder" — it is the cap.

---

## 4. Per-node results

All figures **n=3 papers** (the three the 212-unit gold covers), 1 repeat,
threshold 0.44. `$/run` is per replay.

| node | arm | $/run | tok/run | findings/run | units of 76 | units of 212 | structurally broken |
|---|---|---:|---:|---:|---|---|---|
| `reviewer_panel_node` (52%) | **control** | 0.02223 | 14,681 | 11.89 | **20 ± 2** | **48 ± 5** | no |
| | `gpt-5-mini` | 0.00000 | 0 | 1.00 | 0 ± 1 | 1 ± 1 | **YES — 9/9 calls failed** |
| | `gpt-5-nano` | 0.00000 | 0 | 1.00 | 0 ± 1 | 1 ± 1 | **YES — 9/9 calls failed** |
| `extract_claims` (23%) | **control** | 0.02295 | 13,368 | 11.33 | not scorable | not scorable | no |
| | `gpt-5-mini` | 0.00911 | 16,286 | 11.67 | not scorable | not scorable | no |
| | `gpt-5-nano` | 0.00094 | 4,510 | 2.67 | not scorable | not scorable | **YES — 2/3 failed** |
| `structural_checks` (12%) | **control** | 0.02364 | 7,040 | 2.67 | **2 ± 1** | **3 ± 1** | no |
| | `gpt-5-mini` | 0.00000 | 0 | 0.00 | 0 ± 1 | 0 ± 1 | **YES — 3/3 failed** |
| | `gpt-5-nano` | 0.00000 | 0 | 0.00 | 0 ± 1 | 0 ± 1 | **YES — 3/3 failed** |
| `meta_reviewer_node` (10%) | **control** | 0.01376 | 5,055 | 17.33 | **19 ± 2** | **39 ± 4** | no |
| | `gpt-5-mini` | 0.00260 | 3,930 | 12.00 | 17 ± 2 | 38 ± 4 | **YES — 1/3 failed** |
| | `gpt-5-nano` | 0.00000 | 0 | 0.00 | 0 ± 1 | 0 ± 1 | **YES — 3/3 failed** |

A `$0.00000/run` on a broken arm is not a saving. It is the accounting defect in
§5: those calls consumed their full completion budget and recorded nothing.

**Control reproduces.** `reviewer_panel_node`/control scored **20 ± 2** of 76 and
**48 ± 5** of 212, against **22 ± 3** and **54 ± 6** for the equivalent arm
recorded in `PANEL_SCOPING.md`. Both overlap within their bands, on a different
harness. Control was re-measured in the same process as its comparison arms.

### The one interesting row

`meta_reviewer_node` on `gpt-5-mini` matched **17 ± 2** of 76 against control's
**19 ± 2** — *overlapping bands, no detectable difference* — at **5.3× lower
cost**, while producing 12.0 findings/run against 17.33. But it did that on the
**2 of 3 papers where the call completed at all**. A one-in-three hard failure
rate disqualifies it regardless of what the surviving two scored, and n=2 is
below the point where this instrument resolves anything. Read it as *"mini looks
competent when it is allowed to finish"* — a hypothesis for the follow-up in §6,
not a result.

---

## 5. Accounting: the ledger under-reports twice

The brief flagged one defect (`record_usage` estimating tokens at `len//4`
against a corpus that tokenizes at ~3.4 chars/token). This sweep found a
**second, larger one**:

**A call that fails on the length limit records no usage at all.**
`record_response_usage` is only reached on success; the failure path raises
first. So every broken cheap-tier arm is billed for a full completion budget
(1,500–8,000 reasoning tokens per call) and **the ledger reports $0.0000**.

Reconstructed from the `CompletionUsage` the API returns inside the error text,
for the first six arms alone:

| arm | ledgered | unrecorded | failed calls |
|---|---:|---:|---:|
| `meta_reviewer` / mini | $0.0049 | $0.0100 | 2 |
| `meta_reviewer` / nano | $0.0000 | $0.0030 | 3 |
| `structural_checks` / mini | $0.0000 | $0.0133 | 3 |
| `structural_checks` / nano | $0.0000 | $0.0027 | 3 |
| `extract_claims` / nano | $0.0025 | $0.0077 | 2 |

The direction matters: it is exactly the **cheap, failing** arms that are
under-reported, so a naive reading of the ledger says "nano is nearly free" when
nano is in fact burning full completion budgets and returning nothing.

### Spend for this sweep

Budget `$6.00`, via `NOESIS_LLM_MAX_SPEND_USD` on every invocation.

| | amount |
|---|---:|
| node calls, recorded in the sink | $0.6446 |
| matcher/confirmation calls | ~$0.75 |
| **total ledgered** | **~$1.55** |
| unrecorded failed calls (§5, reconstructed) | +$0.1300 |
| **true total** | **~$1.68** |

Runs 1 and 3 printed exact ledger totals (`$0.3277`, `$0.6262` — the latter
confirmed against a `NOESIS_LLM_USAGE_LOG` ground-truth sink). Run 2's total was
never printed because the `match.py` crash in §7 killed the process before the
final line; its share is reconstructed from the sink plus the identical
re-run, so `~$1.55` carries perhaps `±$0.10`.

One number worth keeping: in run 3 the **matcher cost more than the nodes it was
scoring** — `$0.4260` of confirmation calls on `gpt-5.2` against `$0.2001` of
`reviewer_panel` node spend. Scoring, not sweeping, is the expensive half of
this harness.

---

## 6. Routing recommendation

**Ship nothing. No node tolerates a downgrade as the pipeline is configured
today.** Not one of the four expensive nodes can be moved to `gpt-5-mini` or
`gpt-5-nano` without breaking it.

| node | share of spend | verdict |
|---|---:|---|
| `reviewer_panel_node` | 51.9% | **stays on 5.2** — mini and nano both fail 9/9 |
| `extract_claims` | 23.1% | **stays on 5.2** — mini is clean and 60% cheaper, but its quality is *unmeasured* |
| `structural_checks` | 12.0% | **stays on 5.2** — mini and nano both fail 3/3 |
| `meta_reviewer_node` | 10.0% | **stays on 5.2** — mini fails 1/3 |

**The honest headline: this sweep did not measure a quality cliff, because the
cheap models never got far enough to have their quality judged.** Nine of the
twelve cheap-tier arms failed at the API boundary with zero output. "The cheap
model is worse" is *not* what was observed; "the cheap model never answered" is.

### The blocker is a config value, not a model

Every failure is the same: a reasoning model spends `max_completion_tokens` on
reasoning tokens and emits nothing. That is a property of the node's cap
(1,500–2,500 for three of the four nodes), not of the model's ability. **The
question "where is the quality cliff" is still open**, and this measurement
cannot close it.

### The follow-up that would close it

Not run here — it needs a second override (completion budget / `reasoning_effort`)
and is a separate change from model routing:

1. Raise `max_completion_tokens` on the three tight nodes, or set
   `reasoning_effort="low"`/`"minimal"` on the cheap arms, so the model has a
   budget to answer from.
2. Re-run this sweep unchanged.
3. Only then compare quality.

Until step 3, any claim about mini's quality on `reviewer_panel` or
`structural_checks` is unsupported — those arms produced **no data at all**.

### The prize, if it survives that test

`gpt-5-mini` is ~7× cheaper on input and output. The four swept nodes are 97.0%
of pipeline spend at `$0.1832`/run. If mini held quality across all four — **which
is exactly what is not yet known** — the pipeline would fall to roughly
`$0.03`/run, a ~**80%** saving. That number is the *upside being tested*, not a
result. The only measured saving available today is `$0.0000`, because every arm
that was cheaper was also broken.

---

## 7. What was changed, and what was not

**Production defaults are unchanged.** Every call site keeps the model it had;
`model_for(site, default)` is the identity function on that default when no
environment override is set.

| file | change |
|---|---|
| `app/workflows/draft_analysis/model_routing.py` | new — the override seam |
| `nodes/reviewer_panel.py` | 2 hardcoded strings → `model_for(...)`, same default |
| `nodes/claim_extraction.py` | 1 hardcoded string → `model_for(...)`, same default |
| `nodes/meta_reviewer.py` | 1 hardcoded string → `model_for(...)`, same default |
| `services/structural_review.py` | 1 hardcoded string → `model_for(...)`, same default |
| `services/retry_utils.py` | `temperature=0` strip extended to the tiers that reject it |
| `core/llm_budget.py` | price entries for `gpt-5-nano` and `gpt-5.1` |

The two price entries are not cosmetic: an unpriced model contributes **$0** to
`_total_usd`, so `NOESIS_LLM_MAX_SPEND_USD` cannot see it and every cost figure
quoting it is silently zero rather than visibly unknown. Both rates were
cross-checked against two official OpenAI pages, per the protocol already
documented in that file.

### A scoring crash used to discard paid measurements

`match.py` raised `RuntimeError: Missing confirmation for pair index 101` while
scoring the `reviewer_panel_node` control arm, *after* all nine replays had been
billed. Records existed only in memory, so the crash threw away the measurement
and kept the charge. Replays are now appended **before** scoring, and a scoring
failure is recorded as `score_error` on the arm rather than ending the batch.
`match.py` itself was not modified.

### Harness version 2

The first pass read `meta_review` keys (`priorities`, `key_concerns`) that the
node never writes — `MetaReviewOutput` defines `must_address`,
`nice_to_address`, `consensus_weaknesses` — and read `extracted_claims` where
the state key is `claims`. Both reported **zero findings for every arm**, which
reads as "all arms identical" rather than "the measurement is broken".
`HARNESS_VERSION` is part of the config hash, so the v1 rows remain in the
append-only sink and remain distinguishable rather than averaging with the
corrected ones. **v1 rows for `meta_reviewer_node` and `extract_claims` should
be ignored.**
