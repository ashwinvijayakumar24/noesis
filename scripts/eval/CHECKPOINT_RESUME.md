# N11 — Durable checkpointer, interrupt, resume

**Headline.** A draft-analysis run that dies after the reviewer panel and resumes
instead of restarting saves **$0.1605 of a $0.1832 run (87.6%) and 70,425 of
77,847 tokens**. Averaged uniformly over all 18 possible durable-prefix lengths
the saving is **$0.0566/run (30.9%) and 26,024 tokens**.
*n* = 160 measured node replays (8 papers × 17 nodes, plus 24 for the 3-persona
fan-out), no-corpus configuration.

**Resume works across process death.** 27/27 SIGKILL-and-resume trials completed
in a fresh interpreter, with **0** violations of the durable-prefix property
(no node at or before the last durable checkpoint was ever re-executed).
*n* = 27 (9 crash depths × 3 repeats).

**Actual spend: $1.4658** against a `MAX_SPEND_USD` ceiling of $6
(`NOESIS_LLM_MAX_SPEND_USD=6`, 64 LLM calls, log at
`scripts/eval/results/checkpoint_bench_usage.jsonl`). The crash/resume benchmark
itself spends **$0** — it replaces node bodies with stubs and exercises the real
topology.

---

## 1. What was broken

Resume was dead by construction, in five independent ways:

| Site | Problem |
|---|---|
| `graph.py:549` | `workflow.compile()` — no checkpointer at all |
| `graph.py:653` | `ainvoke(state)` — no `config`, so no `thread_id` |
| `checkpoints.py:25-265` | `PostgresCheckpointSaver` called **twice per run from outside the graph**: a run-status row, not a checkpointer |
| `checkpoints.py:88` → `core/privacy.py:84-109` | its payload went through `minimize_workflow_checkpoint`, which keeps counts and drops every substantive channel |
| `graph.py:724-727` / `:673` | `resume_draft_analysis_workflow` therefore raised **on purpose**, and rows were deleted on success anyway |

A run dying at node 15 of 18 re-executed all 18 and re-paid every LLM call.

## 2. Checkpointer choice, and the tradeoff

The prompt offered two options: LangGraph's `AsyncPostgresSaver` over a direct
connection, or `BaseCheckpointSaver` over `supabase.table()`. **Neither was
taken, and the reason is a dependency fact rather than a preference:**

```
langgraph                      0.2.64   installed
langgraph-checkpoint           2.1.2    installed   (BaseCheckpointSaver, JsonPlusSerializer)
langgraph-checkpoint-postgres           NOT installed
psycopg (v3)                            NOT installed   (project ships psycopg2-binary + asyncpg)
```

`langgraph.checkpoint.postgres` requires psycopg v3. Using it means adding **two**
dependencies to a frozen product. What was built instead is the third option:
`NoesisPostgresSaver` implements LangGraph's own `BaseCheckpointSaver`, uses
LangGraph's own `JsonPlusSerializer`, and writes the **upstream table shape**
(`thread_id / checkpoint_ns / checkpoint_id / parent_checkpoint_id / type /
checkpoint / metadata` plus a `checkpoint_writes` sidecar keyed on `task_id+idx`).
Migration `039_langgraph_checkpoints.sql` names them `noesis_lg_*` so the
canonical tables can be created alongside later — swapping to the upstream saver
is a rename, not a data migration.

**Why not `supabase.table()`.** It is the project's rule (`CLAUDE.md`) and it was
seriously considered. Two things rule it out for a checkpointer specifically:

1. **Integrity.** Resuming from a torn row is worse than restarting, because it
   costs money *and* produces output nobody can trust. The saver stores a
   `payload_sha256` and refuses to deserialize a row that fails it
   (`CheckpointCorruptError`). PostgREST would work for this, but it also means
   every checkpoint write is an HTTP round trip through Kong, PostgREST and
   PostgreSQL rather than one libpq round trip — and §5 shows the write latency
   is already the binding constraint on how much prefix survives a crash.
2. **Binary payloads.** `JsonPlusSerializer` emits msgpack bytes. Round-tripping
   those through PostgREST means base64 in JSON, which inflates the row and adds
   an encoding step in the one path that must not be clever.

