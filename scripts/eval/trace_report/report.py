"""CLI: span JSONL -> a readable table plus an append-only machine-readable JSONL.

    python3 -m trace_report.report noesis_traces.jsonl --sort p95
    python3 -m trace_report.report traces/*.jsonl --sort cost --json out/trace_report.jsonl

Run from ``scripts/eval`` (or with it on ``PYTHONPATH``).

Printing rules, enforced here so they cannot be lost between the metrics and
the eye reading them:

* every percentile column is printed beside its ``n``, and a quantile the
  sample cannot support prints ``n/a (n=3 < 20)`` -- never a number, never a
  blank;
* a run total whose spans were not all priceable prints with a ``>=`` and the
  unpriced count, never as a clean dollar figure;
* a node that never executed prints ``--`` in every numeric column and is
  labelled, so it is not mistaken for a node that ran instantly.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path
from typing import Any, Sequence

if __package__ in (None, ""):  # allow `python3 report.py ...`
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from trace_report import metrics as M  # type: ignore[no-redef]
    from trace_report import parse as P  # type: ignore[no-redef]
else:
    from . import metrics as M
    from . import parse as P

SORT_KEYS = ("p50", "p95", "total", "self", "cost", "name")


# ---------------------------------------------------------------------------
# Table rendering
# ---------------------------------------------------------------------------

def render_table(headers: Sequence[str], rows: Sequence[Sequence[str]], align_right: Sequence[int] = ()) -> str:
    if not rows:
        return "  (no rows)"
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def line(cells: Sequence[str]) -> str:
        out = []
        for i, cell in enumerate(cells):
            out.append(cell.rjust(widths[i]) if i in align_right else cell.ljust(widths[i]))
        return "  " + "  ".join(out).rstrip()

    sep = "  " + "  ".join("-" * w for w in widths)
    return "\n".join([line(headers), sep, *(line(r) for r in rows)])


def _ms(value: float | None) -> str:
    return "--" if value is None else f"{value:,.1f}"


def _usd(value: float | None) -> str:
    return "--" if value is None else f"${value:,.4f}"


# ---------------------------------------------------------------------------
# Report assembly
# ---------------------------------------------------------------------------

def build_report(
    result: P.ParseResult,
    *,
    sort: str = "p95",
    split_variants: bool = True,
    min_n: dict[str, int] | None = None,
    expected_nodes: Sequence[str] | None = None,
) -> dict[str, Any]:
    traces = list(result.traces.values())
    key = M.default_key if split_variants else M.merged_key

    latency = M.node_latency(traces, key=key, expected_nodes=expected_nodes, min_n=min_n)
    costs = M.run_costs(traces)
    node_costs = M.cost_by_node(traces)

    total_usd = sum(c.usd for c in costs)
    unpriced = sum(c.unpriced_spans for c in costs)
    priced_runs = [c for c in costs if c.complete]

    def sort_value(row: M.NodeLatency) -> tuple:
        if sort == "name":
            return (0, row.node)
        if sort == "total":
            metric = row.total_wall_ms
        elif sort == "self":
            metric = row.total_self_ms
        elif sort == "cost":
            bucket = node_costs.get(row.node)
            metric = bucket.usd if bucket else 0.0
        elif sort == "p50":
            metric = row.wall.get("p50") or 0.0
        else:  # p95: fall back to max when p95 is refused, so ordering still works
            metric = row.wall.get("p95")
            if metric is None:
                metric = row.wall.max or 0.0
        # never-executed rows always sink to the bottom
        return (1 if row.never_executed else 0, -float(metric), row.node)

    latency.sort(key=sort_value)

    return {
        "generated_at": time.time(),
        "sort": sort,
        "split_variants": split_variants,
        "min_n": dict(min_n or M.DEFAULT_MIN_N),
        "parse": result.stats.to_dict(),
        "traces": len(traces),
        "nodes": [row.to_dict() for row in latency],
        "node_costs": {k: v.to_dict() for k, v in sorted(node_costs.items())},
        "runs": [c.to_dict() for c in costs],
        "cost_summary": {
            "total_usd": total_usd,
            "complete": unpriced == 0,
            "unpriced_spans": unpriced,
            "runs": len(costs),
            "complete_runs": len(priced_runs),
            "mean_usd_per_complete_run": (
                sum(c.usd for c in priced_runs) / len(priced_runs) if priced_runs else None
            ),
        },
        "tokens": {
            "total": M.token_totals(traces).to_dict(),
            "by_model": {k: v.to_dict() for k, v in sorted(M.tokens_by_model(traces).items())},
            "by_node": {k: v.to_dict() for k, v in sorted(M.tokens_by_node(traces).items())},
        },
        "critical_paths": [M.critical_path(t).to_dict() for t in traces],
        "fanouts": [c.to_dict() for t in traces for c in M.fanout_concurrency(t)],
        "llm_share": [M.llm_io_share(t).to_dict() for t in traces],
        "_latency_objects": latency,  # stripped before serialization
    }


def render(report: dict[str, Any]) -> str:
    out: list[str] = []
    stats = report["parse"]
    thresholds = report["min_n"]

    out.append("=" * 100)
    out.append("NOESIS TRACE REPORT")
    out.append("=" * 100)
    out.append(
        f"files={len(stats['files'])}  lines={stats['lines_read']}  spans={stats['spans_parsed']}  "
        f"traces={report['traces']}"
    )
    if stats["malformed_lines"] or stats["duplicate_span_ids"] or stats["orphan_spans"]:
        out.append(
            f"SKIPPED/REPAIRED: malformed_lines={stats['malformed_lines']}  "
            f"duplicate_span_ids={stats['duplicate_span_ids']}  "
            f"orphan_spans={stats['orphan_spans']} (kept, re-rooted)"
        )
        for sample in stats["malformed_samples"][:5]:
            out.append(f"    {sample['file']}:{sample['line']}  {sample['reason']}")
    else:
        out.append("no malformed lines, no duplicate span ids, no orphans")

    # -- per-node latency ---------------------------------------------------
    out.append("")
    out.append(f"PER-NODE LATENCY (ms) -- sorted by {report['sort']}")
    out.append(
        "wall = span duration incl. children; self = wall minus the UNION of child intervals "
        "(union, not sum: the 3 reviewers overlap)"
    )
    out.append(
        "p95 requires n>=%s, p99 requires n>=%s; below that the cell says so instead of guessing"
        % (thresholds.get("p95"), thresholds.get("p99"))
    )
    headers = ["node", "n", "wall p50", "wall p95", "wall max", "self p50", "self p95", "total wall", "total self", "$"]
    rows: list[list[str]] = []
    for row in report["_latency_objects"]:
        cost = report["node_costs"].get(row.node)
        if row.never_executed:
            rows.append([row.node, "0", "NEVER EXECUTED", "--", "--", "--", "--", "--", "--", "--"])
            continue
        cost_cell = "--"
        if cost is not None:
            cost_cell = _usd(cost["usd"]) + ("" if cost["complete"] else " >=")
        rows.append(
            [
                row.node,
                str(row.executions),
                row.wall.label("p50"),
                row.wall.label("p95"),
                _ms(row.wall.max),
                row.self_.label("p50"),
                row.self_.label("p95"),
                _ms(row.total_wall_ms),
                _ms(row.total_self_ms),
                cost_cell,
            ]
        )
    out.append(render_table(headers, rows, align_right=set(range(1, len(headers)))))

    inexact = [r for r in report["_latency_objects"] if r.inexact_self_spans]
    if inexact:
        out.append(
            "  NOTE: self time approximated for "
            + ", ".join(f"{r.node} ({r.inexact_self_spans} span(s))" for r in inexact)
            + " -- a child span lacked start/end, so overlap could not be measured."
        )

    # -- cost ---------------------------------------------------------------
    summary = report["cost_summary"]
    out.append("")
    out.append("COST PER RUN")
    if summary["unpriced_spans"]:
        out.append(
            f"INCOMPLETE: {summary['unpriced_spans']} llm_call span(s) could not be priced. "
            "Totals below are LOWER BOUNDS, not costs."
        )
    cost_rows = [
        [
            r["run_id"][:24],
            r["trace_id"][:12],
            _usd(r["usd"]) + ("" if r["complete"] else " >="),
            str(r["llm_spans"]),
            str(r["unpriced_spans"]),
            "yes" if r["complete"] else "NO",
        ]
        for r in report["runs"]
    ]
    out.append(
        render_table(
            ["run", "trace", "usd", "llm spans", "unpriced", "complete"],
            cost_rows,
            align_right={2, 3, 4, 5},
        )
    )
    mean = summary["mean_usd_per_complete_run"]
    out.append(
        f"  total={_usd(summary['total_usd'])}{'' if summary['complete'] else ' >='}  "
        f"runs={summary['runs']}  fully-priced runs={summary['complete_runs']}  "
        f"mean/complete run={_usd(mean)}"
    )

    # -- tokens -------------------------------------------------------------
    tokens = report["tokens"]["total"]
    out.append("")
    out.append("TOKENS")
    out.append(
        f"  calls={tokens['calls']}  input={tokens['input_tokens']:,} "
        f"(cached {tokens['cached_tokens']:,} / uncached {tokens['uncached_input_tokens']:,})  "
        f"output={tokens['output_tokens']:,}  no-usage calls={tokens['calls_without_usage']}"
    )
    model_rows = [
        [
            model,
            str(b["calls"]),
            f"{b['input_tokens']:,}",
            f"{b['cached_tokens']:,}",
            f"{b['output_tokens']:,}",
            "--" if b["cache_hit_rate"] is None else f"{b['cache_hit_rate'] * 100:.1f}%",
        ]
        for model, b in report["tokens"]["by_model"].items()
    ]
    out.append(render_table(["model", "calls", "input", "cached", "output", "cache hit"], model_rows, align_right={1, 2, 3, 4, 5}))

    # -- critical path ------------------------------------------------------
    out.append("")
    out.append("CRITICAL PATH (the blocking chain -- what actually bounds latency)")
    for path in report["critical_paths"][:5]:
        out.append(f"  trace {path['trace_id'][:12]}  total={_ms(path['total_ms'])} ms")
        for entry in path["spans"][:8]:
            share = entry["ms"] / path["total_ms"] * 100 if path["total_ms"] else 0.0
            out.append(f"      {entry['name']:<44} {entry['ms']:>10,.1f} ms  {share:>5.1f}%")
    if len(report["critical_paths"]) > 5:
        out.append(f"  ... {len(report['critical_paths']) - 5} more trace(s) in the JSON output")

    # -- fan-out ------------------------------------------------------------
    out.append("")
    out.append("FAN-OUT CONCURRENCY (work performed vs wall time it occupied)")
    fanouts = report["fanouts"]
    if not fanouts:
        out.append("  (no parent whose children overlapped)")
    else:
        fan_rows = [
            [
                f["parent_name"],
                str(f["sibling_count"]),
                _ms(f["sum_ms"]),
                _ms(f["union_ms"]),
                _ms(f["max_ms"]),
                "--" if f["speedup"] is None else f"{f['speedup']:.2f}x",
                _ms(f["saved_ms"]),
                _ms(f["overhead_ms"]),
            ]
            for f in fanouts[:10]
        ]
        out.append(
            render_table(
                ["parent", "children", "sum work", "wall (union)", "slowest", "speedup", "saved", "parent overhead"],
                fan_rows,
                align_right=set(range(1, 8)),
            )
        )

    # -- llm share ----------------------------------------------------------
    out.append("")
    out.append("LLM-I/O SHARE OF WALL TIME (union share is the one comparable to 100%)")
    share_rows = [
        [
            s["trace_id"][:12],
            str(s["call_count"]),
            _ms(s["run_wall_ms"]),
            _ms(s["llm_union_ms"]),
            "--" if s["union_share"] is None else f"{s['union_share'] * 100:.1f}%",
            _ms(s["llm_sum_ms"]),
            "--" if s["sum_share"] is None else f"{s['sum_share'] * 100:.1f}%",
        ]
        for s in report["llm_share"][:10]
    ]
    out.append(
        render_table(
            ["trace", "calls", "run wall", "llm union", "union %", "llm sum", "sum %"],
            share_rows,
            align_right=set(range(1, 7)),
        )
    )
    out.append("")
    return "\n".join(out)


def append_json(report: dict[str, Any], path: str) -> None:
    """Append one JSON object per invocation. Never rewrites history."""
    payload = {k: v for k, v in report.items() if not k.startswith("_")}
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, default=str) + "\n")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="trace_report.report",
        description="Per-node latency, cost and concurrency from tracing JSONL span files.",
    )
    parser.add_argument("paths", nargs="+", help="span JSONL file(s); globs allowed")
    parser.add_argument("--sort", choices=SORT_KEYS, default="p95", help="node table sort key")
    parser.add_argument("--json", dest="json_path", default=None, help="append the machine-readable report here")
    parser.add_argument(
        "--merge-variants",
        action="store_true",
        help="group the 3 reviewer branches under one node name instead of splitting them",
    )
    parser.add_argument(
        "--min-n-p95", type=int, default=M.DEFAULT_MIN_N["p95"], help="refuse p95 below this n"
    )
    parser.add_argument(
        "--min-n-p99", type=int, default=M.DEFAULT_MIN_N["p99"], help="refuse p99 below this n"
    )
    parser.add_argument(
        "--expect-node",
        action="append",
        default=[],
        help="node name that SHOULD have run; printed as NEVER EXECUTED when absent (repeatable)",
    )
    args = parser.parse_args(argv)

    files: list[str] = []
    for pattern in args.paths:
        matches = sorted(glob.glob(pattern))
        files.extend(matches or [pattern])

    result = P.load_span_files(files)
    if not result.traces:
        print("no usable spans found in: " + ", ".join(files), file=sys.stderr)
        print(json.dumps(result.stats.to_dict(), indent=2), file=sys.stderr)
        return 1

    min_n = dict(M.DEFAULT_MIN_N)
    min_n["p95"] = args.min_n_p95
    min_n["p99"] = args.min_n_p99

    report = build_report(
        result,
        sort=args.sort,
        split_variants=not args.merge_variants,
        min_n=min_n,
        expected_nodes=args.expect_node or None,
    )
    print(render(report))
    if args.json_path:
        append_json(report, args.json_path)
        print(f"appended machine-readable report to {args.json_path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
