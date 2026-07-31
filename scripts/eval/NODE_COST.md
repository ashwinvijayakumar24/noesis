# Node replay cost — the first complete measurement

Measured 2026-07-31. Tool: `scripts/eval/node_eval.py`. Results appended to
`scripts/eval/results/node_eval.jsonl` (run ids `f0af0ecb5365`, `9c11daa01698`,
`82092c60b36c`, `dc045ccaaadb`).

## Every cost figure produced before this run was a lower bound

Not "approximately right" — **low by a margin that cannot be recovered**.

`scripts/eval/match.py` computes the severity-weighted-recall metric and makes
two kinds of network call: an embedding batch and one or more GPT confirmation
calls. Until 2026-07-30 it called the OpenAI client directly. Those calls were:

* not recorded by `llm_budget`, so they appeared in no total this harness printed;
* not bounded by `NOESIS_LLM_KILL_SWITCH`, `EVAL_REPLAY_ONLY`,
  `NOESIS_LLM_MAX_CALLS` or `NOESIS_LLM_MAX_SPEND_USD`.

The margin is unrecoverable rather than merely unknown. The matcher's disk
caches (`cache/match/embed`, `cache/match/confirm`) store an embedding vector
and a `{confirmed, reason}` verdict respectively — no prompt text, no usage
block, no model. There is nothing on disk from which the missing token counts
could be reconstructed. The most-quoted prior figure, **$0.21999** for a
three-invocation node-replay exercise, made **6 uncounted matcher calls** (3
embed + 3 confirm, visible only as counters in `match_stats`) and reported
$0.00 for all of them.

The matcher is now guarded and recorded (`match._match_label` composes
`match:` with the ambient node label). This run is therefore the first complete
figure the harness has produced.

`node_eval.replay_once` now slices `llm_budget` twice per replay: `usage` is
what the node spent inside its span, `match_usage` is what scoring its output
spent afterwards. Both are in the run total. `run_summary.spend_by_label`
carries per-label dollars so the total is reconcilable against its own
breakdown — the property that was silently false before, since node-only totals
could never have summed to the money actually being spent.

### Still outside the accounting

`scripts/eval/atomize_reviews.py` (gold-side atomization) also calls OpenAI
directly and is still neither guarded nor recorded. It contributed **$0.00 to
this run**: `score_replay` now returns `atomize_stats`, and every replay
reported `{"cache_hits": 4, "llm_calls": 0}` — the atomize cache was fully warm
for all three papers. That is luck, not a guarantee. It is the one remaining
bypass and it should be wired up the same way `match.py` was.

## Total

| | node | matcher | total |
|---|---|---|---|
| recorded spend | $0.16761 | $0.03255 | **$0.20016** |
| share | 83.7% | **16.3%** | 100% |

**Matcher spend is 16.3% of the complete figure** — that is exactly the margin
older numbers were missing, and it is not uniform. It scales with how many
items a node emits, not with what the node cost:

| node | node $ | matcher $ | matcher share |
|---|---|---|---|
| `run_quality_diagnostics` | $0.00000 | $0.00277 | **100%** |
| `editor_pass_node` | $0.00339 | $0.00297 | **46.7%** |
| `reviewer_panel_node[methodology]` | $0.12098 | $0.02682 | 18.1% |

A node the old accounting reported as **free** costs $0.00277 to measure. The
cheaper the node, the worse the old figure was in relative terms.

Against the prior exercise: the old $0.21999 was node spend only. On these
replays the matcher runs about **$0.005 per scored `reviewer_panel_node`
replay**, so the prior metric-enabled run (`4ce7276cc133`, 3 replays, reported
$0.06256) was short by roughly **$0.015, about 19% of its true cost**.

## Per-node

Same shape as the prior table. All figures from run ids above; `wall` is summed
node span time (matcher time is outside the span, as before).

| node | n | wall | LLM calls | input (cached) | node $ | matcher $ | matcher calls | total $ |
|---|---|---|---|---|---|---|---|---|
| `reviewer_panel_node[methodology]` | 5 | 96.43s | 5 | 46,120 (36,352) | $0.12098 | $0.02682 | 10 | **$0.14779** |
| `reviewer_panel_node[literature_positioning]` | 1 | 19.52s | 1 | 8,697 (8,064) | $0.02251 | — | 0 | $0.02251 |
| `reviewer_panel_node[clarity]` | 1 | 16.64s | 1 | 8,657 (8,064) | $0.02073 | — | 0 | $0.02073 |
| `editor_pass_node` | 3 | 23.35s | 3 | 2,682 (0) | $0.00339 | $0.00297 | 2 | **$0.00636** |
| `run_quality_diagnostics` | 3 | 0.18s | 0 | 0 | $0.00000 | $0.00277 | 3 | **$0.00277** |

Model: `gpt-5.2-chat-latest` for nodes, `gpt-5.2` + `text-embedding-3-small`
for the matcher. Embedding spend is negligible ($0.000029 across the whole
run); essentially all matcher cost is the confirmation call.

