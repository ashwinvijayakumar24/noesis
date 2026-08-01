"""
Benchmark for durable checkpointing and mid-graph resume (N11).

Three independent measurements, none of which spends money:

1. **Resume success rate across crash depths.** A parent process runs the real
   ``create_draft_analysis_workflow`` topology in a child, waits until N
   checkpoints are durable, SIGKILLs the child, and resumes in a *fresh
   interpreter*. Records whether the resume completed and, crucially, whether any
   node at or before the last durable step re-executed. ``n = len(--crash-points)
   x --repeat``.

2. **Checkpoint-durability lag.** LangGraph does not await ``aput`` inline -- it
   submits it to a background executor (``pregel/loop.py:705``). So the durable
   prefix at the moment of a crash is not "every node that returned", it is
   "every node whose checkpoint write had landed". This sweep kills from *inside*
   a node at varying node durations and measures how much prefix survives -- the
   difference between a durability guarantee and a hope. It is reported
   separately so measurement (1) cannot be mistaken for it.

3. **Tokens and dollars saved.** The per-node cost of the completed prefix,
   from *measured* replays produced by ``node_eval.py`` against the on-disk state
   fixtures (``--node-costs``). Nothing here is estimated from a token count or a
   price list applied to a guess; a node with no successful replay is reported as
   unmeasured rather than filled in.

The graph runs with stubbed node *bodies* and the real topology, real conditional
edges and the real 3-way ``Send`` fan-out. Node bodies are what cost money;
topology is what the checkpointer has to get right.

Usage
-----
    python3 scripts/eval/checkpoint_resume_bench.py \\
        --dsn postgresql://postgres:postgres@127.0.0.1:54322/postgres \\
        --node-costs scripts/eval/results/checkpoint_bench_nodes.jsonl \\
        --out scripts/eval/results/checkpoint_resume_bench.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND = REPO_ROOT / "services" / "backend"
WORKER = BACKEND / "tests" / "_checkpoint_worker.py"

sys.path.insert(0, str(BACKEND))
from tests._checkpoint_worker import NODE_NAMES  # noqa: E402
from tests.test_checkpointer_resume import (  # noqa: E402
    NODE_DELAY,
    _drop,
    _last_durable_step,
    sigkill_after_durable,
)

#: The reviewer fan-out is one superstep containing three tasks, so a single
#: "node execution" count of 3 for ``reviewer_panel_node`` is the healthy value.
FANOUT_NODES = {"reviewer_panel_node": 3}


def _run_worker(dsn: str, thread: str, ledger: Path, mode: str, **kw) -> dict[str, Any]:
    cmd = [
        sys.executable,
        str(WORKER),
        "--dsn", dsn,
        "--thread", thread,
        "--ledger", str(ledger),
        "--mode", mode,
    ]
    for flag, value in kw.items():
        if value is None:
            continue
        cmd += [f"--{flag.replace('_', '-')}", str(value)]
    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(BACKEND))
    wall = time.time() - started
    payload: dict[str, Any] = {}
    for line in proc.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                pass
    return {
        "returncode": proc.returncode,
        "wall_seconds": round(wall, 4),
        "payload": payload,
        "stderr_tail": proc.stderr.strip().splitlines()[-3:],
    }


def _ledger_counts(path: Path) -> Counter:
    counts: Counter = Counter()
    if not path.exists():
        return counts
    for line in path.read_text().splitlines():
        if line.strip():
            counts[json.loads(line)["node"]] += 1
    return counts


def _drop_thread(dsn: str, thread: str) -> None:
    import psycopg2

    conn = psycopg2.connect(dsn)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM public.noesis_lg_checkpoint_writes WHERE thread_id = %s",
                (thread,),
            )
            cur.execute(
                "DELETE FROM public.noesis_lg_checkpoints WHERE thread_id = %s",
                (thread,),
            )
        conn.commit()
    finally:
        conn.close()


def _expected(node: str) -> int:
    return FANOUT_NODES.get(node, 1)


def crash_and_resume(dsn: str, min_checkpoints: int, tmp: Path) -> dict[str, Any]:
    """One parent-delivered SIGKILL + one out-of-process resume.

    The crash point is expressed as "after N durable checkpoints" rather than
    "inside node X", because N is the only thing a resume can be graded against:
    a superstep whose write never landed was never durable and must re-run.
    """
    thread = f"bench-{uuid.uuid4()}"
    ledger = tmp / f"{thread}.jsonl"
    started = time.time()
    returncode, durable_step = sigkill_after_durable(thread, ledger, min_checkpoints)
    run_wall = time.time() - started
    before = _ledger_counts(ledger)

    resume = _run_worker(dsn, thread, ledger, "resume", node_delay=NODE_DELAY)
    after = _ledger_counts(ledger)

    reexecuted = {n: after[n] - before[n] for n in before if after[n] > before[n]}
    durable_idx = NODE_NAMES.index(durable_step) if durable_step in NODE_NAMES else -1
    # Re-running a node whose checkpoint never landed is correct. Re-running one
    # at or before the last durable step is a bug.
    violations = [n for n in reexecuted if NODE_NAMES.index(n) <= durable_idx]

    _drop(thread)
    try:
        ledger.unlink()
    except OSError:
        pass

    return {
        "min_checkpoints": min_checkpoints,
        "killed_by_signal": returncode == -9,
        "durable_step": durable_step,
        "durable_index": durable_idx + 1,
        "executions_before_crash": sum(before.values()),
        "resume_ok": bool(resume["payload"].get("ok")),
        "resume_progress": resume["payload"].get("progress_percentage"),
        "resume_reviewer_outputs": resume["payload"].get("reviewer_outputs"),
        "resume_error": resume["payload"].get("error"),
        "reexecuted": reexecuted,
        "durable_prefix_violations": violations,
        "executions_saved": sum(before.values()) - sum(reexecuted.values()),
        "run_wall_seconds": round(run_wall, 4),
        "resume_wall_seconds": resume["wall_seconds"],
        "resume_graph_seconds": resume["payload"].get("wall_seconds"),
    }


def uncontrolled_crash(dsn: str, kill_at: str, node_delay: float, tmp: Path) -> dict[str, Any]:
    """The honest, unpinned case: the process kills itself inside a node.

    Whatever the background checkpoint writer had managed to land is what
    survives. This is what a real crash looks like, and it is reported separately
    so the pinned numbers above cannot be mistaken for it.
    """
    thread = f"bench-unc-{uuid.uuid4()}"
    ledger = tmp / f"{thread}.jsonl"
    _run_worker(dsn, thread, ledger, "run", kill_at=kill_at, node_delay=node_delay)
    before = _ledger_counts(ledger)
    durable_step = _last_durable_step(thread)
    resume = _run_worker(dsn, thread, ledger, "resume", node_delay=node_delay)
    after = _ledger_counts(ledger)
    reexecuted = {n: after[n] - before[n] for n in before if after[n] > before[n]}
    _drop(thread)
    try:
        ledger.unlink()
    except OSError:
        pass
    return {
        "kill_at": kill_at,
        "node_delay": node_delay,
        "executions_before_crash": sum(before.values()),
        "durable_step": durable_step,
        "durable_index": (
            NODE_NAMES.index(durable_step) + 1 if durable_step in NODE_NAMES else 0
        ),
        "resume_ok": bool(resume["payload"].get("ok")),
        "reexecuted_count": sum(reexecuted.values()),
        "executions_saved": sum(before.values()) - sum(reexecuted.values()),
    }


def cold_run(dsn: str, node_delay: float, tmp: Path) -> dict[str, Any]:
    thread = f"bench-cold-{uuid.uuid4()}"
    ledger = tmp / f"{thread}.jsonl"
    res = _run_worker(dsn, thread, ledger, "run", node_delay=node_delay)
    counts = _ledger_counts(ledger)
    _drop_thread(dsn, thread)
    try:
        ledger.unlink()
    except OSError:
        pass
    return {
        "ok": bool(res["payload"].get("ok")),
        "executions": sum(counts.values()),
        "wall_seconds": res["wall_seconds"],
        "graph_seconds": res["payload"].get("wall_seconds"),
    }


# ---------------------------------------------------------------------------
# Measured per-node cost, from node_eval replays against the state fixtures
# ---------------------------------------------------------------------------


def load_node_costs(path: Path) -> dict[str, dict[str, Any]]:
    """Aggregate ``node_eval.py`` replay records into per-node measured cost.

    Only ``status == "ok"`` replays count. A node that never replayed cleanly is
    absent from the result and is reported as unmeasured downstream -- filling it
    in with a neighbour's cost would manufacture exactly the kind of
    unprovenanced number this repo has been removing.
    """
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("record_type") != "replay" or rec.get("status") != "ok":
            continue
        usage = rec.get("usage") or {}
        buckets[rec["node"]].append(
            {
                "usd": float(usage.get("estimated_usd") or 0.0),
                "tokens": int(usage.get("total_tokens") or 0),
                "calls": int(usage.get("calls") or 0),
                "wall": float(rec.get("wall_seconds") or 0.0),
            }
        )

    out: dict[str, dict[str, Any]] = {}
    for node, rows in buckets.items():
        # The fan-out runs three personas per graph execution; a replay is one
        # persona, so the graph-level cost of that node is 3x a replay.
        multiplier = FANOUT_NODES.get(node, 1)
        out[node] = {
            "n_replays": len(rows),
            "mean_usd_per_replay": round(statistics.mean(r["usd"] for r in rows), 6),
            "mean_tokens_per_replay": round(statistics.mean(r["tokens"] for r in rows), 1),
            "mean_wall_per_replay": round(statistics.mean(r["wall"] for r in rows), 3),
            "graph_multiplier": multiplier,
            "graph_usd": round(statistics.mean(r["usd"] for r in rows) * multiplier, 6),
            "graph_tokens": round(statistics.mean(r["tokens"] for r in rows) * multiplier, 1),
            "graph_wall": round(statistics.mean(r["wall"] for r in rows) * multiplier, 3),
        }
    return out


def savings_table(costs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """For every durable prefix length, what that prefix already paid for.

    Resuming skips the prefix; a cold re-run pays it again. That difference is
    the headline number, and it is a *measured* sum of measured parts -- each
    per-node figure comes from ``node_eval.py`` replaying that node against real
    on-disk state fixtures with real LLM calls and real recorded usage.
    """
    measured = [n for n in NODE_NAMES if n in costs]
    unmeasured = [n for n in NODE_NAMES if n not in costs]
    full_usd = sum(costs[n]["graph_usd"] for n in measured)
    full_tokens = sum(costs[n]["graph_tokens"] for n in measured)
    full_wall = sum(costs[n]["graph_wall"] for n in measured)

    rows = []
    for idx, node in enumerate(NODE_NAMES):
        prefix = [n for n in NODE_NAMES[:idx] if n in costs]
        saved_usd = sum(costs[n]["graph_usd"] for n in prefix)
        saved_tokens = sum(costs[n]["graph_tokens"] for n in prefix)
        saved_wall = sum(costs[n]["graph_wall"] for n in prefix)
        rows.append(
            {
                "resumed_at": node,
                "durable_prefix_length": idx,
                "prefix_nodes_measured": len(prefix),
                "prefix_nodes_unmeasured": idx - len(prefix),
                "usd_saved": round(saved_usd, 6),
                "tokens_saved": round(saved_tokens, 1),
                "wall_seconds_saved": round(saved_wall, 3),
                "pct_of_full_run_usd": (
                    round(100 * saved_usd / full_usd, 1) if full_usd else None
                ),
            }
        )
    return {
        "nodes_measured": len(measured),
        "nodes_unmeasured": unmeasured,
        "full_run_usd": round(full_usd, 6),
        "full_run_tokens": round(full_tokens, 1),
        "full_run_wall_seconds": round(full_wall, 3),
        "per_crash_point": rows,
        "mean_usd_saved_uniform_crash": round(
            statistics.mean(r["usd_saved"] for r in rows), 6
        ),
        "mean_tokens_saved_uniform_crash": round(
            statistics.mean(r["tokens_saved"] for r in rows), 1
        ),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dsn", default=os.environ.get(
        "NOESIS_TEST_CHECKPOINT_DSN",
        "postgresql://postgres:postgres@127.0.0.1:54322/postgres",
    ))
    p.add_argument("--repeat", type=int, default=1)
    p.add_argument("--crash-points", default="1,3,5,7,9,11,13,15,17",
                   help="durable-checkpoint counts at which to SIGKILL")
    p.add_argument("--delay-sweep", default="0,0.02,0.1,0.3",
                   help="node durations for the uncontrolled-crash sweep")
    p.add_argument("--sweep-kill-at", default="reviewer_judge_node")
    p.add_argument("--node-costs", type=Path,
                   default=REPO_ROOT / "scripts/eval/results/checkpoint_bench_nodes.jsonl")
    p.add_argument("--out", type=Path,
                   default=REPO_ROOT / "scripts/eval/results/checkpoint_resume_bench.json")
    args = p.parse_args(argv)

    result: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "dsn_host": args.dsn.split("@")[-1],
        "node_order": NODE_NAMES,
        "node_delay_seconds": NODE_DELAY,
    }

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # -- 1. resume success across crash depths --------------------------
        points = [int(x) for x in args.crash_points.split(",") if x.strip()]
        trials = []
        for _ in range(args.repeat):
            for k in points:
                t = crash_and_resume(args.dsn, k, tmp)
                trials.append(t)
                print(
                    f"  durable>={k:<3} sigkill={t['killed_by_signal']} "
                    f"resume_ok={t['resume_ok']} durable_step={t['durable_step']} "
                    f"saved={t['executions_saved']}/{t['executions_before_crash']} "
                    f"violations={t['durable_prefix_violations']}",
                    flush=True,
                )
        result["crash_matrix"] = {
            "n": len(trials),
            "sigkill_confirmed": sum(1 for t in trials if t["killed_by_signal"]),
            "resume_success": sum(1 for t in trials if t["resume_ok"]),
            "resume_success_rate": round(
                sum(1 for t in trials if t["resume_ok"]) / len(trials), 4
            ),
            "durable_prefix_violations": sum(
                len(t["durable_prefix_violations"]) for t in trials
            ),
            "mean_executions_saved": round(
                statistics.mean(t["executions_saved"] for t in trials), 2
            ),
            "mean_resume_wall_seconds": round(
                statistics.mean(t["resume_wall_seconds"] for t in trials), 3
            ),
            "distinct_durable_steps": sorted(
                {t["durable_step"] for t in trials if t["durable_step"]}
            ),
            "trials": trials,
        }

        # -- 2. cold-run control --------------------------------------------
        colds = [cold_run(args.dsn, NODE_DELAY, tmp) for _ in range(3)]
        result["cold_run"] = {
            "n": len(colds),
            "node_delay": NODE_DELAY,
            "executions": colds[0]["executions"],
            "mean_wall_seconds": round(
                statistics.mean(c["wall_seconds"] for c in colds), 4
            ),
            "mean_graph_seconds": round(
                statistics.mean(c["graph_seconds"] or 0 for c in colds), 4
            ),
            "runs": colds,
        }

        # -- 3. uncontrolled crash: how much prefix actually survives --------
        sweep = []
        for delay in [float(x) for x in args.delay_sweep.split(",") if x.strip()]:
            for _ in range(max(1, args.repeat)):
                t = uncontrolled_crash(args.dsn, args.sweep_kill_at, delay, tmp)
                sweep.append(t)
                print(
                    f"  uncontrolled delay={delay:<6} ran={t['executions_before_crash']} "
                    f"durable={t['durable_index']} resume_ok={t['resume_ok']} "
                    f"saved={t['executions_saved']}",
                    flush=True,
                )
        by_delay: dict[float, list[dict]] = defaultdict(list)
        for t in sweep:
            by_delay[t["node_delay"]].append(t)
        result["durability_lag_sweep"] = {
            "kill_at": args.sweep_kill_at,
            "kill_index": NODE_NAMES.index(args.sweep_kill_at) + 1,
            "note": (
                "LangGraph submits aput to a background executor "
                "(langgraph/pregel/loop.py:705) rather than awaiting it inline, so "
                "the durable prefix at crash time is the set of checkpoints that "
                "had LANDED, not the set of nodes that had returned. With "
                "sub-millisecond stub nodes the writer is outrun; with node "
                "durations comparable to real ones it is not."
            ),
            "by_node_delay": {
                str(d): {
                    "n": len(ts),
                    "mean_executions_before_crash": round(
                        statistics.mean(t["executions_before_crash"] for t in ts), 2
                    ),
                    "mean_durable_index": round(
                        statistics.mean(t["durable_index"] for t in ts), 2
                    ),
                    "mean_executions_saved": round(
                        statistics.mean(t["executions_saved"] for t in ts), 2
                    ),
                    "resume_success_rate": round(
                        sum(1 for t in ts if t["resume_ok"]) / len(ts), 3
                    ),
                }
                for d, ts in sorted(by_delay.items())
            },
            "trials": sweep,
        }

    if args.node_costs.exists():
        costs = load_node_costs(args.node_costs)
        result["node_costs"] = costs
        result["savings"] = savings_table(costs)
    else:
        result["node_costs_error"] = f"{args.node_costs} not found"

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2))
    print(f"\nwrote {args.out}")
    cm = result["crash_matrix"]
    print(
        f"resume success {cm['resume_success']}/{cm['n']} "
        f"| durable-prefix violations {cm['durable_prefix_violations']}"
    )
    if "savings" in result:
        sv = result["savings"]
        print(
            f"full run ${sv['full_run_usd']} over {sv['nodes_measured']} measured nodes; "
            f"mean saved on a uniform crash ${sv['mean_usd_saved_uniform_crash']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
