# RESUME_BULLETS.md

Every bullet below traces to a measured number in a named file. Nothing here is
estimated, rounded up, or inferred. The rule that produced this document is the
one `LEARNING_AUDIT_ADDENDUM.md` exists to enforce: **a claim without a number
and an `n` behind it gets deleted, not softened.**

Two projects. `reviewer-agent` is a separate public-ready repo; Noesis is the
existing product. They are deliberately separate resume lines.

---

## Project 1 — `reviewer-agent` (new repo)

> An autonomous manuscript-critique agent benchmarked head-to-head against an
> 18-node LangGraph DAG on identical labels.

### The bullets

**1.** Built a tool-calling critique agent — dynamic tool selection, enforced step
budgets, loop detection, and context compaction under a swept context ceiling —
and benchmarked it against a hand-built 18-node LangGraph pipeline on the same
ICLR review labels; **475 tests, runs green with zero external dependencies**.

**2.** Ran the orchestration comparison honestly and **published the loss**:
orchestrated workers cost **2.56× more per finding** than a single agent
(n=48 vs 158 findings, matched arm, one process) — but the single agent's
quotes failed verbatim verification at **7.6× the rate** (0.3958 vs 0.0523,
Fisher p = 3.4×10⁻⁸), making it **1.69× per *verified* finding**. The cheap
option was cheap partly because it asserted quotes that were not in the paper.

**3.** Diagnosed why orchestration underperformed rather than accepting the
number: **29 of 30 workers exhausted their step budget mid-read**, funded at a
median 5 steps against a median 9-page scope. Raising the pool moved producers
**1/30 → 11/30 and findings 5 → 77** with the prompt byte-identical, and
fabrication statistically unchanged (Fisher p = 1.0) — so the yield came from
funding, not from pressure.

**4.** Showed the agent's findings were **anti-correlated with where human
reviewers found problems**: 88% of 170 mapped human review units fell on the
four concerns that produced nothing, while the single productive concern carried
12% and selected the two shortest sections in every manuscript.

**5.** Built per-resource authorization and a **durable human-in-the-loop
approval gate** that survives process death — **SIGKILL 20/20 resumed in a fresh
interpreter, side effect applied exactly once 20/20** — and measured it against a
31-case indirect prompt-injection set: **31/31 unauthorized writes blocked vs
31/31 allowed with the gate off**, alongside the cost that buys it (a blanket-deny
gate also blocks **100% of legitimate writes**; an approver that reads the
proposal blocks 0%).

**6.** Measured a tool-description A/B with everything else held fixed and
**reported the negative result**: the disciplined descriptions were **0.61 steps
worse** while costing **+988 catalogue tokens per call** (n=36/arm) — because
**90.2% of 2,751 tool calls went to a single tool**, so descriptions could not
influence a choice the model barely made.

### Traceability

| bullet | source | key `n` |
|---|---|---|
| 1 | `BENCHMARKS.md`, repo test suite | 475 tests, 240 runs |
| 2 | `BENCHMARKS.md` §4.5 | 48 / 158 findings |
| 3 | `docs/WORKER_YIELD.md` | 30 workers, 6 orchestrations/arm |
| 4 | `docs/WORKER_YIELD.md` | 170 mapped units of 212 |
| 5 | `eval/injection/INTERLOCK.md`, `tests/test_approval.py` | 31 cases, 20 SIGKILL trials |
| 6 | `BENCHMARKS.md` §3 | 36/arm, 2,751 calls |

---

## Project 2 — Noesis (existing product)

### The bullets

**7.** Produced the system's **first user-visible end-to-end latency
measurement** — **p50 212.82 s, n=7**, per-stage — and found from it that **the
PDF is parsed twice on every upload**, once for format validation and again for
ingest, accounting for **68.66 s p50 (39.2% of the path)**.

**8.** Made a mid-pipeline resume path real and proved it across **actual process
death — SIGKILL 27/27 resumed in a fresh interpreter with zero durable-prefix
violations** — measuring **87.6% of a run's cost recovered** when resuming after
the most expensive stage (n=160 node replays); found and fixed a privacy defect
in the process, where fan-out was persisting the full manuscript to disk three
times per run.