The two single-persona panel rows ran `--no-metric` (they exist to measure
prefix caching, not quality), hence no matcher spend.

### Comparability with the prior table

* `editor_pass_node` and `run_quality_diagnostics` are the identical selection
  (same 2 nodes × same 3 papers). `editor_pass_node` consumed **exactly 2,682
  prompt tokens both times** — the fixtures are deterministic inputs, so the
  only movement is on the output side ($0.00399 → $0.00339, 1,360 completion
  tokens this time).
* The panel row is **not** the same composition. The prior `n=5` mixed two
  papers (`10eQ4Cfh8p` and the much larger `9ceadCJY4B`, which alone accounted
  for 53,535 of the prior 90,215 input tokens). This run is 5 × `10eQ4Cfh8p`,
  deliberately, so latency variance is measured on one fixture instead of being
  confounded by fixture size. Compare per-call, not row totals.

### Does the corpus change affect comparability?

No, for this selection. The database went from 118 documents / 4 topics to
5,948 chunks / 344 documents / 15 topics. That is irrelevant here because:

* node fixtures are JSON on disk and already contain whatever evidence the node
  saw upstream — a replayed `reviewer_panel_node` does not re-query the corpus;
* the matcher embeds critique text and gold review units, not corpus chunks,
  and its embedding cache is keyed on text, not on database state.

It **would** matter for `search_literature`, `detect_gaps` or
`discover_external_sources`, which query live. None of those are in this
selection, and a future cost comparison that includes them is not comparable
across the corpus change.

## What the prefix-caching reorder actually bought

The panel prompt was reordered so the shared preamble and manuscript come first
and the persona block last, giving a byte-identical prefix across all three
personas. The 58.8% hit-rate figure came from a purpose-built A/B. Here is what
it does on the normal replay path.

Replaying one persona at a time, on paper `10eQ4Cfh8p`:

| call | prompt | cached | hit rate | $ |
|---|---|---|---|---|
| methodology #1 (nothing warm) | 9,224 | 0 | 0.0% | $0.035224 |
| methodology #2–#5 (same persona again) | 9,224 | 9,088 | 98.5% | $0.02071 / $0.02027 / $0.02395 / $0.02083 |
| clarity (persona never sent before) | 8,657 | 8,064 | **93.2%** | $0.020733 |
| literature_positioning (ditto) | 8,697 | 8,064 | **92.7%** | $0.022511 |

