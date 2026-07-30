# Prompt caching in the reviewer panel

Measured 2026-07-30. Model `gpt-5.2-chat-latest`, priced from
`app/core/llm_budget.py` (input $1.75 / cached input $0.175 / output $14.00 per
1M tokens, retrieved 2026-07-30).

## What was already true

OpenAI's automatic prefix cache was already working with no `cache_control`
anywhere in this repo. Replaying the *same* prompt twice within the cache TTL
already returned ~99% `cached_tokens`. Nothing here turns caching on.

What did **not** work was cache reuse *across the three panel personas*, which
is where the volume is: one draft produces three reviewer calls whose prompts are
~88% identical text.

## The ordering problem

The prompt cache keys on an exact token prefix. The old assembly put the variable
part first:

```
system : REVIEWER_PROMPTS[reviewer_type]   <- persona text, differs at token ~5
user   : "Review this paper:\n\n" + metadata + profile + FULL MANUSCRIPT
         + persona-specific context slice
```

Because the persona sits at the head of the system message, the three calls
diverge on their first few tokens and share **no** cacheable prefix — the
manuscript (the expensive part) was paid for at full input rate three times.

## The new ordering

```
system : SHARED_REVIEWER_PREAMBLE          <- byte-identical for all 3 personas
                                              (generic framing + RATING_CALIBRATION)
user   : "Review this paper:\n\n"
         + DRAFT METADATA                  <- shared
         + MANUSCRIPT PROFILE / route      <- shared
         + FULL MANUSCRIPT TEXT            <- shared, the expensive block
         + persona context slice           <- variable
         + "YOUR REVIEWER ASSIGNMENT:" + persona block   <- variable, LAST
```

`build_shared_reviewer_prefix()` produces the invariant head;
`build_reviewer_messages()` assembles the pair. `REVIEWER_PROMPTS` is retained
(persona + calibration, as before) because `reviewer_judge._retry_reviewer`
consumes it as a standalone system prompt.

Prefix-breakers checked and confirmed absent from the shared head: no timestamp,
no uuid, no `draft_id`/`project_id`/`user_id`, no reviewer type. Every list
rendered into the profile block (`domain_tags`, `secondary_domains`,
`FORBIDDEN_REVIEW_STANDARDS`, `DOMAIN_PROMPT_PACKS`) comes from an ordered
list/tuple, not a set, so the block is byte-stable across runs.
`tests/test_prompt_cache_structure.py` pins all of this without touching the
network.

## Measured: cold panel of 3 personas, one draft

Paper `eR4W9tnJoZ` (~9.1k prompt tokens/call), no prior warm cache for this
paper, arms run AFTER-then-BEFORE so the old layout had every chance to warm:

| | prompt tokens | cached tokens | hit rate | $/panel | $/replay |
|---|---|---|---|---|---|
| BEFORE (persona first) | 27,265 | 0 | **0.0%** | $0.1103 | $0.0368 |
| AFTER (shared prefix first) | 27,428 | 16,128 | **58.8%** | $0.0841 | $0.0280 |

Per-call: calls 2 and 3 of the panel go from 0 cached tokens to 8,064 cached
(87–93% of their prompt). Call 1 is always cold — it is what populates the cache.
Ceiling for a 3-call panel is therefore ~2/3 × (shared fraction) ≈ 59%, which is
what was measured. Cost reduction on a cold panel: **23.8%**.

Prompt tokens rise 0.6% (+~55 tokens/call) because the shared preamble adds a
short framing sentence. That is paid once at full rate and returned tenfold.

Confirmation on a second paper (`10eQ4Cfh8p`, 2 rounds × 3 personas):

* round 1 (cold): BEFORE 34.4% (contaminated — one persona was already warm from
  concurrent work), AFTER 60.7%
* round 2 (exact repeat): BEFORE 98.9%, AFTER 98.7% — as expected, exact repeats
  already cached fine under either layout. The reordering does not help repeats;
  it helps the *first* pass, which is the only pass a real user run has.

## Manuscript compaction — `DRAFT_REVIEWER_COMPACT_MANUSCRIPT`

Default **OFF**. When set (`1/true/yes/on`), `_reviewer_manuscript_text()` routes
the draft through `_section_excerpts()` (1400 chars/section, max 7 sections,
`[:5000]` fallback when no headings are detected) and caps the result at
`DRAFT_REVIEWER_MANUSCRIPT_MAX_CHARS` (24000).

`node_eval.py --node reviewer_panel_node --paper 10eQ4Cfh8p --reviewer-type
methodology --repeat 5`:

| | prompt tokens/replay | $/replay | recall mean (n) | recall stdev |
|---|---|---|---|---|
| OFF | 9,224 | $0.0216 (4 replays, ~98% warm) | 0.0087 (n=4) | 0.0058 |
| ON | 3,622 | $0.0204 (5 replays, ~87% warm) | 0.0100 (n=5) | 0.0101 |

**Token reduction: 60.7%.** The $/replay difference is only ~5% and is *not* the
real cost picture — both arms ran against a warm cache, where input is already
billed at the 10× discount. On a cold call the saving is the full 60.7% of input:
9,224 → 3,622 tokens ≈ $0.0161 → $0.0063.

**Quality effect: not resolvable.** The severity-weighted-recall metric is
quantized here in steps of 0.0116 (one matched review unit), both arms sit within
one step of zero, and the spread swamps the difference (Welch t ≈ 0.24). This is
the known variance floor: `temperature` is stripped for `gpt-5.2*` models and no
seed is available, so identical inputs give different outputs. With n=4/5 the
compaction quality delta **could not be distinguished from run-to-run noise** —
do not read the +0.0013 as an improvement.

There is also a first-principles cost that the metric cannot see: the
`GROUNDING RULE` in `RATING_CALIBRATION` instructs reviewers to search the entire
manuscript before claiming something is absent. Compaction removes ~60% of that
text, so false "not reported" critiques should become *more* likely. Keep the
flag OFF until an eval with enough repetitions to resolve it exists.

## Not changed

`audit_domain_triggers()` still sends the full uncompacted manuscript, and its
checklist sits before the manuscript in the user message. It is the second-call
path that makes a triggered replay ~6× the single-call cost. It cannot share the
panel's cached prefix (different system prompt, different task), and compacting
it would manufacture false "absent" verdicts — the audit exists precisely to
check for presence. Left alone deliberately.
