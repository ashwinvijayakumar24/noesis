# AGENT_HARNESS_PLAN.md

**The project.** One new repo: an autonomous manuscript-critique agent that operates over Noesis's domain, benchmarked against Noesis's 18-node workflow on shared labels.

**Why it exists.** Noesis is a **workflow**, not an agent — you decide control flow at graph-build time, the model never chooses a tool, and there are zero function-calling sites in the entire codebase. This project is the only thing in your portfolio that closes agent orchestration, tool design, just-in-time context, and trajectory evaluation. Companion to `docs/history/NOESIS_BUILD_PLAN.md`; the two are budgeted together.

---

## The bar: who decides control flow

| | Noesis | This harness |
|---|---|---|
| Which step runs next | you, at build time | **model, at runtime** |
| Which tool is called | no tools exist | **model chooses** |
| When it's finished | `END` edge | **model decides, budget enforces** |
| On tool failure | absorbed, pipeline continues | **loop adapts** |
| Worker count | hardcoded 3 | **decided at runtime from triage** |
| Worker context | ~95% identical (full manuscript to each) | **disjoint slices** |

**Minimum bar to count as agent work — all six, or it's a chained pipeline with extra steps:**

1. Model chooses which tool to call and when, with no predetermined order
2. Model decides when it's finished
3. Error recovery: a tool fails or returns nothing and the loop **adapts** rather than crashing
4. Step budget and loop detection, both **observed binding** at least sometimes
5. **Context compaction under long-horizon pressure, actually triggered** (see forcing functions — this is the one that silently doesn't happen)
6. Phase B: runtime-decided worker count with per-worker context isolation

---

## Separate repo, Noesis as the domain

**Separate repo because:** it forces a real interface boundary, it's a separate resume line, it's public and readable, and it can be agent-shaped from line one.

**Noesis as the domain because:** the #1 failure mode of portfolio agent projects is a toy domain. A weather-plus-calculator ReAct loop teaches nothing and reads as tutorial output. Noesis gives you real academic PDFs, real awkward payloads, 61 atomized human ICLR reviews as labels — and, uniquely, **an existing non-agentic baseline on identical labels.**

Tools import Noesis's Python modules directly (retrieval + draft services). No need for the full Docker stack — only local pgvector from `docs/history/NOESIS_BUILD_PLAN.md` N0.2.

### Acceptance test for the whole project

**If it can't be scored against the Noesis DAG on the same labels, it's a toy. Kill it.**

---

## Repo layout

```
reviewer-agent/
  harness/
    loop.py           # ReAct loop, step budget, termination, loop detection
    context.py        # budget accounting, compaction, structured notes
    tools/
      registry.py     # schemas, dispatch, namespacing
      literature.py   # search_literature
      draft.py        # get_draft_section (paginated)
      anchors.py      # verify_anchor
      citations.py    # check_citation
      artifacts.py    # Phase B.5: write_review_artifact (side-effecting)
    orchestrator.py   # Phase B: triage, worker spawn, scoping, synthesis
    policy.py         # Phase B.5: permissions, per-resource authz, approval gate
  eval/
    labels.py         # shared with Noesis: 15 OpenReview papers, atomized units
    baseline.py       # runs the Noesis DAG for comparison
    trajectory.py     # tool selection, plan quality, step efficiency, loops
    reliability.py    # pass^k across repeated runs
    report.py         # append-only results
  README.md           # includes the negative results
```

---

# Phase A — the tool loop (~10 h)

**Goal.** A model that decides what to read and when to stop.

### Tools — four, deliberately

| Tool | Backed by | Design note |
|---|---|---|
| `search_literature(query, k)` | `rag_retrieval.retrieve_relevant_chunks` | Returns trimmed chunks with doc IDs, not raw blobs |
| `get_draft_section(title_or_id, page)` | parsed manuscript structure | **Paginated on purpose** — the model must choose what to read. This is also forcing function #1 for compaction |
| `verify_anchor(quote)` | verbatim substring check (`draft_evidence_gate.py:35-54`) | Cheap, high-frequency; teaches the model to ground itself |
| `check_citation(claim, reference)` | `citation_judge` | Expensive; the model must learn to use it sparingly |

**Tool-design rules to apply and then measure:** namespacing · token-efficient responses (return the minimum that lets the model decide) · pagination, filtering, and truncation with sensible defaults · **error messages written as prompts**, not stack traces · natural-language identifiers over opaque UUIDs · response-format enums.

**Measurable claim available here:** rewrite one tool description, hold everything else fixed, and report the change in steps-to-completion. *"A better tool description cut mean steps from X to Y"* is a rare, concrete tool-design result.

### Loop

- Thought → action → observation → terminate
- **Step budget**, enforced. Log every time it binds; if it never binds, it's decoration
- **Loop detection**: repeated identical tool calls, repeated no-result calls, oscillation between two tools
- **Error recovery**: tool raises / returns empty / returns malformed → the loop feeds a prompt-shaped error back and the model adapts. Test by deliberately breaking each tool
- **Termination criteria**: explicit, and distinct from budget exhaustion. Track which one fired

### Context management — the part that silently doesn't happen

A 4-tool critique loop over an 8-page ICLR paper terminates in ~10–25 steps and **never fills the window**, so a compaction path you wrote never fires and you'd be claiming a capability you never exercised. Two forcing functions — **implement at least one, ideally both:**

1. **Long-horizon by construction.** Critique section-by-section through the *paginated* reader, over a 60-page thesis rather than a short paper. Reading the manuscript becomes dozens of tool calls.
2. **Artificial context ceiling.** Cap the harness at 32k regardless of the model's real window. Compaction becomes mandatory, and the ceiling becomes a dial you can sweep. **Benchmark: quality vs context ceiling at 16k / 32k / 64k / uncapped** — better than "I implemented compaction."

Also implement **structured note-taking**: a durable scratchpad of confirmed findings that survives compaction, so evidence isn't lost when history is summarized.

### Topics closed by Phase A

Dynamic tool selection · termination criteria · error recovery and adaptation · step budgets · loop detection · tool schema design and token-efficient responses · **just-in-time context vs pre-stuffing** (structurally impossible in Noesis, which pre-retrieves everything because it has no tools) · tool scoping cost · compaction under pressure · structured note-taking · trajectory eval basics.

### Phase A benchmarks

- Tool-selection accuracy vs a hand-labeled trajectory (~20 runs)
- Mean and p95 steps-to-completion
- Wasted-call rate (calls whose result was never used)
- Error-recovery rate (broken-tool trials that still completed)
- Loop-detection trigger rate · step-budget bind rate
- Termination-reason distribution
- Quality vs context ceiling
- **Severity-weighted recall vs the Noesis DAG on the same papers**
- Tokens and $ per finding, agent vs DAG

### Phase A acceptance

All six minimum-bar items demonstrated, with the compaction path **observed firing in logs**. A DAG comparison on shared labels, reported both ways.

---

# Phase B — real orchestration (~12 h)

**Goal.** Multi-agent that earns the name.

**Phase A is not orchestration.** It's one actor with dynamic control flow. Many people stop here and still say "multi-agent" — which is exactly the mistake already on your resume about Noesis. Don't repeat it in a new repo.

### Build

1. **Triage pass.** The orchestrator reads a cheap manuscript profile and enumerates concerns.
2. **Runtime-decided worker count.** N workers where N follows from triage — not a constant. Noesis hardcodes 3 at `graph.py:370`; the whole point is that you don't.
3. **Per-worker scope assignment.** Each worker gets a concern *and the specific sections it needs* — nothing more.
4. **Real context isolation.** Each worker sees only its slice. This is the strongest technical argument for multi-agent and precisely what Noesis fails: all three reviewers receive the entire manuscript via `reviewer_panel.py:350-351`.
5. **Budget allocation across workers.** A token/step budget per worker, and a policy for what happens when one exhausts it.
6. **Worker failure handling.** A worker times out or returns nothing — retry, reassign, or proceed degraded? Noesis's answer is a synthetic rating-5 fallback that propagates into meta-review as a real vote, invisibly (`reviewer_panel.py:872-891`). Do better, and *measure* how often it happens.
7. **Synthesis over context the orchestrator never saw.** The hard part, and the easiest to skip. Noesis's judge node sees all three outputs *in full*; your orchestrator won't. Deciding how much to trust a worker's summary — and whether to spend a step verifying it — is the actual lesson of orchestration.

### Topics closed by Phase B

Orchestrator–worker pattern · when multi-agent genuinely beats single-agent (parallel context isolation, not "specialists are smarter") · the token-cost multiplier, measured · coordination failure modes · state across agents · sub-agent context isolation · result aggregation under uncertainty.

### Phase B benchmarks

- Worker count distribution vs manuscript complexity (proves it's dynamic)
- Context tokens per worker vs the DAG's per-reviewer tokens (proves isolation)
- **Tokens and $ per finding: agent vs orchestrated-agent vs DAG**
- Recall delta at each configuration
- Orchestrator decision quality (hand-labeled: was the decomposition sensible before the first worker call?)
- Worker failure rate and its effect on final quality

### Phase B acceptance

Worker count demonstrably varies with input. Per-worker context is measurably smaller than the DAG's. Cost comparison published **including the case where the agent loses.**

---

# Phase B.5 — one side-effecting tool, behind a gate (~5 h)

**Goal.** Approval gates and per-resource authorization. Not sandboxing — see the honesty note.

### Build

- **One side-effecting tool:** `write_review_artifact(draft_id, artifact)` → storage.
- **Hard constraint:** Noesis's own rule is *no auto-writing user drafts — critique/reviewer behavior only*. Write review **artifacts**, never the manuscript. Breaching this to learn a pattern is not a trade worth making.
- **Approval path:** propose → pause → human approve/deny → resume. Log approval latency and deny-path correctness.
- **Durable pause** requires `docs/history/NOESIS_BUILD_PLAN.md` **N11** (real LangGraph checkpointer + `interrupt`). Without it you get in-process approval only — ~2 h instead of ~5 h, and it teaches materially less, because a human-in-the-loop decision that dies with the process isn't an approval gate.
- **Per-resource authorization, not a boolean allowlist.** The tool must prove the caller owns the `draft_id` it acts on. Noesis has a live bug of exactly this shape — WebSocket IDOR at `drafts.py:2304-2310` validates the token but never checks draft ownership — so this is a real authorization build, not a toy.

### Interlock with N12 (injection defenses) — this upgrades both

Blast radius is bounded today only because nothing can act. Give the agent a write tool and injected text in a third-party abstract (fetched from OpenAlex/Semantic Scholar, which you don't control) can **forge an artifact**. That makes the approval gate a *measurable mitigation*:

**Benchmark: attack success rate with vs without the approval gate.** Better than either build produces alone.

### Honesty note on sandboxing

Writing a blob to storage through your own client is an authorized API call, **not** sandboxing. Real sandboxing constrains arbitrary code: filesystem isolation, network egress policy, syscall filtering, CPU/memory/wall-clock limits, escape resistance (container / gVisor / Firecracker / WASM). That needs a code-execution tool — Phase D below. Until then the honest line is:

> "I built approval gates and per-resource authorization. I did not build sandboxed execution — that needs untrusted-code isolation, and here's what it would require."

---

# Phase C — MCP wrapper (~5 h, optional)

Expose the harness's tools over MCP. **Learning value is low** — it's the wire format, and the non-obvious knowledge lives in the harness. Two real reasons to do it anyway: it forces tool-description discipline, and it produces a **demoable artifact** loadable in Claude Code. Distribution argument, not a learning one. Never before Phases A and B work.

---

# Phase D — sandboxed execution (~8 h, December+, optional)

A container-exec tool with filesystem isolation, egress policy, and resource limits. The only path to claiming sandboxing honestly. Lowest priority in the document; skip without guilt.

---

# Evaluation — the thing that makes this credible

Most people can build an agent. Almost no undergraduate can prove theirs works. This section is the differentiator, and it reuses Noesis machinery: `node_eval.py` replays nodes from serialized fixtures (214 MB on disk, `Makefile:16` sets `EVAL_STATE_DIR`), and `mine_failures.py:296-311` clusters missed gold units and proposes the responsible component.

### Order of operations

1. **Error analysis first.** Read 50 real trajectories before writing a single scorer. Metrics chosen before you've seen failures measure the wrong thing. This is the most-skipped step and the highest-value one.
2. **Then** write scorers for the failures you actually saw.

### What to score beyond the final output

An agent can reach the right answer through a broken path, or fail silently three steps in. Output-only grading rewards both.

| Dimension | Metric |
|---|---|
| Tool selection | right tool, right arguments, vs hand-labeled trajectory |
| Plan quality | was the decomposition sensible **before** the first call? |
| Trajectory | reasoning coherence, step efficiency, dead ends, loops |
| Reliability | **pass^k over ≥3 runs** — variance will be large, since `temperature=0` is silently stripped for `gpt-5.2*` at `retry_utils.py:33-46` and no seed is ever set |
| Cost | tokens and $ per finding |
| Degradation | worker-failure rate and its quality impact |

Reference-free trajectory judging and gold-trajectory comparison both apply; hand-label ~20 gold trajectories, then use a judge for the rest. **Calibrate the judge against your labels** and report Cohen's κ — the same discipline as `docs/history/NOESIS_BUILD_PLAN.md` N8. τ-bench and SWE-bench: know them by name and shape; don't try to run them.

### Falsifiability checklist

1. Scored against the Noesis DAG on the **same labels** (15 OpenReview papers, severity-weighted recall)
2. A **trajectory** eval, not just an output score
3. **pass^k over ≥3 runs** — one lucky trace proves nothing
4. **A negative result reported.** The agent will probably cost more per finding than the DAG. Publishing that is the credibility marker; omitting it is the tell
5. Step budget and compaction both **observed binding**
6. Results append-only, never overwritten

---

# What this project does not cover

Say it plainly rather than stretching:

- **Sandboxed execution** — Phase D only; otherwise conceptual
- **Production agent ops** — no real users means no online scorers, no drift detection, no cost-at-scale. `docs/history/NOESIS_BUILD_PLAN.md` N1/N14 cover that half
- **Multi-turn user interaction and mid-run interruption** — needs streaming plus durable resume (N11 + Phase B.5)
- **Multi-GPU / collectives** — untouched by this project and by Noesis. Still a separate ~10 h 2-GPU exercise, optional, and only if your serving layer lands early
- **Everything in the inference-engine and serving-layer lanes** — out of scope by design

---

# Budget and milestones

| Phase | Hours | Tier |
|---|---|---|
| A — tool loop | 10 | **1** |
| B — orchestration | 12 | **1** |
| Eval wiring (shared labels, baseline runner, trajectory scorers) | 6 | **1** |
| B.5 — write tool + approval gate + authz | 5 | 2 (needs N11) |
| C — MCP | 5 | 2 |
| D — sandboxing | 8 | 3 |

**Tier 1 harness total ≈ 28 h.** Combined with `docs/history/NOESIS_BUILD_PLAN.md` Tier 1 (≈62 h) that's **≈90 h** — the full Sept–Nov discretionary budget at 10–15 h/week, shared with your serving layer. This is why Noesis `N7` (RRF + contextual retrieval, 16 h) was pushed to Tier 2: Phase B displaced it, deliberately, because agents are the lead lane.

**Sequencing against Noesis:** N0 → N1 → N2 → N3 → N4 → **Harness A** → **Harness B** → N5 → N6. Rationale: tracing first, because a multi-step agent without a trace viewer is undebuggable and long traces are where tracing pays off most; the retrieval eval before the harness, because it's the ruler you score the agent with; N6 last but never cut, because it's the prefix-caching bridge your serving layer depends on.

---

# Interview stories this produces

1. **"I built both and measured."** A workflow and an agent over the same task with the same labels. Almost nobody has the comparison, and the comparison is the insight — including where the agent loses.
2. **"Why Noesis is a workflow, deliberately."** Known decomposition, auditable output, reproducibility. That's correct engineering judgment, not a shortcoming — and you can now name the conditions under which you'd choose otherwise.
3. **"Context isolation is the real argument for multi-agent."** You can point at a system where you failed to achieve it (~95% identical context across three reviewers) and one where you did, with per-worker token counts to prove it.
4. **"A better tool description cut mean steps from X to Y."** Concrete tool-design evidence.
5. **"My step budget binds N% of the time and here's what happens when it does."** Evidence the safety rails are load-bearing rather than decorative.
6. **"The approval gate dropped injection success from X% to Y%."** Security reasoning tied to a measured number.