**9.** Built a retrieval evaluation harness over **338 queries and 8,554
relevance judgments** that reports every metric against its construction ceiling,
and used it to show that **cross-encoder reranking buys +3.2% recall@10 for
+13.3 s per query** — then that the delta was the wrong thing to chase, because
**86.5% of all misses were documents never in the candidate pool**: the headroom
is first-stage recall, not ranking.

**10.** Found by arithmetic that a **shipped LLM reranker had never reranked
anything** — its arm reproduced the unranked control to **17 significant figures**
on three rank-sensitive metrics. Root cause: a reasoning model's tokens consumed
its entire 100-token completion budget, returning an empty body into a silent
`except`. Fixed, and made the failure countable so it cannot recur invisibly.

**11.** Hardened the benchmark's own integrity after a concurrency incident in
which **two runs shared a config hash while describing different corpora**,
invalidating a published result; added corpus fingerprinting at both ends of a
run so a mid-run change raises instead of being recorded.

### Traceability

| bullet | source | key `n` |
|---|---|---|
| 7 | `scripts/eval/E2E_LATENCY.md` | 7 complete runs |
| 8 | `scripts/eval/CHECKPOINT_RESUME.md` | 27 SIGKILL trials, 160 replays |
| 9 | `scripts/eval/retrieval/RERANK.md` | 338 queries |
| 10 | `rag_retrieval.py`, commit `663e0f6` | 338/338 and 100/100 calls |
| 11 | `WAVE_LOG.md` §concurrency incident | — |

---

## What must NOT be claimed

Kept here deliberately, because the failure mode this whole effort was built to
avoid is a plausible sentence with nothing behind it.

| tempting | why it is false |
|---|---|
| "Improved retrieval by 3.2%" | True and useless without the +13.3 s/query it costs, which makes it unshippable |
| "Multi-agent system outperforms single-agent" | It loses. 2.56× per finding, 1.69× per verified finding |
| "Built context compaction for long-horizon agents" | Fires at 8k (0.333, n=12) and, under a genuine long-horizon workload, at 16k (0.333, n=6, 4 events). It does **not** fire at 16k+ on the ordinary Phase A task — peak prompt is 10,092 tokens against a 13,600 trigger, so that zero is a **workload bound, not a broken path**. Claimable only with the workload named |
| "Loop detection prevents runaway agents" | **One of three channels has ever bound.** `loop_no_result` fires 1.0000 (n=6) under an empty retriever — and is **fixture-only**, since `NoesisSearch` has `similarity_threshold=0.0` and structurally cannot return empty. `loop_repeated_call` and `loop_oscillation` have never bound in **270 runs**; max identical streak is **1** against a threshold of 3, including 30 runs built to induce looping. `gpt-5.2` under failure varies its calls and dies on the step budget instead |
| "Prompt-injection defenses reduced attack success" | No defense produced a measurable ASR reduction. ASR 0.0645 → 0.0645 (n=31) |
| "The approval gate stops real attacks" | Proven only under forced compliance. Under a real model, no attack in the set ever proposed a write — the payloads demand sentences, not actions |
| "recall@10 improved from 0.2195 to 0.2270" | Different corpora. The control moved to 0.2200 when 6 documents were re-ingested; 0.2195 belongs to an index that no longer exists |
| "human-authored labels" | The reviews are human; the **segmentation into units was done by GPT-5.2**. Say "human reviews, model-segmented" |
| any p95 on the latency work | n=7. A p95 over seven runs is the maximum wearing a percentile's name |

---

## The through-line, if asked in an interview

Five separate times in this work, a measurement described a mechanism that was
not running:

1. a retrieval control contaminated by a corpus swapped mid-run;
2. a synthesis verifier whose candidate population was structurally empty —
   no finding carried a quote, so it verified nothing on every real run;
3. orchestration "losing 11.94×" that was a step pool funded at half what the
   task needs;
4. an LLM reranker that never executed;
5. a config hash that omitted the orchestrator entirely, so two runs differing
   8× in cost per finding hashed identically.

Four of the five were caught only because a **second** agent re-derived the first
one's number and it did not match. The single most transferable lesson is that
**an identity — of a corpus, a config, a capability — has to be recorded at the
granularity at which it can change**, and that a number reproducing something
*too exactly* is evidence, not reassurance.
