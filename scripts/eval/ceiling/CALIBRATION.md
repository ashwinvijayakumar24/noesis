# The operating point, on 266 labels instead of 146

`CEILING.md` §3 recommends moving `match.COS_THRESHOLD` from 0.55 to 0.44–0.45,
and says plainly why you should not believe the recall figure it quotes:

> the `[0.40, 0.45)` bin holds 1065 pairs and contributed **1** positive out of
> 20 labelled. That single label carries an estimated weight of 53 positives,
> ~18% of all estimated true matches, and it is the entire reason recall falls
> from 1.00 to 0.82 across 0.42→0.44. The shape of the curve is solid; the exact
> recall figure in that band is not.

This file labels that band densely and recomputes the curve. **120 new
hand-labelled pairs**, four bins across 0.42–0.48, 30 each, none of them a pair
CEIL had already seen. Combined with CEIL's 146, the curve now rests on
**n = 266**, and the 0.42-0.48 decision band on **147** labels rather than 27.

## The verdict, first

**0.45 survives. The recall CEIL estimated at 0.822 on one label is 0.819
[0.599, 0.932] on 80 labels in `[0.40,0.45)` — a 0.003 move.** The thin bin was not
hiding anything.

**The recommended point is 0.44** — recall **0.842** [0.625, 0.945], precision
**0.213** [0.141, 0.309], estimated 1170 candidate pairs (n = 266 labelled,
39 positive). It is not a meaningfully different choice from 0.45; the data
cannot tell them apart, and the tie is broken by the cost asymmetry, which
prefers the lower.

**The plateau is 0.43–0.47.** Every threshold in that span has a recall point
estimate inside 0.44's confidence interval. That is a 0.04-wide flat, which is
the useful part of this result: the exact number does not matter much, and
0.55 is nowhere near it.

**The intervals below cover sampling error only.** A separate measurement
(§6) puts the `gpt-5.2` confirmer's run-to-run disagreement at 3.8–6.3% of
pairs, and re-judging the same 80 pairs four times gave positive counts of
10, 13, 13, 10. **The judge's disagreement with itself (κ = 0.75–0.85) is
about the size of its disagreement with the hand labels (κ = 0.647).** Any
downstream unit count carries that on top of everything here.

---

## 1. What was added, and what was not touched

| | |
|---|---|
| CEIL's labels | **146**, `pair_labels.json`. Read, never written. Every one is in the union |
| New labels | **120**, `hand_labels_dense.json`, seed `20260802` |
| Union | **266** pairs, 39 positive |
| Bins | 4 across 0.42–0.48, **30 drawn per bin**, no bin exhausted (smallest candidate pool was 159) |
| Criterion | CEIL's, unchanged and quoted verbatim in the label file. Changing it would have made the two sets unpoolable |
| Blindness | The producing system is absent from `hand_labels_dense.json` and was never shown to the labeller |
| Matcher | `scripts/eval/match.py` untouched. Embeddings 100% cache hits, $0 |
| Spend | **$0.3630** against a $3.00 ceiling (§7) |

Note on the brief: it named `hand_labels.json` as the source of CEIL's pair
labels. That file holds the 212 *taxonomy* labels. The pair labels are in
`pair_labels.json`, and that is what was extended.

### The union stratification

The two draws use different bin edges, so the union is re-weighted against a
finer partition that refines both. Each labelled pair stands for
`stratum_population / stratum_labelled` matrix pairs. CEIL's draw is uniform
within `[0.40,0.45)`, hence uniform within any sub-interval of it, so pooling
its members with the dense draw inside a stratum is a simple random sample of
that stratum — the dense draw excluded everything CEIL had already labelled, so
there is no double counting.