**The honest cost of this choice:** the application otherwise has **no direct
Postgres connection anywhere** — everything goes through PostgREST, and
psycopg2/asyncpg have zero call sites in `app/`. Enabling checkpointing in a
deployed environment therefore requires provisioning
`NOESIS_CHECKPOINT_DB_URL` with the Supabase direct-connection string. Without
it the feature flag is inert and the graph compiles exactly as before. This is a
real operational cost of the decision, not a footnote.

**Default OFF.** `NOESIS_CHECKPOINT_ENABLED` unset ⇒ `build_checkpointer()`
returns `None` ⇒ `create_draft_analysis_workflow` takes a *branch* to bare
`workflow.compile()` rather than passing `checkpointer=None`, so compile-time
defaults cannot perturb the disabled path.

## 3. Privacy vs durability — reconciled, not traded

`minimize_workflow_checkpoint` exists because manuscript text should not sit
around. A real checkpointer must persist enough to resume. These look like they
must trade against each other. **Here they do not, and the reason is specific:**

The three channels that carry manuscript body text —

```python
MANUSCRIPT_CHANNELS = frozenset({"draft_content", "parse_artifact", "structure"})
```

— are **already caller-supplied parameters** of `run_draft_analysis_workflow`
(`draft_content`, `parse_artifact`, `initial_structure`). A caller that can start
a run can re-supply them on a resume, from Supabase Storage and
`draft_parse_artifacts`, exactly as it does on a fresh run. So excluding them
from the checkpoint costs **zero** resumability. `structure` is the only one a
node ever *writes* (`extract_structure`), and that node makes no LLM call — so
even in the worst case its exclusion costs no money.

`resume_draft_analysis_workflow(draft_id, draft_content, ...)` therefore **requires**
the manuscript, and `CheckpointRehydrationError` is raised rather than resuming
with an empty `draft_content`. The privacy design cannot silently decay into a
correctness bug.

**Where the scrubbing is applied** (all four, because missing any one leaks):
`checkpoint["channel_values"]`; the nested `__start__` channel, into which
LangGraph stages the *entire* input state as one dict; checkpoint `metadata`,
which carries `writes` and (for the first checkpoint) `source="input"` with the
whole input state; and pending writes.

### The honest limit

**A checkpoint row is not content-free.** Derived text — `claims[].claim_text`,
`reviewer_feedback[].feedback_text`, anchors — is quoted from the manuscript and
*is* in the row. That text is already stored durably and without expiry in
`draft_claims` and `reviewer_feedback`, so a checkpoint row introduces no new
*class* of content, and unlike those tables it carries a 24 h TTL and is deleted
eagerly on success. It is a shorter-lived copy of already-persisted data — but it
is a copy, and that is the accurate claim.

### A leak this work found

`route_to_reviewer_panel` dispatches
`Send("reviewer_panel_node", inject_context({**state, "reviewer_type": rt}))` —
**the entire state, manuscript included, once per persona**. LangGraph persists
those `Send` objects as pending writes on `__pregel_tasks`. The scrubber only
understood `dict`, so the `Send`s sailed through and the full manuscript was
written to disk three times per run. Every shape-based assertion passed; only
`test_no_manuscript_text_survives_the_crash`, which greps the raw `BYTEA`,
caught it. `_scrub_mapping` now handles `dict`, `list`/`tuple` and `Send`
recursively, with a matching `_rehydrate_mapping`.

## 4. The bespoke saver and deletion-on-success

**Kept, unchanged, and kept separate.** `PostgresCheckpointSaver` writes two
privacy-minimized run-status rows per run and is read by `get_workflow_progress`.
It is a *status recorder*; conflating it with checkpointing is what produced the
original bug, so the two concerns now live side by side in `checkpoints.py` with
the distinction stated in the module docstring, writing to different tables.

Deletion policy, by table:

* `draft_analysis_checkpoints` (status) — unchanged: written at start and end,
  deleted on success. Correct for a status row; nobody resumes from it.
