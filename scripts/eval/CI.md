# CI and the eval gate

## The problem this exists to fix

`.github/workflows/ci.yml` contained zero references to `scripts/eval`. No
workflow ran `run_eval.py`, `check_heldout.py`, `benchmarks.py --check`, or any
`make eval-*` target. Meanwhile the regression gate inside `run_eval.py` had been
failing since 2026-06-20 — `scoreboard.json` reported `mean_overall 6.97` against
`min_overall: 8.5` in `config.yaml` — and nobody noticed, because nothing ran it.

A quality gate that nothing runs is not a gate. This file describes what now
runs, what deliberately does not, and why.

## The split: free vs. paid

Every real measurement in this project either costs OpenAI money or needs a
pgvector database holding an ingested corpus. A GitHub PR runner has neither.
So the work is split in two, and the split is the whole design:

| | Runs on a PR | Costs money | Needs a DB |
|---|---|---|---|
| `scripts/eval/ci_gate.py` | yes, blocking | no | no |
| `benchmarks.py --check` (full) | no — skips, sinks are gitignored | no | no |
| `run_eval.py` / `run_harness.py` | **never** | yes | yes |
| `retrieval/run_retrieval_eval.py` | **never** | yes | yes |
| `node_eval.py` replay | **never** | yes | no (needs gitignored fixtures) |

Nothing in the right-hand column may ever be added to the PR workflow. If you
want it in CI, it goes in `eval-nightly.yml`.

## Workflow layout

```
.github/workflows/
  ci.yml               push + pull_request. Now contains an `eval-gate` job.
  eval-nightly.yml     schedule + workflow_dispatch ONLY. Never blocks a merge.
```

### `ci.yml` → job `eval-gate`

Blocking. Two steps:

1. `pytest scripts/eval/tests/test_ci_gate.py -q` — the gate's own tests.
2. `python scripts/eval/ci_gate.py --base <PR base sha>` — the gate.

It checks out with `fetch-depth: 0` because the append-only check diffs against
the PR base commit; a shallow clone cannot resolve that ref and the check would
SKIP silently, which is worse than failing.

Nothing else in `ci.yml` was made stricter. `security` is still `|| true` and the
frontend steps still `|| echo` to success — those were already non-gating and
tightening them was not this change's job. The known backend baseline is
**984 passed, 2 failed** (`test_reviewer_context_caps_long_draft_at_24000`,
`test_reviewer_panel_failure_returns_empty_list`); both are pre-existing and
deliberately deferred, and `eval-gate` neither blocks on them nor hides them.

The `deploy` job SSHes into an EC2 box and runs `git reset --hard origin/master`.
**The product is frozen and that box is torn down** (see `VITE_FREEZE_MODE`), so
that job cannot succeed. It was left exactly as it was — fixing or removing it is
out of scope here and would be an unrelated change.

### `eval-nightly.yml`

`schedule` (07:00 UTC) and `workflow_dispatch` only. It has no `needs:`
relationship with any PR job and must **not** be added to branch protection.

| Job | What it does |
|---|---|
| `integrity-strict` | the same gate as the PR, with `--strict` (warnings fail) |
| `preflight` | resolves credential presence into job outputs |
| `node-replay` | paid node replay, with `NOESIS_LLM_MAX_SPEND_USD` set |
| `retrieval-eval` | paid + DB retrieval eval |
| `notify` | opens a GitHub issue when a scheduled run fails |

A missing credential produces a **skipped** job and a `::warning::`, never a
green tick. `skipped` means "not measured", not "passed" — the notification body
says so explicitly, because the failure mode this repo actually hit was a silent
absence of measurement, not a loud failure.

Cron on GitHub is best-effort and can be dropped entirely on a quiet repo. Treat
a missing nightly run as *unknown*, not as *passed*.

## What the owner must configure

No secret values appear anywhere in this repo, and none should be committed.
Set these as **repository secrets** (Settings → Secrets and variables → Actions):

| Secret | Needed by | Effect if unset |
|---|---|---|
| `OPENAI_API_KEY` | `node-replay`, `retrieval-eval` | both jobs skip with a warning |
| `EVAL_DB_HOST` | `retrieval-eval` | job skips with a warning |
| `EVAL_DB_PORT`, `EVAL_DB_NAME`, `EVAL_DB_USER`, `EVAL_DB_PASSWORD` | `retrieval-eval` | falls back to `db.py` local defaults, which will not resolve on a runner |

Also required for the nightly to do anything real, and **not** solvable with
secrets:

- **Replay fixtures.** `scripts/eval/cache/` is gitignored, so a clean
  GitHub-hosted checkout has no state fixtures and `node_eval.py` has nothing to
  replay. The workflow detects this and skips loudly. To make it real, either
  run the nightly on a runner that holds the eval cache, or restore
  `scripts/eval/cache/state/` from an artifact before the replay step.
- **An ingested corpus.** `retrieval-eval` needs a pgvector database that already
  holds the eval corpus. Against an empty database the harness records the run
  `valid: false` — which the integrity gate then refuses to let anyone quote.

Branch protection: mark `eval-gate` as required. Do not mark any nightly job as
required.

## `ci_gate.py`

```
python3 scripts/eval/ci_gate.py                     # working tree vs HEAD
python3 scripts/eval/ci_gate.py --base origin/master
python3 scripts/eval/ci_gate.py --strict            # warnings become failures
python3 scripts/eval/ci_gate.py --json              # machine-readable
```

Stdlib only. No network, no database, no credentials — `pyyaml` is deliberately
not imported, which is why the threshold parser is a twelve-line regex reader.

