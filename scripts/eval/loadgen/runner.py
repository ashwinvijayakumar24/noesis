"""CLI: offer load at the draft-analysis graph and report what came back.

    cd scripts/eval
    python3 -m loadgen.runner --dry-run --mode open --lam 0.05 --n 120
    python3 -m loadgen.runner --mode open --lam 0.02 0.05 0.10 --n 120 --warmup 8
    python3 -m loadgen.runner --mode closed --concurrency 1 2 4 --n 120
    python3 -m loadgen.runner --compare-fanout --mode closed --concurrency 1 --n 40
    python3 -m loadgen.runner --real-llm --n 3 --warmup 1 --mode closed --concurrency 1 --yes

Cost control, in the order the brakes engage:

1. ``--dry-run`` prints the planned request count and estimated spend and then
   exits. It never imports a node and never makes a call.
2. Stub mode is the default. Real calls require ``--real-llm`` *and* ``--yes``.
3. ``--real-llm`` sets ``NOESIS_LLM_MAX_CALLS`` and ``NOESIS_LLM_MAX_SPEND_USD``
   before anything is imported, so ``llm_budget.check_llm_allowed`` halts the
   run from inside every call site if the estimate was wrong.

Results append to ``scripts/eval/results/loadgen.jsonl``, keyed by a config hash
that includes the load model. Append-only, never rewritten in place.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from . import EVAL_DIR, EXCLUSION_NOTE
from .latency_profile import LatencyProfile, env_profile
from .loadmodel import LoadModel, RunResult, run_load
from .stats import Summary, summarize, table
from .workload import GraphWorkload, load_fixtures

DEFAULT_RESULTS = EVAL_DIR / "results" / "loadgen.jsonl"

#: LLM calls per graph run, as (low, high). Counted, not guessed: stub runs
#: record every call by node, and a no-corpus run comes out at 8-9 (extract_claims 1,
#: structural_checks 1, editor_pass 1, reviewer_panel 3 + up to 2 judge-triggered
#: retries, reviewer_judge 1, meta_reviewer 1). `high` allows for validation
#: retries and domain-trigger audits. Bounds the --dry-run estimate only; the run
#: itself is bounded by NOESIS_LLM_MAX_CALLS.
#:
#: NOTE this is the *no-corpus* call count. With project documents present,
#: search_literature / map_citations / detect_gaps / citation_judge stop
#: short-circuiting and add calls, so a corpus-backed run is strictly more
#: expensive and strictly slower than anything measured here.
CALLS_PER_RUN = (8, 14)

#: Mean $/call across the two nodes with recorded spend (NODE_COST.md:
#: reviewer_panel $0.0242/call, editor_pass $0.00113/call). A wide, honest
#: bracket rather than a single number, because 16 of 18 nodes have never had
#: their spend recorded.
USD_PER_CALL = (0.002, 0.030)


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------

def dry_run_report(models: list[LoadModel], fixtures_n: int) -> str:
    lines = [
        "DRY RUN -- no LLM call, no graph import, no request issued.",
        EXCLUSION_NOTE,
        f"fixtures available: {fixtures_n}",
        "",
    ]
    total_runs = sum(m.n_requests for m in models)
    for m in models:
        lo, hi = CALLS_PER_RUN
        lines.append(f"  {m.describe()}")
        lines.append(
            f"      graph runs: {m.n_requests}  "
            f"(measured {m.n_requests - m.warmup_requests}, warmup {m.warmup_requests})"
        )
        lines.append(f"      LLM calls: {m.n_requests * lo}-{m.n_requests * hi}")
        if m.llm == "real":
            lines.append(
                f"      est. spend: ${m.n_requests * lo * USD_PER_CALL[0]:.2f}"
                f"-${m.n_requests * hi * USD_PER_CALL[1]:.2f}"
            )
        else:
            lines.append("      est. spend: $0.00 (stubbed LLM -- zero network calls)")
        if m.mode == "open" and m.rate:
            lines.append(f"      est. arrival span: {m.n_requests / m.rate:,.0f}s")
    lines.append("")
    lo, hi = CALLS_PER_RUN
    real = [m for m in models if m.llm == "real"]
    lines.append(f"TOTAL graph runs: {total_runs}")
    lines.append(f"TOTAL LLM calls: {total_runs * lo}-{total_runs * hi}")
    if real:
        n = sum(m.n_requests for m in real)
        lines.append(
            f"TOTAL estimated spend: ${n * lo * USD_PER_CALL[0]:.2f}"
            f"-${n * hi * USD_PER_CALL[1]:.2f}  (REAL LLM)"
        )
    else:
        lines.append("TOTAL estimated spend: $0.00 (all models stubbed)")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def _extra_from(result: RunResult, profile: LatencyProfile, control) -> dict:
    graph = [r.detail.get("graph_seconds") for r in result.records
             if not r.warmup and r.ok and r.detail.get("graph_seconds")]
    branches = [r.detail.get("reviewer_branches", 0) for r in result.records
                if not r.warmup and r.ok]
    extra: dict = {
        "exclusions_note": EXCLUSION_NOTE,
        "latency_profile": profile.to_dict(),
        "profile_provenance": profile.provenance(),
        "reviewer_branches_mean": round(statistics.fmean(branches), 3) if branches else None,
        "chars_mean": round(statistics.fmean(
            [r.detail.get("chars", 0) for r in result.records if r.ok and r.detail]
        ), 1) if any(r.detail for r in result.records) else None,
    }
    if graph:
        extra["graph_seconds_mean"] = round(statistics.fmean(graph), 4)
    if control is not None:
        extra["stub_llm_calls"] = control.counters.calls
        extra["stub_llm_calls_by_node"] = dict(sorted(control.counters.by_node.items()))
        extra["supabase_write_attempts"] = len(control.guard.write_attempts)
        extra["supabase_reads"] = control.guard.reads
    try:
        from app.core.llm_budget import totals
        t = totals()
        extra["llm_budget_totals"] = {
            "calls": t["calls"],
            "estimated_usd": round(t["estimated_usd"], 6),
            "prompt_tokens": t["prompt_tokens"],
            "completion_tokens": t["completion_tokens"],
        }
    except Exception:
        pass
    return extra


async def execute(models: list[LoadModel], args) -> list[Summary]:
    from .stubs import install_stubs
    from . import fanout

    if args.trace:
        # Per-node spans, so the fan-out's actual overlap can be measured rather
        # than inferred from the total. Read back with trace_report.
        from app.core.tracing import configure_tracing
        configure_tracing("jsonl", str(args.trace))

    profile = env_profile(seed=args.seed, speedup=args.speedup)
    control = install_stubs(profile, stub_llm=not args.real_llm, list_len=args.list_len)

    # Import the graph only AFTER install_stubs has rebound the client modules.
    import app.workflows.draft_analysis.graph  # noqa: F401

    fixtures = load_fixtures(papers=args.papers or None)
    if not fixtures:
        raise SystemExit("no state fixtures found under scripts/eval/cache/state/")

    summaries: list[Summary] = []
    for m in models:
        if m.serial_reviewers:
            fanout.install_serial_reviewers()
        else:
            fanout.restore_reviewers()
        workload = GraphWorkload(fixtures)
        print(f"\n>>> {m.describe()}", flush=True)
        t0 = time.perf_counter()
        result = await run_load(workload, m)
        print(f"    done in {time.perf_counter() - t0:,.1f}s", flush=True)
        control.assert_no_writes()
        summaries.append(summarize(result, extra=_extra_from(result, profile, control)))
    fanout.restore_reviewers()
    return summaries


def append_results(summaries: list[Summary], path: Path, run_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:  # append-only, always
        for s in summaries:
            fh.write(json.dumps({
                "record_type": "loadgen",
                "run_id": run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **s.to_dict(),
            }, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_models(args) -> list[LoadModel]:
    common = dict(
        n_requests=args.n,
        warmup_requests=args.warmup,
        slo_seconds=args.slo,
        seed=args.seed,
        llm="real" if args.real_llm else "stub",
        workload="graph",
    )
    models: list[LoadModel] = []
    variants = [False, True] if args.compare_fanout else [args.serial_reviewers]
    for serial in variants:
        if args.mode == "open":
            for lam in args.lam:
                models.append(LoadModel(mode="open", rate=lam, serial_reviewers=serial, **common))
        else:
            for c in args.concurrency:
                models.append(LoadModel(mode="closed", concurrency=c, serial_reviewers=serial, **common))
    return models


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="loadgen.runner",
        description="Load-test the 18-node draft-analysis graph. GRAPH-LEVEL latency only.",
    )
    p.add_argument("--mode", choices=["open", "closed"], default="open")
    p.add_argument("--lam", type=float, nargs="+", default=[0.05],
                   help="open-loop Poisson arrival rate(s), req/s; repeat for a sweep")
    p.add_argument("--concurrency", type=int, nargs="+", default=[2],
                   help="closed-loop worker count(s); repeat for a sweep")
    p.add_argument("--n", type=int, default=40, help="requests offered per load point")
    p.add_argument("--warmup", type=int, default=4,
                   help="leading requests discarded from all statistics")
    p.add_argument("--slo", type=float, default=60.0,
                   help="goodput SLO in seconds of response time")
    p.add_argument("--seed", type=int, default=1234)
    p.add_argument("--speedup", type=float, default=1.0,
                   help="divide every stubbed service time by this; ratios preserved, "
                        "absolute seconds are then time-compressed and labelled so")
    p.add_argument("--list-len", type=int, default=3,
                   help="items the stub puts in each list field of a structured output")
    p.add_argument("--papers", nargs="*", default=None,
                   help="restrict to these fixture paper ids")
    p.add_argument("--serial-reviewers", action="store_true",
                   help="force the 3 reviewer Send branches to run sequentially")
    p.add_argument("--compare-fanout", action="store_true",
                   help="run every load point twice, parallel and serial reviewers")
    p.add_argument("--real-llm", action="store_true",
                   help="make REAL paid calls; requires --yes")
    p.add_argument("--max-calls", type=int, default=200,
                   help="NOESIS_LLM_MAX_CALLS for --real-llm")
    p.add_argument("--max-spend", type=float, default=3.0,
                   help="NOESIS_LLM_MAX_SPEND_USD for --real-llm")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    p.add_argument("--trace", type=Path, default=None,
                   help="write per-node spans here (JSONL) for fan-out analysis")
    p.add_argument("--latency", choices=["response", "service"], default="response",
                   help="which latency the table reports; response = arrival->done")
    args = p.parse_args(argv)

    models = build_models(args)

    if args.dry_run:
        print(dry_run_report(models, len(load_fixtures(papers=args.papers or None))))
        return 0

    if args.real_llm:
        if not args.yes:
            print("--real-llm makes paid calls; pass --yes to confirm.", file=sys.stderr)
            return 2
        # Set before any app import so llm_budget reads them at call time.
        os.environ["NOESIS_LLM_MAX_CALLS"] = str(args.max_calls)
        os.environ["NOESIS_LLM_MAX_SPEND_USD"] = str(args.max_spend)
        from env import load_backend_env  # scripts/eval/env.py
        load_backend_env()
        print(f"REAL LLM: ceiling {args.max_calls} calls / ${args.max_spend:.2f}")

    # The graph's own eval escape hatches: skip the OpenAlex/Unpaywall network
    # hop (out of scope, and a real external dependency would dominate the
    # measurement) and disable the preliminary halt so the reviewer panel -- the
    # thing being measured -- actually runs.
    os.environ.setdefault("EVAL_SKIP_EXTERNAL_SOURCE_DISCOVERY", "1")
    os.environ.setdefault("EVAL_DISABLE_PRE_REVIEWER_HALT", "1")

    run_id = uuid.uuid4().hex[:12]
    summaries = asyncio.run(execute(models, args))

    print("\n" + "=" * 100)
    print(f"RUN {run_id}   latency reported: {args.latency}-time (seconds)")
    print(EXCLUSION_NOTE)
    if args.real_llm:
        print("LLM: REAL")
    else:
        print("LLM: STUBBED -- latencies below are synthetic draws, not observed API times.")
    for line in summaries[0].extra.get("profile_provenance", []):
        print("  " + line)
    print("=" * 100)
    print(table(summaries, latency=args.latency))

    for s in summaries:
        if s.n_failed:
            print(f"\n  FAILURES  {s.model.describe()}\n    {s.errors}")

    append_results(summaries, args.results, run_id)
    print(f"\nappended {len(summaries)} record(s) to {args.results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