* `noesis_lg_checkpoints` / `_writes` (real) — deleted eagerly on success (there
  is nothing left to resume and no reason to hold derived text), **retained on
  failure** (they are the entire point of that path), with a 24 h `expires_at`
  backstop for runs that die before reaching either.

**Reported, not fixed:** the bespoke saver is currently **unreachable on this
path**. `_run_draft_analysis_workflow` hardcodes `"stage_only": True` in the
initial state (commit `79dc543`), and commit `6ae7b11` added
`checkpoint_enabled = checkpoint_enabled and not stage_only`. So no status row is
ever written and `get_workflow_progress` always returns `not_started`. Both lines
predate this work and neither is a checkpointing concern, so they are left alone
and flagged here.

## 5. Benchmarks

Regenerate: `python3 scripts/eval/checkpoint_resume_bench.py --repeat 3`
Raw results: `scripts/eval/results/checkpoint_resume_bench.json`

### 5.1 Method, and what is stubbed

Two halves, deliberately separated:

* **Crash/resume behaviour** runs the *real* 18-node
  `create_draft_analysis_workflow` topology — real conditional edges, real 3-way
  `Send` fan-out, real `_traced_node` wrappers — with node **bodies** replaced by
  counting stubs. Bodies are what cost money; topology is what a checkpointer
  gets wrong. Stubbing the topology instead would have been the mistake.
* **Cost** comes from `node_eval.py` replaying each real node against the on-disk
  state fixtures (`EVAL_STATE_DIR`, `Makefile:16`) with real LLM calls and real
  `llm_budget`-recorded usage. Nothing is estimated from a tokenizer or a price
  list applied to a guess.

Each stub appends one `fsync`'d line to a ledger shared across both processes, so
node executions can be counted across the death boundary. Buffered I/O would lose
the last entries to SIGKILL and make the resume look better than it was.

### 5.2 Resume success rate — n = 27

A parent process runs the graph in a child, waits until *N* checkpoints are
**durable**, `SIGKILL`s the child, then resumes in a **new** interpreter.
Crash depths N ∈ {1,3,5,7,9,11,13,15,17}, 3 repeats.

| Metric | Value |
|---|---|
| SIGKILL confirmed (`returncode == -9`) | 27 / 27 |
| Resume completed to `END` in a fresh process | **27 / 27 (100%)** |
| Durable-prefix violations (a node at/before the last durable checkpoint re-ran) | **0** |
| Mean node executions preserved per trial | 8.44 |
| Distinct durable steps observed | 14 of 18 nodes |

The crash *moment* is chosen by the parent rather than by a sleep. This is not
the benchmark flattering itself: see §5.4 for why, and §5.5 for the uncontrolled
measurement reported alongside it.

Control arm (`test_cold_rerun_reexecutes_everything`): the same crash followed by
a fresh thread re-executes all **20** tasks and re-pays for every node the
crashed run had completed.

### 5.3 Tokens and dollars saved — n = 160 replays (8 papers)

Per-node measured cost, no-corpus configuration, `gpt-5.2-chat-latest` except
`editor_pass_node` (`gpt-5-mini`). "Graph" figures multiply the fan-out node by 3.

| Node | n | $/graph | tokens | wall (s) |
|---|---|---|---|---|
| extract_structure | 8 | 0.00000 | 0 | 0.01 |
| profile_manuscript | 8 | 0.00000 | 0 | 1.09 |
| extract_references | 8 | 0.00000 | 0 | 0.11 |
| **extract_claims** | 8 | **0.04227** | 14,291 | 12.70 |
| categorize_claims | 8 | 0.00000 | 0 | 0.00 |
| verify_citations | 8 | 0.00000 | 0 | 0.00 |
| search_literature | 8 | 0.00000 | 0 | 0.47 |
| map_citations | 8 | 0.00000 | 0 | 0.00 |
| detect_gaps | 8 | 0.00000 | 0 | 0.00 |
| discover_external_sources | 8 | 0.00000 | 0 | 0.04 |
| citation_judge_node | 8 | 0.00000 | 0 | 0.00 |
| run_quality_diagnostics | 8 | 0.00000 | 0 | 0.09 |
| **structural_checks** | 8 | **0.02193** | 6,919 | 12.53 |
| editor_pass_node | 8 | 0.00125 | 1,458 | 7.63 |
| **reviewer_panel_node** (×3) | 24 | **0.09504** | 47,757 | 55.10 |
| reviewer_judge_node | 8 | 0.00438 | 1,808 | 3.17 |
| **meta_reviewer_node** | 8 | **0.01834** | 5,614 | 12.60 |
| synthesize_report | 8 | 0.00000 | 0 | 0.00 |
| **full run** | | **$0.18322** | **77,847** | **105.6** |