| stratum | population | CEIL | dense | n | positives | weight |
|---|---:|---:|---:|---:|---:|---:|
| [0.000,0.300) | 7759 | 20 | – | 20 | 0 | 387.9 |
| [0.300,0.400) | 4599 | 20 | – | 20 | 0 | 229.9 |
| [0.400,0.420) | 499 | 8 | – | 8 | 0 | 62.4 |
| **[0.420,0.435)** | 334 | 9 | **30** | **39** | **3** | 8.6 |
| **[0.435,0.450)** | 232 | 3 | **30** | **33** | **4** | 7.0 |
| **[0.450,0.465)** | 216 | 6 | **30** | **36** | **7** | 6.0 |
| **[0.465,0.480)** | 168 | 9 | **30** | **39** | **5** | 4.3 |
| [0.480,0.500) | 192 | 5 | – | 5 | 2 | 38.4 |
| [0.500,0.550) | 282 | 20 | – | 20 | 3 | 14.1 |
| [0.550,0.600) | 128 | 20 | – | 20 | 4 | 6.4 |
| [0.600,0.700) | 72 | 20 | – | 20 | 9 | 3.6 |
| [0.700,1.010) | 6 | 6 | – | 6 | 2 | 1.0 |
| **total** | **14483** | **146** | **120** | **266** | **39** | |

Weights in the decision band fell from 53.3 to between 4.3 and 8.6. That is the
whole point of the exercise: no label in 0.42–0.48 now stands for more than nine
matrix pairs.

(5 of the 14,488 matrix pairs have negative cosine. CEIL's bins start at 0.00
and never drew from them; they are excluded here for the same reason it does not
matter — every threshold considered is ≥ 0.40, so they are true negatives in
every row and enter no precision or recall denominator.)

---

## 2. How the 120 were labelled

For each pair the labeller saw exactly three things: the finding text, the label
unit text, and the cosine. Not which system produced the finding, not what CEIL
had labelled nearby, not the curve. The question was CEIL's, unaltered: *does
this finding raise the same underlying concern as this unit?* Same topic,
different concern scores 0.

Every label carries a one-line reason, so any individual call can be disputed
without disputing the method. Some that a reader might want to argue with:

- **`dag-147~cXs5md5wAq::anon1::05`, cosine 0.4677 → 1.** The finding says the
  contribution "risks appearing incremental"; the unit says the method is "weak
  on novelty". Different words for one objection.
- **`dag-168~cXs5md5wAq::anon3::17`, cosine 0.4313 → 0.** The finding asks for
  a GEM/FBA related-work paragraph; the unit asks whether the authors truly
  believe GEMs will be the solution. Same object, different demand — a related
  work paragraph does not answer "wait for more data".
- **`dag-066~10eQ4Cfh8p::anon3::20`, cosine 0.4358 → 1.** The finding asks for a consolidated
  symbol table; the unit lists undeclared abbreviations. The finding's remedy is
  the unit's fix, so it counts.
- **`dag-050~10eQ4Cfh8p::anon3::04`, cosine 0.4205 → 0.** The finding says baselines are not
  documented; the unit says the evaluation is not comprehensive. Documentation is
  not breadth. This one is close, and going the other way would raise the
  0.42–0.435 bin from 2/30 to 3/30.

Positives by bin, before any curve was computed:

| bin | positives | n | rate |
|---|---:|---:|---:|
| [0.420,0.435) | 2 | 30 | 0.067 |
| [0.435,0.450) | 4 | 30 | 0.133 |
| [0.450,0.465) | 5 | 30 | 0.167 |
| [0.465,0.480) | 4 | 30 | 0.133 |
| **total** | **15** | **120** | **0.125** |

Monotone enough to be believable and not so clean as to look arranged. CEIL's
two overlapping bins gave 1/20 in `[0.40,0.45)` and 5/20 in `[0.45,0.50)`; the
dense draw lands between them.

### The temptation, recorded

The brief asks that any urge to relabel after seeing the curve be written down
rather than acted on. There was one. After the sweep showed recall at 0.43
sitting at 0.942 — suspiciously close to the 1.000 of the bins below — the
2/30 in `[0.420,0.435)` looked low, and pair 7 above (the documentation/breadth
call) is exactly the kind of borderline that would have fixed it. It was not
changed. It is listed above instead so a reader can make the change themselves
and see it move recall at 0.43 by about a point.