### Exit codes

| Code | Meaning |
|---|---|
| 0 | all blocking checks passed (warnings may have been printed) |
| 1 | at least one blocking check FAILED |
| 2 | warnings present and `--strict` was given |
| 3 | the gate itself could not run (not a git repo, git unavailable, bad args) |

Every failure prints the exact command to reproduce it locally.

### The checks

Each encodes a failure mode this project actually hit.

**`board-tracked-sources`** — blocking, runs everywhere.
`benchmarks.json` records a line count for each sink it was built from. If a sink
that is *tracked in git* has a different line count than the board recorded, the
board is stale. A drifted board is a lying board. Fix: `make benchmarks`, commit
both `BENCHMARKS.md` and `benchmarks.json`.

**`board-regenerates`** — blocking where runnable, otherwise SKIP.
The full `benchmarks.py --check`. Four of its eight sinks are gitignored
(`retrieval_eval.jsonl`, `node_eval_spans.jsonl`, `ingest_manifest.jsonl`,
`ann_sweep.jsonl`), so on a clean checkout the board **cannot** be regenerated
and this check SKIPs rather than failing on absent data. That is the honest
answer, not a hole: `board-tracked-sources` still covers the tracked sinks in CI,
and this check does the complete job on any machine that has the sinks. Run it
locally with `make benchmarks-check`.

**`append-only`** — blocking, runs everywhere.
`results/history.jsonl`, `results/openreview_history.jsonl` and
`results/node_eval.jsonl` are append-only: they are the only durable record this
repo has of its own eval scores. The check requires the base ref's content to be
a line-wise prefix of the current content, so a shrink or an in-place line
rewrite fails. This repo already destroyed its eval history once by overwriting
`scoreboard.json` in place; that is why the check exists and why it blocks.
Recovery is printed in the failure message:
`git show <base>:<path> > <path>`, then append the new records.

**`invalid-run-quoted`** — blocking, runs everywhere.
`run_retrieval_eval.py` marks a run `valid: false` when its verdict finds a join
bug or an empty fusion leg, and prints `RUN INVALID -- DO NOT QUOTE THESE
NUMBERS`. This check builds the registry of invalidated `run_id`s from the
tracked board (`retrieval.invalidated[*].run_id`) plus any jsonl sink present in
the checkout, then scans tracked measurement markdown for those ids. A mention
alongside a number, with no invalidation marker within three lines, fails.
`gold/*.md` are excluded — they are reference critiques, not measurement reports.
In CI the registry comes from the board alone, since the sinks are gitignored;
locally it is a superset.

**`metric-without-n`** — warning.
A headline metric (`recall@k`, `NDCG@k`, `MRR`, `precision@k`, `mean overall`)
stated with a number and no sample size within two lines. It is a warning and not
a gate on purpose: a markdown table can legitimately carry its `n` in a column
header or a caption the heuristic cannot see, and against the current docs it
reports **38** hits, most of them table rows whose `n` lives in the surrounding
prose. A noisy blocking check gets disabled, and a disabled check is worth less
than an honest warning. `--strict` promotes it, and the nightly runs `--strict`.

**`threshold-note`** — warning.
If the `thresholds:` block in `config.yaml` moves relative to the base ref and
the new value is not mentioned in the threshold change log below, warn. Moving
`min_overall` is how a failing gate becomes a passing one without any code
improving, so it should be visible in review — but it is legitimate often enough
that blocking would be wrong.

## Threshold change log

Add a line here whenever `scripts/eval/config.yaml` thresholds move. Name the
key, the old and new value, and why.

- (no changes recorded yet — `min_overall: 8.5`, `min_dim_score: 7.5`,
  `max_mean_drop: 0.5` as of this file's creation)

> Standing note, not a change: `min_overall: 8.5` has been violated by the
> measured `mean_overall 6.97` since 2026-06-20. The gate is correct and the
> product is below it. Lowering the threshold to make it green would be exactly
> the move this log exists to make visible.

## Known open findings

**The `eval-gate` job will be red on its first run, and it is right to be.**
Against a clean clone (what CI sees), the gate reports:

- **FAIL `board-tracked-sources`** — the committed `benchmarks.json` records 31
  lines for `results/node_eval.jsonl`, but the committed `node_eval.jsonl` holds
  14. The board was regenerated locally against 31 records and committed, while
  the 17 newer records were never committed. The tracked board therefore
  describes data that does not exist at `HEAD` — precisely the "generated
  artefact drifted from its source" failure this check is for.
  Fix: commit the appended `scripts/eval/results/node_eval.jsonl` records (they
  are already un-gitignored for exactly this reason), then `make benchmarks` and
  commit both board outputs.

Running `python3 scripts/eval/ci_gate.py` on a full local checkout (where the
gitignored sinks exist) additionally reports:

- **FAIL `board-regenerates`** — the tracked `BENCHMARKS.md` and
  `benchmarks.json` are stale. The board records 8 records for
  `results/retrieval_eval.jsonl`; the file holds 15. Fix with `make benchmarks`
  and commit both outputs. This does not fire in CI, where the sink is absent.
- **WARN `metric-without-n`** — 38 hits across `ANN_SWEEP.md`, `BASELINE_15.md`,
  `KEYWORD_QUERY.md`, `BENCHMARKS.md` and `retrieval/BASELINE.md`.
- **Not a gate finding, but adjacent:** `results/history.jsonl` does not exist
  and `results/openreview_history.jsonl` is untracked, even though `.gitignore`
  negates both specifically so they would survive a clone. Until they are
  committed, the append-only check has only `node_eval.jsonl` to protect.