Savings by how far the durable prefix reached:

| Durable prefix | resume enters at | $ saved | tokens saved | LLM wall saved | % of run |
|---|---|---|---|---|---|
| 4 nodes | categorize_claims | 0.0423 | 14,291 | 13.9 s | 23.1% |
| 13 nodes | editor_pass_node | 0.0642 | 21,210 | 27.0 s | 35.0% |
| 14 nodes | reviewer_panel_node | 0.0655 | 22,668 | 34.7 s | 35.7% |
| **15 nodes** | **reviewer_judge_node** | **0.1605** | **70,425** | **89.8 s** | **87.6%** |
| 16 nodes | meta_reviewer_node | 0.1649 | 72,233 | 92.9 s | 90.0% |
| 17 nodes | synthesize_report | 0.1832 | 77,847 | 105.5 s | 100% |
| *uniform mean over all 18* | | **0.0566** | **26,024** | | **30.9%** |

The shape is the point: **the value is almost entirely in the tail.** The reviewer
fan-out alone is 52% of the run's cost, so a crash *after* it is worth ~14× more
to resume than a crash before `extract_claims`. Ten of the eighteen nodes cost
$0 — they make no LLM call — so a checkpointer that only protected the cheap
prefix would be worthless.

Zero-cost caveats, stated because they bound the claim:

* Ten nodes have **no LLM call site at all** — their $0 is structural, not a
  measurement failure.
* `map_citations` and `citation_judge_node` **do** have call sites but measured
  $0 here: every fixture is from a *no-corpus* eval run, so
  `claims_with_citations` is empty and both nodes short-circuit
  (`citation_judge.py:180`). With a populated corpus they are non-zero, so
  **$0.18322 is a lower bound on full-run cost** and every saving above is a
  lower bound too.
* Costs are per-call `estimated_usd` from `llm_budget`, which prices
  `response.usage`. 228,608 of 557,784 prompt tokens were cache hits; the prices
  reflect that.

### 5.4 Wall-clock

Two different numbers, and conflating them would be dishonest:

* **Graph-machinery wall clock** (stubbed bodies, `--node-delay 0.15`): cold run
  **5.29 s** (n=3), mean resume **8.23 s** (n=27). Resume is *slower* here, and
  that is expected: with zero-cost node bodies the only work left is checkpoint
  I/O plus a fresh interpreter start, so the measurement is dominated by exactly
  the overhead resuming adds. It is reported because hiding it would be worse.
* **LLM wall clock saved** (measured, §5.3): resuming after the reviewer panel
  skips **89.8 s of 105.6 s** of node execution. This is the number that matters,
  because in a real run the nodes — not the checkpoint writes — are the clock.

Checkpoint write cost on this machine: a single `put` commit against Dockerised
Postgres has a **median of 42 ms and a p90 of 149 ms** (n=25). That is an
artefact of Docker Desktop on macOS (a *trivial* `INSERT`+`COMMIT` on the same
database measures 42 ms median / 259 ms max); a WAL fsync on server NVMe is
sub-millisecond. Read the ratio, not the absolute.

### 5.5 The durability lag — the caveat, measured rather than hidden

**LangGraph does not await `aput` inline.** It submits it to a background
executor and chains it on the previous write
(`langgraph/pregel/loop.py:705`, comment: *"save it, without blocking"*).
So "the node returned" and "the checkpoint is on disk" are two different events,
and a crash in between correctly loses that superstep.