---

## 3. The curve, with intervals

Precision and recall are ratio estimators over unequal weights, so a Wilson
interval on the raw label count would be far too narrow. Each interval is a 95%
**Wilson score interval computed on Kish's effective sample size**,
`n_eff = (Σw)² / Σw²`, over the relevant conditioning set — predicted-positives
for precision, actual-positives for recall. A bin whose estimate rests on one
heavily-weighted label gets the wide interval it deserves.

| thr | precision | 95% CI | recall | 95% CI | F1 | est. candidates | n ≥ thr | n_eff P | n_eff R |
|---:|---:|:---:|---:|:---:|---:|---:|---:|---:|---:|
| 0.40 | 0.139 | [0.083, 0.225] | 1.000 | [0.833, 1.000] | 0.244 | 2129 | 226 | 90.5 | 19.1 |
| 0.41 | 0.158 | [0.100, 0.240] | 1.000 | [0.833, 1.000] | 0.273 | 1880 | 222 | 102.4 | 19.1 |
| 0.42 | 0.182 | [0.127, 0.254] | 1.000 | [0.833, 1.000] | 0.308 | 1630 | 218 | 140.2 | 19.1 |
| 0.43 | 0.196 | [0.135, 0.277] | 0.942 | [0.748, 0.989] | 0.325 | 1424 | 194 | 118.1 | 19.1 |
| **0.44** | **0.213** | **[0.141, 0.309]** | **0.842** | **[0.625, 0.945]** | 0.341 | **1170** | 161 | 90.0 | 19.1 |
| **0.45** | **0.228** | **[0.149, 0.332]** | **0.819** | **[0.599, 0.932]** | 0.357 | **1064** | 146 | 78.3 | 19.1 |
| 0.46 | 0.232 | [0.143, 0.354] | 0.697 | [0.473, 0.855] | 0.348 | 890 | 117 | 59.1 | 19.1 |
| 0.47 | 0.246 | [0.146, 0.385] | 0.648 | [0.426, 0.820] | 0.357 | 779 | 94 | 47.2 | 19.1 |
| 0.48 | 0.263 | [0.149, 0.422] | 0.604 | [0.386, 0.787] | 0.367 | 680 | 71 | 37.2 | 19.1 |
| 0.49 | 0.249 | [0.141, 0.401] | 0.475 | [0.275, 0.683] | 0.327 | 565 | 68 | 39.8 | 19.1 |
| 0.50 | 0.210 | [0.118, 0.345] | 0.345 | [0.175, 0.567] | 0.261 | 488 | 66 | 47.1 | 19.1 |
| 0.51 | 0.263 | [0.153, 0.413] | 0.345 | [0.175, 0.567] | 0.298 | 389 | 59 | 41.3 | 19.1 |
| 0.52 | 0.283 | [0.167, 0.437] | 0.345 | [0.175, 0.567] | 0.311 | 361 | 57 | 39.9 | 19.1 |
| 0.53 | 0.303 | [0.180, 0.464] | 0.297 | [0.141, 0.521] | 0.300 | 291 | 52 | 37.1 | 19.1 |
| 0.54 | 0.319 | [0.192, 0.480] | 0.297 | [0.141, 0.521] | 0.308 | 276 | 51 | 36.8 | 19.1 |
| **0.55 (deployed)** | **0.291** | **[0.173, 0.447]** | **0.202** | **[0.081, 0.424]** | 0.239 | **206** | 46 | 39.1 | 19.1 |
| 0.56 | 0.305 | [0.173, 0.479] | 0.159 | [0.056, 0.376] | 0.209 | 155 | 38 | 31.7 | 19.1 |
| 0.57 | 0.332 | [0.186, 0.520] | 0.138 | [0.045, 0.351] | 0.195 | 123 | 33 | 27.3 | 19.1 |
| 0.58 | 0.371 | [0.213, 0.562] | 0.138 | [0.045, 0.351] | 0.201 | 110 | 31 | 25.7 | 19.1 |
| 0.59 | 0.379 | [0.214, 0.578] | 0.116 | [0.034, 0.326] | 0.178 | 91 | 28 | 23.8 | 19.1 |
| 0.60 | 0.441 | [0.261, 0.638] | 0.116 | [0.034, 0.326] | 0.184 | 78 | 26 | 22.9 | 19.1 |