The load-bearing rows are the last two. Those personas' prompts had **never**
been sent, yet 8,064 tokens came back cached — that is the shared prefix, and
nothing but the reorder puts it there. 8,064 tokens is 87.4% of the
methodology prompt, against the 85% the A/B claimed (8,064 = 63 × 128, i.e. it
is quantised to OpenAI's cache block size).

Rolled up to a cold three-persona panel: 16,128 cached of 26,578 prompt tokens
= **60.7% hit rate**, versus the A/B's 58.8%. Costing the cached tokens at the
full input rate instead of the cached rate ($1.75 vs $0.175 per 1M) gives a
counterfactual uncached panel of $0.10387 against the measured $0.07847, i.e.
**24.5% cheaper per cold panel**, versus the A/B's 23.8%.

Both A/B numbers reproduce on the real replay path, within ~2 points.

One caveat that matters for reading the table: in a `--repeat` run the
*repeats* also hit the cache (98.5%, larger than the cross-persona prefix
because the whole prompt including the persona block is warm). So a repeat-N
panel measurement understates cost per genuinely cold panel. Only the first
call of a cold run is priced like production. That is why the aggregate row
above shows `cached_prompt_fraction = 0.788` — it is 1 cold call and 4 warm
ones, not a production figure.

`DRAFT_REVIEWER_COMPACT_MANUSCRIPT` remains OFF and was OFF for this run.

## Variance

### Latency — measurable, n=5

`reviewer_panel_node[methodology]` @ `10eQ4Cfh8p`, 5 replays of one fixture:

```
17.10  18.26  19.69  24.13  17.25   (seconds)
mean 19.286   sd 2.897   CV 15.0%   min 17.10   max 24.13
```

95% CI on the mean (t, 4 df): **19.29 ± 3.60 s → [15.69, 22.89]**.

The prior claim of CV ~7% came from n=3 and does not survive n=5 — the spread
roughly doubled once a fifth sample was drawn. What is defensible: a latency
difference smaller than about **±19% of the mean (~±3.6 s)** is not resolvable
with n=5 on this node. Anything claimed inside that band needs more samples,
not more confidence. Note the 24.13 s outlier is a single sample and there is
no basis in n=5 for excluding it.

The three cheap nodes are not interestingly variable: `run_quality_diagnostics`
runs in 0.02–0.12 s and makes no LLM call at all.

### Quality — still unresolvable, no delta reported

Severity-weighted recall across the same 5 replays, 79 gold units:

```
0.0463  0.0232  0.0000  0.0116  0.0116
mean 0.0185   sd 0.0176   CV 95%
```

In matched units: **4, 2, 0, 1, 1** out of 79. The metric is quantised at
~0.0116 per matched unit, so sd ≈ 1.5 quanta and the observed range spans the
entire signal. Five draws from the same fixture, same prompt, same model
produced anything from zero matches to four.

**No quality delta is reported from this run, and none should be inferred from
it.** The cause is unchanged: `retry_utils` strips `temperature` for every
`gpt-5.2*` model and no seed is set anywhere, so replays are genuinely
non-deterministic. At n=5 the CV improved from the prior ~172% only because the
mean happened to land away from zero, not because the measurement got tighter.
Any quality claim on this node needs either a seed, a much larger n, or a
metric that is not quantised at 1/79 of its own range.

## Spend against estimate

| run | selection | estimated node calls | actual | recorded $ |
|---|---|---|---|---|
| `f0af0ecb5365` | diagnostics + editor × 3 papers, metric ON | 3–3 | 3 | $0.009126 |
| `9c11daa01698` | panel[methodology] × 5, metric ON | 5–10 | 5 | $0.147794 |
| `82092c60b36c` | panel[clarity] × 1, `--no-metric` | 1–2 | 1 | $0.020733 |
| `dc045ccaaadb` | panel[literature_positioning] × 1, `--no-metric` | 1–2 | 1 | $0.022511 |
| | | **10–17** | **10** | **$0.200164** |

Every invocation set both `NOESIS_LLM_MAX_CALLS` and
`NOESIS_LLM_MAX_SPEND_USD`; no ceiling tripped and no run halted. Actual node
calls landed on the low end of every band — the conditional domain-audit call
that widens the panel estimate to 2 never fired.

**Plus about $0.02 that is not in that table.** A first attempt at the
`literature_positioning` replay was killed by an operator-side shell timeout
(a buffering pipeline, not the node — the retry completed in 19.5 s). The node
had almost certainly already made its call. `NOESIS_LLM_USAGE_LOG` was not set
for that attempt, so the process died with its usage only in memory and the
spend is gone. True spend for this exercise is therefore **~$0.22**, against
the prior exercise's $0.21999 — same order, as intended.

That is a small, on-theme lesson: **set `NOESIS_LLM_USAGE_LOG` on every paid
run.** It is an append-only sink written per call, so a killed process still
leaves its spend on disk. The retry did set it and the record survived.

## Reproducing this

From the repo root, with `OPENAI_API_KEY` exported (`node_eval` is run as a
module so that `score_replay`'s `scripts.eval.*` imports resolve):

```bash
set -a; . services/backend/.env; set +a

# 1. Always dry-run first. Resolves the selection, prints the estimate band,
#    imports no node and makes no call.
python3 -m scripts.eval.node_eval \
  --node run_quality_diagnostics --node editor_pass_node \
  --paper 10eQ4Cfh8p --paper 9ceadCJY4B --paper ApjY32f3Xr --dry-run

# 2. Cheap nodes, metric ON — this is what surfaces matcher spend.
NOESIS_LLM_MAX_CALLS=20 NOESIS_LLM_MAX_SPEND_USD=0.06 \
NOESIS_LLM_USAGE_LOG=/tmp/usage.jsonl \
python3 -m scripts.eval.node_eval \
  --node run_quality_diagnostics --node editor_pass_node \
  --paper 10eQ4Cfh8p --paper 9ceadCJY4B --paper ApjY32f3Xr

# 3. Latency + quality variance on one fixture.
NOESIS_LLM_MAX_CALLS=30 NOESIS_LLM_MAX_SPEND_USD=0.20 \
NOESIS_LLM_USAGE_LOG=/tmp/usage.jsonl \
python3 -m scripts.eval.node_eval \
  --node reviewer_panel_node --paper 10eQ4Cfh8p \
  --reviewer-type methodology --repeat 5 --yes

# 4. Prefix caching. Must run within the cache TTL (~5-10 min) of step 3, and
#    with --no-metric: these measure cache hits, not quality.
for rt in clarity literature_positioning; do
  NOESIS_LLM_MAX_CALLS=6 NOESIS_LLM_MAX_SPEND_USD=0.05 \
  NOESIS_LLM_USAGE_LOG=/tmp/usage.jsonl \
  python3 -m scripts.eval.node_eval \
    --node reviewer_panel_node --paper 10eQ4Cfh8p \
    --reviewer-type "$rt" --repeat 1 --no-metric
done
```

Notes for whoever repeats this:

* Order matters in step 4. It only measures the cross-persona prefix if a
  sibling persona was sent recently. Run it cold and you measure nothing.
* `--repeat` inflates the cache hit rate. Do not quote a repeat-N
  `cached_prompt_fraction` as a production number.
* The matcher call count is *not* in the `--dry-run` estimate band — it depends
  on how many items the node emits and how much of the pair cache hits. Leave
  headroom in the ceilings or pass `--no-metric`.
* Results are append-only. Nothing here ever opens
  `results/node_eval.jsonl` in anything but `"a"` mode; this repo has lost its
  eval history to an in-place rewrite once already.