That makes the durable prefix a function of *node duration ÷ write latency*.
Killing from **inside** a node at `reviewer_judge_node` (18 task executions
completed), n=3 per row:

| stub node duration | mean durable index | mean executions preserved | resume succeeded |
|---|---|---|---|
| 0 s | 0.0 | — | **2 / 3** |
| 0.02 s | 12.3 | 14.7 | 3 / 3 |
| 0.10 s | 14.0 | 17.0 | 3 / 3 |
| 0.30 s | 12.7 | 14.7 | 3 / 3 |

With instantaneous nodes the writer is outrun completely: in one of three trials
**zero** checkpoints had landed, so there was nothing to resume from and the
resume correctly failed. (The `executions_saved` figure is meaningless in that
row — nothing was preserved *and* nothing was re-executed, because nothing ran.)
Once node duration exceeds write latency the durable prefix is essentially
complete. Real nodes take **3–13 s** (§5.3) against a 42 ms write, a ratio of
70–300×, so production sits far to the right of this table — but the guarantee is
"at most the supersteps whose writes had not landed", not "everything that
returned", and that is the accurate statement.

This is also why the tests in §5.2 let the parent pick the kill moment: otherwise
they would be measuring Docker's fsync latency, and the only way to make them
green would be to tune a sleep until the flake stopped.

## 6. Interrupt / resume

Both halves work and are tested (`test_checkpoint_resume.py::TestInterrupt`):

* **Static** — `interrupt_before` from `NOESIS_CHECKPOINT_INTERRUPT_BEFORE`
  (comma-separated node names, empty by default). The graph durably stops before
  the named node; the run resumes with `ainvoke(None, config)`.
* **Dynamic** — `langgraph.types.interrupt()` raised inside a node, resumed with
  `Command(resume=value)`, threaded through
  `resume_draft_analysis_workflow(..., resume_value=...)`.

Both are unreachable while the feature flag is off, because neither exists
without a checkpointer. This is the substrate a durable human-in-the-loop
approval gate needs: the decision outlives the process.

## 7. Verification

| Requirement | Evidence |
|---|---|
| SIGKILL mid-graph, resume in a **new process** | `tests/test_checkpointer_resume.py::test_sigkill_mid_graph_resumes_in_a_new_process` — parametrised over 3 crash depths, asserts `returncode == -9` |
| Completed nodes **not** re-executed (counted) | `::test_completed_nodes_are_not_reexecuted_after_sigkill` — append-only cross-process ledger; asserts nothing at or before the last durable step re-runs |
| Cold-run control | `::test_cold_rerun_reexecutes_everything` — all 20 tasks re-run |
| Privacy after an ungraceful death | `::test_no_manuscript_text_survives_the_crash` — greps raw `BYTEA` |
| Resume refuses without the manuscript | `::test_resume_refuses_without_the_manuscript` |
| No regressions | `python3 -m pytest tests/ -q --ignore=tests/e2e` → **2 failed, 1064 passed**; both failures pre-existing and in files owned by another agent (`test_draft_quality_rescue.py`, `test_peer_review_panel.py`). Count did not grow. `tests/e2e` needs a live backend, which is not running. |
| Spend under ceiling | **$1.4658** of $6 |

`test_checkpointer_resume.py` (7 tests, cross-process) and
`test_checkpoint_resume.py` (34 tests, in-process) both pass. The split is
deliberate: in-process exception recovery does not evidence durability, because
it leaves the interpreter, the `Pregel` loop and the saver's connection alive.

## 8. Still unverified

* Never run against Supabase **production** Postgres — the RLS/`REVOKE` block in
  migration 039 is untested there. Production is off-limits by instruction;
  everything here ran against local Supabase (`127.0.0.1:54322`).
* The TTL sweep function `prune_expired_lg_checkpoints()` exists but is not
  scheduled.
* Crash/resume used stub node bodies, so the checkpoint machinery is proven, not
  the LLM output of a resumed run. The cost numbers come from real replays of
  real nodes, but the two were not measured in a single end-to-end resumed run —
  doing that needs the full Docker stack (GROBID, docling, backend, worker),
  which is not up.
* Cost is measured only in the no-corpus configuration (§5.3).