### Against CEIL, side by side

| threshold | CEIL precision (n=146) | union precision (n=266) | CEIL recall | union recall | union recall 95% CI |
|---:|---:|---:|---:|---:|:---:|
| 0.40 | 0.141 | 0.139 | 1.000 | 1.000 | [0.833, 1.000] |
| 0.44 | 0.221 | 0.213 | 0.822 | **0.842** | [0.625, 0.945] |
| 0.45 | 0.232 | 0.228 | 0.822 | **0.819** | [0.599, 0.932] |
| 0.48 | 0.253 | 0.263 | 0.534 | 0.604 | [0.386, 0.787] |
| 0.50 | 0.210 | 0.210 | 0.342 | 0.345 | [0.175, 0.567] |
| 0.55 | 0.291 | 0.291 | 0.200 | 0.202 | [0.081, 0.424] |
| 0.60 | 0.441 | 0.441 | 0.115 | 0.116 | [0.034, 0.326] |

**Nothing moved by more than 0.07, and the 0.45 point moved by 0.003.** 120
labels bought confirmation rather than correction — which is the outcome you
want from a replication and the one you cannot claim without running it.

### The `n_eff` column is the honest part of this table

`n_eff` for recall is **19.1 at every threshold**. There are 39 hand-labelled
positives, but they carry weights from 1.0 to 38.4, and the effective sample
behind every recall figure in this file is about nineteen observations. That is
why the intervals are ±0.15 wide and why they should be quoted whenever the
number is. Densifying 0.42–0.48 raised `n_eff` for *precision* substantially
(78–140 in the band, against CEIL's 40-odd) but recall is limited by the
positives, and most of the estimated positive mass still sits in strata that
were not densified.

### Where the thin bin went

It moved. `[0.480, 0.500)` now holds 192 pairs, **5** labels, and 2 positives at
weight 38.4 — about 26% of all estimated true matches resting on two labels. And
`[0.400, 0.420)` holds 499 pairs and 8 labels, all negative, at weight 62.4.

That second one is the live risk, and it bites in the direction that matters:
**if one of those 8 were actually a match, recall at 0.44 falls from 0.842 to
0.696** [0.446, 0.867]. The curve's claim that recall is 1.000 below 0.42 rests
on 48 labels across three strata with zero positives between them, which is
reassuring, but `[0.400,0.420)` itself has only 8.

This is CEIL's caveat displaced downward by 0.02, and it is stated here rather
than left for the next agent to find. It argues for a *lower* threshold, not a
higher one: if true matches exist at 0.40–0.42, 0.44 is throwing them away. The
next densification, if there is one, should be `[0.400,0.420)` and
`[0.480,0.500)`.

---

## 4. Choosing the point

### The cost asymmetry — adopted, with one correction

CEIL's argument, which stands:

> This is a prefilter for a downstream judge, not a decision. A false negative is
> unrecoverable — the pair is never shown to the confirmer and the unit is scored
> as missed forever. A false positive costs one more line in a batched 20-pair
> confirmation call, about $0.0002.

Adopted. The measured evidence for it is in §6: the confirmer, shown a pair,
recovers 72% of true matches (n = 39 hand-positives) — it is not the bottleneck.
The prefilter at 0.55 shows it 20%. Precision losses at the prefilter are
recoverable by the judge; recall losses are not recoverable by anything.

One correction to how the asymmetry gets applied. CEIL's rule — *the lowest
threshold whose estimated candidate volume stays inside 6 candidates per
finding* — makes the operating point a function of a confirmation budget nobody
has defended. At 201 findings that budget is 1206 candidates, which admits 0.44
(1170) and rejects 0.43 (1424) by 18%. The recall difference between them is
0.842 vs 0.942, and the cost difference is 254 extra confirmations, about
**$0.05**. If a false negative is really worth three orders of magnitude more
than a false positive, then $0.05 does not buy the right to lose 10 points of
recall, and the binding constraint is the budget constant, not the curve.

So: **0.44 under CEIL's stated budget. 0.43 if the budget is what it appears to
be, namely arbitrary.** The honest statement is that the data does not
distinguish them (§ below) and the choice is a policy question about
confirmation spend, which should be made explicitly rather than smuggled in as
`max_candidates_per_finding=6.0`.

### Does 0.45 survive?

**Yes.** Recall 0.819 [0.599, 0.932], with `[0.40,0.45)` now carrying 80 labels
and 7 positives against CEIL's 20 and 1. The 53-positive weight that one label carried is now spread over 72 labels
carrying 4.3–8.6 each, and the answer did not change. Precision 0.228 [0.149,
0.332] against CEIL's 0.232.

The recall figure was **not** overstated. The correction is to its *credibility*,
not its value.

### How flat is the neighbourhood?

Thresholds whose recall point estimate falls inside 0.44's interval
[0.625, 0.945]:

| threshold | recall | inside 0.44's CI? |
|---:|---:|:---:|
| 0.42 | 1.000 | no (above) |
| 0.43 | 0.942 | yes |
| **0.44** | **0.842** | — |
| 0.45 | 0.819 | yes |
| 0.46 | 0.697 | yes |
| 0.47 | 0.648 | yes |
| 0.48 | 0.604 | no |

**The plateau is 0.43–0.47, four hundredths wide.** Anywhere in it, the evidence
says the same thing. This is what makes the recommendation robust: it is not a
point on a slope, and picking 0.44 versus 0.46 is not a decision this data can
make or unmake.

The deployed 0.55 is not in it, and not close. Its recall, 0.202 [0.081, 0.424],
does not overlap 0.44's [0.625, 0.945] — **the gap between the deployed
threshold and the recommended one is larger than the uncertainty on either**,
which is the one comparison in this document that is unambiguous. 0.55 also
remains worse than 0.60 on precision (0.291 vs 0.441) while being worse than
0.44 on recall by a factor of four. There is no reading of this curve on which
it is the right number.

### The near-miss, as real data

Agent FIX's decision record contains the closest below-threshold rejection in
the live corpus:

```
cosine 0.549169   (threshold 0.55)
finding: "Results are reported as averages only, with no variance, standard
          deviation, or statistical tests"
unit:    "Finally, no standard deviation has been reported nor multiple runs."
```

An unambiguous match, discarded by 0.0008, with the next two rejections at
0.549099 and 0.549024. Three true-looking pairs clustered within 0.0002 of the
cutoff is not an argument about where the boundary should be — it is an
observation that the boundary currently sits in the middle of the distribution
rather than beside it. At 0.44 all three are confirmed.

---

## 5. Estimated effect on the published match counts

**These are estimates, clearly labelled. Re-baselining is the next agent's job**
— nothing here re-ran the scorer, and `ceiling.jsonl` was not written to.

> ↻ **Re-baselined 2026-08-01. The estimates held; all three came in slightly
> high of them, and the reason is worth more than the numbers.**
>
> | | 0.55 | 0.45 (measured) | 0.44 **estimated** | 0.44 **measured** |
> |---|---:|---:|---:|---:|
> | DAG | 31 | 56 / 57 | ≈ 57 | **61 ± 7** |
> | agent | 12 | 23 | ≈ 23 | **24 ± 3** |
> | union | 41 | 72 / 73 | ≈ 73 ± 7 | **77 ± 8** |
>
> Union 77 is inside the ±7 band this section published; DAG 61 is inside a ±10%
> band on ≈57; agent 24 is one off ≈23. **Nothing landed outside.**
>
> **Where the method under-predicted, and it was not the recall curve.** The
> candidate-volume estimate in §3 is exact at 0.45 — it predicted 1064 pairs and
> the real corpus has 1064 — but at 0.44 it predicted 1170 against an actual
> **1219**, 4.2% low. The stratified estimate slightly understates how much
> volume the 0.44–0.45 slice actually admits on this corpus. Those 155 extra
> pairs yielded **+4 DAG units and +1 agent unit** over the 0.45 rerun, i.e.
> about **1 unit per 31 extra candidates** — a better yield than "the extra 106
> are mostly false positives the confirmer rejects" implies, and the direction
> that argues for 0.43 rather than against it.
>
> Run provenance: 1219 candidate pairs, 1079 confirm-cache hits, **140 live
> verdicts** on the baselining run ($0.1648). An immediate second run at the same
> threshold was **100% cache-served — 1219/1219, 0 live verdicts, $0.0000 — and
> reproduced 61 / 24 / 77 exactly** under the same config hash
> `06723c2f759c246a`. `ceiling.jsonl` holds both rows.

CEIL measured, on the same 201-finding corpus:

| | 0.55 (deployed) | 0.45 (CEIL, measured) | 0.44 (estimated) |
|---|---:|---:|---:|
| DAG units matched | 31 / 212 | 56 | **≈ 57** |
| agent units matched | 12 / 212 | 23 | **≈ 23** |
| union | 41 / 212 | 72 | **≈ 73** |

Method: recall rises 0.819 → 0.842, a 2.8% relative gain, applied to the
increment CEIL measured above the 0.55 baseline (DAG +25, agent +11, union +31).
Candidate volume rises 1064 → 1170, +10%, and the extra 106 are mostly false
positives the confirmer rejects.

**The band on those numbers is dominated by the judge, not by the threshold.**
FIX scored the same corpus against two verdict sets and got 37 vs 41 units from
74 identically-confirmed pairs. Combined with §6, the union figure is better
written **≈ 73 ± 7** than as an integer. The difference between operating at
0.44 and at 0.45 is roughly one unit and is invisible underneath that.

At 0.43, the same arithmetic gives DAG ≈ 62, agent ≈ 25, union ≈ 79 — which is
the +6 units the confirmation budget constant is currently buying nobody.

---

## 6. Cohen's κ, and the error term the intervals do not cover

### The confirmer against the hand labels, on the union

| | value | n |
|---|---:|---:|
| κ, union | **0.647** | 266 |
| κ, dense labels only | **0.596** | 120 |
| κ, CEIL's labels only (reported in `CEILING.md`) | 0.673 | 146 |
| judge precision vs hand | 0.683 | 41 judge-positives |
| judge recall vs hand | 0.718 | 39 hand-positives |

Substantial agreement, and slightly *lower* than CEIL's — expected, because the
dense sample is drawn entirely from the band where the decision is hardest.
κ = 0.596 on 120 pairs all sitting between 0.42 and 0.48 is a stronger result
than κ = 0.673 on a sample that includes 40 pairs below cosine 0.40 where
agreeing is free.

The substantive reading is unchanged: **the confirmation judge is not the
bottleneck.** Shown a true match, it confirms 72% of them. The prefilter at 0.55
shows it one in five.

### The judge does not agree with itself either

Every interval in §3 covers **sampling error only**. It says nothing about the
confirmer's own variance, and that variance is not small. The same 80 pairs,
drawn from the 0.42–0.60 band, judged against cold caches at `temperature=0`:

| measurement | run A positives | run B positives | disagreements | rate | κ(A, B) |
|---|---:|---:|---:|---:|---:|
| first pair of runs | 10 | 13 | 5 / 80 | 6.3% | 0.747 |
| second pair of runs | 13 | 10 | 3 / 80 | 3.8% | 0.848 |

Four independent judgements of the same 80 pairs produced 10, 13, 13, 10
positives — a **±15% swing on the positive count from nothing but re-running the
model.**

Put the two κ figures next to each other:

> **κ(judge, judge) = 0.75–0.85. κ(judge, hand) = 0.647.**

The confirmer agrees with a second copy of itself only a little better than it
agrees with an independent human labeller. So the "independent check" that
κ = 0.647 provides is weaker than it looks: a meaningful part of the residual
disagreement is the judge being inconsistent, not the judge and the labeller
disagreeing about anything.

**Which error dominates?** They are the same order of magnitude, and which one
wins depends on what is being quoted:

- For the **threshold decision**, sampling error dominates. The recall interval
  at 0.44 is ±0.16 wide; judge flake moves confirmed-pair counts by ~5%. The
  prefilter recall estimates in §3 do not involve the judge at all — they are
  computed against hand labels — so the choice of 0.43–0.45 is not exposed to it.
- For any **published unit count**, judge variance dominates and the sampling
  interval is irrelevant, because the count is one realisation of a stochastic
  pipeline rather than an estimate from a sample. A number like "72 / 212" should
  carry ±7, and re-running is not a way to check it.

The sentence that matters: **`COS_THRESHOLD` can now be set on evidence, but no
unit count downstream of the confirmer should be quoted to the integer until the
confirmer is made deterministic** — which is a cache-key or a self-consistency
problem, not a calibration one.

---

## 7. Spend

| step | |
|---|---|
| Embeddings | 413 texts, **100% cache hits**, $0 |
| Matrix, sample, sweep, intervals | deterministic, $0 |
| `--confirm` over the union (266 pairs, 120 new) | $0.0719 |
| Judge variance, measurement 1 (160 calls) | $0.1542 |
| Judge variance, measurement 2 (160 calls) | $0.1369 |
| **Total** | **$0.3630** against **$3.00** |

Each figure is `llm_budget.total_spend_usd()` printed by that process on exit.
No Supabase contacted; nothing here needs a database.

---

## 8. Reproducing this

```bash
# free and deterministic: the curve, the intervals, the label arithmetic
python3 -m pytest scripts/eval/tests/test_calibrate_dense.py -q

# free: re-derive the sweep from the two committed label files
python3 -m scripts.eval.ceiling.calibrate_dense

# free: re-derive the blind sample (should reproduce hand_labels_dense.json's pairs)
python3 -m scripts.eval.ceiling.calibrate_dense --emit-sample /tmp/sample.json

# paid: the confirmation judge, for kappa and for its own variance
NOESIS_LLM_MAX_SPEND_USD=3.00 python3 -m scripts.eval.ceiling.calibrate_dense --confirm
NOESIS_LLM_MAX_SPEND_USD=3.00 python3 -m scripts.eval.ceiling.calibrate_dense --judge-variance
```

`sweep_dense.json` carries the full weighted union, so
`test_committed_curve_reproduces_from_the_committed_labels` recomputes every row
of §3 with no embeddings, no cache, and no model.

## 9. What this does not say

- ~~It does not change `match.py`. `COS_THRESHOLD` is still 0.55.~~ ↻ **Adopted
  2026-08-01.** `match.py` now carries `CALIBRATED_COS_THRESHOLD = 0.44` as its
  default and `LEGACY_COS_THRESHOLD = 0.55` alongside it, overridable with
  `NOESIS_MATCH_COS_THRESHOLD`. The 0.55 lineage is expressible and every
  pre-existing row stays interpretable.
- ~~It does not re-baseline anything. §5 is arithmetic on CEIL's measurements,
  not a scoring run.~~ ↻ **Re-baselined 2026-08-01**, see the box in §5. The
  arithmetic held.
- It does not fix the denominator defect (`CEILING.md` §2): 27 of the 212 units
  are fragments no system can match, and every recall figure that divides by 212
  is wrong in a way no threshold fixes.
- One labeller. κ = 0.647 against a model that disagrees with itself at
  κ ≈ 0.8 is the only external check, and §6 explains why it is weaker evidence
  than it appears. There is still no second human.
- Three manuscripts, 201 findings, 212 units. The band positive rate — 12.5% in
  0.42–0.48 — is a property of this corpus's finding style, and a system that
  wrote shorter findings would sit at different cosines entirely.
